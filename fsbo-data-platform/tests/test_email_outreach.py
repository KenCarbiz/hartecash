"""Email outreach channel: POST /messages/email/send.

The email backend defaults to "console" in dev, which logs the
message + reports sent=True. Real backends (SendGrid, SMTP) are
exercised when their env vars are set.
"""

from itertools import count

from sqlalchemy import select

from fsbo.messaging.tcpa import record_opt_out
from fsbo.models import Interaction, Lead, Listing, Message


_ext = count(1)


def _seed(db, *, with_email: str | None = "seller@example.com") -> Lead:
    listing = Listing(
        source="craigslist",
        external_id=f"cl-{next(_ext)}",
        url="http://x",
        title="2018 Honda Accord",
        seller_phone="(813) 555-0100",
        seller_email=with_email,
        zip_code="33607",
        classification="private_seller",
    )
    db.add(listing)
    db.flush()
    lead = Lead(
        dealer_id="demo-dealer",
        listing_id=listing.id,
        status="contacted",
    )
    db.add(lead)
    db.flush()
    return lead


def test_send_email_records_message_and_interaction(client, db_session):
    lead = _seed(db_session)
    r = client.post(
        "/messages/email/send",
        json={
            "lead_id": lead.id,
            "subject": "Quick question about your Accord",
            "body": "Hi, I'm with a local dealership — are you still selling?",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sent"] is True
    assert body["backend"] == "console"

    msg = db_session.scalar(select(Message).where(Message.id == body["message_id"]))
    assert msg is not None
    assert msg.channel == "email"
    assert msg.to_email == "seller@example.com"
    assert msg.subject == "Quick question about your Accord"
    assert msg.status == "sent"

    interactions = db_session.scalars(
        select(Interaction).where(Interaction.lead_id == lead.id)
    ).all()
    assert any(i.kind == "email" and i.direction == "outbound" for i in interactions)


def test_send_email_400s_without_destination(client, db_session):
    lead = _seed(db_session, with_email=None)
    r = client.post(
        "/messages/email/send",
        json={"lead_id": lead.id, "subject": "Hi", "body": "hello"},
    )
    assert r.status_code == 400


def test_send_email_override_to_email(client, db_session):
    lead = _seed(db_session, with_email=None)
    r = client.post(
        "/messages/email/send",
        json={
            "lead_id": lead.id,
            "to_email": "alt@example.com",
            "subject": "x",
            "body": "y",
        },
    )
    assert r.status_code == 200
    msg = db_session.scalar(
        select(Message).where(Message.id == r.json()["message_id"])
    )
    assert msg.to_email == "alt@example.com"


def test_send_email_404s_on_other_dealers_lead(client, db_session):
    lead = _seed(db_session)
    lead.dealer_id = "other-dealer"
    db_session.flush()
    r = client.post(
        "/messages/email/send",
        json={"lead_id": lead.id, "subject": "x", "body": "y"},
    )
    assert r.status_code == 404


def test_send_email_blocks_when_seller_opted_out_of_sms(client, db_session):
    """STOP keyword on SMS should block emails too — a seller who
    said "stop contacting me" shouldn't get emails either."""
    lead = _seed(db_session)
    record_opt_out(db_session, "demo-dealer", "8135550100", source="stop_keyword")
    db_session.flush()

    r = client.post(
        "/messages/email/send",
        json={"lead_id": lead.id, "subject": "x", "body": "y"},
    )
    assert r.status_code == 451
    assert "opted_out" in r.json()["detail"]


def test_email_message_appears_in_unified_feed_with_subject(client, db_session):
    lead = _seed(db_session)
    client.post(
        "/messages/email/send",
        json={
            "lead_id": lead.id,
            "subject": "Cash offer for your truck",
            "body": "We can come Saturday morning.",
        },
    )

    body = client.get(f"/leads/{lead.id}/feed").json()
    msg_entries = [e for e in body["entries"] if e["kind"] == "message:outbound"]
    assert len(msg_entries) == 1
    assert "[email · Cash offer for your truck]" in msg_entries[0]["body"]


def test_messages_list_returns_channel_and_email_fields(client, db_session):
    lead = _seed(db_session)
    client.post(
        "/messages/email/send",
        json={"lead_id": lead.id, "subject": "Hi", "body": "Hello"},
    )
    rows = client.get(f"/leads/{lead.id}/messages").json()
    assert len(rows) == 1
    assert rows[0]["channel"] == "email"
    assert rows[0]["to_email"] == "seller@example.com"
    assert rows[0]["subject"] == "Hi"
