"""Auto-close leads + auto-mark listings when the seller says sold."""

from datetime import datetime, timezone

from sqlalchemy import select

from fsbo.models import Interaction, Lead, Listing


def _seed(db_session, phone="(813) 555-0101"):
    listing = Listing(
        source="craigslist",
        external_id="cl-sold-1",
        url="http://x",
        title="2018 Honda Accord",
        seller_phone=phone,
        zip_code="33607",
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()
    lead = Lead(dealer_id="demo-dealer", listing_id=listing.id, status="contacted")
    db_session.add(lead)
    db_session.flush()
    return lead, listing


def _post_inbound(client, body: str, from_number: str = "+18135550101"):
    return client.post(
        "/webhooks/twilio/inbound",
        data={
            "From": from_number,
            "To": "+15558675309",
            "Body": body,
            "MessageSid": "SMtest",
        },
    )


def test_inbound_sold_marks_listing_and_closes_lead(client, db_session):
    lead, listing = _seed(db_session)
    r = _post_inbound(client, "Sorry, already sold")
    assert r.status_code == 200

    db_session.refresh(listing)
    db_session.refresh(lead)
    assert listing.sold_at is not None
    assert listing.auto_hidden is True
    assert "already sold" in (listing.sold_signal or "").lower()
    assert lead.status == "lost"

    # Audit interaction was logged
    interactions = db_session.scalars(
        select(Interaction).where(Interaction.lead_id == lead.id)
    ).all()
    assert any(
        i.actor == "system" and i.body and "auto-closed" in i.body
        for i in interactions
    )


def test_inbound_not_for_sale_closes_lead_only(client, db_session):
    lead, listing = _seed(db_session)
    r = _post_inbound(client, "Decided to keep it, thanks")
    assert r.status_code == 200

    db_session.refresh(listing)
    db_session.refresh(lead)
    # Listing isn't marked sold (seller didn't sell, just withdrew)
    assert listing.sold_at is None
    assert lead.status == "lost"


def test_inbound_interested_does_not_auto_close(client, db_session):
    lead, listing = _seed(db_session)
    r = _post_inbound(client, "Yes still available, $19500")
    assert r.status_code == 200

    db_session.refresh(lead)
    assert lead.status == "contacted"  # unchanged


def test_already_purchased_lead_not_re_closed(client, db_session):
    lead, listing = _seed(db_session)
    lead.status = "purchased"
    db_session.flush()
    r = _post_inbound(client, "I sold it")
    assert r.status_code == 200

    db_session.refresh(lead)
    assert lead.status == "purchased"  # don't downgrade
