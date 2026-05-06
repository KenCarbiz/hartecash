"""Stale-lead queue (response-SLA breach detection).

GET /leads/stale returns leads that:
  - status is 'new' or 'contacted'
  - older than sla_minutes (default 5)
  - have no outbound Interaction, Message, or VoiceCall yet
  - aren't archived

The dashboard renders these as the "respond now" queue. Industry data
shows responding under 5 minutes more than doubles contact rates;
this gives reps a working surface for the SLA they care about.
"""

from datetime import datetime, timedelta, timezone
from itertools import count

from fsbo.models import Interaction, Lead, Listing, Message, VoiceCall


_ext = count(1)


def _seed_listing(db, **overrides) -> Listing:
    base = dict(
        source="craigslist",
        external_id=f"cl-stale-{next(_ext)}",
        url="http://x",
        title="2018 Honda Accord",
        seller_phone="(813) 555-0100",
        zip_code="33607",
        year=2018,
        make="Honda",
        model="Accord",
        price=18500,
        city="Tampa",
        state="FL",
        classification="private_seller",
    )
    base.update(overrides)
    listing = Listing(**base)
    db.add(listing)
    db.flush()
    return listing


def _seed_lead(
    db,
    *,
    dealer="demo-dealer",
    status="new",
    minutes_old=10,
    deleted: bool = False,
    listing: Listing | None = None,
) -> Lead:
    if listing is None:
        listing = _seed_listing(db)
    created = datetime.now(timezone.utc) - timedelta(minutes=minutes_old)
    lead = Lead(
        dealer_id=dealer,
        listing_id=listing.id,
        status=status,
        created_at=created,
        updated_at=created,
    )
    if deleted:
        lead.deleted_at = datetime.now(timezone.utc)
        lead.deleted_by = dealer
    db.add(lead)
    db.flush()
    return lead


def test_stale_leads_returns_uncontacted_old_leads(client, db_session):
    lead = _seed_lead(db_session, minutes_old=15)
    r = client.get("/leads/stale")
    assert r.status_code == 200
    rows = r.json()
    ids = [row["id"] for row in rows]
    assert lead.id in ids
    found = next(row for row in rows if row["id"] == lead.id)
    assert found["minutes_since_created"] >= 15
    # Listing fields are eagerly joined for dashboard rendering.
    assert found["listing_make"] == "Honda"


def test_stale_leads_excludes_recent_under_sla(client, db_session):
    """Brand-new lead is inside the SLA window, not yet stale."""
    lead = _seed_lead(db_session, minutes_old=2)
    r = client.get("/leads/stale?sla_minutes=5")
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert lead.id not in ids


def test_stale_leads_excludes_after_outbound_interaction(client, db_session):
    lead = _seed_lead(db_session, minutes_old=20)
    db_session.add(
        Interaction(
            lead_id=lead.id,
            kind="text",
            direction="outbound",
            body="hey",
        )
    )
    db_session.flush()

    r = client.get("/leads/stale")
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert lead.id not in ids


def test_stale_leads_excludes_after_outbound_message(client, db_session):
    lead = _seed_lead(db_session, minutes_old=20)
    db_session.add(
        Message(
            lead_id=lead.id,
            dealer_id="demo-dealer",
            channel="sms",
            direction="outbound",
            body="hey",
            to_number="(813) 555-0100",
        )
    )
    db_session.flush()

    r = client.get("/leads/stale")
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert lead.id not in ids


def test_stale_leads_excludes_after_voice_call(client, db_session):
    lead = _seed_lead(db_session, minutes_old=20)
    db_session.add(
        VoiceCall(
            lead_id=lead.id,
            dealer_id="demo-dealer",
            to_number="(813) 555-0100",
            status="completed",
        )
    )
    db_session.flush()

    r = client.get("/leads/stale")
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert lead.id not in ids


def test_stale_leads_excludes_archived_leads(client, db_session):
    lead = _seed_lead(db_session, minutes_old=20, deleted=True)
    r = client.get("/leads/stale")
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert lead.id not in ids


def test_stale_leads_excludes_negotiating_or_later(client, db_session):
    """Once a lead has progressed past initial contact (negotiating /
    appointment / purchased / lost), it's no longer in the SLA queue
    even if outbound contact wasn't logged as an Interaction."""
    lead = _seed_lead(db_session, minutes_old=120, status="negotiating")
    r = client.get("/leads/stale")
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert lead.id not in ids


def test_stale_leads_oldest_first(client, db_session):
    """Rep wants to work the most-urgent (oldest) lead first."""
    older = _seed_lead(db_session, minutes_old=60)
    newer = _seed_lead(db_session, minutes_old=10)
    r = client.get("/leads/stale")
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert ids.index(older.id) < ids.index(newer.id)


def test_stale_leads_is_dealer_scoped(client, db_session):
    """Other dealer's stale leads must not leak."""
    listing = _seed_listing(db_session)
    other = _seed_lead(
        db_session, dealer="other-dealer", listing=listing, minutes_old=30
    )
    mine = _seed_lead(db_session, minutes_old=30)
    r = client.get("/leads/stale")
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert mine.id in ids
    assert other.id not in ids


def test_stale_leads_respects_custom_sla_minutes(client, db_session):
    """Different dealerships have different SLAs — 30 min is also
    common (lead-aggregator industry standard)."""
    in_window = _seed_lead(db_session, minutes_old=15)
    breaching = _seed_lead(db_session, minutes_old=45)

    r = client.get("/leads/stale?sla_minutes=30")
    ids = [row["id"] for row in r.json()]
    assert breaching.id in ids
    assert in_window.id not in ids
