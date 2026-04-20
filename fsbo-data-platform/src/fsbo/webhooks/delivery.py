"""Webhook dispatch + retry.

Flow:
  1. A listing.created event enqueues WebhookDelivery rows for each matching sub.
  2. The delivery worker pulls pending rows, POSTs payloads with HMAC signature.
  3. On non-2xx, marks next_attempt_at with exponential backoff (up to 5 attempts).
"""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.logging import get_logger
from fsbo.models import Listing, WebhookDelivery, WebhookSubscription

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
    """Create pending delivery rows for all active subs matching this listing."""
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
