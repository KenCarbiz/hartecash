from fsbo.models import Listing


def _seed_listings(db, count=5):
    ids = []
    for i in range(count):
        row = Listing(
            source="craigslist",
            external_id=f"bulk-{i}",
            url=f"http://x/{i}",
            title=f"2018 Ford F-150 #{i}",
            year=2018,
            make="Ford",
            model="F-150",
            price=20000 + i,
            classification="private_seller",
        )
        db.add(row)
        db.flush()
        ids.append(row.id)
    return ids


def test_bulk_claim_all_new(client, db_session):
    ids = _seed_listings(db_session, count=4)
    r = client.post(
        "/leads/bulk-claim",
        json={"listing_ids": ids, "assigned_to": "alice"},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["claimed"] == 4
    assert body["already_claimed"] == 0
    assert body["missing_listings"] == []


def test_bulk_claim_idempotent_against_prior(client, db_session):
    ids = _seed_listings(db_session, count=3)
    client.post(
        "/leads",
        json={"listing_ids": ids[:1]},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    # One of them already claimed
    client.post(
        "/leads",
        json={"listing_id": ids[0]},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    r = client.post(
        "/leads/bulk-claim",
        json={"listing_ids": ids},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    body = r.json()
    assert body["claimed"] == 2
    assert body["already_claimed"] == 1


def test_bulk_claim_reports_missing(client, db_session):
    ids = _seed_listings(db_session, count=2)
    r = client.post(
        "/leads/bulk-claim",
        json={"listing_ids": ids + [9999]},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    body = r.json()
    assert 9999 in body["missing_listings"]
    assert body["claimed"] == 2
