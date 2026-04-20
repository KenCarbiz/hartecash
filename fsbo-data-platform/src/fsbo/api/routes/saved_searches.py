"""Saved searches: named filter presets that dealers can re-run and alert on."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.db import get_session
from fsbo.models import SavedSearch

router = APIRouter(prefix="/saved-searches", tags=["saved-searches"])

DealerIdHeader = Annotated[str, Header(alias="X-Dealer-Id")]


class SavedSearchIn(BaseModel):
    name: str
    query: dict
    alerts_enabled: bool = False


class SavedSearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dealer_id: str
    name: str
    query: dict
    alerts_enabled: bool
    last_run_at: datetime | None
    created_at: datetime


@router.get("", response_model=list[SavedSearchOut])
def list_searches(
    dealer_id: DealerIdHeader, db: Annotated[Session, Depends(get_session)]
) -> list[SavedSearchOut]:
    rows = db.scalars(
        select(SavedSearch)
        .where(SavedSearch.dealer_id == dealer_id)
        .order_by(SavedSearch.created_at.desc())
    ).all()
    return [SavedSearchOut.model_validate(r) for r in rows]


@router.post("", response_model=SavedSearchOut, status_code=201)
def create_search(
    payload: SavedSearchIn,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> SavedSearchOut:
    existing = db.scalar(
        select(SavedSearch).where(
            SavedSearch.dealer_id == dealer_id, SavedSearch.name == payload.name
        )
    )
    if existing:
        existing.query = payload.query
        existing.alerts_enabled = payload.alerts_enabled
        db.flush()
        return SavedSearchOut.model_validate(existing)

    row = SavedSearch(
        dealer_id=dealer_id,
        name=payload.name,
        query=payload.query,
        alerts_enabled=payload.alerts_enabled,
    )
    db.add(row)
    db.flush()
    return SavedSearchOut.model_validate(row)


@router.delete("/{search_id}", status_code=204)
def delete_search(
    search_id: int,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> None:
    row = db.get(SavedSearch, search_id)
    if not row or row.dealer_id != dealer_id:
        raise HTTPException(404, "saved search not found")
    db.delete(row)
