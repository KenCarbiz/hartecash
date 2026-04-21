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


class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    NEGOTIATING = "negotiating"
    APPOINTMENT = "appointment"
    PURCHASED = "purchased"
    LOST = "lost"


class InteractionKind(StrEnum):
    NOTE = "note"
    CALL = "call"
    TEXT = "text"
    EMAIL = "email"
    TASK = "task"
    STATUS_CHANGE = "status_change"


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

    # Research-informed scoring fields.
    # Raw likelihood output from the dealer classifier (0..1). Separate from
    # `classification` because the label can be overridden but the score is
    # always the raw signal aggregate.
    dealer_likelihood: Mapped[float | None] = mapped_column(Float)
    scam_score: Mapped[float | None] = mapped_column(Float)
    lead_quality_score: Mapped[int | None] = mapped_column(Integer, index=True)
    quality_breakdown: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Hard-reject gate. When True the listing is excluded from the default
    # /listings view; still accessible via explicit ?show_hidden=true.
    auto_hidden: Mapped[bool] = mapped_column(default=False, nullable=False)
    auto_hide_reason: Mapped[str | None] = mapped_column(String(64))


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


class SellerIdentity(Base):
    """A node in the curbstoner-detection graph.

    Each row is one identifier extracted from a listing (phone number,
    email, image-background perceptual hash). A seller_identity with
    listing_count >= 10 is a near-certain curbstoner cluster — use the
    auto-hide rules to suppress those listings from the dealer feed.
    """

    __tablename__ = "seller_identities"
    __table_args__ = (
        UniqueConstraint("kind", "value", name="uq_seller_identity_kind_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    listing_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 168-slot posting-hour histogram: {slot: count} where slot = weekday*24 + hour.
    hour_histogram: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SellerIdentityLink(Base):
    """Join: listing ↔ seller identity. One listing can reference several
    identities (phone + email + image hash)."""

    __tablename__ = "seller_identity_links"
    __table_args__ = (
        UniqueConstraint(
            "listing_id", "identity_id", name="uq_seller_identity_link"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    identity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Dealer(Base):
    """Organization that owns listings, leads, API keys, users. The dealer_id
    string on every scoped row references Dealer.slug (not Dealer.id) so
    existing rows with 'demo-dealer' don't have to migrate."""

    __tablename__ = "dealers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PasswordResetToken(Base):
    """One-time password-reset link. Created by POST /auth/forgot; valid
    for 1 hour; marked used_at on first consumption."""

    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index("ix_password_reset_tokens_token_hash", "token_hash", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invitation(Base):
    """One-time sign-up link for adding teammates to an existing dealer.

    `token_hash` stores SHA-256 of the raw token. The raw token is
    returned only once at creation, same pattern as API keys. Admins
    can revoke; expired or revoked invites can't be accepted.
    """

    __tablename__ = "invitations"
    __table_args__ = (
        Index("ix_invitations_token_hash", "token_hash", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dealer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="member", nullable=False)
    invited_by: Mapped[int] = mapped_column(Integer, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class User(Base):
    """A person who logs in. Belongs to one dealer. Password is bcrypt-hashed."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    name: Mapped[str | None] = mapped_column(String(256))
    dealer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), default="member", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiKey(Base):
    """Dealer-scoped API key. Used by the browser extension and any other
    programmatic integrations. The token is stored as a SHA-256 hash; only
    the prefix is retained in plaintext for UX ("ac_live_abc…")."""

    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_api_keys_token_hash", "token_hash", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dealer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    """Outbound/inbound SMS tied to a lead. Wraps Twilio's Message resource."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_lead", "lead_id"),
        Index("ix_messages_twilio_sid", "twilio_sid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dealer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lead_id: Mapped[int | None] = mapped_column(Integer)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    from_number: Mapped[str | None] = mapped_column(String(32))
    to_number: Mapped[str | None] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(32))
    twilio_sid: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PriceHistory(Base):
    """Log every price change we observe on a listing. Drops = motivation signal;
    increases = owner correcting a mistake."""

    __tablename__ = "price_history"
    __table_args__ = (Index("ix_price_history_listing_time", "listing_id", "observed_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    delta: Mapped[float | None] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Lead(Base):
    """A dealer's claim on a listing. One listing can have multiple leads if
    multiple dealers work the same seller, but within a single dealer
    (dealer_id), a listing has at most one lead."""

    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("dealer_id", "listing_id", name="uq_lead_dealer_listing"),
        Index("ix_leads_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dealer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    listing_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default=LeadStatus.NEW.value, nullable=False)
    offered_price: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Interaction(Base):
    """Log entry on a lead: calls, texts, notes, tasks, status changes."""

    __tablename__ = "interactions"
    __table_args__ = (Index("ix_interactions_lead_created", "lead_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str | None] = mapped_column(String(16))  # outbound | inbound
    actor: Mapped[str | None] = mapped_column(String(128))
    body: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SavedSearch(Base):
    """Dealer-scoped saved filter set for quickly re-running + alerting on."""

    __tablename__ = "saved_searches"
    __table_args__ = (
        UniqueConstraint("dealer_id", "name", name="uq_search_dealer_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dealer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    query: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    alerts_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MessageTemplate(Base):
    """Reusable outreach message, scoped to a dealer. Supports {{placeholders}}
    that get filled from the listing context when rendered.

    Known placeholders:
      {{year}} {{make}} {{model}} {{trim}} {{price}} {{mileage}}
      {{city}} {{state}} {{vin}}
    """

    __tablename__ = "message_templates"
    __table_args__ = (
        UniqueConstraint("dealer_id", "name", name="uq_template_dealer_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dealer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(
        String(32), nullable=False, default="outreach"
    )  # outreach | vin_request | offer | follow_up | custom
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DailyActivity(Base):
    """Daily per-user activity totals for the battle tracker."""

    __tablename__ = "daily_activity"
    __table_args__ = (
        UniqueConstraint("dealer_id", "user_id", "date", name="uq_activity_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dealer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    messages_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    calls_made: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    offers_made: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    appointments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    purchases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goal_messages: Mapped[int] = mapped_column(Integer, default=60, nullable=False)


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
