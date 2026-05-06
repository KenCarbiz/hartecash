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


def test_radius_total_counts_only_in_radius(client, db_session):
    """Regression: previous impl counted unfiltered candidates within a
    5x window. `total` should equal the number of listings within the
    radius, not within some arbitrary candidate window."""
    _add(db_session, external_id="tampa-a", zip_code="33607", price=20000)
    _add(db_session, external_id="tampa-b", zip_code="33607", price=21000)
    _add(db_session, external_id="orlando", zip_code="32801", price=22000)  # ~84mi
    _add(db_session, external_id="miami", zip_code="33101", price=23000)  # ~280mi
    _add(db_session, external_id="denver", zip_code="80201", price=24000)  # ~1800mi

    r = client.get(
        "/listings",
        params={"near_zip": "33607", "radius_miles": 50, "classification": ""},
    )
    body = r.json()
    # Only tampa-a + tampa-b are inside 50mi of 33607 (Orlando is ~84mi).
    assert body["total"] == 2
    assert {i["external_id"] for i in body["items"]} == {"tampa-a", "tampa-b"}


def test_radius_pagination_offsets_into_filtered_set(client, db_session):
    """Regression: paginating past page 1 should slice into the
    filtered (within-radius) set, not the pre-filter candidate window."""
    # Seed 5 in-radius listings (all in 33607).
    for i in range(5):
        _add(db_session, external_id=f"tampa-{i}", zip_code="33607", price=20000 + i)
    # Plus a far listing that should never appear regardless of offset.
    _add(db_session, external_id="denver", zip_code="80201", price=19000)

    page1 = client.get(
        "/listings",
        params={
            "near_zip": "33607",
            "radius_miles": 50,
            "classification": "",
            "limit": 2,
            "offset": 0,
        },
    ).json()
    page2 = client.get(
        "/listings",
        params={
            "near_zip": "33607",
            "radius_miles": 50,
            "classification": "",
            "limit": 2,
            "offset": 2,
        },
    ).json()

    assert page1["total"] == 5
    assert page2["total"] == 5
    page1_ids = {i["external_id"] for i in page1["items"]}
    page2_ids = {i["external_id"] for i in page2["items"]}
    assert len(page1_ids) == 2
    assert len(page2_ids) == 2
    # Pages must not overlap and must not include "denver".
    assert page1_ids.isdisjoint(page2_ids)
    assert "denver" not in (page1_ids | page2_ids)
