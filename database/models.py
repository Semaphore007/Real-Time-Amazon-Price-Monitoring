"""
SQLAlchemy ORM models for the e-commerce price monitoring system.

Maps 1-to-1 with database/schema.sql.  All timestamp columns use
TIMESTAMPTZ (timezone-aware) so that comparisons always stay consistent
regardless of the server locale.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# 1. Products
# ---------------------------------------------------------------------------
class Product(Base):
    __tablename__ = "products"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    asin:         Mapped[str]           = mapped_column(String(32), unique=True, index=True, nullable=False)
    title:        Mapped[str]           = mapped_column(Text, nullable=False)
    brand:        Mapped[str | None]    = mapped_column(String(120))
    category:     Mapped[str | None]    = mapped_column(String(120), index=True)
    sub_category: Mapped[str | None]    = mapped_column(String(120))
    image_url:    Mapped[str | None]    = mapped_column(Text)
    product_url:  Mapped[str | None]    = mapped_column(Text)
    is_active:    Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    created_at:   Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:   Mapped[datetime]      = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    price_history:  Mapped[list[PriceHistory]]  = relationship(back_populates="product", cascade="all, delete-orphan")
    listings:       Mapped[list[Listing]]        = relationship(back_populates="product", cascade="all, delete-orphan")
    buy_box_history:Mapped[list[BuyBoxHistory]] = relationship(back_populates="product", cascade="all, delete-orphan")
    alert_rules:    Mapped[list[AlertRule]]      = relationship(back_populates="product", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Product asin={self.asin!r} title={self.title[:40]!r}>"


# ---------------------------------------------------------------------------
# 2. Sellers  — seller_id is the marketplace-native string (e.g. Amazon's A1B2C3D4)
# ---------------------------------------------------------------------------
class Seller(Base):
    __tablename__ = "sellers"

    id:               Mapped[int]        = mapped_column(Integer, primary_key=True)
    seller_id:        Mapped[str]        = mapped_column(String(64), unique=True, index=True, nullable=False)
    name:             Mapped[str]        = mapped_column(String(255), nullable=False)
    rating:           Mapped[float|None] = mapped_column(Numeric(3, 2))
    review_count:     Mapped[int|None]   = mapped_column(Integer)
    fulfillment_type: Mapped[str|None]   = mapped_column(String(40))   # FBA | FBM | Amazon
    is_active:        Mapped[bool]       = mapped_column(Boolean, nullable=False, default=True)
    created_at:       Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:       Mapped[datetime]   = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    price_history:   Mapped[list[PriceHistory]]  = relationship(back_populates="seller")
    listings:        Mapped[list[Listing]]        = relationship(back_populates="seller")
    buy_box_history: Mapped[list[BuyBoxHistory]] = relationship(back_populates="seller")
    alert_rules:     Mapped[list[AlertRule]]      = relationship(back_populates="seller")

    def __repr__(self) -> str:
        return f"<Seller seller_id={self.seller_id!r} name={self.name!r}>"


# ---------------------------------------------------------------------------
# 3. Locations
# ---------------------------------------------------------------------------
class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("pincode", "city", name="uq_locations_pincode_city"),)

    id:      Mapped[int]       = mapped_column(Integer, primary_key=True)
    pincode: Mapped[str]       = mapped_column(String(12), index=True, nullable=False)
    city:    Mapped[str|None]  = mapped_column(String(120))
    state:   Mapped[str|None]  = mapped_column(String(120), index=True)
    country: Mapped[str]       = mapped_column(String(60), nullable=False, default="India")

    # Relationships
    price_history:   Mapped[list[PriceHistory]]  = relationship(back_populates="location")
    listings:        Mapped[list[Listing]]        = relationship(back_populates="location")
    buy_box_history: Mapped[list[BuyBoxHistory]] = relationship(back_populates="location")

    def __repr__(self) -> str:
        return f"<Location pincode={self.pincode!r} city={self.city!r}>"


# ---------------------------------------------------------------------------
# 4. Listings  (current snapshot — one row per ASIN × seller offer)
# ---------------------------------------------------------------------------
class Listing(Base):
    __tablename__ = "listings"

    id:            Mapped[int]        = mapped_column(BigInteger, primary_key=True)
    asin:          Mapped[str]        = mapped_column(
        String(32), ForeignKey("products.asin", ondelete="CASCADE"), index=True, nullable=False
    )
    seller_id:     Mapped[str]        = mapped_column(
        String(64), ForeignKey("sellers.seller_id", ondelete="CASCADE"), index=True, nullable=False
    )
    location_id:   Mapped[int|None]   = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    price:         Mapped[float]      = mapped_column(Numeric(12, 2), nullable=False)
    mrp:           Mapped[float|None] = mapped_column(Numeric(12, 2))
    currency:      Mapped[str]        = mapped_column(String(3), nullable=False, default="INR")
    is_buybox:     Mapped[bool]       = mapped_column(Boolean, nullable=False, default=False)
    is_fba:        Mapped[bool]       = mapped_column(Boolean, nullable=False, default=False)
    availability:  Mapped[str|None]   = mapped_column(String(60))
    delivery_days: Mapped[int|None]   = mapped_column(SmallInteger)
    seller_rating: Mapped[float|None] = mapped_column(Numeric(3, 2))
    timestamp:     Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    product:  Mapped[Product]       = relationship(back_populates="listings")
    seller:   Mapped[Seller]        = relationship(back_populates="listings")
    location: Mapped[Location|None] = relationship(back_populates="listings")

    def __repr__(self) -> str:
        return f"<Listing asin={self.asin!r} seller_id={self.seller_id!r} price={self.price}>"


# ---------------------------------------------------------------------------
# 5. PriceHistory  (immutable, append-only time-series)
# ---------------------------------------------------------------------------
class PriceHistory(Base):
    __tablename__ = "price_history"

    id:           Mapped[int]        = mapped_column(BigInteger, primary_key=True)
    asin:         Mapped[str]        = mapped_column(
        String(32), ForeignKey("products.asin", ondelete="CASCADE"), index=True, nullable=False
    )
    seller_id:    Mapped[str|None]   = mapped_column(
        String(64), ForeignKey("sellers.seller_id", ondelete="SET NULL"), index=True
    )
    location_id:  Mapped[int|None]  = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), index=True)
    price:        Mapped[float]     = mapped_column(Numeric(12, 2), nullable=False)
    mrp:          Mapped[float|None]= mapped_column(Numeric(12, 2))
    currency:     Mapped[str]       = mapped_column(String(3), nullable=False, default="INR")
    availability: Mapped[str|None]  = mapped_column(String(60))
    rating:       Mapped[float|None]= mapped_column(Numeric(3, 2))
    review_count: Mapped[int|None]  = mapped_column(Integer)
    is_fba:       Mapped[bool]      = mapped_column(Boolean, nullable=False, default=False)
    source:       Mapped[str]       = mapped_column(String(60), nullable=False, default="scraper")
    timestamp:    Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    product:  Mapped[Product]       = relationship(back_populates="price_history")
    seller:   Mapped[Seller|None]   = relationship(back_populates="price_history")
    location: Mapped[Location|None] = relationship(back_populates="price_history")

    def __repr__(self) -> str:
        return f"<PriceHistory asin={self.asin!r} price={self.price} ts={self.timestamp}>"


# ---------------------------------------------------------------------------
# 6. BuyBoxHistory
# ---------------------------------------------------------------------------
class BuyBoxHistory(Base):
    __tablename__ = "buy_box_history"

    id:          Mapped[int]       = mapped_column(BigInteger, primary_key=True)
    asin:        Mapped[str]       = mapped_column(
        String(32), ForeignKey("products.asin", ondelete="CASCADE"), index=True, nullable=False
    )
    seller_id:   Mapped[str]       = mapped_column(
        String(64), ForeignKey("sellers.seller_id", ondelete="CASCADE"), index=True, nullable=False
    )
    location_id: Mapped[int|None]  = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    price:       Mapped[float]     = mapped_column(Numeric(12, 2), nullable=False)
    captured_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    product:  Mapped[Product]       = relationship(back_populates="buy_box_history")
    seller:   Mapped[Seller]        = relationship(back_populates="buy_box_history")
    location: Mapped[Location|None] = relationship(back_populates="buy_box_history")

    def __repr__(self) -> str:
        return f"<BuyBoxHistory asin={self.asin!r} seller_id={self.seller_id!r} price={self.price}>"


# ---------------------------------------------------------------------------
# 7. AlertRule  (user-configured thresholds stored as JSONB)
# ---------------------------------------------------------------------------
class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint("severity IN ('info','warning','critical')", name="ck_alert_rules_severity"),
    )

    id:             Mapped[int]       = mapped_column(Integer, primary_key=True)
    asin:           Mapped[str]       = mapped_column(
        String(32), ForeignKey("products.asin", ondelete="CASCADE"), index=True, nullable=False
    )
    seller_id:      Mapped[str|None]  = mapped_column(
        String(64), ForeignKey("sellers.seller_id", ondelete="CASCADE"), index=True
    )
    condition:      Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    severity:       Mapped[str]       = mapped_column(String(20), nullable=False, default="info")
    is_active:      Mapped[bool]      = mapped_column(Boolean, nullable=False, default=True)
    notify_email:   Mapped[str|None]  = mapped_column(String(255))
    notify_webhook: Mapped[str|None]  = mapped_column(Text)
    created_at:     Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:     Mapped[datetime]  = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    product: Mapped[Product]      = relationship(back_populates="alert_rules")
    seller:  Mapped[Seller|None]  = relationship(back_populates="alert_rules")
    alerts:  Mapped[list[Alert]]  = relationship(back_populates="rule", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<AlertRule id={self.id} asin={self.asin!r} condition={self.condition}>"


# ---------------------------------------------------------------------------
# 8. Alert  (fired alert events — one row per trigger)
# ---------------------------------------------------------------------------
class Alert(Base):
    __tablename__ = "alerts"

    id:              Mapped[int]            = mapped_column(BigInteger, primary_key=True)
    rule_id:         Mapped[int|None]       = mapped_column(ForeignKey("alert_rules.id", ondelete="SET NULL"))
    asin:            Mapped[str]            = mapped_column(String(32), index=True, nullable=False)
    seller_id:       Mapped[str|None]       = mapped_column(String(64))
    condition:       Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # snapshot at fire time
    message:         Mapped[str]            = mapped_column(Text, nullable=False)
    severity:        Mapped[str]            = mapped_column(String(20), nullable=False, default="info")
    old_value:       Mapped[float|None]     = mapped_column(Numeric(12, 2))
    new_value:       Mapped[float|None]     = mapped_column(Numeric(12, 2))
    triggered_at:    Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    acknowledged_at: Mapped[datetime|None]  = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str|None]       = mapped_column(String(120))

    # Relationship
    rule: Mapped[AlertRule|None] = relationship(back_populates="alerts")

    def __repr__(self) -> str:
        return f"<Alert id={self.id} asin={self.asin!r} severity={self.severity!r}>"


# ---------------------------------------------------------------------------
# 9. ScrapeJob  (audit log for every scrape run)
# ---------------------------------------------------------------------------
class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','success','failed','retrying')",
            name="ck_scrape_jobs_status",
        ),
    )

    id:            Mapped[int]       = mapped_column(BigInteger, primary_key=True)
    asin:          Mapped[str|None]  = mapped_column(String(32), index=True)
    status:        Mapped[str]       = mapped_column(String(20), nullable=False, default="pending", index=True)
    attempts:      Mapped[int]       = mapped_column(SmallInteger, nullable=False, default=0)
    started_at:    Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    finished_at:   Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    proxy_used:    Mapped[str|None]  = mapped_column(String(120))
    error_message: Mapped[str|None]  = mapped_column(Text)
    created_at:    Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    def __repr__(self) -> str:
        return f"<ScrapeJob id={self.id} asin={self.asin!r} status={self.status!r}>"
