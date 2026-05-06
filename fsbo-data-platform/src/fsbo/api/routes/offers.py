"""Seller-facing firm cash offers.

Dealer creates an offer with a 48-hour expiry + line-item deductions.
Server mints a public token; the dealer texts the seller a short link
(`https://app.../o/<token>`) which renders a clean, branded page with:

  - The number, big.
  - Each deduction itemized ("$300 off for the 2022 Carfax accident").
  - A countdown to expiry.
  - One-tap "Accept" / "Decline" buttons.

When the seller accepts, we close the loop: an Interaction is logged
on the lead, the lead status moves to `appointment` (the dealer side
gets pinged via the alerts worker), and the offer status becomes
`accepted`.

Dealer endpoints (auth-gated):
  POST /offers                     — create
  GET  /offers/by-lead/{lead_id}   — list a lead's offers
  POST /offers/{id}/withdraw       — pull back before the seller sees it

Public endpoints (NO auth — token-only):
  GET  /offers/public/{token}              — view (records seller_viewed_at)
  POST /offers/public/{token}/accept       — seller accepts
  POST /offers/public/{token}/decline      — seller declines
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.auth.resolver import DealerId
from fsbo.db import get_session
from fsbo.models import Interaction, InteractionKind, Lead, Listing, Offer

router = APIRouter(tags=["offers"])

DEFAULT_VALIDITY_HOURS = 48
MAX_VALIDITY_HOURS = 168  # 7 days, hard cap


# ---- Schemas ---------------------------------------------------------


class BreakdownLine(BaseModel):
    label: str = Field(..., max_length=128)
    amount_cents: int  # negative = deduction, positive = bump


class OfferIn(BaseModel):
    lead_id: int
    amount_cents: int = Field(..., gt=0)
    breakdown: list[BreakdownLine] = []
    notes: str | None = Field(None, max_length=1000)
    valid_hours: int = Field(DEFAULT_VALIDITY_HOURS, ge=1, le=MAX_VALIDITY_HOURS)


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_token: str
    lead_id: int
    listing_id: int
    amount_cents: int
    breakdown: list
    notes: str | None
    expires_at: datetime
    status: str
    seller_response_at: datetime | None
    seller_response_note: str | None
    seller_viewed_at: datetime | None
    created_at: datetime


class PublicOfferOut(BaseModel):
    """Trimmed view exposed to the seller via the public token. Hides
    dealer_id + lead_id (they're internal). Includes vehicle context
    so the offer page can show "your 2018 Honda Accord"."""

    public_token: str
    amount_cents: int
    breakdown: list
    notes: str | None
    expires_at: datetime
    expires_in_seconds: int
    status: str
    vehicle_label: str  # "2018 Honda Accord" / "your vehicle"
    dealer_name: str | None
    photos: list[str]


class SellerResponseIn(BaseModel):
    note: str | None = Field(None, max_length=1000)


# ---- Helpers ---------------------------------------------------------


def _vehicle_label(listing: Listing) -> str:
    bits = [str(listing.year) if listing.year else None, listing.make, listing.model]
    label = " ".join(b for b in bits if b)
    return label or "your vehicle"


def _resolve_dealer_name(db: Session, dealer_slug: str) -> str | None:
    from fsbo.models import Dealer

    row = db.scalar(select(Dealer).where(Dealer.slug == dealer_slug))
    return row.name if row else None


def _seconds_until(when: datetime) -> int:
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = when - datetime.now(timezone.utc)
    return max(0, int(delta.total_seconds()))


def _is_expired(offer: Offer) -> bool:
    if offer.status in ("accepted", "declined", "withdrawn"):
        return False
    expires = offer.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > expires


def _require_lead(db: Session, lead_id: int, dealer_id: str) -> Lead:
    lead = db.get(Lead, lead_id)
    if not lead or lead.dealer_id != dealer_id:
        raise HTTPException(404, "lead not found")
    return lead


# ---- Dealer endpoints ------------------------------------------------


@router.post("/offers", response_model=OfferOut, status_code=201)
def create_offer(
    payload: OfferIn,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> OfferOut:
    lead = _require_lead(db, payload.lead_id, dealer_id)
    listing = db.get(Listing, lead.listing_id)
    if not listing:
        raise HTTPException(404, "listing not found")

    expires = datetime.now(timezone.utc) + timedelta(hours=payload.valid_hours)
    offer = Offer(
        public_token=secrets.token_urlsafe(24),
        dealer_id=dealer_id,
        lead_id=lead.id,
        listing_id=lead.listing_id,
        amount_cents=payload.amount_cents,
        breakdown=[b.model_dump() for b in payload.breakdown],
        notes=payload.notes,
        expires_at=expires,
        status="pending",
    )
    db.add(offer)
    db.flush()

    # Log the offer creation on the lead's timeline.
    db.add(
        Interaction(
            lead_id=lead.id,
            kind=InteractionKind.NOTE.value,
            actor=dealer_id,
            body=(
                f"offer sent: ${payload.amount_cents / 100:,.0f} "
                f"(expires in {payload.valid_hours}h)"
            ),
        )
    )
    if lead.offered_price is None or lead.offered_price < payload.amount_cents / 100:
        lead.offered_price = payload.amount_cents / 100
    lead.updated_at = datetime.now(timezone.utc)
    db.flush()

    return OfferOut.model_validate(offer)


@router.get("/offers/by-lead/{lead_id}", response_model=list[OfferOut])
def list_offers_for_lead(
    lead_id: int,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> list[OfferOut]:
    _require_lead(db, lead_id, dealer_id)
    rows = db.scalars(
        select(Offer)
        .where(Offer.lead_id == lead_id, Offer.dealer_id == dealer_id)
        .order_by(Offer.created_at.desc())
    ).all()
    return [OfferOut.model_validate(r) for r in rows]


@router.post("/offers/{offer_id}/withdraw", response_model=OfferOut)
def withdraw_offer(
    offer_id: int,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> OfferOut:
    offer = db.get(Offer, offer_id)
    if not offer or offer.dealer_id != dealer_id:
        raise HTTPException(404, "offer not found")
    if offer.status != "pending":
        raise HTTPException(409, f"can't withdraw a {offer.status} offer")
    offer.status = "withdrawn"
    offer.updated_at = datetime.now(timezone.utc)
    db.add(
        Interaction(
            lead_id=offer.lead_id,
            kind=InteractionKind.NOTE.value,
            actor=dealer_id,
            body="offer withdrawn",
        )
    )
    db.flush()
    return OfferOut.model_validate(offer)


# ---- Public (seller) endpoints — NO AUTH ----------------------------


def _public_view(db: Session, offer: Offer) -> PublicOfferOut:
    listing = db.get(Listing, offer.listing_id)
    label = _vehicle_label(listing) if listing else "your vehicle"
    photos: list[str] = []
    if listing:
        # Prefer mirrored proxy URLs over the FB CDN ones (they expire).
        for idx, _ in enumerate(listing.mirrored_images or []):
            photos.append(f"/listings/{listing.id}/image/{idx}")
        if not photos:
            photos = list(listing.images or [])[:6]

    status = "expired" if _is_expired(offer) else offer.status
    return PublicOfferOut(
        public_token=offer.public_token,
        amount_cents=offer.amount_cents,
        breakdown=list(offer.breakdown or []),
        notes=offer.notes,
        expires_at=offer.expires_at,
        expires_in_seconds=_seconds_until(offer.expires_at),
        status=status,
        vehicle_label=label,
        dealer_name=_resolve_dealer_name(db, offer.dealer_id),
        photos=photos,
    )


@router.get("/offers/public/{token}", response_model=PublicOfferOut)
def public_get_offer(
    token: str, db: Annotated[Session, Depends(get_session)]
) -> PublicOfferOut:
    offer = db.scalar(select(Offer).where(Offer.public_token == token))
    if not offer:
        raise HTTPException(404, "offer not found")
    if offer.seller_viewed_at is None:
        offer.seller_viewed_at = datetime.now(timezone.utc)
        db.add(
            Interaction(
                lead_id=offer.lead_id,
                kind=InteractionKind.NOTE.value,
                actor="seller",
                body=f"viewed offer #{offer.id}",
            )
        )
        db.flush()
    return _public_view(db, offer)


@router.post(
    "/offers/public/{token}/accept", response_model=PublicOfferOut
)
def public_accept_offer(
    token: str,
    payload: SellerResponseIn,
    db: Annotated[Session, Depends(get_session)],
) -> PublicOfferOut:
    offer = db.scalar(select(Offer).where(Offer.public_token == token))
    if not offer:
        raise HTTPException(404, "offer not found")
    if _is_expired(offer):
        raise HTTPException(410, "offer expired")
    if offer.status != "pending":
        raise HTTPException(409, f"offer is already {offer.status}")

    offer.status = "accepted"
    offer.seller_response_at = datetime.now(timezone.utc)
    offer.seller_response_note = (payload.note or "")[:1000] or None

    # Move the lead to appointment status; log the acceptance.
    lead = db.get(Lead, offer.lead_id)
    if lead and lead.status not in ("purchased", "lost"):
        lead.status = "appointment"
        lead.updated_at = datetime.now(timezone.utc)
    db.add(
        Interaction(
            lead_id=offer.lead_id,
            kind=InteractionKind.STATUS_CHANGE.value,
            actor="seller",
            body=(
                f"offer #{offer.id} ACCEPTED · "
                f"${offer.amount_cents / 100:,.0f}"
                + (f" · note: {offer.seller_response_note}" if offer.seller_response_note else "")
            ),
        )
    )
    db.flush()
    return _public_view(db, offer)


@router.post(
    "/offers/public/{token}/decline", response_model=PublicOfferOut
)
def public_decline_offer(
    token: str,
    payload: SellerResponseIn,
    db: Annotated[Session, Depends(get_session)],
) -> PublicOfferOut:
    offer = db.scalar(select(Offer).where(Offer.public_token == token))
    if not offer:
        raise HTTPException(404, "offer not found")
    if _is_expired(offer):
        raise HTTPException(410, "offer expired")
    if offer.status != "pending":
        raise HTTPException(409, f"offer is already {offer.status}")

    offer.status = "declined"
    offer.seller_response_at = datetime.now(timezone.utc)
    offer.seller_response_note = (payload.note or "")[:1000] or None
    db.add(
        Interaction(
            lead_id=offer.lead_id,
            kind=InteractionKind.NOTE.value,
            actor="seller",
            body=(
                f"offer #{offer.id} DECLINED"
                + (f" · note: {offer.seller_response_note}" if offer.seller_response_note else "")
            ),
        )
    )
    db.flush()
    return _public_view(db, offer)
