"""Per-rep leaderboard analytics."""

from datetime import datetime, timedelta, timezone
from itertools import count

from fsbo.models import (
    Interaction,
    InteractionKind,
    Lead,
    Listing,
    Message,
    Offer,
    VoiceCall,
)

_external_id_counter = count(1)


def _seed_lead(db, assigned_to: str | None, status: str = "new") -> Lead:
    eid = f"cl-{next(_external_id_counter)}"
    listing = Listing(
        source="craigslist",
        external_id=eid,
        url="http://x",
        title="2018 Honda Accord",
        seller_phone="(813) 555-0100",
        zip_code="33607",
        classification="private_seller",
    )
    db.add(listing)
    db.flush()
    lead = Lead(
        dealer_id="demo-dealer",
        listing_id=listing.id,
        assigned_to=assigned_to,
        status=status,
    )
    db.add(lead)
    db.flush()
    return lead


def test_leaderboard_empty_when_no_leads(client):
    body = client.get("/analytics/leaderboard").json()
    assert body["reps"] == []


def test_leaderboard_aggregates_per_rep(client, db_session):
    lead_a = _seed_lead(db_session, "alice", status="purchased")
    lead_b = _seed_lead(db_session, "alice", status="appointment")
    _seed_lead(db_session, "bob", status="new")

    body = client.get("/analytics/leaderboard").json()
    reps = {r["assigned_to"]: r for r in body["reps"]}
    assert reps["alice"]["leads_claimed"] == 2
    assert reps["alice"]["leads_purchased"] == 1
    assert reps["alice"]["leads_appointment"] == 1
    assert reps["bob"]["leads_claimed"] == 1
    assert reps["bob"]["leads_purchased"] == 0


def test_leaderboard_orders_by_composite_score(client, db_session):
    # alice gets one purchase (5pts); bob gets two appointments (4pts);
    # alice should rank above bob.
    _seed_lead(db_session, "alice", status="purchased")
    _seed_lead(db_session, "bob", status="appointment")
    _seed_lead(db_session, "bob", status="appointment")

    body = client.get("/analytics/leaderboard").json()
    order = [r["assigned_to"] for r in body["reps"]]
    assert order.index("alice") < order.index("bob")


def test_leaderboard_treats_blank_assigned_to_as_unassigned(client, db_session):
    _seed_lead(db_session, "", status="new")
    _seed_lead(db_session, None, status="new")  # type: ignore[arg-type]
    body = client.get("/analytics/leaderboard").json()
    names = [r["assigned_to"] for r in body["reps"]]
    assert "(unassigned)" in names


def test_leaderboard_counts_outbound_messages(client, db_session):
    lead = _seed_lead(db_session, "alice")
    db_session.add(
        Message(
            dealer_id="demo-dealer",
            lead_id=lead.id,
            direction="outbound",
            to_number="8135550100",
            body="hi",
            status="delivered",
        )
    )
    db_session.add(
        Message(
            dealer_id="demo-dealer",
            lead_id=lead.id,
            direction="inbound",
            from_number="8135550100",
            body="still avail",
            status="received",
        )
    )
    db_session.flush()

    body = client.get("/analytics/leaderboard").json()
    rep = next(r for r in body["reps"] if r["assigned_to"] == "alice")
    assert rep["sms_sent"] == 1  # inbound doesn't count


def test_leaderboard_counts_voice_calls_and_offers(client, db_session):
    lead = _seed_lead(db_session, "alice")
    db_session.add(
        VoiceCall(
            lead_id=lead.id,
            dealer_id="demo-dealer",
            to_number="8135550100",
            status="completed",
            duration_seconds=120,
        )
    )
    db_session.add(
        Offer(
            public_token="t1",
            dealer_id="demo-dealer",
            lead_id=lead.id,
            listing_id=lead.listing_id,
            amount_cents=1850000,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
            status="pending",
        )
    )
    db_session.add(
        Offer(
            public_token="t2",
            dealer_id="demo-dealer",
            lead_id=lead.id,
            listing_id=lead.listing_id,
            amount_cents=1900000,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
            status="accepted",
            seller_response_at=datetime.now(timezone.utc),
        )
    )
    db_session.flush()

    body = client.get("/analytics/leaderboard").json()
    rep = next(r for r in body["reps"] if r["assigned_to"] == "alice")
    assert rep["voice_calls"] == 1
    assert rep["offers_sent"] == 2
    assert rep["offers_accepted"] == 1


def test_leaderboard_avg_response_minutes(client, db_session):
    lead = _seed_lead(db_session, "alice")
    # First outbound interaction 15 minutes after lead creation.
    db_session.add(
        Interaction(
            lead_id=lead.id,
            kind=InteractionKind.TEXT.value,
            direction="outbound",
            body="hi",
            created_at=lead.created_at + timedelta(minutes=15),
        )
    )
    db_session.flush()
    body = client.get("/analytics/leaderboard").json()
    rep = next(r for r in body["reps"] if r["assigned_to"] == "alice")
    assert rep["avg_response_minutes"] is not None
    assert 14 <= rep["avg_response_minutes"] <= 16


def test_leaderboard_window_excludes_old_leads(client, db_session):
    # Lead that's 60 days old shouldn't appear when window=30 days
    lead = _seed_lead(db_session, "alice")
    lead.created_at = datetime.now(timezone.utc) - timedelta(days=60)
    db_session.flush()
    body = client.get("/analytics/leaderboard?days=30").json()
    assert body["reps"] == []
