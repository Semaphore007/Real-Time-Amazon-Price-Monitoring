"""
FastAPI application — Amazon Price Monitoring System.

Routes:
  /health                        — liveness probe
  /products                      — list / detail
  /price-history/{asin}          — chronological rows
  /price-history/ohlc/{asin}     — OHLC candle bars
  /sellers                       — seller registry
  /sellers/ranking               — buy-box win rate ranking
  /sellers/competitiveness/{asin}— per-seller stats for one ASIN
  /listings/{asin}               — latest offer per seller
  /market/snapshot               — cross-product latest snapshot
  /buy-box-history/{asin}        — buy-box ownership events
  /buy-box/current               — current winner per product
  /buy-box/ownership             — ownership pct per seller
  /alert-rules                   — CRUD for alert thresholds
  /alerts                        — fired alert events
  /alerts/{id}/acknowledge       — mark alert seen
  /analytics/summary             — KPI dashboard
  /analytics/price-trends/{asin} — daily price trend
  /analytics/price-drops         — detected price drop events
  /analytics/undercutting        — undercutting events
  /analytics/heatmap             — seller × location heatmap
  /ws/alerts                     — WebSocket real-time feed
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from analytics.price_analysis import AnalyticsService
from monitoring.alerts import AlertDispatcher
from api.models import (
    AcknowledgeRequest,
    AlertOut,
    AlertRuleCreate,
    AlertRuleOut,
    AnalyticsSummary,
    BuyBoxOwnership,
    JobStatus,
    OfferSnapshot,
    PriceTrend,
    ProductDetail,
    ProductSummary,
    SellerInfo,
    SellerRanking,
    TriggerCrawlRequest,
)
from config.settings import get_settings
from database.connection import init_database
from database.repository import MonitoringRepository

logger  = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------
_session_factory = init_database(settings.database_url)
repository       = MonitoringRepository(_session_factory)
analytics        = AnalyticsService(repository)
dispatcher       = AlertDispatcher(settings)

if settings.seed_demo_data:
    repository.ensure_seed_data()

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.app_name,
    version="3.0.0",
    description=(
        "Production-grade Real-Time Price Monitoring System "
        "for Amazon India products (bearings & beyond)."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UTC = timezone.utc


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws) if hasattr(self.active, "discard") else (
            self.active.remove(ws) if ws in self.active else None
        )

    async def broadcast(self, data: Any) -> None:
        message = json.dumps(data, default=str)
        dead: list[WebSocket] = []
        for ws in list(self.active):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# ===========================================================================
# HEALTH
# ===========================================================================

@app.get("/health", tags=["System"], summary="Liveness probe")
def health() -> dict:
    return {
        "status":      "ok",
        "app":         settings.app_name,
        "environment": settings.environment,
        "timestamp":   datetime.now(UTC).isoformat(),
    }


# ===========================================================================
# PRODUCTS
# ===========================================================================

@app.get(
    "/products",
    response_model=list[ProductSummary],
    tags=["Products"],
    summary="List all tracked products",
)
def get_products(
    query: str | None = Query(default=None, description="Filter by ASIN or title substring"),
    active_only: bool = Query(default=True),
) -> list[dict]:
    return repository.list_products(query=query, active_only=active_only)


@app.get(
    "/product/{asin}",
    response_model=ProductDetail,
    tags=["Products"],
    summary="Full details for a single ASIN",
)
def get_product(asin: str) -> dict:
    product = repository.get_product_details(asin)
    if product is None:
        raise HTTPException(404, detail=f"Product {asin!r} not found")
    return product


# ===========================================================================
# PRICE HISTORY
# ===========================================================================

@app.get(
    "/price-history/{asin}",
    tags=["Prices"],
    summary="Chronological price rows for one ASIN",
)
def get_price_history(
    asin: str,
    location: str | None = Query(default=None, description="Pincode filter"),
    seller_id: str | None = Query(default=None),
    days: int = Query(default=90, ge=1, le=365, description="Look-back window in days"),
    limit: int  = Query(default=500, ge=1, le=5000),
) -> list[dict]:
    from datetime import timedelta
    since = datetime.now(UTC) - timedelta(days=days)
    rows  = repository.get_price_history(asin, location=location, seller_id=seller_id, since=since)
    return rows[-limit:]


@app.get(
    "/price-history",
    tags=["Prices"],
    summary="Recent price rows across all products",
)
def get_all_price_history(
    limit: int = Query(default=200, ge=1, le=2000),
) -> list[dict]:
    frame = repository.price_history_frame()
    if frame.empty:
        return []
    frame = frame.sort_values("timestamp", ascending=False).head(limit)
    return frame.where(frame.notna(), None).to_dict(orient="records")


@app.get(
    "/price-history/ohlc/{asin}",
    tags=["Prices"],
    summary="Open/High/Low/Close daily price bars",
)
def get_price_ohlc(
    asin: str,
    period: str = Query(default="D", description="'D'=daily, 'W'=weekly, 'M'=monthly"),
) -> list[dict]:
    df = analytics.price_ohlc(asin, period=period)
    if df.empty:
        return []
    return df.where(df.notna(), None).to_dict(orient="records")


@app.get(
    "/analytics/price-trends/{asin}",
    tags=["Analytics"],
    summary="Daily average price trend per seller",
)
def get_price_trends(asin: str) -> dict:
    frame = repository.price_history_frame(asin)
    if frame.empty:
        return {"asin": asin, "trends": [], "overall_min": None, "overall_max": None, "overall_avg": None}

    frame = frame.dropna(subset=["price"])
    frame["date"] = frame["timestamp"].dt.normalize().astype(str)
    daily = (
        frame.groupby(["date", "seller_name"])["price"]
        .mean()
        .round(2)
        .reset_index()
    )
    return {
        "asin":        asin,
        "trends":      daily.to_dict(orient="records"),
        "overall_min": float(frame["price"].min()),
        "overall_max": float(frame["price"].max()),
        "overall_avg": round(float(frame["price"].mean()), 2),
    }


# ===========================================================================
# SELLERS
# ===========================================================================

@app.get(
    "/sellers",
    response_model=list[SellerInfo],
    tags=["Sellers"],
    summary="All registered sellers",
)
def get_sellers(active_only: bool = Query(default=True)) -> list[dict]:
    return repository.list_sellers(active_only=active_only)


@app.get(
    "/sellers/ranking",
    response_model=list[SellerRanking],
    tags=["Sellers"],
    summary="Sellers ranked by buy-box win rate",
)
def get_seller_ranking() -> list[dict]:
    summary      = analytics.build_summary()
    win_rate_map = {r["seller_name"]: r["win_rate_pct"]     for r in summary["buy_box_win_rate"]}
    share_map    = {r["seller_name"]: r["market_share_pct"] for r in summary["seller_market_share"]}
    all_sellers  = set(win_rate_map) | set(share_map)
    result = [
        {
            "seller_name":          name,
            "buy_box_win_rate_pct": win_rate_map.get(name, 0.0),
            "market_share_pct":     share_map.get(name, 0.0),
        }
        for name in sorted(all_sellers)
    ]
    return sorted(result, key=lambda r: r["buy_box_win_rate_pct"], reverse=True)


@app.get(
    "/sellers/competitiveness/{asin}",
    tags=["Sellers"],
    summary="Per-seller competitiveness stats for one ASIN",
)
def get_seller_competitiveness(asin: str) -> list[dict]:
    df = analytics.seller_competitiveness(asin)
    if df.empty:
        return []
    return df.where(df.notna(), None).to_dict(orient="records")


# ===========================================================================
# LISTINGS / OFFERS
# ===========================================================================

@app.get(
    "/listings/{asin}",
    tags=["Listings"],
    summary="Latest offer snapshot per seller for one ASIN",
)
def get_latest_listings(
    asin: str,
    location: str | None = Query(default=None),
) -> list[dict]:
    offers = repository.get_latest_offers(asin)
    if location:
        offers = [o for o in offers if o.get("location") == location]
    return offers


@app.get(
    "/market/snapshot",
    tags=["Listings"],
    summary="Latest offer per seller across all products",
)
def get_market_snapshot() -> list[dict]:
    frame = repository.latest_market_snapshot()
    if frame.empty:
        return []
    return frame.where(frame.notna(), None).to_dict(orient="records")


# ===========================================================================
# BUY BOX
# ===========================================================================

@app.get(
    "/buy-box-history/{asin}",
    tags=["BuyBox"],
    summary="Buy-box ownership history for one ASIN",
)
def get_buy_box_history(asin: str) -> list[dict]:
    return repository.get_buy_box_history(asin)


@app.get(
    "/buy-box/current",
    tags=["BuyBox"],
    summary="Current buy-box winner per product",
)
def get_current_buy_box() -> list[dict]:
    frame = repository.buy_box_frame()
    if frame.empty:
        return []
    latest = frame.sort_values("captured_at").groupby("asin").tail(1)
    return latest.where(latest.notna(), None).to_dict(orient="records")


@app.get(
    "/buy-box/ownership",
    tags=["BuyBox"],
    summary="Buy-box ownership percentage per seller",
)
def get_buy_box_ownership(
    asin: str | None = Query(default=None),
) -> list[dict]:
    return analytics.buy_box_ownership(asin)


# ===========================================================================
# ALERT RULES
# ===========================================================================

@app.get(
    "/alert-rules",
    response_model=list[AlertRuleOut],
    tags=["Alerts"],
    summary="List all active alert rules",
)
def list_alert_rules(
    asin: str | None = Query(default=None),
) -> list[dict]:
    return repository.list_alert_rules(asin=asin, active_only=True)


@app.post(
    "/alert-rules",
    response_model=AlertRuleOut,
    tags=["Alerts"],
    summary="Create or update an alert rule",
    status_code=201,
)
def create_alert_rule(payload: AlertRuleCreate) -> dict:
    # Verify product exists
    product = repository.get_product(payload.asin)
    if product is None:
        raise HTTPException(404, detail=f"Product {payload.asin!r} not found")

    rule_id = repository.upsert_alert_rule(
        asin=payload.asin,
        condition=payload.condition,
        severity=payload.severity,
        seller_id=payload.seller_id,
        notify_email=payload.notify_email,
        notify_webhook=payload.notify_webhook,
    )
    rules = repository.list_alert_rules(asin=payload.asin, active_only=False)
    rule  = next((r for r in rules if r["id"] == rule_id), None)
    if rule is None:
        raise HTTPException(500, detail="Alert rule created but could not be retrieved")
    return rule


@app.delete(
    "/alert-rules/{rule_id}",
    tags=["Alerts"],
    summary="Deactivate an alert rule",
    status_code=204,
)
def deactivate_alert_rule(rule_id: int) -> None:
    from sqlalchemy import update
    from database.models import AlertRule
    from database.connection import get_session_factory
    with _session_factory() as session:
        session.execute(
            update(AlertRule).where(AlertRule.id == rule_id).values(is_active=False)
        )
        session.commit()


# ===========================================================================
# ALERTS
# ===========================================================================

@app.get(
    "/alerts",
    response_model=list[AlertOut],
    tags=["Alerts"],
    summary="Recent fired alert events",
)
def get_alerts(
    limit: int = Query(default=100, ge=1, le=500),
    asin: str | None = Query(default=None),
    unacknowledged_only: bool = Query(default=False),
) -> list[dict]:
    return repository.list_alerts(
        limit=limit, asin=asin, unacknowledged_only=unacknowledged_only
    )


@app.post(
    "/alerts/{alert_id}/acknowledge",
    tags=["Alerts"],
    summary="Mark an alert as acknowledged",
)
def acknowledge_alert(
    alert_id: int,
    payload: AcknowledgeRequest,
) -> dict:
    repository.acknowledge_alert(alert_id, payload.acknowledged_by)
    return {"status": "acknowledged", "alert_id": alert_id}


# ===========================================================================
# ANALYTICS
# ===========================================================================

@app.get(
    "/analytics/summary",
    response_model=AnalyticsSummary,
    tags=["Analytics"],
    summary="KPI dashboard — aggregated metrics",
)
def get_summary(asin: str | None = Query(default=None)) -> dict:
    return analytics.build_summary(asin)


@app.get(
    "/analytics/price-drops",
    tags=["Analytics"],
    summary="Detected price-drop events (>= threshold %)",
)
def get_price_drops(
    asin: str | None  = Query(default=None),
    threshold_pct: float = Query(default=5.0, ge=0.1, le=100.0),
) -> list[dict]:
    return analytics.detect_price_drops(asin=asin, threshold_pct=threshold_pct)


@app.get(
    "/analytics/undercutting",
    tags=["Analytics"],
    summary="Undercutting detection results",
)
def get_undercutting() -> list[dict]:
    return analytics.detect_undercutting()


@app.get(
    "/analytics/heatmap",
    tags=["Analytics"],
    summary="Seller × location min-price heatmap",
)
def get_price_heatmap(asin: str | None = Query(default=None)) -> list[dict]:
    heatmap = analytics.price_heatmap(asin)
    if heatmap.empty:
        return []
    heatmap = heatmap.reset_index()
    return heatmap.where(heatmap.notna(), None).to_dict(orient="records")


@app.get(
    "/analytics/buy-box-ownership",
    tags=["Analytics"],
    summary="Buy-box ownership percentage per seller (× ASIN)",
)
def get_analytics_buy_box_ownership(
    asin: str | None = Query(default=None),
) -> list[dict]:
    return analytics.buy_box_ownership(asin)


@app.post(
    "/analytics/evaluate-alerts",
    tags=["Analytics"],
    summary="Manually trigger alert rule evaluation (admin / scheduler hook)",
)
def evaluate_alerts() -> dict:
    fired = analytics.evaluate_alert_rules()
    for a in fired:
        repository.fire_alert(**a)
        alert_type = a["condition"].get("type", "alert")
        dispatcher.dispatch(
            subject=f"[{alert_type}] {a['asin']}",
            body=a["message"],
            severity=a["severity"],
        )
    return {"evaluated": True, "alerts_fired": len(fired)}


# ===========================================================================
# WEBSOCKET — real-time alert feed
# ===========================================================================

@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        snapshot = analytics.build_summary()
        await websocket.send_text(
            json.dumps({"type": "snapshot", "data": snapshot}, default=str)
        )
        while True:
            await asyncio.sleep(30)
            alerts = repository.list_alerts(limit=5, unacknowledged_only=True)
            await websocket.send_text(
                json.dumps({"type": "alerts", "data": alerts}, default=str)
            )
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        manager.disconnect(websocket)
