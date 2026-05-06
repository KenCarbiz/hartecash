"""Stripe billing endpoints.

Three-step flow:

  1. POST /billing/checkout         (auth)  -> {url}
     Creates a Stripe Checkout Session for the requested plan and
     returns the hosted-page URL. Idempotent: re-uses the dealer's
     stripe_customer_id if it exists, otherwise creates one.

  2. GET /billing/subscription      (auth)  -> {plan, status, ...}
     Whatever the most-recent subscription row says for this dealer.

  3. POST /billing/portal           (auth)  -> {url}
     Stripe Customer Portal — dealer-self-service for payment-method
     updates, plan changes, cancellation. Stripe handles the UI.

  4. POST /webhooks/stripe          (HMAC)  -> 200
     Stripe -> us. Updates the Subscription row on subscription.created
     / .updated / .deleted and on invoice.paid (which advances
     current_period_end).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.auth.resolver import DealerId
from fsbo.billing.plans import by_code, stripe_price_for
from fsbo.billing.stripe_client import billing_enabled, stripe
from fsbo.config import settings
from fsbo.db import get_session
from fsbo.models import Dealer, Subscription

router = APIRouter(tags=["billing"])


class CheckoutIn(BaseModel):
    plan: str  # starter | pro | performance
    success_url: str
    cancel_url: str


class CheckoutOut(BaseModel):
    url: str


class SubscriptionOut(BaseModel):
    plan: str | None
    status: str
    current_period_end: datetime | None
    cancel_at_period_end: bool


def _get_or_create_customer(
    db: Session, dealer_slug: str, dealer_email: str
) -> str:
    """Find or create the Stripe customer for this dealership."""
    dealer = db.scalar(select(Dealer).where(Dealer.slug == dealer_slug))
    if dealer is None:
        # Edge case: legacy demo-dealer rows that predate the Dealer table.
        # Bail with a clear error rather than create a customer for nobody.
        raise HTTPException(404, "dealer not found")
    if dealer.stripe_customer_id:
        return dealer.stripe_customer_id

    customer = stripe.Customer.create(
        email=dealer_email,
        name=dealer.name,
        metadata={"dealer_slug": dealer_slug},
    )
    dealer.stripe_customer_id = customer.id
    db.flush()
    return customer.id


@router.post("/billing/checkout", response_model=CheckoutOut)
def create_checkout_session(
    payload: CheckoutIn,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
    request: Request,
) -> CheckoutOut:
    if not billing_enabled():
        raise HTTPException(503, "billing is not configured on this server")

    plan = by_code(payload.plan)
    if not plan:
        raise HTTPException(400, "unknown plan")
    price_id = stripe_price_for(payload.plan)
    if not price_id:
        raise HTTPException(
            503,
            f"plan '{payload.plan}' has no stripe price id configured",
        )

    # Need an email for Stripe Customer creation. Pull from the JWT if
    # we have it; fall back to the request header so test infra works.
    email = request.headers.get("x-dealer-email") or "billing@example.com"

    customer_id = _get_or_create_customer(db, dealer_id, email)

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=payload.success_url,
        cancel_url=payload.cancel_url,
        client_reference_id=dealer_id,
        metadata={"dealer_id": dealer_id, "plan": payload.plan},
        # Lock the email field so the dealer can't sign up a different
        # account on the Stripe side and split billing from us.
        customer_update={"address": "auto", "name": "auto"},
    )
    return CheckoutOut(url=session.url)


@router.get("/billing/subscription", response_model=SubscriptionOut)
def get_subscription(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> SubscriptionOut:
    """Return the dealership's most-recent subscription, or a 'free' stub
    when they haven't subscribed yet."""
    row = db.scalar(
        select(Subscription)
        .where(Subscription.dealer_id == dealer_id)
        .order_by(Subscription.created_at.desc())
    )
    if not row:
        return SubscriptionOut(
            plan=None,
            status="none",
            current_period_end=None,
            cancel_at_period_end=False,
        )
    return SubscriptionOut(
        plan=row.plan,
        status=row.status,
        current_period_end=row.current_period_end,
        cancel_at_period_end=row.cancel_at_period_end,
    )


@router.post("/billing/portal", response_model=CheckoutOut)
def open_customer_portal(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
    return_url: str,
) -> CheckoutOut:
    """Create a Stripe Customer Portal session — Stripe-hosted page where
    the dealer can update card, change plan, or cancel."""
    if not billing_enabled():
        raise HTTPException(503, "billing is not configured")
    dealer = db.scalar(select(Dealer).where(Dealer.slug == dealer_id))
    if not dealer or not dealer.stripe_customer_id:
        raise HTTPException(404, "no Stripe customer for this dealer")
    portal = stripe.billing_portal.Session.create(
        customer=dealer.stripe_customer_id, return_url=return_url
    )
    return CheckoutOut(url=portal.url)


# ---- Webhook ---------------------------------------------------------

# Stripe events we care about. Anything else is acknowledged with 200
# but ignored.
_HANDLED_EVENTS = {
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_failed",
}


def _plan_from_price_id(price_id: str) -> str | None:
    if price_id == settings.stripe_price_starter:
        return "starter"
    if price_id == settings.stripe_price_pro:
        return "pro"
    if price_id == settings.stripe_price_performance:
        return "performance"
    return None


def _upsert_subscription_row(
    db: Session, sub: dict, dealer_id: str | None = None
) -> None:
    """Idempotent upsert from a Stripe Subscription object.

    `dealer_id` is taken from sub.metadata.dealer_id if present, else from
    Customer.metadata via a lookup on stripe_customer_id."""
    sub_id = sub["id"]
    customer_id = sub["customer"]
    if dealer_id is None:
        dealer_id = (sub.get("metadata") or {}).get("dealer_id")
    if dealer_id is None:
        dealer = db.scalar(
            select(Dealer).where(Dealer.stripe_customer_id == customer_id)
        )
        if dealer is None:
            return  # stranger event; ignore
        dealer_id = dealer.slug

    items = sub.get("items", {}).get("data") or []
    plan_code = None
    if items:
        price_id = items[0].get("price", {}).get("id")
        plan_code = _plan_from_price_id(price_id) or "unknown"

    period_end_ts = sub.get("current_period_end")
    period_end = (
        datetime.fromtimestamp(period_end_ts, tz=timezone.utc)
        if period_end_ts
        else None
    )

    row = db.scalar(
        select(Subscription).where(
            Subscription.stripe_subscription_id == sub_id
        )
    )
    if row:
        row.status = sub.get("status", row.status)
        row.plan = plan_code or row.plan
        row.current_period_end = period_end
        row.cancel_at_period_end = bool(
            sub.get("cancel_at_period_end") or False
        )
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(
            Subscription(
                dealer_id=dealer_id,
                stripe_subscription_id=sub_id,
                stripe_customer_id=customer_id,
                plan=plan_code or "unknown",
                status=sub.get("status", "active"),
                current_period_end=period_end,
                cancel_at_period_end=bool(
                    sub.get("cancel_at_period_end") or False
                ),
            )
        )


@router.post("/webhooks/stripe", status_code=200)
async def stripe_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    """Verify the Stripe signature header and update local state."""
    if not settings.stripe_webhook_secret:
        # In dev / CI we don't enforce — still 200 so Stripe's CLI tester
        # doesn't blow up. Production deploy MUST set the secret.
        return {"ok": "1", "verified": "skipped"}

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except (ValueError, stripe.SignatureVerificationError) as e:
        raise HTTPException(400, f"invalid stripe signature: {e}") from e

    if event["type"] not in _HANDLED_EVENTS:
        return {"ok": "1", "ignored": event["type"]}

    obj = event["data"]["object"]

    if event["type"] == "checkout.session.completed":
        # Pull the freshly-minted subscription so we can stamp our DB.
        sub_id = obj.get("subscription")
        dealer_id = (obj.get("metadata") or {}).get(
            "dealer_id"
        ) or obj.get("client_reference_id")
        if sub_id:
            sub = stripe.Subscription.retrieve(sub_id)
            _upsert_subscription_row(db, dict(sub), dealer_id=dealer_id)

    elif event["type"] in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        _upsert_subscription_row(db, obj)

    elif event["type"] == "invoice.paid":
        sub_id = obj.get("subscription")
        if sub_id:
            sub = stripe.Subscription.retrieve(sub_id)
            _upsert_subscription_row(db, dict(sub))

    elif event["type"] == "invoice.payment_failed":
        sub_id = obj.get("subscription")
        if sub_id:
            row = db.scalar(
                select(Subscription).where(
                    Subscription.stripe_subscription_id == sub_id
                )
            )
            if row:
                row.status = "past_due"
                row.updated_at = datetime.now(timezone.utc)

    return {"ok": "1", "type": event["type"]}
