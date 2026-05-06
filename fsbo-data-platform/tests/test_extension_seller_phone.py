"""Seller phone capture from Messenger threads."""

from fsbo.models import Listing


def _seed(db, **overrides):
    row = Listing(
        source=overrides.pop("source", "facebook_marketplace"),
        external_id=overrides.pop("external_id", "fb-1234"),
        url="https://www.facebook.com/marketplace/item/1234",
        title="2018 Ford F-150",
        classification="private_seller",
        **overrides,
    )
    db.add(row)
    db.flush()
    return row


def test_phone_captured_when_listing_has_none(client, db_session):
    listing = _seed(db_session)
    r = client.post(
        "/sources/extension/seller-phone",
        json={
            "listing_id": listing.id,
            "phone": "(813) 555-1234",
            "context": "I'll text you my number, 813-555-1234",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["seller_phone"] == "8135551234"
    db_session.refresh(listing)
    assert listing.seller_phone == "8135551234"
    # Observation logged in raw
    obs = listing.raw["phone_observations"]
    assert len(obs) == 1
    assert obs[0]["phone"] == "8135551234"
    assert "813-555-1234" in obs[0]["context"]


def test_phone_resolves_by_external_id(client, db_session):
    listing = _seed(db_session, external_id="fb-9999")
    r = client.post(
        "/sources/extension/seller-phone",
        json={
            "external_id": "fb-9999",
            "source": "facebook_marketplace",
            "phone": "8135551234",
        },
    )
    assert r.status_code == 200
    assert r.json()["listing_id"] == listing.id


def test_phone_strips_country_code(client, db_session):
    listing = _seed(db_session)
    r = client.post(
        "/sources/extension/seller-phone",
        json={"listing_id": listing.id, "phone": "+1 813 555 1234"},
    )
    assert r.status_code == 200
    assert r.json()["seller_phone"] == "8135551234"


def test_phone_rejects_garbage(client, db_session):
    listing = _seed(db_session)
    r = client.post(
        "/sources/extension/seller-phone",
        json={"listing_id": listing.id, "phone": "not a phone"},
    )
    assert r.status_code == 400


def test_phone_does_not_overwrite_existing(client, db_session):
    listing = _seed(db_session, seller_phone="8131110000")
    r = client.post(
        "/sources/extension/seller-phone",
        json={"listing_id": listing.id, "phone": "8132220000"},
    )
    assert r.status_code == 200
    db_session.refresh(listing)
    # Original phone stays canonical
    assert listing.seller_phone == "8131110000"
    # But the new one is logged for review
    obs_phones = [o["phone"] for o in listing.raw["phone_observations"]]
    assert "8132220000" in obs_phones


def test_phone_unknown_listing_404(client):
    r = client.post(
        "/sources/extension/seller-phone",
        json={"listing_id": 999999, "phone": "8135551234"},
    )
    assert r.status_code == 404
