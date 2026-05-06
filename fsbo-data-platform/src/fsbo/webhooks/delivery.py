"""Webhook dispatch + retry.

Flow:
  1. A domain event (listing.created, lead.status_changed, offer.accepted,
     offer.declined, voice_call.completed) enqueues WebhookDelivery rows
     for each matching active subscription.
  2. The delivery worker pulls pending rows, POSTs payloads with HMAC
     signature in the X-FSBO-Signature header.
  3. On non-2xx, marks next_attempt_at with exponential backoff
     (up to 5 attempts).

Dealer scoping:
- listing.created fires globally — the corpus is shared, dealers
  subscribe with filters (e.g. {"state": "FL"}) to slice it.
- All other events are dealer-scoped: only subscriptions belonging
  to the same dealer as the resource get a delivery.
"""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.logging import get_logger
from fsbo.models import (
    Lead,
    Listing,
    Offer,
    VoiceCall,
    WebhookDelivery,
    WebhookSubscription,
)

# Canonical event names. The first is global (cross-dealer); the rest
# are dealer-scoped — the enqueue helper filters subs by dealer_id.
GLOBAL_EVENTS = {"listing.created"}
DEALER_EVENTS = {
    "lead.status_changed",
    "offer.accepted",
    "offer.declined",
    "voice_call.completed",
}
ALL_EVENTS = GLOBAL_EVENTS | DEALER_EVENTS

log = get_logger(__name__)

_MAX_ATTEMPTS = 5
_BACKOFF_SECONDS = [30, 120, 600, 3600, 21600]


def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def listing_payload(listing: Listing) -> dict:
    return {
        "event": "listing.created",
        "listing": {
            "id": listing.id,
            "source": listing.source,
            "external_id": listing.external_id,
            "url": listing.url,
            "title": listing.title,
            "year": listing.year,
            "make": listing.make,
            "model": listing.model,
            "trim": listing.trim,
            "mileage": listing.mileage,
            "price": listing.price,
            "vin": listing.vin,
            "city": listing.city,
            "state": listing.state,
            "zip_code": listing.zip_code,
            "classification": listing.classification,
            "posted_at": listing.posted_at.isoformat() if listing.posted_at else None,
        },
    }


def matches_filters(listing: Listing, filters: dict) -> bool:
    """Subscription filters are an AND-joined dict of equality checks."""
    for key, value in (filters or {}).items():
        actual = getattr(listing, key, None)
        if isinstance(value, list):
            if actual not in value:
                return False
        else:
            if actual != value:
                return False
    return True


def enqueue_for_listing(db: Session, listing: Listing) -> int:
    """Create pending delivery rows for all active subs matching this listing.
    listing.created is GLOBAL — every active subscription with the
    matching event + matching filters gets a row."""
    subs = db.scalars(
        select(WebhookSubscription).where(
            WebhookSubscription.active.is_(True),
            WebhookSubscription.event == "listing.created",
        )
    ).all()

    count = 0
    payload = listing_payload(listing)
    now = datetime.now(timezone.utc)
    for sub in subs:
        if not matches_filters(listing, sub.filters):
            continue
        db.add(
            WebhookDelivery(
                subscription_id=sub.id,
                listing_id=listing.id,
                event="listing.created",
                payload=payload,
                status="pending",
                next_attempt_at=now,
            )
        )
        count += 1
    return count


def _enqueue_dealer_scoped(
    db: Session,
    *,
    event: str,
    dealer_id: str,
    payload: dict[str, Any],
    listing_id: int | None = None,
) -> int:
    """Common helper: fan an event out to every active subscription
    belonging to `dealer_id` for this event type. Returns the number of
    delivery rows created."""
    if event not in DEALER_EVENTS:
        raise ValueError(
            f"event {event!r} is not in DEALER_EVENTS — use enqueue_for_listing"
        )
    subs = db.scalars(
        select(WebhookSubscription).where(
            WebhookSubscription.active.is_(True),
            WebhookSubscription.event == event,
            WebhookSubscription.dealer_id == dealer_id,
        )
    ).all()
    if not subs:
        return 0

    now = datetime.now(timezone.utc)
    count = 0
    for sub in subs:
        db.add(
            WebhookDelivery(
                subscription_id=sub.id,
                listing_id=listing_id or 0,
                event=event,
                payload=payload,
                status="pending",
                next_attempt_at=now,
            )
        )
        count += 1
    return count


def lead_payload(lead: Lead, *, prev_status: str | None = None) -> dict[str, Any]:
    return {
        "event": "lead.status_changed",
        "lead": {
            "id": lead.id,
            "dealer_id": lead.dealer_id,
            "listing_id": lead.listing_id,
            "assigned_to": lead.assigned_to,
            "status": lead.status,
            "prev_status": prev_status,
            "offered_price": lead.offered_price,
            "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
        },
    }


def offer_payload(offer: Offer, kind: str) -> dict[str, Any]:
    """`kind` is the event suffix: 'accepted' or 'declined'."""
    return {
        "event": f"offer.{kind}",
        "offer": {
            "id": offer.id,
            "dealer_id": offer.dealer_id,
            "lead_id": offer.lead_id,
            "listing_id": offer.listing_id,
            "amount_cents": offer.amount_cents,
            "status": offer.status,
            "seller_response_at": offer.seller_response_at.isoformat()
            if offer.seller_response_at
            else None,
            "seller_response_note": offer.seller_response_note,
        },
    }


def voice_call_payload(call: VoiceCall) -> dict[str, Any]:
    return {
        "event": "voice_call.completed",
        "voice_call": {
            "id": call.id,
            "dealer_id": call.dealer_id,
            "lead_id": call.lead_id,
            "duration_seconds": call.duration_seconds,
            "status": call.status,
            "intake": dict(call.intake or {}),
            "turn_count": len(call.turns or []),
        },
    }


def enqueue_for_lead_status_change(
    db: Session, lead: Lead, prev_status: str | None
) -> int:
    return _enqueue_dealer_scoped(
        db,
        event="lead.status_changed",
        dealer_id=lead.dealer_id,
        payload=lead_payload(lead, prev_status=prev_status),
        listing_id=lead.listing_id,
    )


def enqueue_for_offer_response(db: Session, offer: Offer) -> int:
    if offer.status not in ("accepted", "declined"):
        return 0
    return _enqueue_dealer_scoped(
        db,
        event=f"offer.{offer.status}",
        dealer_id=offer.dealer_id,
        payload=offer_payload(offer, offer.status),
        listing_id=offer.listing_id,
    )


def enqueue_for_voice_call_completed(db: Session, call: VoiceCall) -> int:
    return _enqueue_dealer_scoped(
        db,
        event="voice_call.completed",
        dealer_id=call.dealer_id,
        payload=voice_call_payload(call),
    )


async def deliver_pending(db: Session, batch_size: int = 25) -> int:
    """Deliver up to batch_size pending webhooks. Returns number attempted."""
    now = datetime.now(timezone.utc)
    deliveries = db.scalars(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.status == "pending",
            WebhookDelivery.next_attempt_at <= now,
        )
        .limit(batch_size)
    ).all()

    if not deliveries:
        return 0

    async with httpx.AsyncClient(timeout=10.0) as client:
        for d in deliveries:
            sub = db.get(WebhookSubscription, d.subscription_id)
            if not sub or not sub.active:
                d.status = "cancelled"
                continue
            await _attempt(client, db, d, sub)

    return len(deliveries)


async def _attempt(
    client: httpx.AsyncClient, db: Session, d: WebhookDelivery, sub: WebhookSubscription
) -> None:
    body = json.dumps(d.payload, separators=(",", ":")).encode()
    signature = sign_payload(sub.secret, body)
    d.attempts += 1
    try:
        resp = await client.post(
            sub.url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-FSBO-Event": d.event,
                "X-FSBO-Signature": signature,
                "X-FSBO-Delivery-Id": str(d.id),
            },
        )
        d.last_status_code = resp.status_code
        if 200 <= resp.status_code < 300:
            d.status = "delivered"
            d.delivered_at = datetime.now(timezone.utc)
            d.next_attempt_at = None
            return
        d.last_error = f"HTTP {resp.status_code}: {resp.text[:500]}"
    except httpx.HTTPError as e:
        d.last_error = str(e)[:500]

    if d.attempts >= _MAX_ATTEMPTS:
        d.status = "failed"
        d.next_attempt_at = None
    else:
        delay = _BACKOFF_SECONDS[min(d.attempts - 1, len(_BACKOFF_SECONDS) - 1)]
        d.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        log.info(
            "webhook.retry",
            delivery_id=d.id,
            attempts=d.attempts,
            retry_in_seconds=delay,
            error=d.last_error,
        )
