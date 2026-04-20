import secrets
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.db import get_session
from fsbo.models import WebhookSubscription

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class SubscriptionIn(BaseModel):
    name: str
    url: HttpUrl
    event: str = "listing.created"
    filters: dict = {}


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    event: str
    filters: dict
    active: bool
    created_at: datetime


class SubscriptionCreated(SubscriptionOut):
    secret: str  # only returned once, on create


@router.post("/subscriptions", response_model=SubscriptionCreated, status_code=201)
def create_subscription(
    payload: SubscriptionIn, db: Annotated[Session, Depends(get_session)]
) -> SubscriptionCreated:
    secret = secrets.token_urlsafe(32)
    sub = WebhookSubscription(
        name=payload.name,
        url=str(payload.url),
        secret=secret,
        event=payload.event,
        filters=payload.filters,
    )
    db.add(sub)
    db.flush()
    return SubscriptionCreated(
        id=sub.id,
        name=sub.name,
        url=sub.url,
        event=sub.event,
        filters=sub.filters,
        active=sub.active,
        created_at=sub.created_at,
        secret=secret,
    )


@router.get("/subscriptions", response_model=list[SubscriptionOut])
def list_subscriptions(
    db: Annotated[Session, Depends(get_session)],
) -> list[SubscriptionOut]:
    rows = db.scalars(select(WebhookSubscription)).all()
    return [SubscriptionOut.model_validate(r) for r in rows]


@router.delete("/subscriptions/{sub_id}", status_code=204)
def delete_subscription(
    sub_id: int, db: Annotated[Session, Depends(get_session)]
) -> None:
    sub = db.get(WebhookSubscription, sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="subscription not found")
    sub.active = False
