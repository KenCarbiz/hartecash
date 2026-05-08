"""Analytics: conversion funnel + source breakdown.

Dealers need to see: am I actually buying more cars? Which sources produce
the keepers? Which saved searches are dead weight?

The funnel semantics:
    listings_surfaced   private-seller + not auto_hidden + first_seen in window
    leads_claimed       Lead rows for this dealer created in window
    leads_contacted     leads with at least one outbound Interaction in window
    leads_appointment   leads whose status hit `appointment` in window
    leads_purchased     leads whose status hit `purchased` in window
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from fsbo.auth.resolver import DealerId
from fsbo.db import get_session
from fsbo.models import (
    Classification,
    Dealer,
    DealerGroup,
    Interaction,
    Lead,
    Listing,
    Message,
    Offer,
    VoiceCall,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


class FunnelStage(BaseModel):
    label: str
    key: str
    count: int


class SourceBreakdownRow(BaseModel):
    source: str
    listings: int
    leads_claimed: int
    leads_purchased: int


class FunnelResponse(BaseModel):
    dealer_id: str
    since: datetime
    until: datetime
    stages: list[FunnelStage]
    sources: list[SourceBreakdownRow]


@router.get("/funnel", response_model=FunnelResponse)
def funnel(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
    days: int = Query(30, ge=1, le=365),
) -> FunnelResponse:
    until = datetime.now(timezone.utc)
    since = until - timedelta(days=days)

    listings_surfaced = db.scalar(
        select(func.count())
        .select_from(Listing)
        .where(
            Listing.classification == Classification.PRIVATE_SELLER.value,
            Listing.auto_hidden.is_(False),
            Listing.first_seen_at >= since,
        )
    ) or 0

    leads_claimed_subq = select(Lead.id).where(
        Lead.dealer_id == dealer_id, Lead.created_at >= since
    ).subquery()

    leads_claimed = (
        db.scalar(select(func.count()).select_from(leads_claimed_subq)) or 0
    )

    leads_contacted = db.scalar(
        select(func.count(func.distinct(Interaction.lead_id)))
        .select_from(Interaction)
        .join(Lead, Lead.id == Interaction.lead_id)
        .where(
            and_(
                Lead.dealer_id == dealer_id,
                Interaction.direction == "outbound",
                Interaction.created_at >= since,
            )
        )
    ) or 0

    def _count_by_status(status: str) -> int:
        return (
            db.scalar(
                select(func.count())
                .select_from(Lead)
                .where(
                    and_(
                        Lead.dealer_id == dealer_id,
                        Lead.status == status,
                        Lead.updated_at >= since,
                    )
                )
            )
            or 0
        )

    leads_appointment = _count_by_status("appointment")
    leads_purchased = _count_by_status("purchased")

    stages = [
        FunnelStage(label="Listings surfaced", key="listings_surfaced", count=listings_surfaced),
        FunnelStage(label="Leads claimed", key="leads_claimed", count=leads_claimed),
        FunnelStage(label="Contacted", key="leads_contacted", count=leads_contacted),
        FunnelStage(label="Appointments", key="leads_appointment", count=leads_appointment),
        FunnelStage(label="Purchased", key="leads_purchased", count=leads_purchased),
    ]

    # Per-source breakdown: listings surfaced + leads claimed + purchased.
    source_rows = db.execute(
        select(
            Listing.source,
            func.count(Listing.id),
        )
        .where(
            Listing.classification == Classification.PRIVATE_SELLER.value,
            Listing.auto_hidden.is_(False),
            Listing.first_seen_at >= since,
        )
        .group_by(Listing.source)
    ).all()

    leads_by_source = dict(
        db.execute(
            select(Listing.source, func.count(Lead.id))
            .join(Listing, Listing.id == Lead.listing_id)
            .where(Lead.dealer_id == dealer_id, Lead.created_at >= since)
            .group_by(Listing.source)
        ).all()
    )
    purchased_by_source = dict(
        db.execute(
            select(Listing.source, func.count(Lead.id))
            .join(Listing, Listing.id == Lead.listing_id)
            .where(
                Lead.dealer_id == dealer_id,
                Lead.status == "purchased",
                Lead.updated_at >= since,
            )
            .group_by(Listing.source)
        ).all()
    )

    sources = [
        SourceBreakdownRow(
            source=src,
            listings=int(listings),
            leads_claimed=int(leads_by_source.get(src, 0)),
            leads_purchased=int(purchased_by_source.get(src, 0)),
        )
        for src, listings in source_rows
    ]
    sources.sort(key=lambda r: r.listings, reverse=True)

    return FunnelResponse(
        dealer_id=dealer_id,
        since=since,
        until=until,
        stages=stages,
        sources=sources,
    )


# ---- Per-rep leaderboard ----------------------------------------------


class RepRow(BaseModel):
    """One acquisition rep's column on the leaderboard. assigned_to is
    the per-Lead string field (today: free-text email/handle), so this
    aggregates whatever the dealer is using as their identifier."""

    assigned_to: str
    leads_claimed: int
    leads_contacted: int
    leads_appointment: int
    leads_purchased: int
    sms_sent: int
    voice_calls: int
    offers_sent: int
    offers_accepted: int
    avg_response_minutes: float | None
    # `score` is a simple composite for default ordering: 5 points per
    # purchase + 2 per appointment + 1 per contact. Tunable per dealer
    # later; today the dashboard renders the raw counts so the score
    # is just for sort-on-arrival.
    score: int


class LeaderboardResponse(BaseModel):
    dealer_id: str
    since: datetime
    until: datetime
    reps: list[RepRow]


@router.get("/leaderboard", response_model=LeaderboardResponse)
def leaderboard(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
    days: int = Query(30, ge=1, le=365),
) -> LeaderboardResponse:
    """Per-rep funnel + activity counts for the last N days.

    Aggregates by Lead.assigned_to. Includes blank/null as
    "Unassigned" so dealers see how much of their pipeline is
    floating without an owner.
    """
    until = datetime.now(timezone.utc)
    since = until - timedelta(days=days)

    UNASSIGNED = "(unassigned)"

    def _norm(value: str | None) -> str:
        return (value or "").strip() or UNASSIGNED

    # Pull every lead in the window once, build per-rep buckets.
    rows = db.execute(
        select(Lead.id, Lead.assigned_to, Lead.status, Lead.created_at)
        .where(
            Lead.dealer_id == dealer_id,
            Lead.created_at >= since,
        )
    ).all()

    rep_buckets: dict[str, dict] = {}

    def _bucket(name: str) -> dict:
        if name not in rep_buckets:
            rep_buckets[name] = {
                "leads_claimed": 0,
                "leads_contacted": 0,
                "leads_appointment": 0,
                "leads_purchased": 0,
                "sms_sent": 0,
                "voice_calls": 0,
                "offers_sent": 0,
                "offers_accepted": 0,
                "_response_minutes": [],
                "_lead_ids": set(),
            }
        return rep_buckets[name]

    for lead_id, assigned_to, status, _ in rows:
        b = _bucket(_norm(assigned_to))
        b["leads_claimed"] += 1
        b["_lead_ids"].add(lead_id)
        if status == "appointment":
            b["leads_appointment"] += 1
        if status == "purchased":
            b["leads_purchased"] += 1

    # leads_contacted: distinct leads with at least one outbound
    # interaction in window. Charged to whoever owned the lead at
    # the time we look (good-enough proxy for now).
    contacted_pairs = db.execute(
        select(Lead.assigned_to, func.count(func.distinct(Interaction.lead_id)))
        .join(Interaction, Interaction.lead_id == Lead.id)
        .where(
            Lead.dealer_id == dealer_id,
            Interaction.direction == "outbound",
            Interaction.created_at >= since,
        )
        .group_by(Lead.assigned_to)
    ).all()
    for assigned_to, n in contacted_pairs:
        _bucket(_norm(assigned_to))["leads_contacted"] = int(n)

    # SMS sent: outbound Messages in window per rep.
    sms_pairs = db.execute(
        select(Lead.assigned_to, func.count(Message.id))
        .join(Message, Message.lead_id == Lead.id)
        .where(
            Lead.dealer_id == dealer_id,
            Message.direction == "outbound",
            Message.created_at >= since,
        )
        .group_by(Lead.assigned_to)
    ).all()
    for assigned_to, n in sms_pairs:
        _bucket(_norm(assigned_to))["sms_sent"] = int(n)

    # Voice calls in window per rep.
    voice_pairs = db.execute(
        select(Lead.assigned_to, func.count(VoiceCall.id))
        .join(VoiceCall, VoiceCall.lead_id == Lead.id)
        .where(
            Lead.dealer_id == dealer_id,
            VoiceCall.created_at >= since,
        )
        .group_by(Lead.assigned_to)
    ).all()
    for assigned_to, n in voice_pairs:
        _bucket(_norm(assigned_to))["voice_calls"] = int(n)

    # Offers sent + accepted in window per rep.
    offers_sent_pairs = db.execute(
        select(Lead.assigned_to, func.count(Offer.id))
        .join(Offer, Offer.lead_id == Lead.id)
        .where(
            Lead.dealer_id == dealer_id,
            Offer.created_at >= since,
        )
        .group_by(Lead.assigned_to)
    ).all()
    for assigned_to, n in offers_sent_pairs:
        _bucket(_norm(assigned_to))["offers_sent"] = int(n)

    offers_accepted_pairs = db.execute(
        select(Lead.assigned_to, func.count(Offer.id))
        .join(Offer, Offer.lead_id == Lead.id)
        .where(
            Lead.dealer_id == dealer_id,
            Offer.status == "accepted",
            Offer.seller_response_at >= since,
        )
        .group_by(Lead.assigned_to)
    ).all()
    for assigned_to, n in offers_accepted_pairs:
        _bucket(_norm(assigned_to))["offers_accepted"] = int(n)

    # Average rep response time: minutes between Lead.created_at and
    # the rep's first outbound Interaction on that lead.
    first_outbounds = db.execute(
        select(
            Lead.assigned_to,
            Lead.id,
            Lead.created_at,
            func.min(Interaction.created_at),
        )
        .join(Interaction, Interaction.lead_id == Lead.id)
        .where(
            Lead.dealer_id == dealer_id,
            Lead.created_at >= since,
            Interaction.direction == "outbound",
        )
        .group_by(Lead.assigned_to, Lead.id, Lead.created_at)
    ).all()
    for assigned_to, _, lead_created, first_out in first_outbounds:
        if not first_out or not lead_created:
            continue
        # Coerce to UTC if SQLite returns naive datetimes.
        first_utc = (
            first_out
            if first_out.tzinfo
            else first_out.replace(tzinfo=timezone.utc)
        )
        created_utc = (
            lead_created
            if lead_created.tzinfo
            else lead_created.replace(tzinfo=timezone.utc)
        )
        minutes = max(0.0, (first_utc - created_utc).total_seconds() / 60.0)
        _bucket(_norm(assigned_to))["_response_minutes"].append(minutes)

    reps: list[RepRow] = []
    for name, b in rep_buckets.items():
        rms = b["_response_minutes"]
        avg = sum(rms) / len(rms) if rms else None
        score = (
            5 * b["leads_purchased"]
            + 2 * b["leads_appointment"]
            + 1 * b["leads_contacted"]
        )
        reps.append(
            RepRow(
                assigned_to=name,
                leads_claimed=b["leads_claimed"],
                leads_contacted=b["leads_contacted"],
                leads_appointment=b["leads_appointment"],
                leads_purchased=b["leads_purchased"],
                sms_sent=b["sms_sent"],
                voice_calls=b["voice_calls"],
                offers_sent=b["offers_sent"],
                offers_accepted=b["offers_accepted"],
                avg_response_minutes=round(avg, 1) if avg is not None else None,
                score=score,
            )
        )
    reps.sort(key=lambda r: (r.score, r.leads_purchased, r.leads_claimed), reverse=True)

    return LeaderboardResponse(
        dealer_id=dealer_id, since=since, until=until, reps=reps
    )


# ---- Multi-rooftop rollup ---------------------------------------------


class RooftopFunnelRow(BaseModel):
    dealer_id: str
    leads_claimed: int
    leads_contacted: int
    leads_appointment: int
    leads_purchased: int


class GroupFunnelResponse(BaseModel):
    group_slug: str
    group_name: str
    since: datetime
    until: datetime
    rooftops: list[RooftopFunnelRow]
    totals: RooftopFunnelRow


@router.get("/group-funnel", response_model=GroupFunnelResponse)
def group_funnel(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
    days: int = Query(30, ge=1, le=365),
) -> GroupFunnelResponse:
    """Roll-up funnel across every Dealer in the calling user's
    DealerGroup. Members of the same group all see the same rollup;
    dealers without a group get a 404.
    """
    dealer = db.scalar(select(Dealer).where(Dealer.slug == dealer_id))
    if not dealer or dealer.group_id is None:
        from fastapi import HTTPException

        raise HTTPException(404, "dealer is not in a group")
    group = db.get(DealerGroup, dealer.group_id)
    if not group:
        from fastapi import HTTPException

        raise HTTPException(404, "group not found")

    member_slugs = list(
        db.scalars(
            select(Dealer.slug).where(Dealer.group_id == group.id)
        ).all()
    )
    until = datetime.now(timezone.utc)
    since = until - timedelta(days=days)

    rows: list[RooftopFunnelRow] = []
    totals = {"claimed": 0, "contacted": 0, "appointment": 0, "purchased": 0}
    for slug in member_slugs:
        claimed = (
            db.scalar(
                select(func.count())
                .select_from(Lead)
                .where(Lead.dealer_id == slug, Lead.created_at >= since)
            )
            or 0
        )
        contacted = (
            db.scalar(
                select(func.count(func.distinct(Interaction.lead_id)))
                .select_from(Interaction)
                .join(Lead, Lead.id == Interaction.lead_id)
                .where(
                    Lead.dealer_id == slug,
                    Interaction.direction == "outbound",
                    Interaction.created_at >= since,
                )
            )
            or 0
        )
        appointment = (
            db.scalar(
                select(func.count())
                .select_from(Lead)
                .where(
                    Lead.dealer_id == slug,
                    Lead.status == "appointment",
                    Lead.updated_at >= since,
                )
            )
            or 0
        )
        purchased = (
            db.scalar(
                select(func.count())
                .select_from(Lead)
                .where(
                    Lead.dealer_id == slug,
                    Lead.status == "purchased",
                    Lead.updated_at >= since,
                )
            )
            or 0
        )
        rows.append(
            RooftopFunnelRow(
                dealer_id=slug,
                leads_claimed=int(claimed),
                leads_contacted=int(contacted),
                leads_appointment=int(appointment),
                leads_purchased=int(purchased),
            )
        )
        totals["claimed"] += int(claimed)
        totals["contacted"] += int(contacted)
        totals["appointment"] += int(appointment)
        totals["purchased"] += int(purchased)

    rows.sort(key=lambda r: r.leads_purchased, reverse=True)

    return GroupFunnelResponse(
        group_slug=group.slug,
        group_name=group.name,
        since=since,
        until=until,
        rooftops=rows,
        totals=RooftopFunnelRow(
            dealer_id="(total)",
            leads_claimed=totals["claimed"],
            leads_contacted=totals["contacted"],
            leads_appointment=totals["appointment"],
            leads_purchased=totals["purchased"],
        ),
    )


# ---- Dealership SLA stats -------------------------------------------


class SlaStatsResponse(BaseModel):
    dealer_id: str
    since: datetime
    until: datetime
    sla_minutes: int
    leads_total: int
    leads_responded: int
    leads_unresponded: int
    leads_within_sla: int
    leads_breached: int
    median_response_minutes: float | None
    p90_response_minutes: float | None
    avg_response_minutes: float | None
    pct_under_5_min: float
    pct_under_30_min: float
    pct_under_2_hr: float


@router.get("/sla", response_model=SlaStatsResponse)
def sla_stats(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
    days: int = Query(30, ge=1, le=365),
    sla_minutes: int = Query(5, ge=1, le=1440),
) -> SlaStatsResponse:
    """Dealership-level first-response SLA stats for the last N days.

    Reads Lead.first_responded_at (stamped by fsbo.crm.response on every
    outbound channel). Median + p90 are the metrics sales managers want;
    the % buckets are the lead-aggregator industry benchmarks (5 min,
    30 min, 2 hr).

    Unresponded leads count toward leads_breached only when older than
    sla_minutes — fresh leads inside the window are pending, not breached.
    """
    until = datetime.now(timezone.utc)
    since = until - timedelta(days=days)
    sla_cutoff = until - timedelta(minutes=sla_minutes)

    rows = db.execute(
        select(Lead.created_at, Lead.first_responded_at).where(
            Lead.dealer_id == dealer_id,
            Lead.created_at >= since,
            Lead.deleted_at.is_(None),
        )
    ).all()

    response_minutes: list[float] = []
    leads_responded = 0
    leads_unresponded_old = 0  # breached
    leads_unresponded_fresh = 0  # in-window, not yet stale
    under_5 = 0
    under_30 = 0
    under_120 = 0

    for created_at, first_at in rows:
        created = (
            created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        )
        if first_at is not None:
            first = (
                first_at if first_at.tzinfo else first_at.replace(tzinfo=timezone.utc)
            )
            minutes = max(0.0, (first - created).total_seconds() / 60.0)
            response_minutes.append(minutes)
            leads_responded += 1
            if minutes <= 5:
                under_5 += 1
            if minutes <= 30:
                under_30 += 1
            if minutes <= 120:
                under_120 += 1
        else:
            if created <= sla_cutoff:
                leads_unresponded_old += 1
            else:
                leads_unresponded_fresh += 1

    leads_total = len(rows)
    leads_within_sla = sum(1 for m in response_minutes if m <= sla_minutes)
    leads_breached = (
        leads_unresponded_old
        + sum(1 for m in response_minutes if m > sla_minutes)
    )

    def _percentile(values: list[float], pct: float) -> float | None:
        if not values:
            return None
        import math

        sorted_v = sorted(values)
        # Nearest-rank percentile (ceil convention) — avoids numpy dep
        # and gives the textbook median (middle value for odd N).
        rank = max(1, math.ceil(pct / 100.0 * len(sorted_v)))
        return round(sorted_v[rank - 1], 1)

    avg = round(sum(response_minutes) / len(response_minutes), 1) if response_minutes else None

    def _pct(numerator: int) -> float:
        return round(100.0 * numerator / leads_total, 1) if leads_total else 0.0

    return SlaStatsResponse(
        dealer_id=dealer_id,
        since=since,
        until=until,
        sla_minutes=sla_minutes,
        leads_total=leads_total,
        leads_responded=leads_responded,
        leads_unresponded=leads_unresponded_old + leads_unresponded_fresh,
        leads_within_sla=leads_within_sla,
        leads_breached=leads_breached,
        median_response_minutes=_percentile(response_minutes, 50.0),
        p90_response_minutes=_percentile(response_minutes, 90.0),
        avg_response_minutes=avg,
        pct_under_5_min=_pct(under_5),
        pct_under_30_min=_pct(under_30),
        pct_under_2_hr=_pct(under_120),
    )


# ---- Cross-lead activity log (manager view) -------------------------


class ActivityRow(BaseModel):
    interaction_id: int
    lead_id: int
    listing_id: int
    listing_title: str | None
    actor: str | None  # who did it (rep email or "system")
    kind: str
    direction: str | None
    body: str | None
    created_at: datetime


class ActivityLogResponse(BaseModel):
    dealer_id: str
    rows: list[ActivityRow]
    has_more: bool


@router.get("/activity", response_model=ActivityLogResponse)
def activity_log(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    kind: str | None = Query(None, description="filter by Interaction.kind"),
    actor: str | None = Query(None, description="filter by Interaction.actor"),
) -> ActivityLogResponse:
    """Manager-facing audit feed across every lead in the dealership.

    Joins Interactions to Leads (scoped to dealer_id) so a manager can
    see who did what on which lead in chronological order. Supports
    paging + per-actor / per-kind filters.

    Note: actor falls back to Lead.assigned_to when Interaction.actor
    is null (e.g. for legacy rows). System-generated rows (auto-close
    on STOP keyword, status changes from webhook fan-out) carry
    actor='system'.
    """

    stmt = (
        select(Interaction, Lead, Listing)
        .join(Lead, Interaction.lead_id == Lead.id)
        .join(Listing, Lead.listing_id == Listing.id)
        .where(Lead.dealer_id == dealer_id)
    )
    if kind:
        stmt = stmt.where(Interaction.kind == kind)
    if actor:
        stmt = stmt.where(Interaction.actor == actor)

    # Fetch one extra to detect has_more without a separate count query.
    stmt = stmt.order_by(Interaction.created_at.desc()).limit(limit + 1).offset(offset)
    rows = db.execute(stmt).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    return ActivityLogResponse(
        dealer_id=dealer_id,
        has_more=has_more,
        rows=[
            ActivityRow(
                interaction_id=interaction.id,
                lead_id=lead.id,
                listing_id=listing.id,
                listing_title=listing.title,
                actor=interaction.actor or lead.assigned_to,
                kind=interaction.kind,
                direction=interaction.direction,
                body=interaction.body,
                created_at=interaction.created_at,
            )
            for interaction, lead, listing in rows
        ],
    )
