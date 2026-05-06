"""Seller-facing firm cash offers."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from fsbo.models import Interaction, InteractionKind, Lead, Listing, Offer


def _seed(db):
    listing = Listing(
        source="craigslist",
        external_id="cl-offer-1",
        url="http://x",
        title="2018 Honda Accord",
        seller_phone="(813) 555-0101",
        zip_code="33607",
        year=2018,
        make="Honda",
        model="Accord",
        classification="private_seller",
    )
    db.add(listing)
    db.flush()
    lead = Lead(dealer_id="demo-dealer", listing_id=listing.id, status="contacted")
    db.add(lead)
    db.flush()
    return lead, listing


def test_create_offer_mints_public_token_and_logs_interaction(client, db_session):
    lead, listing = _seed(db_session)
    r = client.post(
        "/offers",
        json={
            "lead_id": lead.id,
            "amount_cents": 1850000,  # $18,500
            "breakdown": [
                {"label": "2018 Accord clean baseline", "amount_cents": 1900000},
                {"label": "2022 Carfax accident", "amount_cents": -30000},
                {"label": "Single-owner records bonus", "amount_cents": -20000},
            ],
            "notes": "Comes with 2 keys + service records.",
            "valid_hours": 48,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["amount_cents"] == 1850000
    assert body["status"] == "pending"
    assert body["public_token"]
    assert len(body["public_token"]) >= 24

    # Lead's offered_price ratchets up to the offer amount in dollars
    db_session.refresh(lead)
    assert lead.offered_price == 18500.0

    # Audit interaction logged
    interactions = db_session.scalars(
        select(Interaction).where(Interaction.lead_id == lead.id)
    ).all()
    assert any(
        i.kind == InteractionKind.NOTE.value
        and i.body
        and "offer sent" in i.body
        for i in interactions
    )


def test_create_offer_rejects_other_dealers_lead(client, db_session):
    listing = Listing(
        source="craigslist",
        external_id="cl-offer-other",
        url="http://x",
        title="x",
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()
    db_session.add(Lead(dealer_id="other-dealer", listing_id=listing.id))
    db_session.flush()
    other = db_session.scalar(
        select(Lead).where(Lead.dealer_id == "other-dealer")
    )
    r = client.post(
        "/offers", json={"lead_id": other.id, "amount_cents": 100000}
    )
    assert r.status_code == 404


def test_public_view_does_not_require_auth(client, db_session):
    lead, listing = _seed(db_session)
    create = client.post(
        "/offers", json={"lead_id": lead.id, "amount_cents": 1850000}
    ).json()
    token = create["public_token"]

    # Public endpoint: clear cookies + drop the dev header
    client.cookies.clear()
    client.headers.pop("X-Dealer-Id", None)
    r = client.get(f"/offers/public/{token}")
    assert r.status_code == 200
    body = r.json()
    assert body["amount_cents"] == 1850000
    assert body["status"] == "pending"
    assert body["vehicle_label"] == "2018 Honda Accord"
    assert "expires_in_seconds" in body
    assert body["expires_in_seconds"] > 0


def test_public_view_records_seller_viewed_timestamp(client, db_session):
    lead, listing = _seed(db_session)
    create = client.post(
        "/offers", json={"lead_id": lead.id, "amount_cents": 1850000}
    ).json()
    token = create["public_token"]

    # First public hit stamps seller_viewed_at + logs an Interaction.
    client.cookies.clear()
    client.headers.pop("X-Dealer-Id", None)
    client.get(f"/offers/public/{token}")

    offer = db_session.scalar(
        select(Offer).where(Offer.public_token == token)
    )
    assert offer.seller_viewed_at is not None
    interactions = db_session.scalars(
        select(Interaction).where(Interaction.lead_id == lead.id)
    ).all()
    assert any(
        i.actor == "seller" and i.body and "viewed offer" in i.body
        for i in interactions
    )


def test_public_accept_moves_lead_to_appointment(client, db_session):
    lead, listing = _seed(db_session)
    create = client.post(
        "/offers", json={"lead_id": lead.id, "amount_cents": 1850000}
    ).json()
    token = create["public_token"]

    client.cookies.clear()
    client.headers.pop("X-Dealer-Id", None)
    r = client.post(
        f"/offers/public/{token}/accept",
        json={"note": "Tomorrow morning at 10am works"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "accepted"

    db_session.refresh(lead)
    assert lead.status == "appointment"

    interactions = db_session.scalars(
        select(Interaction).where(Interaction.lead_id == lead.id)
    ).all()
    assert any(
        i.kind == InteractionKind.STATUS_CHANGE.value
        and i.body
        and "ACCEPTED" in i.body
        for i in interactions
    )


def test_public_decline_does_not_change_lead_status(client, db_session):
    lead, listing = _seed(db_session)
    create = client.post(
        "/offers", json={"lead_id": lead.id, "amount_cents": 1850000}
    ).json()
    token = create["public_token"]

    client.cookies.clear()
    client.headers.pop("X-Dealer-Id", None)
    r = client.post(
        f"/offers/public/{token}/decline",
        json={"note": "Too low, looking for $20k"},
    )
    assert r.status_code == 200
    db_session.refresh(lead)
    assert lead.status == "contacted"


def test_expired_offer_cannot_be_accepted(client, db_session):
    lead, listing = _seed(db_session)
    create = client.post(
        "/offers", json={"lead_id": lead.id, "amount_cents": 1850000}
    ).json()
    token = create["public_token"]

    # Force expiry
    offer = db_session.scalar(
        select(Offer).where(Offer.public_token == token)
    )
    offer.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.flush()

    client.cookies.clear()
    client.headers.pop("X-Dealer-Id", None)
    r = client.post(f"/offers/public/{token}/accept", json={})
    assert r.status_code == 410


def test_withdraw_blocks_seller_acceptance(client, db_session):
    lead, listing = _seed(db_session)
    create = client.post(
        "/offers", json={"lead_id": lead.id, "amount_cents": 1850000}
    ).json()
    offer_id = create["id"]
    token = create["public_token"]

    r = client.post(f"/offers/{offer_id}/withdraw")
    assert r.status_code == 200
    assert r.json()["status"] == "withdrawn"

    client.cookies.clear()
    client.headers.pop("X-Dealer-Id", None)
    r = client.post(f"/offers/public/{token}/accept", json={})
    assert r.status_code == 409


def test_list_offers_for_lead(client, db_session):
    lead, listing = _seed(db_session)
    a = client.post(
        "/offers", json={"lead_id": lead.id, "amount_cents": 1700000}
    ).json()
    b = client.post(
        "/offers", json={"lead_id": lead.id, "amount_cents": 1850000}
    ).json()

    r = client.get(f"/offers/by-lead/{lead.id}")
    assert r.status_code == 200
    ids = {x["id"] for x in r.json()}
    assert ids == {a["id"], b["id"]}


def test_unknown_token_returns_404(client):
    client.cookies.clear()
    client.headers.pop("X-Dealer-Id", None)
    r = client.get("/offers/public/notarealtoken")
    assert r.status_code == 404
