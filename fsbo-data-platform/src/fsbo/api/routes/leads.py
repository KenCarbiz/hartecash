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


@router.get("/leads", response_model=list[LeadOut])
def list_leads(
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
    status: LeadStatus | None = None,
    assigned_to: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[LeadOut]:
    stmt = select(Lead).where(Lead.dealer_id == dealer_id)
    if status:
        stmt = stmt.where(Lead.status == status.value)
    if assigned_to:
        stmt = stmt.where(Lead.assigned_to == assigned_to)
    rows = db.scalars(
        stmt.order_by(Lead.updated_at.desc()).limit(limit).offset(offset)
    ).all()
    return [LeadOut.model_validate(r) for r in rows]


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
