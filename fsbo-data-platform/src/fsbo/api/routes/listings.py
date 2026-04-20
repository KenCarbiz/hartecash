from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from fsbo.api.schemas import ListingOut, ListingsPage
from fsbo.db import get_session
from fsbo.models import Classification, Listing

router = APIRouter(prefix="/listings", tags=["listings"])


@router.get("", response_model=ListingsPage)
def list_listings(
    db: Annotated[Session, Depends(get_session)],
    source: str | None = None,
    make: str | None = None,
    model: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    mileage_max: int | None = None,
    zip_code: str | None = Query(None, alias="zip"),
    q: str | None = Query(None, description="Case-insensitive text search over title/description"),
    classification: str | None = Query(
        Classification.PRIVATE_SELLER.value,
        description="Filter by classification. Pass empty string to disable.",
    ),
    limit: int = Query(50, le=500),
    offset: int = 0,
) -> ListingsPage:
    stmt = select(Listing)
    count_stmt = select(func.count()).select_from(Listing)

    filters = []
    if source:
        filters.append(Listing.source == source)
    if make:
        filters.append(func.lower(Listing.make) == make.lower())
    if model:
        filters.append(func.lower(Listing.model) == model.lower())
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(Listing.title.ilike(pattern), Listing.description.ilike(pattern))
        )
    if year_min is not None:
        filters.append(Listing.year >= year_min)
    if year_max is not None:
        filters.append(Listing.year <= year_max)
    if price_min is not None:
        filters.append(Listing.price >= price_min)
    if price_max is not None:
        filters.append(Listing.price <= price_max)
    if mileage_max is not None:
        filters.append(Listing.mileage <= mileage_max)
    if zip_code:
        filters.append(Listing.zip_code == zip_code)
    if classification:
        filters.append(Listing.classification == classification)

    for f in filters:
        stmt = stmt.where(f)
        count_stmt = count_stmt.where(f)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Listing.posted_at.desc().nulls_last(), Listing.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return ListingsPage(
        items=[ListingOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{listing_id}", response_model=ListingOut)
def get_listing(
    listing_id: int, db: Annotated[Session, Depends(get_session)]
) -> ListingOut:
    row = db.get(Listing, listing_id)
    if not row:
        raise HTTPException(status_code=404, detail="listing not found")
    return ListingOut.model_validate(row)
