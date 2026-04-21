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


def register_listing_identities(db: Session, listing) -> list[SellerIdentity]:
    """Extract every identifying signal we can from the listing and record
    it in the graph. Returns the list of identities linked."""
    identities: list[SellerIdentity] = []

    phone = normalize_phone(getattr(listing, "seller_phone", None))
    if phone:
        ident = upsert_identity(db, "phone", phone)
        if link_listing(db, listing.id, ident):
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
                    identities.append(ident)

    return identities


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
