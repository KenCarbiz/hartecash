"""Stripe billing endpoints.

In dev/CI we don't talk to real Stripe. Tests cover:

  - The checkout endpoint short-circuits with 503 when stripe isn't
    configured, so we don't accidentally fire a real Stripe call from
    a test run.
  - GET /billing/subscription returns "none" for dealerships that
    haven't subscribed yet.
  - The webhook accepts events when no webhook secret is configured
    (dev mode passthrough).
  - Plan catalog matches what the pricing page advertises.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from fsbo.billing.plans import PLANS, by_code
from fsbo.models import Dealer, Subscription


def test_plan_catalog_has_three_skus():
    codes = {p.code for p in PLANS}
    assert codes == {"starter", "pro", "performance"}


def test_starter_pricing_is_249_a_month():
    starter = by_code("starter")
    assert starter is not None
    assert starter.monthly_price_cents == 24900


def test_pro_pricing_is_799_a_month():
    pro = by_code("pro")
    assert pro is not None
    assert pro.monthly_price_cents == 79900


def test_performance_is_zero_dollar_with_metered_acquisition():
    perf = by_code("performance")
    assert perf is not None
    assert perf.monthly_price_cents == 0
    assert perf.capabilities["metered_per_acquisition_cents"] == 25000


def test_checkout_returns_503_when_stripe_not_configured(client):
    r = client.post(
        "/billing/checkout",
        json={
            "plan": "starter",
            "success_url": "https://example.com/ok",
            "cancel_url": "https://example.com/cancel",
        },
    )
    assert r.status_code == 503
    assert "billing" in r.json()["detail"].lower()


def test_subscription_none_for_unsubscribed_dealer(client):
    r = client.get("/billing/subscription")
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] is None
    assert body["status"] == "none"


def test_subscription_returns_most_recent_row(client, db_session):
    """Pin timestamps explicitly — SQLite's default-now is millisecond-
    coarse and the two flushed rows can collide on created_at, making
    'most recent' order-dependent."""
    now = datetime.now(timezone.utc)
    db_session.add(
        Subscription(
            dealer_id="demo-dealer",
            stripe_subscription_id="sub_old",
            stripe_customer_id="cus_1",
            plan="starter",
            status="canceled",
            current_period_end=now - timedelta(days=10),
            created_at=now - timedelta(hours=1),
            updated_at=now - timedelta(hours=1),
        )
    )
    db_session.add(
        Subscription(
            dealer_id="demo-dealer",
            stripe_subscription_id="sub_new",
            stripe_customer_id="cus_1",
            plan="pro",
            status="active",
            current_period_end=now + timedelta(days=20),
            created_at=now,
            updated_at=now,
        )
    )
    db_session.flush()

    body = client.get("/billing/subscription").json()
    assert body["plan"] == "pro"
    assert body["status"] == "active"


def test_webhook_accepts_when_no_secret_configured(client):
    """Dev/CI passthrough: events get a 200 + skipped marker so the
    Stripe CLI doesn't blow up during local plumbing tests."""
    r = client.post(
        "/webhooks/stripe",
        json={"type": "checkout.session.completed", "data": {"object": {}}},
    )
    assert r.status_code == 200
    assert r.json().get("verified") == "skipped"


def test_portal_404s_for_dealer_without_stripe_customer(
    client, db_session, monkeypatch
):
    # Even with billing "enabled" in settings, a dealer without a
    # stripe_customer_id can't open the portal.
    monkeypatch.setattr(
        "fsbo.config.settings.stripe_secret_key", "sk_test_foo"
    )
    db_session.add(Dealer(slug="demo-dealer", name="Demo Dealer"))
    db_session.flush()
    r = client.post(
        "/billing/portal",
        params={"return_url": "https://example.com/"},
    )
    assert r.status_code == 404
