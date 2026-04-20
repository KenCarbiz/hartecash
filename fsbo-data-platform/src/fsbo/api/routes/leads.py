"""Lead + interaction CRM endpoints.

Dealer scoping: every endpoint takes an X-Dealer-Id header (stubbed auth).
Real auth will replace this header with JWT-derived dealer context later.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from fsbo.db import get_session
from fsbo.models import (
    InteractionKind,
    Interaction,
    Lead,
    LeadStatus,
    Listing,
)

router = APIRouter(tags=["crm"])


DealerIdHeader = Annotated[str, Header(alias="X-Dealer-Id")]


class LeadIn(BaseModel):
    listing_id: int
    assigned_to: str | None = None
    notes: str | None = None


class LeadPatch(BaseModel):
    assigned_to: str | None = None
    status: LeadStatus | None = None
    offered_price: float | None = None
    notes: str | None = None


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dealer_id: str
    listing_id: int
    assigned_to: str | None
    status: str
    offered_price: float | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class LeadWithListing(LeadOut):
    listing_title: str | None
    listing_year: int | None
    listing_make: str | None
    listing_model: str | None
    listing_price: float | None
    listing_mileage: int | None
    listing_city: str | None
    listing_state: str | None
    listing_zip: str | None
    listing_source: str


class InteractionIn(BaseModel):
    kind: InteractionKind
    body: str | None = None
    direction: str | None = None
    due_at: datetime | None = None
    meta: dict = {}


class InteractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_id: int
    kind: str
    direction: str | None
    actor: str | None
    body: str | None
    due_at: datetime | None
    completed_at: datetime | None
    meta: dict
    created_at: datetime


# ---------- lead endpoints ----------


@router.post("/leads", response_model=LeadOut, status_code=201)
def create_lead(
    payload: LeadIn,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> LeadOut:
    if not db.get(Listing, payload.listing_id):
        raise HTTPException(404, "listing not found")

    existing = db.scalar(
        select(Lead).where(
            and_(Lead.dealer_id == dealer_id, Lead.listing_id == payload.listing_id)
        )
    )
    if existing:
        return LeadOut.model_validate(existing)

    lead = Lead(
        dealer_id=dealer_id,
        listing_id=payload.listing_id,
        assigned_to=payload.assigned_to,
        notes=payload.notes,
    )
    db.add(lead)
    db.flush()
    return LeadOut.model_validate(lead)


class BulkClaimIn(BaseModel):
    listing_ids: list[int]
    assigned_to: str | None = None


class BulkClaimOut(BaseModel):
    claimed: int
    already_claimed: int
    missing_listings: list[int]


@router.post("/leads/bulk-claim", response_model=BulkClaimOut)
def bulk_claim(
    payload: BulkClaimIn,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> BulkClaimOut:
    if not payload.listing_ids:
        return BulkClaimOut(claimed=0, already_claimed=0, missing_listings=[])

    ids = list({*payload.listing_ids})[:200]  # cap per request

    found_ids = set(
        db.scalars(select(Listing.id).where(Listing.id.in_(ids))).all()
    )
    missing = [i for i in ids if i not in found_ids]

    already = set(
        db.scalars(
            select(Lead.listing_id).where(
                Lead.dealer_id == dealer_id, Lead.listing_id.in_(found_ids)
            )
        ).all()
    )
    to_claim = found_ids - already
    for listing_id in to_claim:
        db.add(
            Lead(
                dealer_id=dealer_id,
                listing_id=listing_id,
                assigned_to=payload.assigned_to,
            )
        )
    db.flush()

    return BulkClaimOut(
        claimed=len(to_claim),
        already_claimed=len(already),
        missing_listings=missing,
    )


@router.get("/leads", response_model=list[LeadWithListing])
def list_leads(
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
    status: LeadStatus | None = None,
    assigned_to: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[LeadWithListing]:
    stmt = (
        select(Lead, Listing)
        .join(Listing, Lead.listing_id == Listing.id)
        .where(Lead.dealer_id == dealer_id)
    )
    if status:
        stmt = stmt.where(Lead.status == status.value)
    if assigned_to:
        stmt = stmt.where(Lead.assigned_to == assigned_to)
    rows = db.execute(
        stmt.order_by(Lead.updated_at.desc()).limit(limit).offset(offset)
    ).all()

    return [
        LeadWithListing(
            id=lead.id,
            dealer_id=lead.dealer_id,
            listing_id=lead.listing_id,
            assigned_to=lead.assigned_to,
            status=lead.status,
            offered_price=lead.offered_price,
            notes=lead.notes,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
            listing_title=listing.title,
            listing_year=listing.year,
            listing_make=listing.make,
            listing_model=listing.model,
            listing_price=listing.price,
            listing_mileage=listing.mileage,
            listing_city=listing.city,
            listing_state=listing.state,
            listing_zip=listing.zip_code,
            listing_source=listing.source,
        )
        for lead, listing in rows
    ]


@router.get("/leads/by-listing/{listing_id}", response_model=LeadOut | None)
def get_lead_by_listing(
    listing_id: int,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> LeadOut | None:
    lead = db.scalar(
        select(Lead).where(
            and_(Lead.dealer_id == dealer_id, Lead.listing_id == listing_id)
        )
    )
    return LeadOut.model_validate(lead) if lead else None


@router.get("/leads/{lead_id}", response_model=LeadOut)
def get_lead(
    lead_id: int,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> LeadOut:
    lead = _require_lead(db, lead_id, dealer_id)
    return LeadOut.model_validate(lead)


@router.patch("/leads/{lead_id}", response_model=LeadOut)
def update_lead(
    lead_id: int,
    payload: LeadPatch,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> LeadOut:
    lead = _require_lead(db, lead_id, dealer_id)

    status_changed = False
    if payload.status is not None and payload.status.value != lead.status:
        prev = lead.status
        lead.status = payload.status.value
        status_changed = True
        db.add(
            Interaction(
                lead_id=lead.id,
                kind=InteractionKind.STATUS_CHANGE.value,
                body=f"{prev} → {lead.status}",
                actor=payload.assigned_to or lead.assigned_to,
            )
        )
    if payload.assigned_to is not None:
        lead.assigned_to = payload.assigned_to
    if payload.offered_price is not None:
        lead.offered_price = payload.offered_price
    if payload.notes is not None:
        lead.notes = payload.notes
    lead.updated_at = datetime.now(timezone.utc)

    _ = status_changed  # reserved for future webhook: lead.status_changed
    return LeadOut.model_validate(lead)


# ---------- interaction endpoints ----------


@router.post("/leads/{lead_id}/interactions", response_model=InteractionOut, status_code=201)
def create_interaction(
    lead_id: int,
    payload: InteractionIn,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> InteractionOut:
    lead = _require_lead(db, lead_id, dealer_id)
    interaction = Interaction(
        lead_id=lead.id,
        kind=payload.kind.value,
        direction=payload.direction,
        body=payload.body,
        due_at=payload.due_at,
        meta=payload.meta,
    )
    db.add(interaction)
    lead.updated_at = datetime.now(timezone.utc)
    db.flush()
    return InteractionOut.model_validate(interaction)


@router.get("/leads/{lead_id}/interactions", response_model=list[InteractionOut])
def list_interactions(
    lead_id: int,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> list[InteractionOut]:
    _require_lead(db, lead_id, dealer_id)
    rows = db.scalars(
        select(Interaction)
        .where(Interaction.lead_id == lead_id)
        .order_by(Interaction.created_at.desc())
    ).all()
    return [InteractionOut.model_validate(r) for r in rows]


@router.post(
    "/leads/{lead_id}/interactions/{interaction_id}/complete",
    response_model=InteractionOut,
)
def complete_interaction(
    lead_id: int,
    interaction_id: int,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> InteractionOut:
    _require_lead(db, lead_id, dealer_id)
    row = db.get(Interaction, interaction_id)
    if not row or row.lead_id != lead_id:
        raise HTTPException(404, "interaction not found")
    row.completed_at = datetime.now(timezone.utc)
    return InteractionOut.model_validate(row)


def _require_lead(db: Session, lead_id: int, dealer_id: str) -> Lead:
    lead = db.get(Lead, lead_id)
    if not lead or lead.dealer_id != dealer_id:
        raise HTTPException(404, "lead not found")
    return lead
