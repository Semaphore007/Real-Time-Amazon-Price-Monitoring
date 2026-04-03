"""
Scrapy item pipelines for amazon_monitor.

Pipeline execution order (configured in settings.py → ITEM_PIPELINES):
  100  ValidationPipeline        — drop items missing critical fields
  200  RawHtmlPipeline           — persist gzip-compressed page HTML
  250  JsonExportPipeline        — append JSONL line to rolling daily file
  300  NormalisationPipeline     — clean numerics, synthesise seller_id, etc.
  400  AmazonMonitoringPipeline  — write normalised snapshot to PostgreSQL
  500  AlertEvaluationPipeline   — fire new alerts based on active rules
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from scrapy.exceptions import DropItem

from config.settings import get_settings
from database.connection import init_database
from database.repository import MonitoringRepository
from analytics.price_analysis import AnalyticsService
from monitoring.alerts import AlertDispatcher
from amazon_monitor.utils.html_store import RawHtmlStore


LOGGER = logging.getLogger(__name__)
UTC    = timezone.utc

# Regex to extract numeric price from strings like "₹1,250.00" or "$12.5"
_PRICE_RE = re.compile(r"[\d,]+\.?\d*")


# ── 1. Validation ──────────────────────────────────────────────────────────────

class ValidationPipeline:
    """Drop items that cannot be stored (no ASIN = untrackable)."""

    REQUIRED = ("asin",)

    def process_item(self, item: dict[str, Any], spider: Any) -> dict[str, Any]:
        for field in self.REQUIRED:
            if not item.get(field):
                raise DropItem(f"Missing required field '{field}' — {dict(item)}")
        return item


# ── 2. Raw HTML storage ────────────────────────────────────────────────────────

class RawHtmlPipeline:
    """
    Saves the raw page HTML (attached by the spider as item["_raw_html"])
    as a gzip file under  raw_html/<spider>/<ASIN>_<ts>.html.gz.

    The private fields are popped so they never reach the DB pipeline.
    """

    def __init__(self) -> None:
        self.store = RawHtmlStore(base_dir=Path("raw_html"))

    def process_item(self, item: dict[str, Any], spider: Any) -> dict[str, Any]:
        html = item.pop("_raw_html", None)
        url  = item.pop("_source_url", "")
        if html:
            try:
                self.store.save(
                    html,
                    asin=item.get("asin", "unknown"),
                    spider_name=spider.name,
                    url=url,
                )
            except Exception as exc:      # noqa: BLE001
                LOGGER.warning("RawHtmlPipeline save failed: %s", exc)
        return item


# ── 3. JSON export ─────────────────────────────────────────────────────────────

class JsonExportPipeline:
    """
    Appends each item as a JSON line to  output/products_<date>.jsonl.
    One file per crawl day — easy to ship to a data lake or replay.
    """

    def __init__(self) -> None:
        self._file = None
        self._path: Path | None = None

    def open_spider(self, spider: Any) -> None:
        out_dir = Path("output")
        out_dir.mkdir(parents=True, exist_ok=True)
        date_str   = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        self._path = out_dir / f"products_{date_str}.jsonl"
        self._file = self._path.open("a", encoding="utf-8")
        LOGGER.info("JsonExportPipeline → %s", self._path)

    def close_spider(self, spider: Any) -> None:
        if self._file:
            self._file.close()

    def process_item(self, item: dict[str, Any], spider: Any) -> dict[str, Any]:
        if self._file:
            self._file.write(json.dumps(_make_serialisable(dict(item)), ensure_ascii=False) + "\n")
            self._file.flush()
        return item


# ── 4. Normalisation ───────────────────────────────────────────────────────────

class NormalisationPipeline:
    """
    Cleans and coerces all numeric/boolean fields before DB write.
    Also synthesises a `seller_id` from seller_name when the spider
    did not have access to the marketplace's native seller ID.
    """

    def process_item(self, item: dict[str, Any], spider: Any) -> dict[str, Any]:
        item["price"]        = _parse_price(item.get("price"))
        item["mrp"]          = _parse_price(item.get("mrp"))
        item["rating"]       = _to_float(item.get("rating"))
        item["review_count"] = _to_int(item.get("review_count"))
        item["is_fba"]       = bool(item.get("is_fba", False))
        item["currency"]     = item.get("currency") or "INR"
        item["source"]       = item.get("source") or "scraper"

        # Synthesise seller_id if the spider only captured the display name
        if not item.get("seller_id") and item.get("seller_name"):
            item["seller_id"] = _synthesise_seller_id(item["seller_name"])

        # Normalise each competing offer
        normalised_offers: list[dict] = []
        for offer in item.get("offers") or []:
            o_name = offer.get("seller_name", "")
            normalised_offers.append({
                **offer,
                "seller_id":     offer.get("seller_id") or _synthesise_seller_id(o_name),
                "price":         _parse_price(offer.get("price")),
                "mrp":           _parse_price(offer.get("mrp")),
                "seller_rating": _to_float(offer.get("seller_rating")),
                "is_fba":        bool(offer.get("is_fba", False)),
                "is_buybox":     bool(offer.get("is_buybox") or offer.get("is_buy_box", False)),
                "currency":      offer.get("currency") or "INR",
            })
        item["offers"] = normalised_offers

        # Drop if price ended up None (can't be stored meaningfully)
        if item["price"] is None:
            LOGGER.warning("ASIN %s has no parseable price — skipping", item.get("asin"))
            raise DropItem(f"Unparseable price for ASIN {item.get('asin')}")

        return item


# ── 5. PostgreSQL write ────────────────────────────────────────────────────────

class AmazonMonitoringPipeline:
    """Persists every normalised snapshot to PostgreSQL and logs the scrape job."""

    def __init__(self) -> None:
        self.repository: MonitoringRepository | None = None
        self._settings = get_settings()

    def open_spider(self, spider: Any) -> None:
        sf = init_database(self._settings.database_url)
        self.repository = MonitoringRepository(sf)
        LOGGER.info(
            "AmazonMonitoringPipeline connected — DB: %s",
            self._settings.database_url.split("@")[-1] if "@" in self._settings.database_url else "local",
        )

    def close_spider(self, spider: Any) -> None:
        self.repository = None

    def process_item(self, item: dict[str, Any], spider: Any) -> dict[str, Any]:
        if self.repository is None:
            raise RuntimeError("AmazonMonitoringPipeline: repository not initialised")

        asin = item.get("asin", "unknown")
        started = datetime.now(UTC)
        try:
            self.repository.record_product_snapshot(dict(item))
            self.repository.log_scrape_job(
                asin=asin,
                status="success",
                attempts=1,
                started_at=started,
                finished_at=datetime.now(UTC),
            )
        except Exception as exc:             # noqa: BLE001
            LOGGER.error("DB write failed for ASIN %s: %s", asin, exc, exc_info=True)
            self.repository.log_scrape_job(
                asin=asin,
                status="failed",
                attempts=1,
                started_at=started,
                finished_at=datetime.now(UTC),
                error_message=str(exc),
            )
        return item


# ── 6. Alert evaluation ────────────────────────────────────────────────────────

class AlertEvaluationPipeline:
    """
    After each item is persisted, check whether any active alert rule
    has been triggered and fire new Alert rows.  Uses a per-item cooldown
    so the same rule doesn't fire more than once per scrape run.
    """

    def __init__(self) -> None:
        self.repository: MonitoringRepository | None = None
        self.analytics:  AnalyticsService   | None = None
        self._settings = get_settings()
        self._fired_this_run: set[tuple] = set()  # (rule_id, asin)

    def open_spider(self, spider: Any) -> None:
        sf = init_database(self._settings.database_url)
        self.repository = MonitoringRepository(sf)
        self.analytics  = AnalyticsService(self.repository)
        self.dispatcher = AlertDispatcher(self._settings)

    def close_spider(self, spider: Any) -> None:
        self.repository = None
        self.analytics  = None
        self._fired_this_run.clear()

    def process_item(self, item: dict[str, Any], spider: Any) -> dict[str, Any]:
        if not (self.repository and self.analytics):
            return item

        asin = item.get("asin")
        if not asin:
            return item

        try:
            # Only evaluate rules that target this ASIN
            pending = self.analytics.evaluate_alert_rules()
            for alert_payload in pending:
                if alert_payload["asin"] != asin:
                    continue
                key = (alert_payload.get("rule_id"), asin)
                if key not in self._fired_this_run:
                    self.repository.fire_alert(**alert_payload)
                    self._fired_this_run.add(key)
                    
                    alert_type = alert_payload["condition"].get("type", "alert")
                    self.dispatcher.dispatch(
                        subject=f"[{alert_type}] {asin}",
                        body=alert_payload["message"],
                        severity=alert_payload["severity"]
                    )
                    
                    LOGGER.info(
                        "Alert fired — ASIN %s: %s",
                        asin, alert_payload["message"]
                    )
        except Exception as exc:            # noqa: BLE001
            LOGGER.warning("AlertEvaluationPipeline error for ASIN %s: %s", asin, exc)

        return item


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_price(value: Any) -> float | None:
    if value in (None, "", "Currently unavailable", "N/A", "—"):
        return None
    text     = str(value).replace(",", "").replace("₹", "").replace("$", "").strip()
    match    = _PRICE_RE.search(text)
    if not match:
        return None
    try:
        return float(Decimal(match.group()))
    except (InvalidOperation, ValueError):
        LOGGER.debug("Could not parse price %r", value)
        return None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else None


def _synthesise_seller_id(name: str) -> str:
    """Create a deterministic, stable ID from a seller display name."""
    return re.sub(r"\s+", "_", name.strip().upper())[:64]


def _make_serialisable(obj: Any) -> Any:
    """Recursively convert non-JSON-serialisable types for JSONL export."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _make_serialisable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_serialisable(v) for v in obj]
    return obj
