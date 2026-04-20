"""AI-assisted endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fsbo.ai.opener import generate_opener
from fsbo.db import get_session
from fsbo.models import Listing

router = APIRouter(prefix="/ai", tags=["ai"])

DealerIdHeader = Annotated[str, Header(alias="X-Dealer-Id")]


class OpenerIn(BaseModel):
    listing_id: int
    tone: str = "direct"  # direct | friendly | cash-buyer


class OpenerOut(BaseModel):
    listing_id: int
    tone: str
    message: str


@router.post("/opener", response_model=OpenerOut)
def ai_opener(
    payload: OpenerIn,
    dealer_id: DealerIdHeader,  # reserved for usage metering per dealer
    db: Annotated[Session, Depends(get_session)],
) -> OpenerOut:
    _ = dealer_id  # usage metering hook-in point
    listing = db.get(Listing, payload.listing_id)
    if not listing:
        raise HTTPException(404, "listing not found")
    message = generate_opener(listing, tone=payload.tone)
    return OpenerOut(listing_id=listing.id, tone=payload.tone, message=message)
