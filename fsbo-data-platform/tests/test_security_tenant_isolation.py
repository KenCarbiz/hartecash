"""Regression tests for the tenant-isolation hardening.

Before this change, six routers (leads, messages, templates, saved_searches,
activity, ai) declared `dealer_id: DealerIdHeader = Header(alias="X-Dealer-Id")`
and trusted any value the caller sent — even in production. A single curl
with a spoofed header read another dealer's CRM.

These tests pin the new behavior:

  1. In production env_mode, every endpoint that takes a DealerId must
     return 401 when called with no auth at all (no cookie, no bearer,
     no X-Dealer-Id header).

  2. In production env_mode, sending only X-Dealer-Id must still 401 —
     the dev fallback is off.

  3. The unauthenticated /sources/extension/ingest path must also 401.

If any of these regress, an entire dealer's pipeline is exfiltratable.
"""

import pytest


@pytest.fixture
def production_client(client, monkeypatch):
    """Test client running in production env_mode (no dev header fallback).

    Strips the default X-Dealer-Id header that conftest.client injects so
    we can verify behavior on a fully-anonymous request.
    """
    monkeypatch.setattr("fsbo.config.settings.env_mode", "production")
    client.headers.pop("X-Dealer-Id", None)
    return client


# -- Endpoints that must require auth in production -------------------------

# Pairs of (METHOD, PATH, optional JSON body). Path params use a fake id.
PROTECTED_ENDPOINTS: list[tuple[str, str, dict | None]] = [
    # CRM
    ("GET", "/leads", None),
    ("POST", "/leads", {"listing_id": 1}),
    ("GET", "/leads/teammates", None),
    ("GET", "/leads/export.csv", None),
    # Messages
    ("POST", "/messages/send", {"lead_id": 1, "body": "hi"}),
    (
        "POST",
        "/messages/email/send",
        {"lead_id": 1, "subject": "Hi", "body": "Hello"},
    ),
    ("GET", "/leads/1/messages", None),
    # Templates
    ("GET", "/templates", None),
    ("POST", "/templates", {"name": "T", "body": "hi"}),
    # Saved searches
    ("GET", "/saved-searches", None),
    ("POST", "/saved-searches", {"name": "S", "query": {}}),
    # Activity tracker
    ("POST", "/activity/bump", {"messages_sent": 1}),
    ("GET", "/activity/today", None),
    ("GET", "/activity/summary", None),
    # AI
    ("POST", "/ai/opener", {"listing_id": 1}),
    # Listings (corpus is shared but reads still require auth)
    ("GET", "/listings", None),
    ("GET", "/listings/1", None),
    ("PATCH", "/listings/1/facts", {"color": "Red"}),
    ("POST", "/listings/1/history/refresh", None),
    ("GET", "/listings/1/history", None),
    ("GET", "/listings/1/duplicates", None),
    ("GET", "/listings/1/stats", None),
    ("GET", "/listings/1/vehicle-file", None),
    # Extension ingest (the FB Marketplace data plane)
    (
        "POST",
        "/sources/extension/ingest",
        {
            "listing": {
                "source": "facebook_marketplace",
                "external_id": "x",
                "url": "https://fb.com/marketplace/item/x",
            }
        },
    ),
    (
        "POST",
        "/sources/extension/ingest/batch",
        {"listings": []},
    ),
    ("GET", "/sources/extension/lookup?url=https://example.com/x", None),
    (
        "POST",
        "/sources/extension/seller-phone",
        {"listing_id": 1, "phone": "8135551234"},
    ),
    # Telemetry (extension breakage reports)
    (
        "POST",
        "/telemetry/extension-breakage",
        {"kind": "graphql_walker_empty", "url": "https://fb.com/marketplace"},
    ),
    # Extension onboarding (issuing a code is dealer-scoped; exchange is
    # intentionally NOT in this list — it's the unauth-by-design exchange
    # that the extension hits during install).
    ("POST", "/extension/install-code", None),
    # Billing (Stripe webhook is signature-verified, NOT in this list)
    (
        "POST",
        "/billing/checkout",
        {
            "plan": "starter",
            "success_url": "https://example.com/ok",
            "cancel_url": "https://example.com/cancel",
        },
    ),
    ("GET", "/billing/subscription", None),
    ("POST", "/billing/portal?return_url=https://example.com/", None),
    # TCPA opt-out registry + consent ledger (dealer-scoped)
    ("POST", "/tcpa/opt-outs", {"phone": "8135551234"}),
    ("GET", "/tcpa/opt-outs", None),
    ("POST", "/tcpa/consents", {"phone": "8135551234", "consent_text": "yes"}),
    ("GET", "/tcpa/consents", None),
    # AI voice agent (dealer-scoped initiation + read; TwiML endpoints
    # are PUBLIC + signature-verified, NOT in this list)
    ("POST", "/voice/calls", {"lead_id": 1}),
    ("GET", "/voice/calls/1", None),
    ("GET", "/leads/1/voice-calls", None),
    # Offers (dealer-side; public token endpoints are intentionally NOT
    # in this list — they're the seller-facing surface and should work
    # without auth)
    ("POST", "/offers", {"lead_id": 1, "amount_cents": 1500000}),
    ("GET", "/offers/by-lead/1", None),
    ("POST", "/offers/1/withdraw", None),
    # Per-rep leaderboard
    ("GET", "/analytics/leaderboard", None),
    # Lead routing config
    ("GET", "/routing", None),
    ("PUT", "/routing", {"mode": "manual", "pool": []}),
    # Webhook subscriptions (dealer-scoped CRUD + event catalog)
    (
        "POST",
        "/webhooks/subscriptions",
        {
            "name": "demo",
            "url": "https://example.com/hook",
            "event": "lead.status_changed",
            "filters": {},
        },
    ),
    ("GET", "/webhooks/subscriptions", None),
    ("DELETE", "/webhooks/subscriptions/1", None),
    ("GET", "/webhooks/events", None),
    # Multi-rooftop dealer groups
    ("POST", "/groups", {"name": "Acme", "slug": "acme"}),
    ("GET", "/groups/me", None),
    ("POST", "/groups/acme/dealers", {"dealer_slug": "tampa"}),
    ("DELETE", "/groups/acme/dealers/tampa", None),
    ("GET", "/analytics/group-funnel", None),
    # Admin
    ("POST", "/admin/rescore", None),
]


@pytest.mark.parametrize("method,path,body", PROTECTED_ENDPOINTS)
def test_no_auth_rejects_in_production(production_client, method, path, body):
    """An unauthenticated caller must be told to authenticate."""
    r = production_client.request(method, path, json=body)
    assert r.status_code == 401, (
        f"{method} {path} returned {r.status_code} without auth in production "
        f"— this endpoint is unprotected."
    )


@pytest.mark.parametrize("method,path,body", PROTECTED_ENDPOINTS)
def test_spoofed_dealer_header_rejected_in_production(
    production_client, method, path, body
):
    """X-Dealer-Id alone must NOT authenticate in production."""
    r = production_client.request(
        method,
        path,
        json=body,
        headers={"X-Dealer-Id": "any-victim-dealer"},
    )
    assert r.status_code == 401, (
        f"{method} {path} accepted a raw X-Dealer-Id header in production "
        f"({r.status_code}) — header injection bypass."
    )
