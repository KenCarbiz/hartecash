"""Source health + scrape run history.

Operational visibility for dealers and admins: are our scrapers actually
producing leads, and how stale is each source?
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fsbo.db import get_session
from fsbo.models import Listing, ScrapeRun

router = APIRouter(tags=["sources"])


class SourceHealth(BaseModel):
    source: str
    total_listings: int
    listings_last_24h: int
    listings_last_7d: int
    last_scrape_at: datetime | None
    last_scrape_error: str | None
    recent_inserted: int
    recent_updated: int


class ScrapeRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    params: dict
    started_at: datetime
    finished_at: datetime | None
    fetched_count: int
    inserted_count: int
    updated_count: int
    error: str | None


@router.get("/sources/health", response_model=list[SourceHealth])
def sources_health(db: Annotated[Session, Depends(get_session)]) -> list[SourceHealth]:
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    source_rows = db.scalars(select(Listing.source).distinct()).all()
    out: list[SourceHealth] = []
    for src in source_rows:
        total = db.scalar(
            select(func.count()).select_from(Listing).where(Listing.source == src)
        ) or 0
        recent_24h = db.scalar(
            select(func.count())
            .select_from(Listing)
            .where(Listing.source == src, Listing.first_seen_at >= cutoff_24h)
        ) or 0
        recent_7d = db.scalar(
            select(func.count())
            .select_from(Listing)
            .where(Listing.source == src, Listing.first_seen_at >= cutoff_7d)
        ) or 0

        last_run = db.scalar(
            select(ScrapeRun)
            .where(ScrapeRun.source == src)
            .order_by(ScrapeRun.started_at.desc())
            .limit(1)
        )

        out.append(
            SourceHealth(
                source=src,
                total_listings=total,
                listings_last_24h=recent_24h,
                listings_last_7d=recent_7d,
                last_scrape_at=last_run.started_at if last_run else None,
                last_scrape_error=last_run.error if last_run else None,
                recent_inserted=last_run.inserted_count if last_run else 0,
                recent_updated=last_run.updated_count if last_run else 0,
            )
        )
    return sorted(out, key=lambda h: h.total_listings, reverse=True)


@router.get("/sources/runs", response_model=list[ScrapeRunOut])
def scrape_runs(
    db: Annotated[Session, Depends(get_session)],
    source: str | None = None,
    limit: int = 50,
) -> list[ScrapeRunOut]:
    stmt = select(ScrapeRun)
    if source:
        stmt = stmt.where(ScrapeRun.source == source)
    rows = db.scalars(stmt.order_by(ScrapeRun.started_at.desc()).limit(limit)).all()
    return [ScrapeRunOut.model_validate(r) for r in rows]
