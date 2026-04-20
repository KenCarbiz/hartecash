def _tile(**kw):
    base = {
        "source": "facebook_marketplace",
        "external_id": "fb-batch-1",
        "url": "https://www.facebook.com/marketplace/item/111",
        "title": "2019 Ford F-150",
        "year": 2019,
        "price": 25000,
        "city": "Tampa",
        "state": "FL",
        "images": ["https://scontent.fake/1.jpg"],
    }
    base.update(kw)
    return base


def test_batch_inserts_many_thin_tiles(client):
    payload = {
        "listings": [
            _tile(external_id=f"fb-batch-{i}", url=f"https://fb/marketplace/item/{100+i}")
            for i in range(5)
        ]
    }
    r = client.post("/sources/extension/ingest/batch", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 5
    assert body["inserted"] == 5
    assert body["updated"] == 0
    assert body["rejected"] == 0


def test_batch_second_pass_updates_not_reinsert(client):
    payload = {"listings": [_tile()]}
    client.post("/sources/extension/ingest/batch", json=payload)
    # Re-ingest the same tile
    r = client.post("/sources/extension/ingest/batch", json=payload)
    body = r.json()
    assert body["inserted"] == 0
    assert body["updated"] == 1


def test_batch_rejects_missing_external_id(client):
    payload = {"listings": [_tile(external_id="")]}
    r = client.post("/sources/extension/ingest/batch", json=payload)
    body = r.json()
    assert body["rejected"] == 1
    assert body["inserted"] == 0


def test_batch_fills_only_gaps(client, db_session):
    # First: thin tile
    client.post(
        "/sources/extension/ingest/batch",
        json={"listings": [_tile(title="2019 F-150 (thin)")]},
    )
    # Then the full detail-page /ingest provides richer data
    client.post(
        "/sources/extension/ingest",
        json={
            "listing": {
                "source": "facebook_marketplace",
                "external_id": "fb-batch-1",
                "url": "https://www.facebook.com/marketplace/item/111",
                "title": "2019 Ford F-150 — clean Carfax, one owner",
                "description": "Complete description here",
                "year": 2019,
                "make": "Ford",
                "model": "F-150",
                "price": 25000,
                "city": "Tampa",
                "state": "FL",
            }
        },
    )
    # A subsequent batch with thin data must NOT clobber richer description.
    client.post(
        "/sources/extension/ingest/batch",
        json={"listings": [_tile(title="stale thin title")]},
    )
    from fsbo.models import Listing
    row = db_session.query(Listing).filter_by(external_id="fb-batch-1").first()
    assert row.description == "Complete description here"
    # Make/model were set by the richer pass; batch shouldn't wipe them.
    assert row.make == "Ford"
    assert row.model == "F-150"


def test_batch_tracks_price_changes(client, db_session):
    client.post(
        "/sources/extension/ingest/batch",
        json={"listings": [_tile(price=25000)]},
    )
    client.post(
        "/sources/extension/ingest/batch",
        json={"listings": [_tile(price=23500)]},
    )
    from fsbo.models import Listing, PriceHistory
    row = db_session.query(Listing).filter_by(external_id="fb-batch-1").first()
    assert row.price == 23500
    history = db_session.query(PriceHistory).filter_by(listing_id=row.id).all()
    assert len(history) >= 2
