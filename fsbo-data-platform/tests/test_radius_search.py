from fsbo.models import Listing


def _add(db, **kwargs):
    row = Listing(
        source="craigslist",
        external_id=kwargs.pop("external_id"),
        url="http://x",
        title=kwargs.pop("title", "2018 Ford F-150"),
        classification="private_seller",
        **kwargs,
    )
    db.add(row)
    db.flush()
    return row


def test_radius_filters_out_far_listings(client, db_session):
    _add(db_session, external_id="tampa", zip_code="33607", price=20000)      # Tampa
    _add(db_session, external_id="miami", zip_code="33101", price=21000)       # Miami (~280mi)
    _add(db_session, external_id="denver", zip_code="80201", price=19000)      # Denver (~1800mi)

    r = client.get(
        "/listings",
        params={"near_zip": "33607", "radius_miles": 100, "classification": ""},
    )
    assert r.status_code == 200
    body = r.json()
    external_ids = {item["external_id"] for item in body["items"]}
    assert "tampa" in external_ids
    assert "denver" not in external_ids


def test_radius_includes_nearby(client, db_session):
    _add(db_session, external_id="tampa", zip_code="33607", price=20000)
    _add(db_session, external_id="orlando", zip_code="32801", price=21000)  # ~84mi

    r = client.get(
        "/listings",
        params={"near_zip": "33607", "radius_miles": 120, "classification": ""},
    )
    external_ids = {item["external_id"] for item in r.json()["items"]}
    assert external_ids == {"tampa", "orlando"}
