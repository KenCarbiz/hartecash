from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
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
        # Default /listings query is "classification = private_seller AND
        # NOT auto_hidden ORDER BY posted_at DESC". A composite index on
        # the leading two filters + the order column lets Postgres serve
        # page 1 from an index scan once the corpus crosses ~50k rows.
        Index(
            "ix_listings_default_feed",
            "classification",
            "auto_hidden",
            "posted_at",
        ),
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
    # License plate (captured via extension OCR or dealer manual entry).
    # Index supports cross-listing dedup lookups when two listings share
    # a plate — a common curbstoner tell.
    license_plate: Mapped[str | None] = mapped_column(String(16), index=True)
    license_plate_state: Mapped[str | None] = mapped_column(String(4))
    color: Mapped[str | None] = mapped_column(String(32))
    # True = runs/drives, False = won't run (parts/project car), None = unknown.
    drivable: Mapped[bool | None] = mapped_column(Boolean)
    # Sold signal: when the seller explicitly tells us via SMS/voice/etc
    # that the vehicle has been sold to someone else, we stamp the time
    # and the verbatim quote. Auto-hides the listing from feeds.
    sold_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    sold_signal: Mapped[str | None] = mapped_column(String(256))
    # Storage keys (relative paths under FSBO_MEDIA_ROOT) for photos we
    # mirrored from sources whose URLs expire (FB CDN). Served via the
    # /listings/{id}/image/{idx} proxy. Empty list = nothing mirrored.
    mirrored_images: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Vision-derived condition assessment from Claude Haiku 4.5. Schema
    # in fsbo.enrichment.condition_vision.ConditionAssessment. Empty
    # dict means "not yet assessed" (assessment may run async after
    # ingest).
    condition: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Cached vehicle-history report (CARFAX / AutoCheck / NMVTIS).
    # Schema in fsbo.history.types.HistoryReport. Empty dict = not
    # fetched yet. Refreshed on demand via the /listings/{id}/history
    # endpoint; cache key is VIN, so re-fetching is cheap.
    history_report: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False
    )
    history_report_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    city: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(8))
    zip_code: Mapped[str | None] = mapped_column(String(16))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    seller_name: Mapped[str | None] = mapped_column(String(256))
    seller_phone: Mapped[str | None] = mapped_column(String(32), index=True)
    seller_email: Mapped[str | None] = mapped_column(String(256), index=True)
    # Marketplace-specific seller signals. profile_url + joined_year are
    # FB-Marketplace specifics that feed the curbstoner scorer; both are
    # optional and may be null for non-FB sources.
    seller_profile_url: Mapped[str | None] = mapped_column(Text)
    seller_joined_year: Mapped[int | None] = mapped_column(Integer)

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
    __table_args__ = (
        Index("ix_webhook_subs_dealer_event", "dealer_id", "event", "active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Dealer that owns the subscription. Events fire only for resources
    # in this dealer's scope; listing.created fires globally because
    # the corpus is shared, but lead/offer/voice events are dealer-scoped.
    dealer_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, default=""
    )
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
    # Stripe billing — denormalized onto Dealer because there's exactly
    # one customer per dealership. Subscription state lives on the
    # separate Subscription row so we can keep history of plan changes
    # + cancellations + reactivations without losing the customer link.
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True
    )
    # Lead-routing config. routing_mode="manual" (default) leaves
    # Lead.assigned_to alone; "least_loaded" auto-assigns new leads
    # to the rep in routing_pool with the fewest active leads. Pool
    # is a list of free-text handles (no User-table dependency).
    routing_mode: Mapped[str] = mapped_column(
        String(16), default="manual", nullable=False
    )
    routing_pool: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False
    )
    # Multi-rooftop: dealers sharing a group_id roll up into a single
    # GM dashboard via /analytics/group-funnel. Nullable — most
    # dealers are independent.
    group_id: Mapped[int | None] = mapped_column(Integer, index=True)


class DealerGroup(Base):
    """A franchise group / multi-rooftop owner. Each member Dealer
    keeps its own listings + leads + users + billing; the group
    layer is purely for cohort analytics.

    Membership is denormalized: every Dealer.group_id pointing at this
    DealerGroup is a member. Owner_dealer_id is the slug of the dealer
    that created the group; today only the owner can add/remove
    members. Richer permissions later.
    """

    __tablename__ = "dealer_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    owner_dealer_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Subscription(Base):
    """A dealer's active (or recently-canceled) Stripe subscription.

    One row per (dealer, stripe_subscription_id). When a dealer
    upgrades/downgrades, Stripe issues a new sub id; we keep the old
    row for audit but trust `Subscription.is_active=False + new active
    row` as the source of truth. Resolved from /billing endpoints by
    most-recent active row per dealer.

    Status mirrors Stripe's enum: trialing, active, past_due, canceled,
    unpaid, incomplete, incomplete_expired.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_dealer_active", "dealer_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dealer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stripe_subscription_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    stripe_customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    plan: Mapped[str] = mapped_column(String(32), nullable=False)  # starter | pro | performance
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
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


class NotificationDelivery(Base):
    """Dedup log: one row per (user, listing, kind) so we don't email a
    user twice about the same lead."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "listing_id", "kind", name="uq_notif_user_listing_kind"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    listing_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


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

    # Notification preferences (see workers/lead_alerts_worker.py).
    alerts_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    alert_min_score: Mapped[int] = mapped_column(Integer, default=80, nullable=False)


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


class ZipGeocode(Base):
    """Cached ZIP -> lat/long row. Geocoding is read-heavy and the
    answer never changes; on cache miss we hit the Census Geocoder
    (free, no API key) and persist the result. The 20-ZIP hot-path
    in fsbo.enrichment.geocode._FALLBACK_ZIPS lets dev/CI work
    without ever touching the network or DB."""

    __tablename__ = "zip_geocodes"

    zip_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(
        String(16), default="census", nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ExtensionInstallCode(Base):
    """Short-lived single-use code that an extension exchanges for an
    API key without ever asking the dealer to copy/paste a long token.

    Flow:
      1. Logged-in dealer hits POST /extension/install-code → server
         generates an 8-char base32 code, stores its sha256 hash with
         a 10-minute TTL, returns the plaintext code to the dashboard.
      2. Extension popup shows a code input. Dealer pastes the code.
      3. Popup POSTs to /extension/exchange-install-code (no auth);
         server looks up the hash, marks it used, mints a fresh ApiKey
         for that dealer, returns the token + dealer_id.

    We never store the plaintext code, and the code is single-use to
    keep the brute-force window small (still rate-limit the exchange
    endpoint at the proxy/CDN layer).
    """

    __tablename__ = "extension_install_codes"
    __table_args__ = (
        Index("ix_install_codes_hash", "code_hash", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dealer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    issued_by_user_id: Mapped[int | None] = mapped_column(Integer)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    """Outbound / inbound message tied to a lead. Originally just SMS
    (wrapping Twilio's Message resource); now also covers email when
    channel="email"."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_lead", "lead_id"),
        Index("ix_messages_twilio_sid", "twilio_sid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dealer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lead_id: Mapped[int | None] = mapped_column(Integer)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    # "sms" (default) | "email". Distinguishes the transport so the
    # unified feed can render different glyphs and the dashboard can
    # filter to one channel.
    channel: Mapped[str] = mapped_column(
        String(16), default="sms", nullable=False
    )
    # SMS leg
    from_number: Mapped[str | None] = mapped_column(String(32))
    to_number: Mapped[str | None] = mapped_column(String(32))
    # Email leg (null for SMS rows)
    from_email: Mapped[str | None] = mapped_column(String(256))
    to_email: Mapped[str | None] = mapped_column(String(256))
    subject: Mapped[str | None] = mapped_column(String(256))
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
    # Soft-delete: rows stay in the DB so the audit trail survives.
    # Filtered out of every query unless the caller explicitly asks for
    # archived rows. Restorable for 30 days; a separate sweeper hard-
    # deletes after that.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    deleted_by: Mapped[str | None] = mapped_column(String(255))
    delete_reason: Mapped[str | None] = mapped_column(String(256))
    # AI-extracted structured intake from voice + SMS conversations.
    # Schema in fsbo.voice.intake.SellerIntake. Empty dict = nothing
    # extracted yet. Updates accumulate (later calls overwrite missing
    # fields, never erase known ones).
    seller_intake: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Timestamp of the first outbound contact on this lead (SMS, email,
    # voice call, or status change to 'contacted'). Stamped once and
    # never updated. Powers per-lead response-SLA reporting + manager
    # coaching ("rep took 3 hours to first-touch this lead").
    first_responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )


class Offer(Base):
    """A dealer's firm cash offer to a seller, with a public token the
    seller can use to view + accept on a clean, branded page (no
    login required).

    The contrarian wedge: every other tool in this category is built
    dealer-side. The seller-facing surface here gives the seller a
    transparent, trackable offer with line-item deductions ("$300 off
    for the 2022 Carfax accident"), a countdown to expiry, and a
    one-tap accept button. Sellers who *understand* the offer accept
    it 2-3x more often.
    """

    __tablename__ = "offers"
    __table_args__ = (
        Index("ix_offers_lead_created", "lead_id", "created_at"),
        Index("ix_offers_dealer_id", "dealer_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    dealer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    lead_id: Mapped[int] = mapped_column(Integer, nullable=False)
    listing_id: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    # Line-item deductions: each entry is
    # {"label": "Carfax accident 2022", "amount_cents": -30000}
    # Positive entries are bumps (e.g. "Records bonus"); negatives are
    # deductions. The dashboard / seller page render them line by line
    # so the offer is explainable.
    breakdown: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # State machine: "pending" -> "accepted" | "declined" | "expired" | "withdrawn"
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False, index=True
    )
    seller_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    seller_response_note: Mapped[str | None] = mapped_column(Text)
    seller_viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VoiceCall(Base):
    """One row per outbound voice call to a seller.

    Twilio assigns a call_sid; we track it from initiation through
    completion, accumulating speech turns + the final structured
    extract. Multiple calls per lead are allowed (callbacks, retries).
    """

    __tablename__ = "voice_calls"
    __table_args__ = (
        Index("ix_voice_calls_lead_created", "lead_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(Integer, nullable=False)
    dealer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    twilio_call_sid: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True
    )
    direction: Mapped[str] = mapped_column(String(16), default="outbound")
    to_number: Mapped[str] = mapped_column(String(32), nullable=False)
    from_number: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    # Each turn is {"role": "ai"|"seller", "text": "...", "at": iso8601}.
    # Stored as a JSON list so we can rebuild the conversation for the
    # extractor without a separate VoiceTurn table.
    turns: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    intake: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
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


class SmsOptOut(Base):
    """A phone number that has opted out of SMS contact, plus when +
    why. Federal TCPA + state mini-TCPA require honoring STOP within
    24 hours; we honor immediately and audit. One row per
    (dealer_id, phone) so a number can opt out of one dealership but
    not another (rare; mostly we treat opt-out as global per number,
    but the dealer-scope leaves room for compliance carve-outs).
    """

    __tablename__ = "sms_opt_outs"
    __table_args__ = (
        UniqueConstraint("dealer_id", "phone", name="uq_optout_dealer_phone"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dealer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    # ^ "stop_keyword" | "manual" | "carrier_unsubscribed" | "regulatory"
    note: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SmsConsent(Base):
    """Affirmative consent record. The dealer captures a yes/no
    response from the seller before the FIRST outbound SMS; the
    timestamp + the verbatim consent language proves we had standing
    consent at the time of the send. Supports class-action defense.
    """

    __tablename__ = "sms_consents"
    __table_args__ = (
        UniqueConstraint(
            "dealer_id", "phone", name="uq_consent_dealer_phone"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dealer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # The exact text the seller saw / agreed to. Stored verbatim, not
    # template-keyed, because the legal artifact is the wording at the
    # moment of consent.
    consent_text: Mapped[str] = mapped_column(Text, nullable=False)
    captured_via: Mapped[str] = mapped_column(String(32), nullable=False)
    # ^ "double_opt_in_sms" | "web_form" | "in_person" | "marketplace_dm"
    captured_by_user: Mapped[str | None] = mapped_column(String(255))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
