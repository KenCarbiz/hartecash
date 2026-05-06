"""Seller identity graph — cluster listings that share identifying signals.

A curbstoner running multiple Facebook Marketplace profiles typically
reuses at least one of:
  * phone number (already tracked in phone_graph.py)
  * email address (surfaces in contact-fields or extension-captured DMs)
  * image background perceptual hash (same driveway / garage / lot
    appearing on multiple listings — huge tell)
  * EXIF GPS clustered within ~50m

This module maintains the SellerIdentity + SellerIdentityLink tables.
Each identifier is a node; a listing references 0-N identifiers; the
listing_count on an identifier is the component size used by the
quality scorer.

Thresholds (wired in quality.py):
  listing_count >= 10 -> auto-hide (hard curbstoner)
  listing_count  5- 9 -> -15 points
  listing_count  3- 4 -> -8 points
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.enrichment.posting_hour import (
    hour_of_week_slot,
    posting_pattern_signal,
    summarize_histogram,
)
from fsbo.models import SellerIdentity, SellerIdentityLink

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")


def normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def extract_emails(text: str | None) -> list[str]:
    if not text:
        return []
    return [m.group(0).lower() for m in EMAIL_RE.finditer(text)]


def upsert_identity(db: Session, kind: str, value: str) -> SellerIdentity:
    """Fetch-or-create a SellerIdentity row, bumping last_seen_at."""
    now = datetime.now(timezone.utc)
    existing = db.scalar(
        select(SellerIdentity).where(
            SellerIdentity.kind == kind, SellerIdentity.value == value
        )
    )
    if existing:
        existing.last_seen_at = now
        return existing
    row = SellerIdentity(kind=kind, value=value, listing_count=0)
    db.add(row)
    db.flush()
    return row


def link_listing(db: Session, listing_id: int, identity: SellerIdentity) -> bool:
    """Link a listing to an identity if not already linked. Returns True if
    this is a new link."""
    existing = db.scalar(
        select(SellerIdentityLink).where(
            SellerIdentityLink.listing_id == listing_id,
            SellerIdentityLink.identity_id == identity.id,
        )
    )
    if existing:
        return False
    db.add(
        SellerIdentityLink(listing_id=listing_id, identity_id=identity.id)
    )
    identity.listing_count = (identity.listing_count or 0) + 1
    return True


def _bump_histogram(ident: SellerIdentity, listing) -> None:
    """Increment the ident's hour-of-week histogram for this listing's
    posting timestamp."""
    slot = hour_of_week_slot(
        getattr(listing, "posted_at", None)
        or getattr(listing, "first_seen_at", None)
    )
    if slot is None:
        return
    # JSON dicts store int keys as strings once persisted; normalize up-front.
    hist = dict(ident.hour_histogram or {})
    key = str(slot)
    hist[key] = int(hist.get(key, 0)) + 1
    ident.hour_histogram = hist


def normalize_plate(plate: str | None) -> str:
    """Plates as stored: uppercase alphanumeric only, max 10 chars.
    Strips spaces / hyphens / state prefixes so '7GTF 123' and
    '7GTF-123' collapse to the same identity."""
    if not plate:
        return ""
    cleaned = "".join(c for c in plate.upper() if c.isalnum())
    return cleaned[:10]


def register_listing_identities(db: Session, listing) -> list[SellerIdentity]:
    """Extract every identifying signal we can from the listing and record
    it in the graph. Returns the list of identities linked."""
    identities: list[SellerIdentity] = []

    phone = normalize_phone(getattr(listing, "seller_phone", None))
    if phone:
        ident = upsert_identity(db, "phone", phone)
        if link_listing(db, listing.id, ident):
            _bump_histogram(ident, listing)
            identities.append(ident)

    # License plate — same plate across multiple listings under
    # different sellers is a stronger curbstoner signal than even
    # phone (curbstoners change phones easily; the plate sticks with
    # the car). State + plate is the natural key, but we collapse on
    # plate alone since cross-state plate matches are vanishingly
    # rare false positives.
    plate = normalize_plate(getattr(listing, "license_plate", None))
    if plate and len(plate) >= 4:
        ident = upsert_identity(db, "plate", plate)
        if link_listing(db, listing.id, ident):
            _bump_histogram(ident, listing)
            identities.append(ident)

    blob = " ".join(
        filter(
            None,
            [
                getattr(listing, "title", None),
                getattr(listing, "description", None),
            ],
        )
    )
    for email in extract_emails(blob):
        ident = upsert_identity(db, "email", email)
        if link_listing(db, listing.id, ident):
            _bump_histogram(ident, listing)
            identities.append(ident)

    # Image-background phashes flow in from the Chrome extension or a
    # dedicated image-processing worker. We accept pre-computed hashes
    # passed via listing.raw["image_bg_phashes"]: list[str].
    raw = getattr(listing, "raw", {}) or {}
    phashes = raw.get("image_bg_phashes") if isinstance(raw, dict) else None
    if isinstance(phashes, list):
        for ph in phashes:
            if isinstance(ph, str) and len(ph) >= 8:
                ident = upsert_identity(db, "image_phash", ph.lower())
                if link_listing(db, listing.id, ident):
                    _bump_histogram(ident, listing)
                    identities.append(ident)

    return identities


def max_posting_hour_signal(db: Session, listing_id: int) -> int:
    """Return the best (most negative) posting-hour signal across all
    identities this listing is linked to.

    Negative = dealer/day-job pattern; positive = authentic private
    seller pattern; 0 = no signal.
    """
    idents = db.scalars(
        select(SellerIdentity)
        .join(
            SellerIdentityLink,
            SellerIdentityLink.identity_id == SellerIdentity.id,
        )
        .where(SellerIdentityLink.listing_id == listing_id)
    ).all()

    best = 0  # most negative wins; positive signals only used when no negative
    any_positive = False
    for ident in idents:
        # JSON keys come back as strings; convert to int slots.
        hist = {int(k): int(v) for k, v in (ident.hour_histogram or {}).items()}
        summary = summarize_histogram(hist)
        signal = posting_pattern_signal(summary)
        if signal < best:
            best = signal
        if signal > 0:
            any_positive = True
    if best < 0:
        return best
    return 2 if any_positive else 0


def max_component_size(
    db: Session, listing_id: int, exclude_self: bool = True
) -> int:
    """Return the size of the largest identity cluster this listing
    belongs to, excluding this listing itself from the count."""
    idents = db.scalars(
        select(SellerIdentity)
        .join(
            SellerIdentityLink,
            SellerIdentityLink.identity_id == SellerIdentity.id,
        )
        .where(SellerIdentityLink.listing_id == listing_id)
    ).all()
    if not idents:
        return 0
    best = max(i.listing_count for i in idents)
    if exclude_self:
        best = max(0, best - 1)
    return best


def find_corpus_vin_for_plate(
    db: Session, plate: str, exclude_listing_id: int | None = None
) -> str | None:
    """When the plate-vision OCR catches a plate, search OUR own
    historical corpus for any other listing with the same plate that
    has a verified VIN. If we find one, that's effectively a free
    plate->VIN lookup (the OG listing already had the VIN).

    Returns the most-recently-seen VIN for the plate, or None.
    """
    from fsbo.models import Listing

    norm = normalize_plate(plate)
    if not norm or len(norm) < 4:
        return None

    # Most stored plates have already been uppercased by the ingest
    # path so the cheap path covers most cases. We can't push
    # normalize_plate into SQL (cross-DB compatibility), but the
    # limit + index on license_plate keeps the loop bounded.
    stmt = (
        select(Listing.vin, Listing.license_plate)
        .where(Listing.vin.is_not(None))
        .where(Listing.license_plate.is_not(None))
    )
    if exclude_listing_id is not None:
        stmt = stmt.where(Listing.id != exclude_listing_id)
    stmt = stmt.order_by(Listing.last_seen_at.desc()).limit(50)

    for vin, plate_value in db.execute(stmt).all():
        if normalize_plate(plate_value) == norm and vin:
            return vin
    return None


def count_listings_sharing_plate(
    db: Session, plate: str, exclude_listing_id: int | None = None
) -> int:
    """How many other listings in the corpus share this plate?
    Used by the curbstoner scorer (a plate on 3+ listings under
    different sellers is almost always a curbstoner)."""
    from fsbo.models import Listing

    norm = normalize_plate(plate)
    if not norm or len(norm) < 4:
        return 0

    stmt = select(Listing.id, Listing.license_plate).where(
        Listing.license_plate.is_not(None)
    )
    if exclude_listing_id is not None:
        stmt = stmt.where(Listing.id != exclude_listing_id)

    count = 0
    for _, plate_v in db.execute(stmt.limit(500)).all():
        if normalize_plate(plate_v) == norm:
            count += 1
    return count
