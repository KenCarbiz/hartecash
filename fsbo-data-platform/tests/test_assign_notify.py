"""Lead-assignment notifications.

Whenever a lead lands in a rep's queue (auto-routed at create time, bulk
auto-claimed, or manually reassigned), we email the rep so they don't
have to refresh the dashboard. The send is best-effort — alert
preferences are honored, transport errors are swallowed.
"""

from itertools import count

import pytest

from fsbo.messaging.email_client import EmailResult
from fsbo.models import Dealer, Lead, Listing, User


_ext = count(1)


def _seed_listing(db, **overrides) -> Listing:
    base = dict(
        source="craigslist",
        external_id=f"cl-assign-{next(_ext)}",
        url="http://x",
        title="2018 Honda Accord",
        seller_phone="(813) 555-0100",
        zip_code="33607",
        year=2018,
        make="Honda",
        model="Accord",
        price=18500,
        city="Tampa",
        state="FL",
        classification="private_seller",
    )
    base.update(overrides)
    listing = Listing(**base)
    db.add(listing)
    db.flush()
    return listing


def _seed_user(
    db,
    email="rep1@dealer.com",
    dealer_id="demo-dealer",
    alerts_enabled=True,
) -> User:
    user = User(
        email=email,
        password_hash="x",
        name="Rep One",
        dealer_id=dealer_id,
        role="member",
        is_active=True,
        alerts_enabled=alerts_enabled,
    )
    db.add(user)
    db.flush()
    return user


def _seed_dealer_with_routing(db, pool: list[str]) -> Dealer:
    dealer = Dealer(
        slug="demo-dealer",
        name="Demo Dealer",
        routing_mode="least_loaded",
        routing_pool=pool,
    )
    db.add(dealer)
    db.flush()
    return dealer


@pytest.fixture
def email_capture(monkeypatch):
    """Patch send_email at the call site to capture invocations."""
    captured: list[dict] = []

    async def fake_send_email(to, subject, text, html_body=None, from_address=None):
        captured.append({"to": to, "subject": subject, "text": text})
        return EmailResult(backend="test", sent=True)

    monkeypatch.setattr(
        "fsbo.messaging.assign_notify.send_email", fake_send_email, raising=True
    )
    return captured


def test_create_lead_routes_and_notifies_rep(client, db_session, email_capture):
    _seed_user(db_session, email="rep1@dealer.com")
    _seed_dealer_with_routing(db_session, pool=["rep1@dealer.com"])
    listing = _seed_listing(db_session)

    r = client.post("/leads", json={"listing_id": listing.id})
    assert r.status_code == 201
    assert r.json()["assigned_to"] == "rep1@dealer.com"

    assert len(email_capture) == 1
    sent = email_capture[0]
    assert sent["to"] == "rep1@dealer.com"
    assert "Honda" in sent["subject"]
    assert "Tampa" in sent["text"]


def test_create_lead_explicit_assignee_also_notifies(
    client, db_session, email_capture
):
    """Explicit assigned_to (manual pick from the UI) still emails the
    rep so they see it without polling."""
    _seed_user(db_session, email="manual@dealer.com")
    listing = _seed_listing(db_session)

    r = client.post(
        "/leads",
        json={"listing_id": listing.id, "assigned_to": "manual@dealer.com"},
    )
    assert r.status_code == 201

    assert len(email_capture) == 1
    assert email_capture[0]["to"] == "manual@dealer.com"


def test_no_notification_when_user_alerts_disabled(
    client, db_session, email_capture
):
    _seed_user(
        db_session, email="muted@dealer.com", alerts_enabled=False
    )
    listing = _seed_listing(db_session)

    r = client.post(
        "/leads",
        json={"listing_id": listing.id, "assigned_to": "muted@dealer.com"},
    )
    assert r.status_code == 201
    assert email_capture == []


def test_no_notification_when_handle_isnt_a_user(
    client, db_session, email_capture
):
    """Routing pool stores free-text handles. If the handle doesn't
    match a User row (e.g. dealer pre-loaded names before inviting),
    we silently skip — no email, no error."""
    listing = _seed_listing(db_session)

    r = client.post(
        "/leads",
        json={"listing_id": listing.id, "assigned_to": "Pre-loaded Handle"},
    )
    assert r.status_code == 201
    assert email_capture == []


def test_no_notification_for_unassigned_lead(client, db_session, email_capture):
    listing = _seed_listing(db_session)
    r = client.post("/leads", json={"listing_id": listing.id})
    assert r.status_code == 201
    assert r.json()["assigned_to"] is None
    assert email_capture == []


def test_bulk_assign_notifies_only_changed_leads(
    client, db_session, email_capture
):
    _seed_user(db_session, email="newowner@dealer.com")
    listing_a = _seed_listing(db_session)
    listing_b = _seed_listing(db_session)
    lead_a = Lead(
        dealer_id="demo-dealer",
        listing_id=listing_a.id,
        assigned_to="oldowner@dealer.com",
    )
    lead_b = Lead(
        dealer_id="demo-dealer",
        listing_id=listing_b.id,
        assigned_to="newowner@dealer.com",  # already correct, should skip
    )
    db_session.add_all([lead_a, lead_b])
    db_session.flush()

    r = client.post(
        "/leads/bulk-assign",
        json={
            "lead_ids": [lead_a.id, lead_b.id],
            "assigned_to": "newowner@dealer.com",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] == 1
    assert body["skipped"] == 1

    assert len(email_capture) == 1
    sent = email_capture[0]
    assert sent["to"] == "newowner@dealer.com"
    # Reassignment context surfaced so the rep knows it's a handoff.
    assert "Reassigned from" in sent["text"]


def test_bulk_assign_unassign_does_not_notify(
    client, db_session, email_capture
):
    listing = _seed_listing(db_session)
    lead = Lead(
        dealer_id="demo-dealer",
        listing_id=listing.id,
        assigned_to="rep@dealer.com",
    )
    db_session.add(lead)
    db_session.flush()

    r = client.post(
        "/leads/bulk-assign",
        json={"lead_ids": [lead.id], "assigned_to": None},
    )
    assert r.status_code == 200
    assert email_capture == []


def test_bulk_claim_with_routing_notifies_each_new_lead(
    client, db_session, email_capture
):
    _seed_user(db_session, email="rep1@dealer.com")
    _seed_user(db_session, email="rep2@dealer.com")
    _seed_dealer_with_routing(
        db_session, pool=["rep1@dealer.com", "rep2@dealer.com"]
    )
    listing_1 = _seed_listing(db_session)
    listing_2 = _seed_listing(db_session)

    r = client.post(
        "/leads/bulk-claim",
        json={"listing_ids": [listing_1.id, listing_2.id]},
    )
    assert r.status_code == 200
    assert r.json()["claimed"] == 2

    # Distributes across the pool — both reps get notified once.
    addressed = sorted(s["to"] for s in email_capture)
    assert addressed == ["rep1@dealer.com", "rep2@dealer.com"]
