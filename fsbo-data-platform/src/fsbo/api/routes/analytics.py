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
from fsbo.models import Classification, Interaction, Lead, Listing

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

    # Local imports — avoid pulling these into module-load surface
    # for places that only care about the funnel.
    from fsbo.models import Message, Offer, VoiceCall

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
