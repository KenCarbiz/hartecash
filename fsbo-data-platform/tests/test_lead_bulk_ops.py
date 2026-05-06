"""Bulk lead operations: bulk-status, bulk-assign, bulk-archive."""

from itertools import count

from sqlalchemy import select

from fsbo.models import Interaction, Lead, Listing, WebhookDelivery, WebhookSubscription


_ext = count(1)


def _seed(db, dealer="demo-dealer", status="contacted", assigned_to=None) -> Lead:
    listing = Listing(
        source="craigslist",
        external_id=f"cl-{next(_ext)}",
        url="http://x",
        title="2018 Honda Accord",
        classification="private_seller",
    )
    db.add(listing)
    db.flush()
    lead = Lead(
        dealer_id=dealer,
        listing_id=listing.id,
        status=status,
        assigned_to=assigned_to,
    )
    db.add(lead)
    db.flush()
    return lead


def test_bulk_status_change_moves_each_lead(client, db_session):
    leads = [_seed(db_session, status="contacted") for _ in range(3)]
    r = client.post(
        "/leads/bulk-status",
        json={
            "lead_ids": [l.id for l in leads],
            "status": "appointment",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] == 3
    assert body["skipped"] == 0
    for lead in leads:
        db_session.refresh(lead)
        assert lead.status == "appointment"

    # Each move logs an audit interaction
    interactions = db_session.scalars(select(Interaction)).all()
    bulk_logs = [i for i in interactions if i.body and "(bulk op)" in i.body]
    assert len(bulk_logs) == 3


def test_bulk_status_skips_already_matching(client, db_session):
    leads = [_seed(db_session, status="appointment") for _ in range(3)]
    leads[0].status = "contacted"
    db_session.flush()

    r = client.post(
        "/leads/bulk-status",
        json={
            "lead_ids": [l.id for l in leads],
            "status": "appointment",
        },
    )
    body = r.json()
    assert body["updated"] == 1
    assert body["skipped"] == 2


def test_bulk_status_requires_status(client, db_session):
    lead = _seed(db_session)
    r = client.post(
        "/leads/bulk-status",
        json={"lead_ids": [lead.id]},
    )
    assert r.status_code == 400


def test_bulk_status_dealer_isolated(client, db_session):
    """Other-dealer's leads come back in not_found, not silently
    updated."""
    mine = _seed(db_session, status="contacted")
    theirs = _seed(db_session, dealer="other-dealer", status="contacted")
    r = client.post(
        "/leads/bulk-status",
        json={"lead_ids": [mine.id, theirs.id], "status": "appointment"},
    )
    body = r.json()
    assert body["updated"] == 1
    assert theirs.id in body["not_found"]
    db_session.refresh(theirs)
    assert theirs.status == "contacted"  # untouched


def test_bulk_status_fires_webhook_per_changed_lead(client, db_session):
    leads = [_seed(db_session, status="contacted") for _ in range(2)]
    db_session.add(
        WebhookSubscription(
            dealer_id="demo-dealer",
            name="hook",
            url="https://example.com/hook",
            secret="s",
            event="lead.status_changed",
            active=True,
        )
    )
    db_session.flush()

    client.post(
        "/leads/bulk-status",
        json={"lead_ids": [l.id for l in leads], "status": "appointment"},
    )

    deliveries = db_session.scalars(
        select(WebhookDelivery).where(
            WebhookDelivery.event == "lead.status_changed"
        )
    ).all()
    assert len(deliveries) == 2


def test_bulk_assign_redistributes_owners(client, db_session):
    leads = [_seed(db_session, assigned_to="alice") for _ in range(3)]
    leads[0].assigned_to = "bob"
    db_session.flush()

    r = client.post(
        "/leads/bulk-assign",
        json={"lead_ids": [l.id for l in leads], "assigned_to": "alice"},
    )
    body = r.json()
    assert body["updated"] == 1
    assert body["skipped"] == 2


def test_bulk_assign_can_clear_owner(client, db_session):
    leads = [_seed(db_session, assigned_to="alice") for _ in range(2)]
    r = client.post(
        "/leads/bulk-assign",
        json={"lead_ids": [l.id for l in leads], "assigned_to": None},
    )
    assert r.json()["updated"] == 2
    for lead in leads:
        db_session.refresh(lead)
        assert lead.assigned_to is None


def test_bulk_archive_soft_deletes(client, db_session):
    leads = [_seed(db_session) for _ in range(3)]
    r = client.post(
        "/leads/bulk-archive",
        json={
            "lead_ids": [l.id for l in leads],
            "reason": "stale list cleanup",
        },
    )
    body = r.json()
    assert body["updated"] == 3
    for lead in leads:
        db_session.refresh(lead)
        assert lead.deleted_at is not None
        assert lead.delete_reason == "stale list cleanup"

    # And these should drop out of the default /leads list
    visible = client.get("/leads").json()
    assert visible == [] or all(item["id"] not in {l.id for l in leads} for item in visible)


def test_bulk_archive_skips_already_archived(client, db_session):
    leads = [_seed(db_session) for _ in range(2)]
    client.post(
        "/leads/bulk-archive",
        json={"lead_ids": [leads[0].id], "reason": "first round"},
    )
    r = client.post(
        "/leads/bulk-archive",
        json={"lead_ids": [l.id for l in leads], "reason": "round 2"},
    )
    body = r.json()
    assert body["updated"] == 1
    assert body["skipped"] == 1


def test_bulk_caps_at_200_ids(client, db_session):
    """Caller can spam 500 ids; we should silently cap to 200."""
    leads = [_seed(db_session) for _ in range(5)]
    r = client.post(
        "/leads/bulk-status",
        json={
            "lead_ids": [l.id for l in leads] + list(range(99000, 99300)),
            "status": "appointment",
        },
    )
    assert r.status_code == 200
    body = r.json()
    # Real leads should at least be reported either updated or not_found
    assert body["updated"] + len(body["not_found"]) <= 200
