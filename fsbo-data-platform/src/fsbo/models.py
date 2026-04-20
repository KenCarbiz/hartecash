from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Classification(StrEnum):
    UNCLASSIFIED = "unclassified"
    PRIVATE_SELLER = "private_seller"
    DEALER = "dealer"
    SCAM = "scam"
    UNCERTAIN = "uncertain"


class SourceName(StrEnum):
    CRAIGSLIST = "craigslist"
    EBAY_MOTORS = "ebay_motors"
    AUTOTRADER = "autotrader"
    CARS_COM = "cars_com"
    FACEBOOK_MARKETPLACE = "facebook_marketplace"
    OFFERUP = "offerup"
    CARGURUS = "cargurus"


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_source_external_id"),
        Index("ix_listings_geo", "zip_code"),
        Index("ix_listings_vehicle", "make", "model", "year"),
        Index("ix_listings_classification", "classification"),
        Index("ix_listings_posted_at", "posted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(256), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)

    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    year: Mapped[int | None] = mapped_column(Integer)
    make: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    trim: Mapped[str | None] = mapped_column(String(128))
    mileage: Mapped[int | None] = mapped_column(Integer)
    price: Mapped[float | None] = mapped_column(Float)
    vin: Mapped[str | None] = mapped_column(String(17), index=True)

    city: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(8))
    zip_code: Mapped[str | None] = mapped_column(String(16))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    seller_name: Mapped[str | None] = mapped_column(String(256))
    seller_phone: Mapped[str | None] = mapped_column(String(32), index=True)

    classification: Mapped[str] = mapped_column(
        String(32), default=Classification.UNCLASSIFIED.value, nullable=False
    )
    classification_confidence: Mapped[float | None] = mapped_column(Float)
    classification_reason: Mapped[str | None] = mapped_column(Text)

    raw: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    images: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    dedup_key: Mapped[str | None] = mapped_column(String(128), index=True)


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret: Mapped[str] = mapped_column(String(128), nullable=False)
    event: Mapped[str] = mapped_column(String(64), nullable=False, default="listing.created")
    filters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (Index("ix_webhook_deliveries_status", "status", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    listing_id: Mapped[int | None] = mapped_column(Integer)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
