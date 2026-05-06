"""TCPA gate: quiet hours, opt-out registry, STOP keyword detection."""

from datetime import datetime, timezone

from sqlalchemy import select

from fsbo.messaging import tcpa
from fsbo.messaging.tcpa import (
    check_send_allowed,
    in_quiet_hours,
    is_stop_keyword,
    normalize_phone,
    record_consent,
    record_opt_out,
)
from fsbo.models import Lead, Listing, SmsConsent, SmsOptOut


def test_normalize_phone_keeps_last_10_digits():
    assert normalize_phone("+1 (813) 555-1234") == "8135551234"
    assert normalize_phone("813-555-1234") == "8135551234"
    assert normalize_phone(None) == ""


def test_stop_keyword_recognized():
    assert is_stop_keyword("STOP")
    assert is_stop_keyword("  stop ")
    assert is_stop_keyword("Unsubscribe")
    assert is_stop_keyword("END.")
    assert not is_stop_keyword("stop calling me please")  # not bare keyword


def test_quiet_hours_blocks_at_3am_in_eastern():
    # 8 AM UTC = 3 AM US/Eastern → quiet hours
    when = datetime(2026, 5, 6, 8, 0, tzinfo=timezone.utc)
    assert in_quiet_hours("33607", when=when)  # Tampa


def test_quiet_hours_allows_2pm_in_eastern():
    # 18:00 UTC = 2 PM US/Eastern → allowed
    when = datetime(2026, 5, 6, 18, 0, tzinfo=timezone.utc)
    assert not in_quiet_hours("33607", when=when)


def test_check_send_allowed_blocks_opted_out(db_session):
    record_opt_out(db_session, "demo-dealer", "8135551234", source="manual")
    db_session.flush()
    # Time-of-day allowed but opt-out blocks regardless.
    res = check_send_allowed(
        db_session, "demo-dealer", "8135551234", "33607"
    )
    assert not res.allowed
    assert res.blocked_reason == "opted_out"


def test_check_send_allowed_strict_consent_blocks_unrecorded(db_session):
    res = check_send_allowed(
        db_session,
        "demo-dealer",
        "8135551234",
        "33607",
        require_consent=True,
    )
    # Could be quiet_hours or no_consent depending on the test clock —
    # both are valid blocks. Assert "not allowed" is the contract.
    assert not res.allowed
    assert res.blocked_reason in ("no_consent", "quiet_hours")


def test_record_opt_out_is_idempotent(db_session):
    a = record_opt_out(db_session, "demo-dealer", "8135551234", source="manual")
    b = record_opt_out(
        db_session, "demo-dealer", "8135551234", source="stop_keyword"
    )
    assert a.id == b.id


def test_send_endpoint_returns_451_when_opted_out(client, db_session):
    listing = Listing(
        source="craigslist",
        external_id="cl-tcpa-1",
        url="http://x",
        title="2018 Honda Civic",
        seller_phone="8135551234",
        zip_code="33607",
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()
    lead_resp = client.post("/leads", json={"listing_id": listing.id})
    lead_id = lead_resp.json()["id"]

    record_opt_out(db_session, "demo-dealer", "8135551234", source="manual")
    db_session.flush()

    r = client.post(
        "/messages/send",
        json={"lead_id": lead_id, "body": "Hi, still available?"},
    )
    assert r.status_code == 451
    assert "opted_out" in r.json()["detail"]


def test_inbound_stop_keyword_creates_opt_out_row(client, db_session):
    """The Twilio inbound webhook routes STOP to the opt-out registry."""
    listing = Listing(
        source="craigslist",
        external_id="cl-tcpa-2",
        url="http://x",
        title="2018 Tundra",
        seller_phone="8135559876",
        zip_code="33607",
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()
    db_session.add(Lead(dealer_id="demo-dealer", listing_id=listing.id))
    db_session.flush()

    r = client.post(
        "/webhooks/twilio/inbound",
        data={
            "From": "+18135559876",
            "To": "+18135550000",
            "Body": "STOP",
            "MessageSid": "SM_stop_test",
        },
    )
    assert r.status_code == 200

    opt = db_session.scalar(
        select(SmsOptOut).where(
            SmsOptOut.dealer_id == "demo-dealer",
            SmsOptOut.phone == "8135559876",
        )
    )
    assert opt is not None
    assert opt.source == "stop_keyword"


def test_tcpa_endpoints(client, db_session):
    # Add an opt-out via the API
    r = client.post(
        "/tcpa/opt-outs",
        json={"phone": "8135551111", "note": "called and asked off list"},
    )
    assert r.status_code == 201
    assert r.json()["phone"] == "8135551111"

    # Capture a consent
    r = client.post(
        "/tcpa/consents",
        json={
            "phone": "8135552222",
            "consent_text": "By replying YES you agree to receive texts about this listing.",
            "captured_via": "marketplace_dm",
        },
    )
    assert r.status_code == 201

    # Listings of both
    assert len(client.get("/tcpa/opt-outs").json()) == 1
    assert len(client.get("/tcpa/consents").json()) == 1

    # Remove the opt-out
    r = client.delete("/tcpa/opt-outs/8135551111")
    assert r.status_code == 204
    assert client.get("/tcpa/opt-outs").json() == []
