"""Dealer-scoped webhook subscriptions.

Each subscription belongs to a dealer; events fire only for resources
owned by the same dealer (lead.status_changed, offer.accepted,
offer.declined, voice_call.completed) or globally for shared-corpus
events (listing.created).

Subscriptions are auth-gated: a dealer can list / create / delete
their OWN subs but never see another dealer's. Global listing events
still go to every subscription with event="listing.created" because
the listing corpus is shared and any dealer can subscribe to the
firehose with their own filters.
"""

import secrets
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.auth.resolver import DealerId
from fsbo.db import get_session
from fsbo.models import WebhookSubscription
from fsbo.webhooks.delivery import ALL_EVENTS

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class SubscriptionIn(BaseModel):
    name: str
    url: HttpUrl
    event: str = "listing.created"
    filters: dict = {}


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dealer_id: str
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
    payload: SubscriptionIn,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> SubscriptionCreated:
    if payload.event not in ALL_EVENTS:
        raise HTTPException(
            400, f"unknown event '{payload.event}'. valid: {sorted(ALL_EVENTS)}"
        )
    secret = secrets.token_urlsafe(32)
    sub = WebhookSubscription(
        dealer_id=dealer_id,
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
        dealer_id=sub.dealer_id,
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
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> list[SubscriptionOut]:
    rows = db.scalars(
        select(WebhookSubscription)
        .where(WebhookSubscription.dealer_id == dealer_id)
        .order_by(WebhookSubscription.created_at.desc())
    ).all()
    return [SubscriptionOut.model_validate(r) for r in rows]


@router.delete("/subscriptions/{sub_id}", status_code=204)
def delete_subscription(
    sub_id: int,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> None:
    sub = db.get(WebhookSubscription, sub_id)
    if not sub or sub.dealer_id != dealer_id:
        raise HTTPException(status_code=404, detail="subscription not found")
    sub.active = False


@router.get("/events", response_model=list[str])
def list_supported_events(
    dealer_id: DealerId,
) -> list[str]:
    """Static list of event names a dealer can subscribe to."""
    _ = dealer_id
    return sorted(ALL_EVENTS)
