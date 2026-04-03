"""
Comprehensive seed data generator — 30 days of realistic price history.

Generates 6 products × 6 sellers × 3 locations × 4 snapshots/day = ~2,592 rows.
Also creates 3 sample alert rules to demonstrate the rule engine.
"""
from __future__ import annotations

import logging
import random
import re
from datetime import datetime, timedelta, timezone

from config.settings import get_settings
from database.connection import init_database
from database.repository import MonitoringRepository

logger = logging.getLogger(__name__)
UTC    = timezone.utc


# ---------------------------------------------------------------------------
# Master catalogue
# ---------------------------------------------------------------------------

PRODUCTS = [
    {"asin": "B0SKF6205", "title": "SKF 6205 Deep Groove Ball Bearing (25×52×15 mm)", "brand": "SKF", "category": "Bearings"},
    {"asin": "B0SKF6203", "title": "SKF 6203 Deep Groove Ball Bearing (17×40×12 mm)", "brand": "SKF", "category": "Bearings"},
    {"asin": "B0SKF6202", "title": "SKF 6202 Deep Groove Ball Bearing (15×35×11 mm)", "brand": "SKF", "category": "Bearings"},
    {"asin": "B0SKF6206", "title": "SKF 6206 Deep Groove Ball Bearing (30×62×16 mm)", "brand": "SKF", "category": "Bearings"},
    {"asin": "B0SKF6207", "title": "SKF 6207 Deep Groove Ball Bearing (35×72×17 mm)", "brand": "SKF", "category": "Bearings"},
    {"asin": "B0SKF6001", "title": "SKF 6001 Deep Groove Ball Bearing (12×28×8 mm)",  "brand": "SKF", "category": "Bearings"},
]

# Each seller has a stable marketplace seller_id, a display name, rating, and fulfilment type
SELLERS = [
    {"seller_id": "INDUSTRIAL_HUB_01",    "name": "Industrial Hub",      "rating": 4.4, "fulfillment": "FBA"},
    {"seller_id": "BEARING_WORLD_02",     "name": "Bearing World",       "rating": 4.1, "fulfillment": "FBM"},
    {"seller_id": "PRECISION_TRADERS_03", "name": "Precision Traders",   "rating": 4.3, "fulfillment": "FBA"},
    {"seller_id": "NATIONAL_BEARINGS_04", "name": "National Bearings",   "rating": 4.0, "fulfillment": "FBM"},
    {"seller_id": "FASTTECH_SUPPLIES_05", "name": "FastTech Supplies",   "rating": 3.9, "fulfillment": "FBA"},
    {"seller_id": "MEGAMART_IND_06",      "name": "MegaMart Industrial", "rating": 4.2, "fulfillment": "FBM"},
]

LOCATIONS = ["600001", "560001", "110001"]

# Base prices per product (INR)
BASE_PRICES: dict[str, float] = {
    "B0SKF6205": 420.0,
    "B0SKF6203": 295.0,
    "B0SKF6202": 252.0,
    "B0SKF6206": 510.0,
    "B0SKF6207": 620.0,
    "B0SKF6001": 185.0,
}

# MRP (20% above base) — fixed for each product
MRP: dict[str, float] = {asin: round(price * 1.20, 2) for asin, price in BASE_PRICES.items()}

# How aggressively each seller prices vs the base
SELLER_MULTIPLIER: dict[str, float] = {
    "INDUSTRIAL_HUB_01":    1.00,
    "BEARING_WORLD_02":     1.02,
    "PRECISION_TRADERS_03": 0.98,
    "NATIONAL_BEARINGS_04": 1.04,
    "FASTTECH_SUPPLIES_05": 0.96,
    "MEGAMART_IND_06":      1.01,
}

# Partial coverage — not every seller sells every product
SELLER_PRODUCT_COVERAGE: dict[str, list[str]] = {
    "INDUSTRIAL_HUB_01":    ["B0SKF6205", "B0SKF6203", "B0SKF6202", "B0SKF6206"],
    "BEARING_WORLD_02":     ["B0SKF6205", "B0SKF6203", "B0SKF6207", "B0SKF6001"],
    "PRECISION_TRADERS_03": ["B0SKF6203", "B0SKF6202", "B0SKF6206", "B0SKF6207"],
    "NATIONAL_BEARINGS_04": ["B0SKF6202", "B0SKF6205", "B0SKF6001"],
    "FASTTECH_SUPPLIES_05": ["B0SKF6205", "B0SKF6206", "B0SKF6207"],
    "MEGAMART_IND_06":      ["B0SKF6203", "B0SKF6202", "B0SKF6001"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _price_with_noise(base: float, rng: random.Random, pct_range: float = 0.05) -> float:
    return round(base + base * rng.uniform(-pct_range, pct_range), 2)


def _buybox_seller_id(asin: str, ts: datetime) -> str:
    """Simulate buy-box rotation every ~3 days."""
    eligible = [s["seller_id"] for s in SELLERS if asin in SELLER_PRODUCT_COVERAGE[s["seller_id"]]]
    if not eligible:
        return SELLERS[0]["seller_id"]
    idx = int(ts.timestamp() // (3 * 86_400)) % len(eligible)
    return eligible[idx]


def _availability(ts: datetime, asin: str, rng: random.Random) -> str:
    """Simulate occasional low-stock or OOS windows."""
    if asin == "B0SKF6202" and int(ts.timestamp() // (10 * 86_400)) % 3 == 0:
        return "Low stock – order soon"
    if rng.random() < 0.02:
        return "Out of Stock"
    return "In stock"


def _seller_by_id(sid: str) -> dict:
    return next(s for s in SELLERS if s["seller_id"] == sid)


# ---------------------------------------------------------------------------
# Snapshot generator
# ---------------------------------------------------------------------------

def generate_snapshots(days: int = 30, snapshots_per_day: int = 4) -> list[dict]:
    """Build the full list of snapshot dicts covering the last *days* days."""
    rng   = random.Random(42)          # deterministic for reproducibility
    now   = datetime.now(UTC)
    start = now - timedelta(days=days)
    interval_hours = 24 / snapshots_per_day
    snapshots: list[dict] = []

    for day_offset in range(days):
        for snap_idx in range(snapshots_per_day):
            ts = start + timedelta(days=day_offset, hours=snap_idx * interval_hours)

            for product in PRODUCTS:
                asin     = product["asin"]
                base     = BASE_PRICES[asin]
                bb_sid   = _buybox_seller_id(asin, ts)
                bb_seller = _seller_by_id(bb_sid)

                # Build competing offer list
                active_sellers = [s for s in SELLERS if asin in SELLER_PRODUCT_COVERAGE[s["seller_id"]]]
                offers: list[dict] = []
                for seller in active_sellers:
                    s_price = _price_with_noise(base * SELLER_MULTIPLIER[seller["seller_id"]], rng)
                    # Occasional promo dip (5% chance, 7–12% off)
                    if rng.random() < 0.05:
                        s_price = round(s_price * rng.uniform(0.88, 0.93), 2)

                    offers.append({
                        "seller_id":      seller["seller_id"],
                        "seller_name":    seller["name"],
                        "price":          s_price,
                        "mrp":            MRP[asin],
                        "currency":       "INR",
                        "availability":   _availability(ts, asin, rng),
                        "is_buybox":      seller["seller_id"] == bb_sid,
                        "is_fba":         seller["fulfillment"] == "FBA",
                        "fulfillment_type": seller["fulfillment"],
                        "seller_rating":  round(seller["rating"] + rng.uniform(-0.1, 0.1), 1),
                    })

                # Buy-box price = winner's price
                bb_price = next((o["price"] for o in offers if o["is_buybox"]), base)

                for location in LOCATIONS:
                    snapshots.append({
                        **product,
                        "price":            bb_price,
                        "mrp":              MRP[asin],
                        "currency":         "INR",
                        "seller_id":        bb_sid,
                        "seller_name":      bb_seller["name"],
                        "buy_box_seller":   bb_seller["name"],
                        "buy_box_seller_id":bb_sid,
                        "fulfillment_type": bb_seller["fulfillment"],
                        "is_fba":           bb_seller["fulfillment"] == "FBA",
                        "availability":     _availability(ts, asin, rng),
                        "rating":           round(4.2 + rng.uniform(-0.2, 0.3), 1),
                        "review_count":     rng.randint(30, 300),
                        "location":         location,
                        "captured_at":      ts,
                        "source":           "seed",
                        "offers":           offers,
                    })

    return snapshots


# ---------------------------------------------------------------------------
# Alert rule seeds
# ---------------------------------------------------------------------------

def _seed_alert_rules(repo: MonitoringRepository) -> None:
    rules = [
        {
            "asin":      "B0SKF6205",
            "condition": {"type": "price_drop", "threshold_pct": 8},
            "severity":  "warning",
            "notify_email": None,
        },
        {
            "asin":      "B0SKF6205",
            "condition": {"type": "price_above", "value": 450.0},
            "severity":  "info",
        },
        {
            "asin":      "B0SKF6202",
            "condition": {"type": "oos", "consecutive_checks": 2},
            "severity":  "critical",
        },
        {
            "asin":      "B0SKF6203",
            "condition": {"type": "buybox_change", "seller_id": "PRECISION_TRADERS_03"},
            "severity":  "warning",
        },
    ]
    for rule in rules:
        repo.upsert_alert_rule(**rule)
    logger.info("Seeded %d alert rules", len(rules))


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

def seed(force: bool = False) -> None:
    """Populate the database with rich 30-day demo data + alert rules."""
    settings   = get_settings()
    repository = MonitoringRepository(init_database(settings.database_url))

    existing = repository.list_products(active_only=False)
    if existing and not force:
        logger.info(
            "Database already has %d products — skipping seed. "
            "Use --force to re-seed.",
            len(existing),
        )
        return

    snapshots = generate_snapshots(days=30, snapshots_per_day=4)
    logger.info("Seeding %d snapshots …", len(snapshots))

    for i, snapshot in enumerate(snapshots, 1):
        repository.record_product_snapshot(snapshot)
        if i % 200 == 0:
            logger.info("  … %d / %d", i, len(snapshots))

    _seed_alert_rules(repository)
    logger.info("Seed complete — %d snapshots, 4 alert rules.", len(snapshots))


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    parser = argparse.ArgumentParser(description="Seed demo data into the price monitor database.")
    parser.add_argument("--force", action="store_true", help="Re-seed even when data already exists")
    parser.add_argument("--days",  type=int, default=30, help="Days of history to generate (default: 30)")
    args = parser.parse_args()
    seed(force=args.force)
