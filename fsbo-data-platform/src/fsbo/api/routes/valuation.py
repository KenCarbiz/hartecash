"""Market value endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fsbo.db import get_session
from fsbo.models import Listing
from fsbo.valuation.market import estimate

router = APIRouter(tags=["valuation"])


class MarketOut(BaseModel):
    sample_size: int
    median: float | None
    p25: float | None
    p75: float | None
    listing_price: float | None
    delta_pct: float | None
    verdict: str


@router.get("/listings/{listing_id}/market", response_model=MarketOut)
def listing_market(
    listing_id: int, db: Annotated[Session, Depends(get_session)]
) -> MarketOut:
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(404, "listing not found")
    est = estimate(db, listing)
    return MarketOut(**est.__dict__)
