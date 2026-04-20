"""Admin endpoints for operational tasks.

These are dealer-id-neutral: they affect global state (e.g. recomputing
scores across every listing) and should be firewalled with real auth
before going live. For now they're unauthenticated so the demo dashboard
can hit them, but in production wrap with an admin-only JWT scope.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.db import get_session
from fsbo.enrichment.attributes import extract as extract_attrs
from fsbo.enrichment.dealer_signals import assess as assess_dealer
from fsbo.enrichment.price_tracking import count_drops
from fsbo.enrichment.quality import score_listing
from fsbo.models import Listing
from fsbo.sources.base import NormalizedListing
from fsbo.valuation.market import estimate as estimate_market

router = APIRouter(prefix="/admin", tags=["admin"])


class RescoreOut(BaseModel):
    total: int
    updated: int


@router.post("/rescore", response_model=RescoreOut)
def rescore_all(
    db: Annotated[Session, Depends(get_session)],
    refresh_signals: bool = True,
) -> RescoreOut:
    """Recompute dealer_likelihood, attributes (if refresh_signals), and
    lead_quality_score for every listing. Useful after the scoring formula
    changes. Rescore is idempotent and safe to re-run.
    """
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(Listing)).all()
    updated = 0

    for row in rows:
        if refresh_signals:
            norm = NormalizedListing(
                source=row.source,
                external_id=row.external_id,
                url=row.url,
                title=row.title,
                description=row.description,
                year=row.year,
                make=row.make,
                model=row.model,
                trim=row.trim,
                mileage=row.mileage,
                price=row.price,
                vin=row.vin,
                city=row.city,
                state=row.state,
                zip_code=row.zip_code,
                seller_phone=row.seller_phone,
            )
            dealer = assess_dealer(norm)
            row.dealer_likelihood = dealer.likelihood
            row.scam_score = dealer.scam_score

            enriched = dict(row.raw or {})
            enriched["attributes"] = extract_attrs(norm).as_dict()
            row.raw = enriched

        market = estimate_market(db, row)
        drops = count_drops(db, row.id)
        dom = None
        posted = row.posted_at or row.first_seen_at
        if posted:
            posted_utc = posted if posted.tzinfo else posted.replace(tzinfo=timezone.utc)
            dom = max(0, int((now - posted_utc).total_seconds() / 86400))

        q = score_listing(
            row,
            market={"median": market.median, "sample_size": market.sample_size},
            dealer_likelihood=row.dealer_likelihood,
            scam_score=row.scam_score,
            price_drops=drops,
            days_on_market=dom,
            now=now,
        )
        row.lead_quality_score = q.score
        row.quality_breakdown = q.breakdown
        updated += 1

    return RescoreOut(total=len(rows), updated=updated)
