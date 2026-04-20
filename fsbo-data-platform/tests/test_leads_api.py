from fsbo.models import Listing


def _seed_listing(db, external_id: str = "cl-1") -> Listing:
    row = Listing(
        source="craigslist",
        external_id=external_id,
        url="https://example.com/x",
        title="2018 Ford F-150",
        year=2018,
        make="Ford",
        model="F-150",
        price=22000,
        classification="private_seller",
    )
    db.add(row)
    db.flush()
    return row


def test_create_lead_idempotent_per_dealer_listing(client, db_session):
    listing = _seed_listing(db_session)
    r1 = client.post(
        "/leads",
        json={"listing_id": listing.id, "assigned_to": "alice"},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    assert r1.status_code == 201
    lead_id = r1.json()["id"]

    # Same dealer + listing → returns existing lead, not a duplicate
    r2 = client.post(
        "/leads",
        json={"listing_id": listing.id, "assigned_to": "bob"},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    assert r2.status_code == 201
    assert r2.json()["id"] == lead_id


def test_dealer_isolation(client, db_session):
    listing = _seed_listing(db_session)
    client.post(
        "/leads",
        json={"listing_id": listing.id},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    # Different dealer can't see dealer-1's leads
    r = client.get("/leads", headers={"X-Dealer-Id": "dealer-2"})
    assert r.status_code == 200
    assert r.json() == []


def test_status_change_creates_interaction(client, db_session):
    listing = _seed_listing(db_session)
    r = client.post(
        "/leads",
        json={"listing_id": listing.id},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    lead_id = r.json()["id"]

    client.patch(
        f"/leads/{lead_id}",
        json={"status": "contacted"},
        headers={"X-Dealer-Id": "dealer-1"},
    )

    interactions = client.get(
        f"/leads/{lead_id}/interactions", headers={"X-Dealer-Id": "dealer-1"}
    ).json()
    assert any(i["kind"] == "status_change" and "contacted" in i["body"] for i in interactions)


def test_add_note_and_complete_task(client, db_session):
    listing = _seed_listing(db_session)
    lead_id = client.post(
        "/leads",
        json={"listing_id": listing.id},
        headers={"X-Dealer-Id": "dealer-1"},
    ).json()["id"]

    # Add a note
    client.post(
        f"/leads/{lead_id}/interactions",
        json={"kind": "note", "body": "Left voicemail"},
        headers={"X-Dealer-Id": "dealer-1"},
    )

    # Add a task
    task_resp = client.post(
        f"/leads/{lead_id}/interactions",
        json={"kind": "task", "body": "Follow up tomorrow"},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    task_id = task_resp.json()["id"]

    # Complete the task
    done = client.post(
        f"/leads/{lead_id}/interactions/{task_id}/complete",
        headers={"X-Dealer-Id": "dealer-1"},
    )
    assert done.status_code == 200
    assert done.json()["completed_at"] is not None


def test_lead_not_found_for_other_dealer(client, db_session):
    listing = _seed_listing(db_session)
    lead_id = client.post(
        "/leads",
        json={"listing_id": listing.id},
        headers={"X-Dealer-Id": "dealer-1"},
    ).json()["id"]

    r = client.get(f"/leads/{lead_id}", headers={"X-Dealer-Id": "dealer-2"})
    assert r.status_code == 404


def test_create_lead_for_missing_listing(client):
    r = client.post(
        "/leads",
        json={"listing_id": 9999},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    assert r.status_code == 404
