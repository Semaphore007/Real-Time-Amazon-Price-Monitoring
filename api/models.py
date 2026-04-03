"""
Pydantic schemas (request/response) for the price monitoring API.

All response models use the new normalized schema:
  - seller_id is the marketplace string key (not an integer PK)
  - Alert rules store conditions as JSONB / dict
  - Alerts carry old/new values for price diff rendering
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


class CamelBase(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=_to_camel,
    )


# ── Auth ──────────────────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserInfo(BaseModel):
    username: str
    role: str


# ── Product ───────────────────────────────────────────────────────────────────

class ProductSummary(CamelBase):
    asin: str
    title: str
    brand: str | None = None
    category: str | None = None
    sub_category: str | None = None
    is_active: bool = True
    updated_at: datetime | None = None


class ProductDetail(ProductSummary):
    latest_price: float | None = None
    latest_seller_id: str | None = None
    buy_box_events: int = 0
    current_buybox_seller_id: str | None = None
    current_buybox_price: float | None = None


# ── Price History ─────────────────────────────────────────────────────────────

class PricePoint(CamelBase):
    asin: str
    seller_id: str | None = None
    seller_name: str | None = None
    location: str | None = None
    price: float
    mrp: float | None = None
    currency: str = "INR"
    availability: str | None = None
    is_fba: bool = False
    timestamp: datetime


class PriceTrend(CamelBase):
    asin: str
    overall_min: float | None = None
    overall_max: float | None = None
    overall_avg: float | None = None
    trends: list[dict[str, Any]] = Field(default_factory=list)


class OHLCBar(CamelBase):
    day: datetime
    open: float
    high: float
    low: float
    close: float
    avg_price: float
    sample_count: int


# ── Seller ────────────────────────────────────────────────────────────────────

class SellerInfo(CamelBase):
    seller_id: str
    name: str
    rating: float | None = None
    fulfillment_type: str | None = None


class SellerCompetitiveness(CamelBase):
    seller_name: str
    total_snapshots: int
    buybox_wins: int
    buybox_win_rate_pct: float
    avg_price: float
    min_price: float
    max_price: float


class SellerRanking(CamelBase):
    seller_id: str | None = None
    seller_name: str
    buy_box_win_rate_pct: float = 0.0
    market_share_pct: float = 0.0


# ── Listings / Offers ─────────────────────────────────────────────────────────

class OfferSnapshot(CamelBase):
    asin: str
    seller_id: str
    seller_name: str
    location: str | None = None
    price: float
    mrp: float | None = None
    is_buybox: bool = False
    is_fba: bool = False
    availability: str | None = None
    seller_rating: float | None = None
    timestamp: datetime


# ── Buy Box ───────────────────────────────────────────────────────────────────

class BuyBoxEvent(CamelBase):
    asin: str
    seller_id: str
    seller_name: str
    location: str | None = None
    price: float
    captured_at: datetime


class BuyBoxOwnership(CamelBase):
    asin: str
    seller_name: str
    events: int
    total: int
    ownership_pct: float


# ── Alert Rules ───────────────────────────────────────────────────────────────

AlertConditionType = Literal[
    "price_drop",
    "price_above",
    "price_below",
    "buybox_change",
    "oos",
    "custom",
]


class AlertRuleCreate(BaseModel):
    asin: str
    condition: dict[str, Any] = Field(
        ...,
        examples=[
            {"type": "price_drop", "threshold_pct": 10},
            {"type": "price_above", "value": 999.0},
            {"type": "buybox_change", "seller_id": "SELLER_01"},
            {"type": "oos", "consecutive_checks": 3},
        ],
    )
    severity: Literal["info", "warning", "critical"] = "info"
    seller_id: str | None = None
    notify_email: str | None = None
    notify_webhook: str | None = None

    @field_validator("condition")
    @classmethod
    def condition_must_have_type(cls, v: dict) -> dict:
        if "type" not in v:
            raise ValueError("condition must contain a 'type' key")
        return v


class AlertRuleOut(CamelBase):
    id: int
    asin: str
    seller_id: str | None = None
    condition: dict[str, Any]
    severity: str
    notify_email: str | None = None


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertOut(CamelBase):
    id: int
    rule_id: int | None = None
    asin: str
    seller_id: str | None = None
    condition: dict[str, Any]
    message: str
    severity: str
    old_value: float | None = None
    new_value: float | None = None
    triggered_at: datetime
    acknowledged_at: datetime | None = None


class AcknowledgeRequest(BaseModel):
    acknowledged_by: str


# ── Scrape Job ────────────────────────────────────────────────────────────────

class TriggerCrawlRequest(BaseModel):
    asins: list[str] | None = None
    queries: list[str] | None = None
    max_pages: int = Field(default=3, ge=1, le=10)


class JobStatus(BaseModel):
    job_id: str
    status: str
    detail: str | None = None


# ── Analytics ─────────────────────────────────────────────────────────────────

class PriceDropEvent(CamelBase):
    asin: str
    prev_price: float
    new_price: float
    drop_pct: float
    timestamp: datetime


class AnalyticsSummary(BaseModel):
    price_points: int = 0
    products_tracked: int = 0
    average_market_price: float | None = None
    min_price_seller: dict[str, Any] | None = None
    frequent_price_changers: list[dict[str, Any]] = Field(default_factory=list)
    buy_box_win_rate: list[dict[str, Any]] = Field(default_factory=list)
    undercutting_events: list[dict[str, Any]] = Field(default_factory=list)
    seller_market_share: list[dict[str, Any]] = Field(default_factory=list)
    price_drop_events: list[dict[str, Any]] = Field(default_factory=list)


# ── Pagination ────────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[Any]


# ── Error ─────────────────────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: Any | None = None
