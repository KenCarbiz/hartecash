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
