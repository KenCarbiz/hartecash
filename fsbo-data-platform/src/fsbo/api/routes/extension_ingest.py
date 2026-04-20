"""Endpoints the browser extension hits.

- POST /sources/extension/ingest  — a listing parsed by the extension from a
  page the dealer is currently viewing. We upsert it like any source would.
- GET  /sources/extension/lookup  — "is this URL already in our feed?" The
  extension uses it to decide whether to show the "already indexed" badge
  before optionally ingesting.
- GET  /listings/{id}/duplicates  — listings that dedup-key match this one,
  so dealers can see cross-source duplicates at a glance.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.db import get_session
from fsbo.enrichment.classifier import classify
from fsbo.enrichment.dedup import compute_dedup_key
from fsbo.enrichment.vin import decode_vin
from fsbo.models import Classification, Listing
from fsbo.sources.base import NormalizedListing

router = APIRouter(tags=["extension"])


class ExtensionListing(BaseModel):
    source: str
    external_id: str
    url: str
    title: str | None = None
    description: str | None = None
    year: int | None = None
    make: str | None = None
    model: str | None = None
    mileage: int | None = None
    price: float | None = None
    vin: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    seller_name: str | None = None
    seller_phone: str | None = None
    images: list[str] = []
    posted_at: datetime | None = None


class IngestIn(BaseModel):
    listing: ExtensionListing


class IngestOut(BaseModel):
    listing_id: int
    duplicate: bool


class LookupOut(BaseModel):
    listing_id: int | None
    duplicate: bool


class DuplicateRow(BaseModel):
    id: int
    source: str
    url: str
    posted_at: datetime | None
    dedup_key: str | None


@router.post("/sources/extension/ingest", response_model=IngestOut)
async def ingest(
    payload: IngestIn, db: Annotated[Session, Depends(get_session)]
) -> IngestOut:
    norm = _to_normalized(payload.listing)

    if norm.vin and not (norm.year and norm.make and norm.model):
        decoded = await decode_vin(norm.vin)
        if decoded and not decoded.error_code:
            norm.year = norm.year or decoded.year
            norm.make = norm.make or decoded.make
            norm.model = norm.model or decoded.model
            norm.trim = norm.trim or decoded.trim

    existing = db.scalar(
        select(Listing).where(
            Listing.source == norm.source,
            Listing.external_id == norm.external_id,
        )
    )
    if existing:
        existing.last_seen_at = datetime.now(timezone.utc)
        # Fill in fields the extension found that weren't set before.
        for attr in (
            "title",
            "description",
            "year",
            "make",
            "model",
            "mileage",
            "price",
            "vin",
            "city",
            "state",
            "zip_code",
            "seller_phone",
            "posted_at",
        ):
            if getattr(existing, attr, None) in (None, "") and getattr(norm, attr, None):
                setattr(existing, attr, getattr(norm, attr))
        if not existing.images and norm.images:
            existing.images = norm.images
        return IngestOut(listing_id=existing.id, duplicate=True)

    row = Listing(
        source=norm.source,
        external_id=norm.external_id,
        url=norm.url,
        title=norm.title,
        description=norm.description,
        year=norm.year,
        make=norm.make,
        model=norm.model,
        mileage=norm.mileage,
        price=norm.price,
        vin=norm.vin,
        city=norm.city,
        state=norm.state,
        zip_code=norm.zip_code,
        seller_name=norm.seller_name,
        seller_phone=norm.seller_phone,
        images=norm.images,
        posted_at=norm.posted_at,
        raw={"source": "extension"},
        dedup_key=compute_dedup_key(norm),
        classification=Classification.UNCLASSIFIED.value,
    )
    db.add(row)
    db.flush()

    result = classify(norm)
    row.classification = result.label
    row.classification_confidence = result.confidence
    row.classification_reason = result.reason

    return IngestOut(listing_id=row.id, duplicate=False)


@router.get("/sources/extension/lookup", response_model=LookupOut)
def lookup(
    db: Annotated[Session, Depends(get_session)],
    url: str = Query(..., min_length=5),
) -> LookupOut:
    clean = url.split("?")[0].rstrip("/")
    existing = db.scalar(
        select(Listing).where(Listing.url.like(f"{clean}%")).limit(1)
    )
    if existing:
        return LookupOut(listing_id=existing.id, duplicate=True)
    return LookupOut(listing_id=None, duplicate=False)


@router.get("/listings/{listing_id}/duplicates", response_model=list[DuplicateRow])
def duplicates_of(
    listing_id: int, db: Annotated[Session, Depends(get_session)]
) -> list[DuplicateRow]:
    base = db.get(Listing, listing_id)
    if not base:
        raise HTTPException(404, "listing not found")
    if not base.dedup_key:
        return []
    rows = db.scalars(
        select(Listing)
        .where(Listing.dedup_key == base.dedup_key, Listing.id != base.id)
        .order_by(Listing.posted_at.desc().nulls_last())
        .limit(20)
    ).all()
    return [
        DuplicateRow(
            id=r.id,
            source=r.source,
            url=r.url,
            posted_at=r.posted_at,
            dedup_key=r.dedup_key,
        )
        for r in rows
    ]


def _to_normalized(payload: ExtensionListing) -> NormalizedListing:
    return NormalizedListing(
        source=payload.source,
        external_id=payload.external_id,
        url=payload.url,
        title=payload.title,
        description=payload.description,
        year=payload.year,
        make=payload.make,
        model=payload.model,
        mileage=payload.mileage,
        price=payload.price,
        vin=payload.vin,
        city=payload.city,
        state=payload.state,
        zip_code=payload.zip_code,
        seller_name=payload.seller_name,
        seller_phone=payload.seller_phone,
        images=payload.images or [],
        posted_at=payload.posted_at,
    )
