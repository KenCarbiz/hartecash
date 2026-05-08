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

from fastapi import APIRouter, Depends, HTTPException, Request
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
    first_responded_at: datetime | None = None
    last_inbound_at: datetime | None = None
    last_seen_inbound_at: datetime | None = None


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

    if assigned_to:
        from fsbo.messaging.assign_notify import notify_assignment

        try:
            notify_assignment(db, lead)
        except Exception:  # noqa: BLE001
            pass

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
    new_leads: list[Lead] = []
    for listing_id in to_claim:
        assigned_to = payload.assigned_to
        if assigned_to is None and routing_pool:
            assigned_to = min(
                routing_pool,
                key=lambda h: (routing_loads[h], routing_pool.index(h)),
            )
            routing_loads[assigned_to] = routing_loads.get(assigned_to, 0) + 1
        lead = Lead(
            dealer_id=dealer_id,
            listing_id=listing_id,
            assigned_to=assigned_to,
        )
        db.add(lead)
        new_leads.append(lead)
    db.flush()

    # Best-effort notify after flush so each lead has its id.
    if any(l.assigned_to for l in new_leads):
        from fsbo.messaging.assign_notify import notify_assignment

        for lead in new_leads:
            if not lead.assigned_to:
                continue
            try:
                notify_assignment(db, lead)
            except Exception:  # noqa: BLE001
                pass

    return BulkClaimOut(
        claimed=len(to_claim),
        already_claimed=len(already),
        missing_listings=missing,
    )


class BulkLeadOpIn(BaseModel):
    """Generic bulk-op payload — caller supplies a list of lead ids
    + the per-op fields. Each endpoint validates only the fields it
    needs."""

    lead_ids: list[int]
    # status-change op
    status: LeadStatus | None = None
    # assign op
    assigned_to: str | None = None
    # archive op
    reason: str | None = None


class BulkLeadOpOut(BaseModel):
    updated: int
    skipped: int
    not_found: list[int]


def _bulk_load_leads(
    db: Session, lead_ids: list[int], dealer_id: str
) -> tuple[list[Lead], list[int]]:
    """Load + dealer-scope-check a list of leads. Returns
    (found_leads, not_found_ids). Caps at 200 to bound the work."""
    ids = list({*lead_ids})[:200]
    rows = db.scalars(
        select(Lead).where(Lead.id.in_(ids), Lead.dealer_id == dealer_id)
    ).all()
    found_ids = {r.id for r in rows}
    return list(rows), [i for i in ids if i not in found_ids]


@router.post("/leads/bulk-status", response_model=BulkLeadOpOut)
def bulk_status_change(
    payload: BulkLeadOpIn,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> BulkLeadOpOut:
    """Move many leads to the same status in one call. Logs a
    status_change Interaction on each lead. Fires the
    lead.status_changed webhook for each that actually changed."""
    if payload.status is None:
        raise HTTPException(400, "status is required")
    leads, missing = _bulk_load_leads(db, payload.lead_ids, dealer_id)
    new_status = payload.status.value

    updated = 0
    skipped = 0
    changed_leads: list[tuple[Lead, str]] = []
    now = datetime.now(timezone.utc)
    for lead in leads:
        if lead.status == new_status:
            skipped += 1
            continue
        prev = lead.status
        lead.status = new_status
        lead.updated_at = now
        db.add(
            Interaction(
                lead_id=lead.id,
                kind=InteractionKind.STATUS_CHANGE.value,
                body=f"{prev} → {new_status} (bulk op)",
                actor=dealer_id,
            )
        )
        changed_leads.append((lead, prev))
        updated += 1
    db.flush()

    # Webhook fan-out (best-effort)
    if changed_leads:
        from fsbo.webhooks.delivery import enqueue_for_lead_status_change

        for lead, prev in changed_leads:
            try:
                enqueue_for_lead_status_change(db, lead, prev)
            except Exception:  # noqa: BLE001
                pass

    return BulkLeadOpOut(updated=updated, skipped=skipped, not_found=missing)


@router.post("/leads/bulk-assign", response_model=BulkLeadOpOut)
def bulk_assign(
    payload: BulkLeadOpIn,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> BulkLeadOpOut:
    """Re-assign many leads to one rep. assigned_to=null clears the
    assignment (back to unassigned). Idempotent: already-matching
    leads count as 'skipped'."""
    new_owner = payload.assigned_to
    leads, missing = _bulk_load_leads(db, payload.lead_ids, dealer_id)

    updated = 0
    skipped = 0
    reassigned: list[tuple[Lead, str]] = []  # (lead, prev_owner) for notification
    now = datetime.now(timezone.utc)
    for lead in leads:
        if lead.assigned_to == new_owner:
            skipped += 1
            continue
        prev = lead.assigned_to or "(unassigned)"
        lead.assigned_to = new_owner
        lead.updated_at = now
        db.add(
            Interaction(
                lead_id=lead.id,
                kind=InteractionKind.NOTE.value,
                body=f"reassigned: {prev} → {new_owner or '(unassigned)'} (bulk op)",
                actor=dealer_id,
            )
        )
        if new_owner:
            reassigned.append((lead, prev))
        updated += 1
    db.flush()

    if reassigned:
        from fsbo.messaging.assign_notify import notify_assignment

        for lead, prev in reassigned:
            try:
                notify_assignment(db, lead, prev_owner=prev)
            except Exception:  # noqa: BLE001
                pass

    return BulkLeadOpOut(updated=updated, skipped=skipped, not_found=missing)


@router.post("/leads/bulk-archive", response_model=BulkLeadOpOut)
def bulk_archive(
    payload: BulkLeadOpIn,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> BulkLeadOpOut:
    """Soft-delete many leads at once. Skips leads that are already
    archived. Reuses the same audit-trail mechanic as the per-lead
    /archive endpoint."""
    leads, missing = _bulk_load_leads(db, payload.lead_ids, dealer_id)
    reason = (payload.reason or "")[:256] or None

    updated = 0
    skipped = 0
    now = datetime.now(timezone.utc)
    for lead in leads:
        if lead.deleted_at is not None:
            skipped += 1
            continue
        lead.deleted_at = now
        lead.deleted_by = dealer_id
        lead.delete_reason = reason
        lead.updated_at = now
        db.add(
            Interaction(
                lead_id=lead.id,
                kind=InteractionKind.STATUS_CHANGE.value,
                body=f"archived (bulk): {reason or 'no reason given'}",
                actor=dealer_id,
            )
        )
        updated += 1
    db.flush()
    return BulkLeadOpOut(updated=updated, skipped=skipped, not_found=missing)


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


# ---------- CSV import (dealer migration: VAN / Frazer / generic) ---------


class ImportRowError(BaseModel):
    row: int
    error: str


class ImportResult(BaseModel):
    imported: int
    skipped_duplicates: int
    errors: list[ImportRowError]


# Header aliases — left side is the canonical key, right side is every
# header variant we'll accept (case-insensitive). Covers VAN, Frazer,
# DealerSocket, and the generic "what people put in spreadsheets".
_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "phone": ("phone", "seller_phone", "seller phone", "mobile", "cell", "cell phone"),
    "email": ("email", "seller_email", "seller email", "e-mail"),
    "year": ("year", "vehicle_year", "yr"),
    "make": ("make", "vehicle_make"),
    "model": ("model", "vehicle_model"),
    "vin": ("vin",),
    "price": ("price", "asking_price", "asking price", "list_price"),
    "mileage": ("mileage", "miles", "odometer"),
    "city": ("city",),
    "state": ("state", "st"),
    "zip": ("zip", "zip_code", "zipcode", "postal_code"),
    "notes": ("notes", "comment", "comments"),
    "assigned_to": ("assigned_to", "assigned to", "owner", "rep", "buyer"),
    "status": ("status", "lead_status", "stage"),
    "title": ("title", "vehicle", "description"),
    "url": ("url", "listing_url", "link", "source_url"),
}

_VALID_STATUSES: set[str] = {s.value for s in LeadStatus}


def _normalize_header(raw: str) -> str | None:
    """Map a CSV header to one of our canonical keys. Returns None if
    the header doesn't match any alias (we just ignore unknown columns).

    Whitespace and underscores are interchangeable so `Vehicle Year`,
    `vehicle_year`, and `vehicle year` all collapse to the same key."""
    cleaned = (raw or "").strip().lower().replace(" ", "_")
    if not cleaned:
        return None
    for canonical, aliases in _HEADER_ALIASES.items():
        if cleaned in (a.replace(" ", "_") for a in aliases):
            return canonical
    return None


def _digits10(phone: str | None) -> str:
    if not phone:
        return ""
    return "".join(c for c in phone if c.isdigit())[-10:]


def _row_int(row: dict[str, str], key: str) -> int | None:
    raw = (row.get(key) or "").strip()
    if not raw:
        return None
    try:
        # Tolerant of "$18,500" -> 18500 and "120,000 mi" -> 120000.
        cleaned = "".join(c for c in raw if c.isdigit())
        return int(cleaned) if cleaned else None
    except ValueError:
        return None


@router.post("/leads/import.csv", response_model=ImportResult)
async def import_leads_csv(
    request: Request,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> ImportResult:
    """Bulk-import leads from a dealer's prior CRM export.

    Accepts multipart/form-data with a single 'file' field OR a raw
    text/csv body. Header row required; columns are matched
    case-insensitively against a permissive alias list (VAN, Frazer,
    DealerSocket, and generic spreadsheet conventions all work).

    Each row must have at least a phone OR email so we can match against
    inbound replies later. Listings are upsert by (dealer, source,
    external_id) where external_id is a stable hash of the contact info,
    so re-uploading the same CSV doesn't duplicate. Leads are dedup'd by
    the existing (dealer, listing) unique constraint.

    Capped at 5000 rows per request to keep the transaction bounded.
    """
    # Pull the bytes from either multipart or raw body.
    content_type = (request.headers.get("content-type") or "").lower()
    if "multipart" in content_type:
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(400, "missing 'file' field")
        raw = await upload.read()  # type: ignore[union-attr]
    else:
        raw = await request.body()

    if not raw:
        raise HTTPException(400, "empty body")
    if len(raw) > 5_000_000:
        raise HTTPException(413, "csv too large; cap is 5 MB")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    reader = csv.reader(io.StringIO(text))
    try:
        header_row = next(reader)
    except StopIteration:
        raise HTTPException(400, "csv has no header row") from None

    # Build a column-index -> canonical-key map; unknown columns are
    # silently dropped.
    col_map: dict[int, str] = {}
    for idx, raw_header in enumerate(header_row):
        canonical = _normalize_header(raw_header)
        if canonical:
            col_map[idx] = canonical
    if not col_map:
        raise HTTPException(
            400,
            "no recognized columns; need at least one of: "
            "phone, email, vin, year/make/model",
        )

    imported = 0
    skipped = 0
    errors: list[ImportRowError] = []
    MAX_ROWS = 5000

    import hashlib

    for line_num, raw_row in enumerate(reader, start=2):
        if line_num - 1 > MAX_ROWS:
            errors.append(
                ImportRowError(
                    row=line_num,
                    error=f"row cap of {MAX_ROWS} exceeded; rest skipped",
                )
            )
            break

        row = {col_map[i]: (raw_row[i] if i < len(raw_row) else "") for i in col_map}

        phone = (row.get("phone") or "").strip() or None
        email = (row.get("email") or "").strip() or None
        vin = (row.get("vin") or "").strip().upper() or None

        if not phone and not email and not vin:
            errors.append(
                ImportRowError(
                    row=line_num,
                    error="missing phone, email, and vin — can't identify seller",
                )
            )
            continue

        # Stable external_id so re-imports dedupe deterministically.
        # Order matters: vin > phone > email so we don't split rows
        # that have multiple identifiers.
        if vin:
            ext_seed = f"vin:{vin}"
        elif phone:
            ext_seed = f"phone:{_digits10(phone)}"
        else:
            ext_seed = f"email:{(email or '').lower()}"
        ext_id = "csv-" + hashlib.sha1(ext_seed.encode()).hexdigest()[:16]

        # Build / find the listing.
        listing = db.scalar(
            select(Listing).where(
                Listing.source == "csv_import",
                Listing.external_id == ext_id,
            )
        )
        if listing is None:
            year = _row_int(row, "year")
            mileage = _row_int(row, "mileage")
            price = _row_int(row, "price")
            title = (row.get("title") or "").strip() or " ".join(
                x
                for x in [
                    str(year) if year else "",
                    (row.get("make") or "").strip(),
                    (row.get("model") or "").strip(),
                ]
                if x
            ).strip() or "(imported)"
            listing = Listing(
                source="csv_import",
                external_id=ext_id,
                url=(row.get("url") or "").strip()
                or f"csv-import:{ext_id}",
                title=title[:256],
                year=year,
                make=(row.get("make") or "").strip() or None,
                model=(row.get("model") or "").strip() or None,
                vin=vin,
                price=price,
                mileage=mileage,
                city=(row.get("city") or "").strip() or None,
                state=(row.get("state") or "").strip() or None,
                zip_code=(row.get("zip") or "").strip() or None,
                seller_phone=phone,
                seller_email=email,
                classification="private_seller",
            )
            db.add(listing)
            db.flush()

        # Upsert the lead within this dealer.
        existing_lead = db.scalar(
            select(Lead).where(
                and_(Lead.dealer_id == dealer_id, Lead.listing_id == listing.id)
            )
        )
        if existing_lead is not None:
            skipped += 1
            continue

        status_raw = (row.get("status") or "").strip().lower().replace(" ", "_")
        status = status_raw if status_raw in _VALID_STATUSES else "new"

        lead = Lead(
            dealer_id=dealer_id,
            listing_id=listing.id,
            assigned_to=(row.get("assigned_to") or "").strip() or None,
            status=status,
            notes=(row.get("notes") or "").strip() or None,
        )
        db.add(lead)
        imported += 1

    db.flush()

    return ImportResult(
        imported=imported,
        skipped_duplicates=skipped,
        errors=errors,
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
            first_responded_at=lead.first_responded_at,
            last_inbound_at=lead.last_inbound_at,
            last_seen_inbound_at=lead.last_seen_inbound_at,
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


class StaleLeadRow(LeadWithListing):
    """A lead in the response-SLA breach queue.

    `minutes_since_created` lets the dashboard color-code urgency
    without re-doing the math client-side.
    """

    minutes_since_created: int


@router.get("/leads/stale", response_model=list[StaleLeadRow])
def list_stale_leads(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
    sla_minutes: int = 5,
    limit: int = 50,
) -> list[StaleLeadRow]:
    """Leads still un-contacted past the SLA window — the "needs
    attention now" queue.

    A lead is stale when:
      - status is still 'new' or 'contacted'
      - it's older than sla_minutes
      - there is no outbound Interaction, Message, or VoiceCall on it
      - it isn't archived
    Ordered oldest-first so the rep works the most-urgent backlog first.
    """
    from fsbo.models import Message, VoiceCall

    if sla_minutes < 0:
        sla_minutes = 0
    if limit > 200:
        limit = 200

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=sla_minutes)

    # Lead ids are globally unique so we could skip the join, but
    # narrowing to this dealer keeps the working set small for big DBs.
    dealer_lead_ids_subq = (
        select(Lead.id).where(Lead.dealer_id == dealer_id)
    )
    contacted_lead_ids = set(
        db.scalars(
            select(Interaction.lead_id)
            .where(
                Interaction.direction == "outbound",
                Interaction.lead_id.in_(dealer_lead_ids_subq),
            )
            .distinct()
        ).all()
    )
    contacted_lead_ids |= set(
        db.scalars(
            select(Message.lead_id)
            .where(
                Message.direction == "outbound",
                Message.lead_id.in_(dealer_lead_ids_subq),
            )
            .distinct()
        ).all()
    )
    contacted_lead_ids |= set(
        db.scalars(
            select(VoiceCall.lead_id)
            .where(VoiceCall.dealer_id == dealer_id)
            .distinct()
        ).all()
    )

    stmt = (
        select(Lead, Listing)
        .join(Listing, Lead.listing_id == Listing.id)
        .where(
            Lead.dealer_id == dealer_id,
            Lead.deleted_at.is_(None),
            Lead.status.in_(("new", "contacted")),
            Lead.created_at <= cutoff,
        )
    )
    if contacted_lead_ids:
        stmt = stmt.where(Lead.id.notin_(contacted_lead_ids))
    stmt = stmt.order_by(Lead.created_at.asc()).limit(limit)

    now = datetime.now(timezone.utc)
    rows = db.execute(stmt).all()
    out: list[StaleLeadRow] = []
    for lead, listing in rows:
        created = (
            lead.created_at
            if lead.created_at.tzinfo
            else lead.created_at.replace(tzinfo=timezone.utc)
        )
        minutes = max(0, int((now - created).total_seconds() // 60))
        out.append(
            StaleLeadRow(
                id=lead.id,
                dealer_id=lead.dealer_id,
                listing_id=lead.listing_id,
                assigned_to=lead.assigned_to,
                status=lead.status,
                offered_price=lead.offered_price,
                notes=lead.notes,
                created_at=lead.created_at,
                updated_at=lead.updated_at,
                first_responded_at=lead.first_responded_at,
                last_inbound_at=lead.last_inbound_at,
                last_seen_inbound_at=lead.last_seen_inbound_at,
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
                minutes_since_created=minutes,
            )
        )
    return out


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


@router.post("/leads/{lead_id}/seen", response_model=LeadOut)
def mark_lead_seen(
    lead_id: int,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> LeadOut:
    """Mark the inbound thread on this lead read (clears the unread
    badge). Idempotent — repeat calls just bump the timestamp."""
    from fsbo.crm.response import mark_inbound_seen

    lead = _require_lead(db, lead_id, dealer_id)
    mark_inbound_seen(lead)
    db.flush()
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
    if (payload.direction or "").lower() == "outbound":
        from fsbo.crm.response import mark_first_response

        mark_first_response(lead)
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
        # Emails ride the same Message rows as SMS but carry a channel
        # marker + subject; surface the subject inline so the dashboard
        # timeline reads naturally without forking the kind enum.
        channel = getattr(m, "channel", "sms") or "sms"
        body = m.body
        subject = getattr(m, "subject", None)
        if channel == "email" and subject:
            body = f"[email · {subject}]\n{m.body}"
        elif channel == "email":
            body = f"[email]\n{m.body}"
        entries.append(
            FeedEntry(
                kind=f"message:{m.direction}",
                direction=m.direction,
                body=body,
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
