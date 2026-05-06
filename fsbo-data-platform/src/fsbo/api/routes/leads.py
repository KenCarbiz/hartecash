"""Lead + interaction CRM endpoints.

Dealer scoping: every endpoint resolves dealer_id via the auth resolver
(session cookie → API token → dev-only header). Raw X-Dealer-Id headers
are rejected in production.
"""

import csv
import io
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from fsbo.auth.resolver import DealerId
from fsbo.db import get_session
from fsbo.models import (
    InteractionKind,
    Interaction,
    Lead,
    LeadStatus,
    Listing,
    User,
)

router = APIRouter(tags=["crm"])


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
    dealer_id: DealerId,
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

    # Auto-assign via routing config when the caller didn't pick a rep.
    assigned_to = payload.assigned_to
    if assigned_to is None:
        from fsbo.api.routes.routing import assign_next

        assigned_to = assign_next(db, dealer_id)

    lead = Lead(
        dealer_id=dealer_id,
        listing_id=payload.listing_id,
        assigned_to=assigned_to,
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
    dealer_id: DealerId,
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
    # Auto-route bulk claims when the caller didn't pin assigned_to.
    # We look up the routing config once + assign each new lead to the
    # currently-least-loaded rep, refreshing the count after each
    # assignment so a 50-listing bulk claim distributes evenly across
    # the pool instead of dumping all 50 on the same person.
    use_routing = payload.assigned_to is None
    routing_loads: dict[str, int] = {}
    routing_pool: list[str] = []
    if use_routing:
        from fsbo.api.routes.routing import (
            ACTIVE_STATUSES,
            LOAD_WINDOW_DAYS,
        )
        from fsbo.models import Dealer

        dealer = db.scalar(select(Dealer).where(Dealer.slug == dealer_id))
        if dealer and dealer.routing_mode == "least_loaded" and dealer.routing_pool:
            routing_pool = list(dealer.routing_pool)
            since = datetime.now(timezone.utc) - timedelta(days=LOAD_WINDOW_DAYS)
            rows = db.execute(
                select(Lead.assigned_to, func.count(Lead.id))
                .where(
                    Lead.dealer_id == dealer_id,
                    Lead.assigned_to.in_(routing_pool),
                    Lead.status.in_(ACTIVE_STATUSES),
                    Lead.created_at >= since,
                )
                .group_by(Lead.assigned_to)
            ).all()
            routing_loads = {h: 0 for h in routing_pool}
            for handle, n in rows:
                if handle in routing_loads:
                    routing_loads[handle] = int(n)

    to_claim = found_ids - already
    for listing_id in to_claim:
        assigned_to = payload.assigned_to
        if assigned_to is None and routing_pool:
            assigned_to = min(
                routing_pool,
                key=lambda h: (routing_loads[h], routing_pool.index(h)),
            )
            routing_loads[assigned_to] = routing_loads.get(assigned_to, 0) + 1
        db.add(
            Lead(
                dealer_id=dealer_id,
                listing_id=listing_id,
                assigned_to=assigned_to,
            )
        )
    db.flush()

    return BulkClaimOut(
        claimed=len(to_claim),
        already_claimed=len(already),
        missing_listings=missing,
    )


class TeammateRow(BaseModel):
    email: str
    name: str | None
    role: str


@router.get("/leads/teammates", response_model=list[TeammateRow])
def list_teammates(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> list[TeammateRow]:
    """People at this dealer who can be assigned a lead."""
    users = db.scalars(
        select(User).where(
            User.dealer_id == dealer_id, User.is_active.is_(True)
        )
    ).all()
    return [TeammateRow(email=u.email, name=u.name, role=u.role) for u in users]


@router.get("/leads/export.csv")
def export_leads_csv(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
    status: LeadStatus | None = None,
    assigned_to: str | None = None,
) -> StreamingResponse:
    """Stream the dealer's leads (joined with listing data) as a CSV."""
    stmt = (
        select(Lead, Listing)
        .join(Listing, Lead.listing_id == Listing.id)
        .where(Lead.dealer_id == dealer_id)
    )
    if status:
        stmt = stmt.where(Lead.status == status.value)
    if assigned_to:
        stmt = stmt.where(Lead.assigned_to == assigned_to)
    stmt = stmt.order_by(Lead.updated_at.desc())

    def _iter() -> Iterator[str]:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "lead_id",
                "status",
                "assigned_to",
                "offered_price",
                "created_at",
                "updated_at",
                "listing_id",
                "source",
                "external_id",
                "title",
                "year",
                "make",
                "model",
                "price",
                "mileage",
                "city",
                "state",
                "zip_code",
                "seller_phone",
                "vin",
                "classification",
                "lead_quality_score",
                "url",
            ]
        )
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()

        for lead, listing in db.execute(stmt).all():
            writer.writerow(
                [
                    lead.id,
                    lead.status,
                    lead.assigned_to or "",
                    lead.offered_price if lead.offered_price is not None else "",
                    lead.created_at.isoformat() if lead.created_at else "",
                    lead.updated_at.isoformat() if lead.updated_at else "",
                    listing.id,
                    listing.source,
                    listing.external_id,
                    listing.title or "",
                    listing.year if listing.year is not None else "",
                    listing.make or "",
                    listing.model or "",
                    listing.price if listing.price is not None else "",
                    listing.mileage if listing.mileage is not None else "",
                    listing.city or "",
                    listing.state or "",
                    listing.zip_code or "",
                    listing.seller_phone or "",
                    listing.vin or "",
                    listing.classification,
                    listing.lead_quality_score
                    if listing.lead_quality_score is not None
                    else "",
                    listing.url or "",
                ]
            )
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()

    filename = (
        f"autoacquisition_leads_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    )
    return StreamingResponse(
        _iter(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/leads", response_model=list[LeadWithListing])
def list_leads(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
    status: LeadStatus | None = None,
    assigned_to: str | None = None,
    include_archived: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[LeadWithListing]:
    stmt = (
        select(Lead, Listing)
        .join(Listing, Lead.listing_id == Listing.id)
        .where(Lead.dealer_id == dealer_id)
    )
    if not include_archived:
        stmt = stmt.where(Lead.deleted_at.is_(None))
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
    dealer_id: DealerId,
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
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> LeadOut:
    lead = _require_lead(db, lead_id, dealer_id)
    return LeadOut.model_validate(lead)


@router.patch("/leads/{lead_id}", response_model=LeadOut)
def update_lead(
    lead_id: int,
    payload: LeadPatch,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> LeadOut:
    lead = _require_lead(db, lead_id, dealer_id)

    prev_status: str | None = None
    status_changed = False
    if payload.status is not None and payload.status.value != lead.status:
        prev_status = lead.status
        lead.status = payload.status.value
        status_changed = True
        db.add(
            Interaction(
                lead_id=lead.id,
                kind=InteractionKind.STATUS_CHANGE.value,
                body=f"{prev_status} → {lead.status}",
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
    db.flush()

    if status_changed:
        from fsbo.webhooks.delivery import enqueue_for_lead_status_change

        try:
            enqueue_for_lead_status_change(db, lead, prev_status)
        except Exception:  # noqa: BLE001 - webhook fan-out is best-effort
            pass

    return LeadOut.model_validate(lead)


class LeadArchiveIn(BaseModel):
    reason: str | None = None


@router.post("/leads/{lead_id}/archive", response_model=LeadOut)
def archive_lead(
    lead_id: int,
    payload: LeadArchiveIn,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> LeadOut:
    """Soft-delete: filtered out of /leads by default but the row stays
    so the audit trail (Interactions, Messages) survives. Logs an
    Interaction so the timeline shows when + why."""
    lead = _require_lead(db, lead_id, dealer_id)
    if lead.deleted_at is not None:
        return LeadOut.model_validate(lead)
    now = datetime.now(timezone.utc)
    lead.deleted_at = now
    lead.deleted_by = dealer_id
    lead.delete_reason = (payload.reason or "")[:256] or None
    db.add(
        Interaction(
            lead_id=lead.id,
            kind=InteractionKind.STATUS_CHANGE.value,
            body=f"archived: {lead.delete_reason or 'no reason given'}",
            actor=dealer_id,
        )
    )
    lead.updated_at = now
    return LeadOut.model_validate(lead)


@router.post("/leads/{lead_id}/restore", response_model=LeadOut)
def restore_lead(
    lead_id: int,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> LeadOut:
    """Undo a soft-delete. Allowed for 30 days after archive; after
    that the row may already be hard-deleted by the sweeper."""
    lead = db.get(Lead, lead_id)
    if not lead or lead.dealer_id != dealer_id:
        raise HTTPException(404, "lead not found")
    if lead.deleted_at is None:
        return LeadOut.model_validate(lead)
    age = datetime.now(timezone.utc) - (
        lead.deleted_at
        if lead.deleted_at.tzinfo
        else lead.deleted_at.replace(tzinfo=timezone.utc)
    )
    if age.days > 30:
        raise HTTPException(410, "archive window expired (30 days)")
    lead.deleted_at = None
    lead.deleted_by = None
    lead.delete_reason = None
    lead.updated_at = datetime.now(timezone.utc)
    db.add(
        Interaction(
            lead_id=lead.id,
            kind=InteractionKind.STATUS_CHANGE.value,
            body="restored from archive",
            actor=dealer_id,
        )
    )
    return LeadOut.model_validate(lead)


# ---------- interaction endpoints ----------


@router.post("/leads/{lead_id}/interactions", response_model=InteractionOut, status_code=201)
def create_interaction(
    lead_id: int,
    payload: InteractionIn,
    dealer_id: DealerId,
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
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> list[InteractionOut]:
    _require_lead(db, lead_id, dealer_id)
    rows = db.scalars(
        select(Interaction)
        .where(Interaction.lead_id == lead_id)
        .order_by(Interaction.created_at.desc())
    ).all()
    return [InteractionOut.model_validate(r) for r in rows]


# ---------- unified inbox feed --------------------------------------------
#
# VAN's "unified messaging hub" stream combines calls, SMS, email, web
# forms, and in-platform notes into one feed per conversation. We have
# the same data — Interactions + Messages tables — but no merged read
# endpoint until now. This produces a single chronological feed the
# dashboard can render as one timeline.


class FeedEntry(BaseModel):
    """One entry in the unified per-lead feed.

    `kind` mirrors the source row type:
      - "interaction:<InteractionKind>" — note / call / text / email /
        task / status_change. body is free text.
      - "message:outbound" / "message:inbound" — Twilio SMS row. body
        is the SMS text. delivery_status is the Twilio status.
    """

    kind: str
    direction: str | None = None
    body: str | None = None
    actor: str | None = None
    delivery_status: str | None = None
    created_at: datetime
    # Reference back to the source row for quick navigation.
    source_id: int
    source_table: str  # "interactions" | "messages"


class UnifiedFeed(BaseModel):
    lead_id: int
    entries: list[FeedEntry]


@router.get("/leads/{lead_id}/feed", response_model=UnifiedFeed)
def lead_feed(
    lead_id: int,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
    limit: int = 200,
) -> UnifiedFeed:
    """Chronological merge of every Interaction + Message + VoiceCall
    tied to a lead. Newest first. Single endpoint -> single timeline ->
    dealer sees the whole conversation in one panel rather than tabbing
    between SMS, notes, and call recordings."""
    lead = _require_lead(db, lead_id, dealer_id)

    interactions = db.scalars(
        select(Interaction)
        .where(Interaction.lead_id == lead.id)
        .order_by(Interaction.created_at.desc())
    ).all()

    from fsbo.models import Message, VoiceCall  # local import — avoid circulars

    messages = db.scalars(
        select(Message)
        .where(Message.lead_id == lead.id)
        .order_by(Message.created_at.desc())
    ).all()

    calls = db.scalars(
        select(VoiceCall)
        .where(VoiceCall.lead_id == lead.id)
        .order_by(VoiceCall.created_at.desc())
    ).all()

    entries: list[FeedEntry] = []
    for i in interactions:
        entries.append(
            FeedEntry(
                kind=f"interaction:{i.kind}",
                direction=i.direction,
                body=i.body,
                actor=i.actor,
                created_at=i.created_at,
                source_id=i.id,
                source_table="interactions",
            )
        )
    for m in messages:
        entries.append(
            FeedEntry(
                kind=f"message:{m.direction}",
                direction=m.direction,
                body=m.body,
                actor=None,
                delivery_status=m.status,
                created_at=m.created_at,
                source_id=m.id,
                source_table="messages",
            )
        )
    for c in calls:
        # Body is a one-line summary; the dashboard's voice panel
        # renders the full transcript via /voice/calls/{id}.
        seller_turns = sum(
            1 for t in (c.turns or []) if (t or {}).get("role") == "seller"
        )
        duration_s = c.duration_seconds or 0
        next_step = (c.intake or {}).get("next_step") or ""
        body_parts = [
            f"AI voice call · status={c.status}",
            f"{seller_turns} seller turns" if seller_turns else None,
            f"{duration_s}s" if duration_s else None,
            f"next: {next_step}" if next_step else None,
        ]
        entries.append(
            FeedEntry(
                kind="voice_call",
                direction="outbound",
                body=" · ".join(p for p in body_parts if p),
                actor=None,
                delivery_status=c.status,
                created_at=c.created_at,
                source_id=c.id,
                source_table="voice_calls",
            )
        )

    # Sort newest-first and cap.
    entries.sort(key=lambda e: e.created_at, reverse=True)
    entries = entries[: min(limit, 1000)]
    return UnifiedFeed(lead_id=lead.id, entries=entries)


@router.post(
    "/leads/{lead_id}/interactions/{interaction_id}/complete",
    response_model=InteractionOut,
)
def complete_interaction(
    lead_id: int,
    interaction_id: int,
    dealer_id: DealerId,
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
