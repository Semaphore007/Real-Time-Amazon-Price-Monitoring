"""
MonitoringRepository — data-access layer for the price monitoring system.

All public methods accept / return plain Python dicts or Pandas DataFrames
so callers never need to import SQLAlchemy models directly.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from database.models import (
    Alert,
    AlertRule,
    BuyBoxHistory,
    Listing,
    Location,
    PriceHistory,
    Product,
    ScrapeJob,
    Seller,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
PINCODE_CITY_MAP: dict[str, tuple[str, str]] = {
    "600001": ("Chennai", "Tamil Nadu"),
    "560001": ("Bangalore", "Karnataka"),
    "110001": ("Delhi", "Delhi"),
    "400001": ("Mumbai", "Maharashtra"),
    "580009": ("Hubli", "Karnataka"),
}

UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------
class MonitoringRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory

    # -----------------------------------------------------------------------
    # Write helpers
    # -----------------------------------------------------------------------

    def record_product_snapshot(self, snapshot: dict[str, Any]) -> None:
        """
        Persist a single scraped snapshot.

        Expected snapshot keys:
            asin, title, brand, category, price, mrp, currency,
            seller_id, seller_name, fulfillment_type, is_fba,
            availability, rating, review_count, location (pincode str),
            captured_at (datetime, optional), offers (list[dict])

        Each `offer` dict: seller_id, seller_name, price, mrp,
            is_buybox, is_fba, availability, seller_rating, fulfillment_type
        """
        with self.session_factory() as session:
            product = self._upsert_product(session, snapshot)
            location = self._get_or_create_location(session, snapshot.get("location"))

            # --- Price history (buy-box / representative price) ---
            buyer_seller = None
            raw_sid = snapshot.get("seller_id") or snapshot.get("buy_box_seller_id")
            raw_name = snapshot.get("seller_name") or snapshot.get("buy_box_seller")
            if raw_sid or raw_name:
                buyer_seller = self._upsert_seller(
                    session,
                    seller_id=raw_sid or self._synthesize_seller_id(raw_name),
                    name=raw_name or raw_sid,
                    rating=snapshot.get("rating"),
                    fulfillment_type="FBA" if snapshot.get("is_fba") else snapshot.get("fulfillment_type", "FBM"),
                )
            ts = snapshot.get("captured_at") or _now()
            session.add(
                PriceHistory(
                    asin=product.asin,
                    seller_id=buyer_seller.seller_id if buyer_seller else None,
                    location_id=location.id if location else None,
                    price=snapshot["price"],
                    mrp=snapshot.get("mrp"),
                    currency=snapshot.get("currency", "INR"),
                    availability=snapshot.get("availability"),
                    rating=snapshot.get("rating"),
                    review_count=snapshot.get("review_count"),
                    is_fba=bool(snapshot.get("is_fba", False)),
                    source=snapshot.get("source", "scraper"),
                    timestamp=ts,
                )
            )

            # --- Buy-box history ---
            bb_sid = snapshot.get("buy_box_seller_id") or (
                buyer_seller.seller_id if buyer_seller else None
            )
            if bb_sid:
                bb_seller = self._upsert_seller(
                    session,
                    seller_id=bb_sid,
                    name=snapshot.get("buy_box_seller") or bb_sid,
                )
                session.add(
                    BuyBoxHistory(
                        asin=product.asin,
                        seller_id=bb_seller.seller_id,
                        location_id=location.id if location else None,
                        price=snapshot["price"],
                        captured_at=ts,
                    )
                )

            # --- Per-offer listings ---
            for offer in snapshot.get("offers", []):
                o_sid = offer.get("seller_id") or self._synthesize_seller_id(offer.get("seller_name"))
                o_seller = self._upsert_seller(
                    session,
                    seller_id=o_sid,
                    name=offer.get("seller_name") or o_sid,
                    rating=offer.get("seller_rating"),
                    fulfillment_type="FBA" if offer.get("is_fba") else offer.get("fulfillment_type", "FBM"),
                )
                session.add(
                    Listing(
                        asin=product.asin,
                        seller_id=o_seller.seller_id,
                        location_id=location.id if location else None,
                        price=offer["price"],
                        mrp=offer.get("mrp"),
                        currency=offer.get("currency", "INR"),
                        is_buybox=bool(offer.get("is_buybox", False)),
                        is_fba=bool(offer.get("is_fba", False)),
                        availability=offer.get("availability"),
                        delivery_days=offer.get("delivery_days"),
                        seller_rating=offer.get("seller_rating"),
                        timestamp=ts,
                    )
                )

            session.commit()

    def upsert_alert_rule(
        self,
        asin: str,
        condition: dict[str, Any],
        severity: str = "info",
        seller_id: str | None = None,
        notify_email: str | None = None,
        notify_webhook: str | None = None,
    ) -> int:
        """Create or update an alert rule; returns the rule id."""
        with self.session_factory() as session:
            existing = session.scalar(
                select(AlertRule).where(
                    AlertRule.asin == asin,
                    AlertRule.condition["type"].astext == condition.get("type"),
                    AlertRule.seller_id == seller_id,
                )
            )
            if existing:
                existing.condition = condition
                existing.severity = severity
                existing.notify_email = notify_email
                existing.notify_webhook = notify_webhook
                existing.is_active = True
                session.commit()
                return existing.id

            rule = AlertRule(
                asin=asin,
                seller_id=seller_id,
                condition=condition,
                severity=severity,
                notify_email=notify_email,
                notify_webhook=notify_webhook,
            )
            session.add(rule)
            session.commit()
            session.refresh(rule)
            return rule.id

    def fire_alert(
        self,
        asin: str,
        condition: dict[str, Any],
        message: str,
        severity: str = "info",
        seller_id: str | None = None,
        old_value: float | None = None,
        new_value: float | None = None,
        rule_id: int | None = None,
    ) -> int:
        """Persist a triggered alert and return its id."""
        with self.session_factory() as session:
            alert = Alert(
                rule_id=rule_id,
                asin=asin,
                seller_id=seller_id,
                condition=condition,
                message=message,
                severity=severity,
                old_value=old_value,
                new_value=new_value,
            )
            session.add(alert)
            session.commit()
            session.refresh(alert)
            return alert.id

    def acknowledge_alert(self, alert_id: int, acknowledged_by: str) -> None:
        with self.session_factory() as session:
            session.execute(
                update(Alert)
                .where(Alert.id == alert_id, Alert.acknowledged_at.is_(None))
                .values(acknowledged_at=_now(), acknowledged_by=acknowledged_by)
            )
            session.commit()

    def log_scrape_job(
        self,
        asin: str | None = None,
        status: str = "pending",
        proxy_used: str | None = None,
        error_message: str | None = None,
        attempts: int = 0,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> int:
        with self.session_factory() as session:
            job = ScrapeJob(
                asin=asin,
                status=status,
                attempts=attempts,
                started_at=started_at,
                finished_at=finished_at,
                proxy_used=proxy_used,
                error_message=error_message,
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            return job.id

    # -----------------------------------------------------------------------
    # Read — Products
    # -----------------------------------------------------------------------

    def list_products(self, query: str | None = None, active_only: bool = True) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(Product).order_by(Product.updated_at.desc())
            if active_only:
                stmt = stmt.where(Product.is_active.is_(True))
            if query:
                term = f"%{query.lower()}%"
                stmt = stmt.where(
                    func.lower(Product.asin).like(term) | func.lower(Product.title).like(term)
                )
            return [self._product_to_dict(p) for p in session.scalars(stmt).all()]

    def get_product(self, asin: str) -> dict | None:
        with self.session_factory() as session:
            product = session.scalar(select(Product).where(Product.asin == asin))
            return self._product_to_dict(product) if product else None

    def get_product_details(self, asin: str) -> dict | None:
        """Returns product + latest price + total buy-box events."""
        with self.session_factory() as session:
            product = session.scalar(select(Product).where(Product.asin == asin))
            if product is None:
                return None

            latest_ph = session.scalar(
                select(PriceHistory)
                .where(PriceHistory.asin == asin)
                .order_by(PriceHistory.timestamp.desc())
                .limit(1)
            )
            bb_count = session.scalar(
                select(func.count()).select_from(BuyBoxHistory).where(BuyBoxHistory.asin == asin)
            )
            current_buybox = session.scalar(
                select(Listing)
                .where(Listing.asin == asin, Listing.is_buybox.is_(True))
                .order_by(Listing.timestamp.desc())
                .limit(1)
            )
            return {
                **self._product_to_dict(product),
                "latest_price": float(latest_ph.price) if latest_ph else None,
                "latest_seller_id": latest_ph.seller_id if latest_ph else None,
                "buy_box_events": bb_count or 0,
                "current_buybox_seller_id": current_buybox.seller_id if current_buybox else None,
                "current_buybox_price": float(current_buybox.price) if current_buybox else None,
            }

    # -----------------------------------------------------------------------
    # Read — Price history
    # -----------------------------------------------------------------------

    def get_price_history(
        self,
        asin: str,
        location: str | None = None,
        seller_id: str | None = None,
        since: datetime | None = None,
    ) -> list[dict]:
        with self.session_factory() as session:
            stmt = (
                select(PriceHistory, Seller, Location)
                .outerjoin(Seller, PriceHistory.seller_id == Seller.seller_id)
                .outerjoin(Location, PriceHistory.location_id == Location.id)
                .where(PriceHistory.asin == asin)
                .order_by(PriceHistory.timestamp.asc())
            )
            if location:
                stmt = stmt.where(Location.pincode == location)
            if seller_id:
                stmt = stmt.where(PriceHistory.seller_id == seller_id)
            if since:
                stmt = stmt.where(PriceHistory.timestamp >= since)

            return [
                {
                    "asin": asin,
                    "price": float(ph.price),
                    "mrp": float(ph.mrp) if ph.mrp else None,
                    "currency": ph.currency,
                    "seller_id": ph.seller_id,
                    "seller_name": seller.name if seller else None,
                    "availability": ph.availability,
                    "is_fba": ph.is_fba,
                    "location": loc.pincode if loc else None,
                    "timestamp": ph.timestamp.isoformat(),
                }
                for ph, seller, loc in session.execute(stmt).all()
            ]

    def price_history_frame(
        self,
        asin: str | None = None,
        since: datetime | None = None,
    ) -> pd.DataFrame:
        with self.session_factory() as session:
            stmt = (
                select(
                    PriceHistory.asin,
                    Product.title,
                    Seller.name.label("seller_name"),
                    Location.pincode.label("location"),
                    PriceHistory.price,
                    PriceHistory.availability,
                    PriceHistory.is_fba,
                    PriceHistory.timestamp,
                )
                .join(Product, PriceHistory.asin == Product.asin)
                .outerjoin(Seller, PriceHistory.seller_id == Seller.seller_id)
                .outerjoin(Location, PriceHistory.location_id == Location.id)
                .order_by(PriceHistory.timestamp.asc())
            )
            if asin:
                stmt = stmt.where(PriceHistory.asin == asin)
            if since:
                stmt = stmt.where(PriceHistory.timestamp >= since)

            rows = session.execute(stmt).all()
            df = pd.DataFrame(rows, columns=["asin", "title", "seller_name", "location",
                                             "price", "availability", "is_fba", "timestamp"])
            if not df.empty:
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            return df

    # -----------------------------------------------------------------------
    # Read — Listings / Offers
    # -----------------------------------------------------------------------

    def get_latest_offers(self, asin: str) -> list[dict]:
        """Returns the most recent listing row per seller for an ASIN."""
        with self.session_factory() as session:
            # Subquery: max timestamp per seller for this asin
            sub = (
                select(
                    Listing.seller_id,
                    func.max(Listing.timestamp).label("max_ts"),
                )
                .where(Listing.asin == asin)
                .group_by(Listing.seller_id)
                .subquery()
            )
            stmt = (
                select(Listing, Seller)
                .join(Seller, Listing.seller_id == Seller.seller_id)
                .join(sub, (Listing.seller_id == sub.c.seller_id) & (Listing.timestamp == sub.c.max_ts))
                .where(Listing.asin == asin)
                .order_by(Listing.price.asc())
            )
            return [
                {
                    "asin": l.asin,
                    "seller_id": l.seller_id,
                    "seller_name": s.name,
                    "price": float(l.price),
                    "mrp": float(l.mrp) if l.mrp else None,
                    "is_buybox": l.is_buybox,
                    "is_fba": l.is_fba,
                    "availability": l.availability,
                    "seller_rating": float(l.seller_rating) if l.seller_rating else None,
                    "timestamp": l.timestamp.isoformat(),
                }
                for l, s in session.execute(stmt).all()
            ]

    def listings_frame(self, asin: str | None = None) -> pd.DataFrame:
        with self.session_factory() as session:
            stmt = (
                select(
                    Listing.asin,
                    Product.title,
                    Seller.name.label("seller_name"),
                    Location.pincode.label("location"),
                    Listing.price,
                    Listing.is_buybox,
                    Listing.is_fba,
                    Listing.availability,
                    Listing.timestamp,
                )
                .join(Product, Listing.asin == Product.asin)
                .join(Seller, Listing.seller_id == Seller.seller_id)
                .outerjoin(Location, Listing.location_id == Location.id)
                .order_by(Listing.timestamp.desc())
            )
            if asin:
                stmt = stmt.where(Listing.asin == asin)
            rows = session.execute(stmt).all()
            df = pd.DataFrame(rows, columns=["asin", "title", "seller_name", "location",
                                             "price", "is_buybox", "is_fba", "availability", "timestamp"])
            if not df.empty:
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            return df

    def latest_market_snapshot(self) -> pd.DataFrame:
        df = self.listings_frame()
        if df.empty:
            return df
        df = df.sort_values("timestamp")
        latest = df.groupby(["asin", "seller_name", "location"], as_index=False).tail(1)
        return latest.sort_values(["asin", "price", "seller_name"])

    # -----------------------------------------------------------------------
    # Read — Buy-box history
    # -----------------------------------------------------------------------

    def get_buy_box_history(self, asin: str) -> list[dict]:
        with self.session_factory() as session:
            stmt = (
                select(BuyBoxHistory, Seller, Location)
                .join(Seller, BuyBoxHistory.seller_id == Seller.seller_id)
                .outerjoin(Location, BuyBoxHistory.location_id == Location.id)
                .where(BuyBoxHistory.asin == asin)
                .order_by(BuyBoxHistory.captured_at.asc())
            )
            return [
                {
                    "asin": asin,
                    "seller_id": s.seller_id,
                    "seller_name": s.name,
                    "location": loc.pincode if loc else None,
                    "price": float(bb.price),
                    "captured_at": bb.captured_at.isoformat(),
                }
                for bb, s, loc in session.execute(stmt).all()
            ]

    def buy_box_frame(self, asin: str | None = None) -> pd.DataFrame:
        with self.session_factory() as session:
            stmt = (
                select(
                    BuyBoxHistory.asin,
                    Seller.name.label("seller_name"),
                    Location.pincode.label("location"),
                    BuyBoxHistory.price,
                    BuyBoxHistory.captured_at,
                )
                .join(Seller, BuyBoxHistory.seller_id == Seller.seller_id)
                .outerjoin(Location, BuyBoxHistory.location_id == Location.id)
                .order_by(BuyBoxHistory.captured_at.asc())
            )
            if asin:
                stmt = stmt.where(BuyBoxHistory.asin == asin)
            rows = session.execute(stmt).all()
            df = pd.DataFrame(rows, columns=["asin", "seller_name", "location", "price", "captured_at"])
            if not df.empty:
                df["captured_at"] = pd.to_datetime(df["captured_at"], utc=True)
            return df

    # -----------------------------------------------------------------------
    # Read — Sellers
    # -----------------------------------------------------------------------

    def list_sellers(self, active_only: bool = True) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(Seller).order_by(Seller.name.asc())
            if active_only:
                stmt = stmt.where(Seller.is_active.is_(True))
            return [
                {
                    "seller_id": s.seller_id,
                    "name": s.name,
                    "rating": float(s.rating) if s.rating else None,
                    "fulfillment_type": s.fulfillment_type,
                }
                for s in session.scalars(stmt).all()
            ]

    # -----------------------------------------------------------------------
    # Read — Alerts
    # -----------------------------------------------------------------------

    def list_alert_rules(self, asin: str | None = None, active_only: bool = True) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(AlertRule).order_by(AlertRule.created_at.desc())
            if active_only:
                stmt = stmt.where(AlertRule.is_active.is_(True))
            if asin:
                stmt = stmt.where(AlertRule.asin == asin)
            return [
                {
                    "id": r.id,
                    "asin": r.asin,
                    "seller_id": r.seller_id,
                    "condition": r.condition,
                    "severity": r.severity,
                    "notify_email": r.notify_email,
                }
                for r in session.scalars(stmt).all()
            ]

    def list_alerts(
        self,
        limit: int = 100,
        asin: str | None = None,
        unacknowledged_only: bool = False,
    ) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(Alert).order_by(Alert.triggered_at.desc()).limit(limit)
            if asin:
                stmt = stmt.where(Alert.asin == asin)
            if unacknowledged_only:
                stmt = stmt.where(Alert.acknowledged_at.is_(None))
            return [
                {
                    "id": a.id,
                    "rule_id": a.rule_id,
                    "asin": a.asin,
                    "seller_id": a.seller_id,
                    "condition": a.condition,
                    "message": a.message,
                    "severity": a.severity,
                    "old_value": float(a.old_value) if a.old_value else None,
                    "new_value": float(a.new_value) if a.new_value else None,
                    "triggered_at": a.triggered_at.isoformat(),
                    "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
                }
                for a in session.scalars(stmt).all()
            ]

    def has_recent_alert(
        self,
        alert_type: str,
        asin: str,
        seller_id: str | None = None,
        cooldown_minutes: int = 60,
    ) -> bool:
        threshold = _now() - timedelta(minutes=cooldown_minutes)
        with self.session_factory() as session:
            stmt = (
                select(Alert.id)
                .where(
                    Alert.asin == asin,
                    Alert.condition["type"].astext == alert_type,
                    Alert.triggered_at >= threshold,
                )
            )
            if seller_id is not None:
                stmt = stmt.where(Alert.seller_id == seller_id)
            return session.scalar(stmt.limit(1)) is not None

    # -----------------------------------------------------------------------
    # Analytics helpers (using DB views when on PostgreSQL)
    # -----------------------------------------------------------------------

    def daily_price_ohlc(self, asin: str) -> pd.DataFrame:
        """Returns open/high/low/close daily prices from the DB view."""
        with self.session_factory() as session:
            try:
                rows = session.execute(
                    text(
                        "SELECT day, low, high, open, close, avg_price, sample_count "
                        "FROM vw_daily_price_ohlc WHERE asin = :asin ORDER BY day"
                    ),
                    {"asin": asin},
                ).all()
                df = pd.DataFrame(rows, columns=["day", "low", "high", "open", "close", "avg_price", "sample_count"])
                if not df.empty:
                    df["day"] = pd.to_datetime(df["day"], utc=True)
                return df
            except Exception:
                # Fallback: compute in Python if view doesn't exist
                return self._compute_ohlc_fallback(asin)

    def _compute_ohlc_fallback(self, asin: str) -> pd.DataFrame:
        df = self.price_history_frame(asin)
        if df.empty:
            return df
        df["day"] = df["timestamp"].dt.floor("D")
        grouped = df.groupby("day")["price"]
        ohlc = grouped.agg(
            low="min", high="max",
            open=lambda s: s.iloc[0],
            close=lambda s: s.iloc[-1],
            avg_price="mean",
            sample_count="count",
        ).reset_index()
        return ohlc

    def seller_competitiveness_frame(self, asin: str) -> pd.DataFrame:
        """Win-rate and avg price per seller for an ASIN."""
        df = self.listings_frame(asin)
        if df.empty:
            return df
        grp = df.groupby("seller_name")
        comp = grp.agg(
            total_snapshots=("price", "count"),
            buybox_wins=("is_buybox", "sum"),
            avg_price=("price", "mean"),
            min_price=("price", "min"),
            max_price=("price", "max"),
        ).reset_index()
        comp["buybox_win_rate_pct"] = (comp["buybox_wins"] / comp["total_snapshots"] * 100).round(2)
        return comp.sort_values("buybox_win_rate_pct", ascending=False)

    # -----------------------------------------------------------------------
    # Seed / init
    # -----------------------------------------------------------------------

    def ensure_seed_data(self) -> None:
        if self.list_products(active_only=False):
            return

        seed_snapshots: Iterable[dict] = [
            {
                "asin": "B0SKF6205",
                "title": "SKF 6205 Deep Groove Ball Bearing",
                "brand": "SKF",
                "category": "Bearings",
                "price": 420.0,
                "mrp": 480.0,
                "seller_id": "INDUSTRIAL_HUB_01",
                "seller_name": "Industrial Hub",
                "availability": "In stock",
                "rating": 4.4,
                "review_count": 126,
                "is_fba": True,
                "fulfillment_type": "FBA",
                "location": "600001",
                "captured_at": datetime(2026, 3, 15, 10, 0, tzinfo=UTC),
                "offers": [
                    {"seller_id": "INDUSTRIAL_HUB_01", "seller_name": "Industrial Hub",
                     "price": 420.0, "mrp": 480.0, "is_buybox": True, "is_fba": True, "seller_rating": 4.4},
                    {"seller_id": "BEARING_WORLD_02", "seller_name": "Bearing World",
                     "price": 428.0, "mrp": 480.0, "is_buybox": False, "is_fba": False, "seller_rating": 4.1},
                ],
            },
            {
                "asin": "B0SKF6205",
                "title": "SKF 6205 Deep Groove Ball Bearing",
                "brand": "SKF",
                "category": "Bearings",
                "price": 408.0,
                "mrp": 480.0,
                "seller_id": "BEARING_WORLD_02",
                "seller_name": "Bearing World",
                "availability": "In stock",
                "rating": 4.4,
                "review_count": 129,
                "is_fba": False,
                "fulfillment_type": "FBM",
                "location": "560001",
                "captured_at": datetime(2026, 3, 15, 11, 0, tzinfo=UTC),
                "offers": [
                    {"seller_id": "INDUSTRIAL_HUB_01", "seller_name": "Industrial Hub",
                     "price": 420.0, "is_buybox": False, "is_fba": True, "seller_rating": 4.4},
                    {"seller_id": "BEARING_WORLD_02", "seller_name": "Bearing World",
                     "price": 408.0, "is_buybox": True, "is_fba": False, "seller_rating": 4.1},
                ],
            },
            {
                "asin": "B0SKF6203",
                "title": "SKF 6203 Deep Groove Ball Bearing",
                "brand": "SKF",
                "category": "Bearings",
                "price": 295.0,
                "mrp": 340.0,
                "seller_id": "PRECISION_TRADERS_03",
                "seller_name": "Precision Traders",
                "availability": "In stock",
                "rating": 4.3,
                "review_count": 87,
                "is_fba": True,
                "fulfillment_type": "FBA",
                "location": "110001",
                "captured_at": datetime(2026, 3, 15, 10, 30, tzinfo=UTC),
                "offers": [
                    {"seller_id": "PRECISION_TRADERS_03", "seller_name": "Precision Traders",
                     "price": 295.0, "is_buybox": True, "is_fba": True, "seller_rating": 4.3},
                    {"seller_id": "NATIONAL_BEARINGS_04", "seller_name": "National Bearings",
                     "price": 301.0, "is_buybox": False, "is_fba": False, "seller_rating": 4.0},
                ],
            },
        ]
        for snap in seed_snapshots:
            self.record_product_snapshot(snap)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _synthesize_seller_id(name: str | None) -> str:
        """Generate a deterministic ID from a seller name (fallback)."""
        if not name:
            return "UNKNOWN_SELLER"
        return name.upper().replace(" ", "_")[:64]

    def _upsert_product(self, session: Session, snapshot: dict) -> Product:
        product = session.scalar(select(Product).where(Product.asin == snapshot["asin"]))
        if product is None:
            product = Product(
                asin=snapshot["asin"],
                title=snapshot.get("title", snapshot["asin"]),
                brand=snapshot.get("brand"),
                category=snapshot.get("category"),
                sub_category=snapshot.get("sub_category"),
                image_url=snapshot.get("image_url"),
                product_url=snapshot.get("product_url"),
            )
            session.add(product)
            session.flush()
        else:
            product.title = snapshot.get("title", product.title)
            product.brand = snapshot.get("brand", product.brand)
            product.category = snapshot.get("category", product.category)
            product.updated_at = _now()
        return product

    def _upsert_seller(
        self,
        session: Session,
        seller_id: str,
        name: str,
        rating: float | None = None,
        fulfillment_type: str | None = None,
    ) -> Seller:
        seller = session.scalar(select(Seller).where(Seller.seller_id == seller_id))
        if seller is None:
            seller = Seller(
                seller_id=seller_id,
                name=name,
                rating=rating,
                fulfillment_type=fulfillment_type,
            )
            session.add(seller)
            session.flush()
        else:
            if rating is not None:
                seller.rating = rating
            if fulfillment_type:
                seller.fulfillment_type = fulfillment_type
        return seller

    def _get_or_create_location(self, session: Session, pincode: str | None) -> Location | None:
        if not pincode:
            return None
        location = session.scalar(select(Location).where(Location.pincode == pincode))
        if location is None:
            city, state = PINCODE_CITY_MAP.get(pincode, (None, None))
            location = Location(pincode=pincode, city=city, state=state)
            session.add(location)
            session.flush()
        return location

    @staticmethod
    def _product_to_dict(p: Product) -> dict:
        return {
            "asin": p.asin,
            "title": p.title,
            "brand": p.brand,
            "category": p.category,
            "sub_category": p.sub_category,
            "is_active": p.is_active,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
