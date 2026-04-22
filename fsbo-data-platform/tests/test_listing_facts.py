from fsbo.models import Listing


def _seed(db):
    row = Listing(
        source="craigslist",
        external_id="ext-plate-1",
        url="http://x",
        title="2019 Ford F-150",
        classification="private_seller",
    )
    db.add(row)
    db.flush()
    return row


def test_patch_sets_plate_state_color(client, db_session):
    listing = _seed(db_session)
    r = client.patch(
        f"/listings/{listing.id}/facts",
        json={
            "license_plate": "abc 1234",
            "license_plate_state": "fl",
            "color": "Graphite Grey",
        },
        headers={"X-Dealer-Id": "dealer-1"},
    )
    assert r.status_code == 200
    body = r.json()
    # Plate + state are uppercased + trimmed
    assert body["license_plate"] == "ABC 1234"
    assert body["license_plate_state"] == "FL"
    assert body["color"] == "Graphite Grey"


def test_patch_vin_also_uppercased(client, db_session):
    listing = _seed(db_session)
    r = client.patch(
        f"/listings/{listing.id}/facts",
        json={"vin": "1fmcu0gd5aka12345"},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    assert r.status_code == 200
    assert r.json()["vin"] == "1FMCU0GD5AKA12345"


def test_patch_empty_string_clears_field(client, db_session):
    listing = _seed(db_session)
    # Set a plate first
    client.patch(
        f"/listings/{listing.id}/facts",
        json={"license_plate": "XYZ-9000"},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    # Clear it with an explicit empty string
    r = client.patch(
        f"/listings/{listing.id}/facts",
        json={"license_plate": ""},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    assert r.status_code == 200
    assert r.json()["license_plate"] is None


def test_patch_omitted_field_preserved(client, db_session):
    listing = _seed(db_session)
    # Set color
    client.patch(
        f"/listings/{listing.id}/facts",
        json={"color": "Silver"},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    # Set plate without touching color
    r = client.patch(
        f"/listings/{listing.id}/facts",
        json={"license_plate": "TEST123"},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    body = r.json()
    assert body["license_plate"] == "TEST123"
    assert body["color"] == "Silver"


def test_patch_unknown_listing(client):
    r = client.patch(
        "/listings/999999/facts",
        json={"color": "Red"},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    assert r.status_code == 404


def test_patch_requires_auth_in_production(client, monkeypatch, db_session):
    listing = _seed(db_session)
    monkeypatch.setattr(
        "fsbo.config.settings.env_mode", "production", raising=True
    )
    # No X-Dealer-Id header, no cookie, no bearer — 401.
    r = client.patch(
        f"/listings/{listing.id}/facts",
        json={"color": "Red"},
    )
    assert r.status_code == 401


def test_listing_exposes_new_fields(client, db_session):
    listing = _seed(db_session)
    client.patch(
        f"/listings/{listing.id}/facts",
        json={
            "license_plate": "7GTF123",
            "license_plate_state": "CA",
            "color": "Midnight Blue",
        },
        headers={"X-Dealer-Id": "dealer-1"},
    )
    r = client.get(f"/listings/{listing.id}")
    body = r.json()
    assert body["license_plate"] == "7GTF123"
    assert body["license_plate_state"] == "CA"
    assert body["color"] == "Midnight Blue"
