"""Inbound-reply tracking + mark-as-seen endpoint.

last_inbound_at moves on every inbound seller message (SMS or email).
last_seen_inbound_at moves only when the rep marks the thread read via
POST /leads/{id}/seen. last_inbound_at > last_seen_inbound_at = unread,
which the dashboard surfaces as a bold-row indicator.
"""

from datetime import datetime, timedelta, timezone
from itertools import count

from fsbo.models import Lead, Listing


_ext = count(1)


def _seed(db, dealer="demo-dealer", phone="(813) 555-0100", email=None):
    listing = Listing(
        source="craigslist",
        external_id=f"cl-ub-{next(_ext)}",
        url="http://x",
        title="2018 Honda Accord",
        seller_phone=phone,
        seller_email=email,
        zip_code="33607",
        classification="private_seller",
    )
    db.add(listing)
    db.flush()
    lead = Lead(dealer_id=dealer, listing_id=listing.id, status="new")
    db.add(lead)
    db.flush()
    return lead, listing


def test_inbound_sms_stamps_last_inbound_at(client, db_session):
    lead, _ = _seed(db_session, phone="(813) 555-1234")
    assert lead.last_inbound_at is None

    r = client.post(
        "/webhooks/twilio/inbound",
        data={
            "From": "(813) 555-1234",
            "To": "(813) 555-9999",
            "Body": "still available?",
            "MessageSid": "SM1",
        },
    )
    assert r.status_code == 200
    db_session.refresh(lead)
    assert lead.last_inbound_at is not None
    # Unread: last_inbound_at set, last_seen_inbound_at None.
    assert lead.last_seen_inbound_at is None


def test_inbound_email_stamps_last_inbound_at(client, db_session):
    lead, _ = _seed(db_session, email="seller@example.com")
    assert lead.last_inbound_at is None

    r = client.post(
        "/webhooks/email/inbound",
        data={
            "from": "seller@example.com",
            "to": "leads@dealer.com",
            "subject": "still got the Accord?",
            "text": "is the Honda still for sale?",
        },
    )
    assert r.status_code == 200
    db_session.refresh(lead)
    assert lead.last_inbound_at is not None
    assert lead.last_seen_inbound_at is None


def test_mark_seen_clears_unread(client, db_session):
    lead, _ = _seed(db_session, phone="(813) 555-1234")
    client.post(
        "/webhooks/twilio/inbound",
        data={
            "From": "(813) 555-1234",
            "To": "(813) 555-9999",
            "Body": "still available?",
            "MessageSid": "SM1",
        },
    )
    db_session.refresh(lead)
    last_in = lead.last_inbound_at
    assert last_in is not None

    r = client.post(f"/leads/{lead.id}/seen")
    assert r.status_code == 200
    db_session.refresh(lead)
    # last_seen_inbound_at >= last_inbound_at => no longer unread
    assert lead.last_seen_inbound_at is not None
    assert (
        lead.last_seen_inbound_at.replace(tzinfo=None)
        >= last_in.replace(tzinfo=None)
    )


def test_subsequent_inbound_makes_thread_unread_again(client, db_session):
    lead, _ = _seed(db_session, phone="(813) 555-1234")

    # First inbound + mark seen.
    client.post(
        "/webhooks/twilio/inbound",
        data={
            "From": "(813) 555-1234",
            "To": "x",
            "Body": "first?",
            "MessageSid": "SM1",
        },
    )
    client.post(f"/leads/{lead.id}/seen")
    db_session.refresh(lead)
    seen_at_1 = lead.last_seen_inbound_at
    assert seen_at_1 is not None

    # Backdate the seen timestamp so the second inbound is provably newer.
    lead.last_seen_inbound_at = seen_at_1 - timedelta(seconds=5)
    db_session.flush()

    # Second inbound — now last_inbound_at > last_seen_inbound_at again.
    client.post(
        "/webhooks/twilio/inbound",
        data={
            "From": "(813) 555-1234",
            "To": "x",
            "Body": "still there?",
            "MessageSid": "SM2",
        },
    )
    db_session.refresh(lead)
    assert lead.last_inbound_at is not None
    assert (
        lead.last_inbound_at.replace(tzinfo=None)
        > lead.last_seen_inbound_at.replace(tzinfo=None)
    )


def test_seen_endpoint_404s_for_other_dealer(client, db_session):
    lead, _ = _seed(db_session, dealer="other-dealer")
    r = client.post(f"/leads/{lead.id}/seen")
    assert r.status_code == 404


def test_lead_get_exposes_inbound_fields(client, db_session):
    lead, _ = _seed(db_session, phone="(813) 555-1234")
    body = client.get(f"/leads/{lead.id}").json()
    assert body["last_inbound_at"] is None
    assert body["last_seen_inbound_at"] is None

    client.post(
        "/webhooks/twilio/inbound",
        data={
            "From": "(813) 555-1234",
            "To": "x",
            "Body": "hi",
            "MessageSid": "SM1",
        },
    )
    body = client.get(f"/leads/{lead.id}").json()
    assert body["last_inbound_at"] is not None


def test_outbound_sms_does_not_touch_inbound_fields(client, db_session):
    """Sending an SMS is OUTBOUND — must not flip the unread state."""
    lead, _ = _seed(db_session)
    # Sending requires lead with phone — already seeded.
    r = client.post("/messages/send", json={"lead_id": lead.id, "body": "hey"})
    # status either 200 (twilio noop) or 4xx (bad config); inbound_at must stay None.
    assert r.status_code in (200, 400, 451, 502)
    db_session.refresh(lead)
    assert lead.last_inbound_at is None
