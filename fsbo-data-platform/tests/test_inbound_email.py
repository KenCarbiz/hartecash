"""Inbound email parsing — SendGrid Inbound Parse webhook target."""

from itertools import count

from sqlalchemy import select

from fsbo.models import Interaction, Lead, Listing, Message


_ext = count(1)


def _seed(db, *, seller_email="seller@example.com") -> Lead:
    listing = Listing(
        source="craigslist",
        external_id=f"cl-{next(_ext)}",
        url="http://x",
        title="2018 Honda Accord",
        seller_email=seller_email,
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


def _post_email(client, **fields):
    base = {
        "from": "seller@example.com",
        "to": "leads@inbound.autoacquisition.io",
        "subject": "Re: your inquiry",
        "text": "Yes still available, $19500",
    }
    base.update(fields)
    return client.post("/webhooks/email/inbound", data=base)


def test_routes_inbound_to_lead_by_seller_email(client, db_session):
    lead = _seed(db_session)
    r = _post_email(client)
    assert r.status_code == 200
    assert r.json()["matched"] == str(lead.id)

    msg = db_session.scalar(select(Message).where(Message.lead_id == lead.id))
    assert msg is not None
    assert msg.channel == "email"
    assert msg.direction == "inbound"
    assert msg.from_email == "seller@example.com"
    assert "still available" in (msg.body or "").lower()


def test_strips_name_from_from_header(client, db_session):
    lead = _seed(db_session, seller_email="jane@example.com")
    r = _post_email(client, **{"from": "Jane Doe <jane@example.com>"})
    assert r.status_code == 200
    assert r.json()["matched"] == str(lead.id)


def test_unknown_sender_returns_no_match(client, db_session):
    _seed(db_session, seller_email="known@example.com")
    r = _post_email(client, **{"from": "stranger@example.com"})
    assert r.status_code == 200
    assert r.json()["matched"] == "none"
    # No Message rows created for unmatched senders
    msgs = db_session.scalars(select(Message)).all()
    assert msgs == []


def test_falls_back_to_html_when_text_missing(client, db_session):
    lead = _seed(db_session)
    r = _post_email(
        client,
        text="",
        html="<html><body>Yes <b>still</b> available</body></html>",
    )
    assert r.status_code == 200
    msg = db_session.scalar(select(Message).where(Message.lead_id == lead.id))
    # HTML tags stripped to readable text
    assert "<b>" not in msg.body
    assert "still" in msg.body


def test_sold_intent_auto_closes_lead(client, db_session):
    lead = _seed(db_session)
    r = _post_email(client, text="Sorry, already sold last week")
    assert r.status_code == 200

    db_session.refresh(lead)
    assert lead.status == "lost"

    # Listing should also be marked sold
    listing = db_session.get(Listing, lead.listing_id)
    assert listing.sold_at is not None
    assert listing.auto_hidden is True

    interactions = db_session.scalars(
        select(Interaction).where(Interaction.lead_id == lead.id)
    ).all()
    assert any(
        i.actor == "system" and "auto-closed" in (i.body or "")
        for i in interactions
    )


def test_not_for_sale_intent_closes_lead_only(client, db_session):
    lead = _seed(db_session)
    _post_email(client, text="Decided to keep it, thanks anyway")
    db_session.refresh(lead)
    assert lead.status == "lost"
    listing = db_session.get(Listing, lead.listing_id)
    assert listing.sold_at is None  # listing not marked sold


def test_token_check_rejects_when_configured(client, monkeypatch):
    monkeypatch.setattr(
        "fsbo.config.settings.inbound_email_token", "shared-secret"
    )
    r = client.post(
        "/webhooks/email/inbound",
        data={"from": "x@y.com", "to": "z@a.b", "subject": "x", "text": "y"},
    )
    assert r.status_code == 403


def test_token_check_passes_with_correct_token(client, db_session, monkeypatch):
    _seed(db_session)
    monkeypatch.setattr(
        "fsbo.config.settings.inbound_email_token", "shared-secret"
    )
    r = client.post(
        "/webhooks/email/inbound?token=shared-secret",
        data={
            "from": "seller@example.com",
            "to": "leads@inbound.example.com",
            "subject": "hi",
            "text": "Yes still available",
        },
    )
    assert r.status_code == 200


def test_dev_mode_skips_token_check_when_unconfigured(client, db_session):
    """Default empty token -> webhook accepts anything in dev/CI."""
    _seed(db_session)
    r = client.post(
        "/webhooks/email/inbound",
        data={
            "from": "seller@example.com",
            "to": "x@y.com",
            "subject": "x",
            "text": "Yes still available",
        },
    )
    assert r.status_code == 200
