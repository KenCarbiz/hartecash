from fsbo.models import Listing


def _payload(**overrides):
    base = {
        "source": "facebook_marketplace",
        "external_id": "fb-123",
        "url": "https://www.facebook.com/marketplace/item/123",
        "title": "2019 Honda Accord Sport",
        "description": "One owner, clean title, 45k miles",
        "year": 2019,
        "make": "Honda",
        "model": "Accord",
        "price": 22500.0,
        "mileage": 45000,
        "city": "Tampa",
        "state": "FL",
    }
    base.update(overrides)
    return {"listing": base}


def test_ingest_creates_new_listing(client):
    r = client.post("/sources/extension/ingest", json=_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["listing_id"] > 0
    assert body["duplicate"] is False


def test_ingest_second_time_is_duplicate(client):
    client.post("/sources/extension/ingest", json=_payload())
    r = client.post("/sources/extension/ingest", json=_payload())
    body = r.json()
    assert body["duplicate"] is True


def test_ingest_fills_missing_fields(client, db_session):
    # First ingest lacks price
    payload1 = _payload(price=None)
    r1 = client.post("/sources/extension/ingest", json=payload1)
    listing_id = r1.json()["listing_id"]

    # Second ingest provides price — should fill in
    client.post("/sources/extension/ingest", json=_payload(price=22500.0))
    row = db_session.get(Listing, listing_id)
    assert row.price == 22500.0


def test_lookup_unknown_url(client):
    r = client.get(
        "/sources/extension/lookup",
        params={"url": "https://www.facebook.com/marketplace/item/999"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["listing_id"] is None
    assert body["duplicate"] is False


def test_lookup_matches_existing_url(client):
    client.post("/sources/extension/ingest", json=_payload())
    r = client.get(
        "/sources/extension/lookup",
        params={"url": "https://www.facebook.com/marketplace/item/123"},
    )
    assert r.json()["duplicate"] is True


def test_duplicates_by_vin(client, db_session):
    vin = "1HGBH41JXMN109186"
    db_session.add(
        Listing(
            source="craigslist",
            external_id="cl-1",
            url="https://tampa.craigslist.org/1.html",
            title="2018 Ford F-150",
            vin=vin,
            dedup_key=f"vin:{vin}",
            classification="private_seller",
        )
    )
    db_session.add(
        Listing(
            source="facebook_marketplace",
            external_id="fb-1",
            url="https://www.facebook.com/marketplace/item/1",
            title="2018 Ford F-150 same car",
            vin=vin,
            dedup_key=f"vin:{vin}",
            classification="private_seller",
        )
    )
    db_session.flush()

    listings = db_session.query(Listing).all()
    base_id = listings[0].id

    r = client.get(f"/listings/{base_id}/duplicates")
    assert r.status_code == 200
    dups = r.json()
    assert len(dups) == 1
    assert dups[0]["source"] == "facebook_marketplace"
