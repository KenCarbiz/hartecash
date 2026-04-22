from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from fsbo.api.schemas import ListingOut, ListingsPage
from fsbo.auth.resolver import DealerId
from fsbo.db import get_session
from fsbo.enrichment.geocode import GeoPoint, geocode, haversine_miles
from fsbo.models import Classification, Listing

router = APIRouter(prefix="/listings", tags=["listings"])


class ListingFactsPatch(BaseModel):
    """Dealer-entered vehicle facts the scraper can't reliably get (plate,
    color). All fields optional — send only what you're updating. Empty
    string clears the field."""

    license_plate: str | None = Field(None, max_length=16)
    license_plate_state: str | None = Field(None, max_length=4)
    color: str | None = Field(None, max_length=32)
    vin: str | None = Field(None, max_length=17)
    drivable: bool | None = None


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
    near_zip: str | None = Query(
        None, description="Center ZIP for radius search (pair with radius_miles)."
    ),
    radius_miles: int | None = Query(None, ge=1, le=500),
    q: str | None = Query(None, description="Case-insensitive text search over title/description"),
    classification: str | None = Query(
        Classification.PRIVATE_SELLER.value,
        description="Filter by classification. Pass empty string to disable.",
    ),
    min_score: int | None = Query(None, ge=0, le=100),
    sort: str = Query("posted_at", pattern="^(posted_at|score|price)$"),
    show_hidden: bool = Query(
        False,
        description="Include auto-hidden listings (hard-rejected scams, curbstoners, branded titles).",
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
    if min_score is not None:
        filters.append(Listing.lead_quality_score >= min_score)
    if not show_hidden:
        filters.append(Listing.auto_hidden.is_(False))

    for f in filters:
        stmt = stmt.where(f)
        count_stmt = count_stmt.where(f)

    if sort == "score":
        order_by = [
            Listing.lead_quality_score.desc().nulls_last(),
            Listing.posted_at.desc().nulls_last(),
        ]
    elif sort == "price":
        order_by = [Listing.price.asc().nulls_last(), Listing.id.desc()]
    else:
        order_by = [Listing.posted_at.desc().nulls_last(), Listing.id.desc()]

    # Radius search: if near_zip + radius_miles set, geocode the center and
    # distance-filter in-memory after fetching a bounded candidate set.
    center: GeoPoint | None = None
    if near_zip and radius_miles:
        center = geocode(near_zip)

    if center:
        # Pull a larger window so we have enough candidates to filter.
        window = max(limit * 5, 200)
        rows = list(
            db.scalars(stmt.order_by(*order_by).limit(window).offset(offset)).all()
        )
        filtered = []
        for r in rows:
            rp = geocode(r.zip_code) if r.zip_code else None
            if rp is None:
                continue
            if haversine_miles(center, rp) <= radius_miles:
                filtered.append(r)
        total = len(filtered)
        rows = filtered[:limit]
    else:
        total = db.scalar(count_stmt) or 0
        rows = db.scalars(stmt.order_by(*order_by).limit(limit).offset(offset)).all()

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


@router.patch("/{listing_id}/facts", response_model=ListingOut)
def patch_listing_facts(
    listing_id: int,
    payload: ListingFactsPatch,
    dealer_id: DealerId,  # require auth; fact edits are rate-limitable later
    db: Annotated[Session, Depends(get_session)],
) -> ListingOut:
    """Manual vehicle-fact entry.

    Scrapers rarely surface license plates (state + number) or exterior
    color — dealers capture these by asking the seller or reading them
    off a photo. This endpoint lets authenticated users fill them in.
    """
    _ = dealer_id  # any authenticated user at any dealer can enrich a listing
    row = db.get(Listing, listing_id)
    if not row:
        raise HTTPException(status_code=404, detail="listing not found")

    def _clean(v: str | None, upper: bool = False) -> str | None:
        if v is None:
            return None  # field omitted — leave existing value alone
        stripped = v.strip()
        if not stripped:
            return ""  # empty string = clear the field
        return stripped.upper() if upper else stripped

    plate = _clean(payload.license_plate, upper=True)
    state = _clean(payload.license_plate_state, upper=True)
    color = _clean(payload.color)
    vin = _clean(payload.vin, upper=True)

    if plate is not None:
        row.license_plate = plate or None
    if state is not None:
        row.license_plate_state = state or None
    if color is not None:
        row.color = color or None
    if vin is not None:
        row.vin = vin or None
    if "drivable" in payload.model_fields_set:
        row.drivable = payload.drivable

    db.flush()
    return ListingOut.model_validate(row)
