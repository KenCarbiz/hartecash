"""Lead soft-delete (archive) + restore.

Soft-delete keeps the row + every interaction / message tied to it so
the audit trail survives — but the lead disappears from the default
GET /leads list. Restore window is 30 days; after that an external
sweeper may hard-delete (not yet implemented).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from fsbo.models import Interaction, InteractionKind, Lead, Listing


def _seed(db):
    db.add(
        Listing(
            source="craigslist",
            external_id="cl-archive-1",
            url="http://x",
            title="2018 Ford F-150",
            classification="private_seller",
        )
    )
    db.flush()
    return db.scalar(select(Listing).where(Listing.external_id == "cl-archive-1"))


def test_archive_hides_from_default_list(client, db_session):
    listing = _seed(db_session)
    r = client.post("/leads", json={"listing_id": listing.id})
    lead_id = r.json()["id"]

    # Visible by default
    assert any(item["id"] == lead_id for item in client.get("/leads").json())

    # Archive
    r = client.post(
        f"/leads/{lead_id}/archive",
        json={"reason": "duplicate of #99"},
    )
    assert r.status_code == 200

    # Hidden from default list
    assert not any(item["id"] == lead_id for item in client.get("/leads").json())

    # Visible with include_archived=true
    r = client.get("/leads", params={"include_archived": True})
    assert any(item["id"] == lead_id for item in r.json())


def test_archive_logs_interaction_with_reason(client, db_session):
    listing = _seed(db_session)
    r = client.post("/leads", json={"listing_id": listing.id})
    lead_id = r.json()["id"]
    client.post(f"/leads/{lead_id}/archive", json={"reason": "bought elsewhere"})

    interactions = db_session.scalars(
        select(Interaction).where(Interaction.lead_id == lead_id)
    ).all()
    assert any(
        i.kind == InteractionKind.STATUS_CHANGE.value
        and i.body
        and "archived" in i.body
        and "bought elsewhere" in i.body
        for i in interactions
    )


def test_restore_clears_deletion_fields(client, db_session):
    listing = _seed(db_session)
    r = client.post("/leads", json={"listing_id": listing.id})
    lead_id = r.json()["id"]
    client.post(f"/leads/{lead_id}/archive", json={"reason": "oops"})

    r = client.post(f"/leads/{lead_id}/restore")
    assert r.status_code == 200
    body = r.json()
    # LeadOut doesn't expose deleted_at; verify in DB.
    db_session.expire_all()
    lead = db_session.get(Lead, lead_id)
    assert lead.deleted_at is None
    assert lead.deleted_by is None
    assert lead.delete_reason is None


def test_restore_after_30_days_returns_410(client, db_session):
    listing = _seed(db_session)
    r = client.post("/leads", json={"listing_id": listing.id})
    lead_id = r.json()["id"]
    client.post(f"/leads/{lead_id}/archive", json={})

    # Simulate 31 days elapsed
    lead = db_session.get(Lead, lead_id)
    lead.deleted_at = datetime.now(timezone.utc) - timedelta(days=31)
    db_session.flush()

    r = client.post(f"/leads/{lead_id}/restore")
    assert r.status_code == 410


def test_archive_other_dealers_lead_returns_404(client, db_session):
    listing = _seed(db_session)
    db_session.add(
        Lead(dealer_id="other-dealer", listing_id=listing.id, status="new")
    )
    db_session.flush()
    other_lead = db_session.scalar(
        select(Lead).where(Lead.dealer_id == "other-dealer")
    )

    r = client.post(f"/leads/{other_lead.id}/archive", json={})
    assert r.status_code == 404
