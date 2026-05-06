"""Unified per-lead feed (VAN parity for "unified messaging hub")."""

from datetime import datetime, timedelta, timezone

from fsbo.models import (
    Interaction,
    InteractionKind,
    Lead,
    Listing,
    Message,
    VoiceCall,
)


def _seed(db_session):
    listing = Listing(
        source="craigslist",
        external_id="cl-feed-1",
        url="http://x",
        title="2018 Honda Accord",
        seller_phone="8135551234",
        zip_code="33607",
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()
    lead = Lead(dealer_id="demo-dealer", listing_id=listing.id, status="new")
    db_session.add(lead)
    db_session.flush()
    return lead


def test_feed_merges_interactions_and_messages_chronologically(client, db_session):
    lead = _seed(db_session)
    base = datetime.now(timezone.utc)

    # 3 interactions + 2 messages interleaved
    db_session.add(
        Interaction(
            lead_id=lead.id,
            kind=InteractionKind.NOTE.value,
            body="left voicemail",
            created_at=base - timedelta(minutes=30),
        )
    )
    db_session.add(
        Message(
            dealer_id="demo-dealer",
            lead_id=lead.id,
            direction="outbound",
            to_number="8135551234",
            body="Hi, still available?",
            status="delivered",
            created_at=base - timedelta(minutes=20),
        )
    )
    db_session.add(
        Message(
            dealer_id="demo-dealer",
            lead_id=lead.id,
            direction="inbound",
            from_number="8135551234",
            body="Yes, $19500 firm",
            status="received",
            created_at=base - timedelta(minutes=15),
        )
    )
    db_session.add(
        Interaction(
            lead_id=lead.id,
            kind=InteractionKind.STATUS_CHANGE.value,
            body="new -> contacted",
            created_at=base - timedelta(minutes=10),
        )
    )
    db_session.add(
        Interaction(
            lead_id=lead.id,
            kind=InteractionKind.NOTE.value,
            body="$500 below market — push hard",
            created_at=base - timedelta(minutes=5),
        )
    )
    db_session.flush()

    body = client.get(f"/leads/{lead.id}/feed").json()
    kinds = [e["kind"] for e in body["entries"]]
    # Newest-first
    assert kinds == [
        "interaction:note",  # most recent note
        "interaction:status_change",
        "message:inbound",
        "message:outbound",
        "interaction:note",  # voicemail (oldest)
    ]
    # Outbound message body comes through verbatim
    assert any(
        e["body"] == "Hi, still available?" and e["delivery_status"] == "delivered"
        for e in body["entries"]
    )


def test_feed_404s_for_other_dealers_lead(client, db_session):
    listing = Listing(
        source="craigslist",
        external_id="cl-other",
        url="http://x",
        title="x",
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()
    db_session.add(
        Lead(dealer_id="other-dealer", listing_id=listing.id, status="new")
    )
    db_session.flush()
    other_lead = (
        db_session.query(Lead).filter_by(dealer_id="other-dealer").one()
    )
    r = client.get(f"/leads/{other_lead.id}/feed")
    assert r.status_code == 404


def test_feed_empty_for_brand_new_lead(client, db_session):
    lead = _seed(db_session)
    body = client.get(f"/leads/{lead.id}/feed").json()
    assert body["lead_id"] == lead.id
    assert body["entries"] == []


def test_feed_includes_voice_calls(client, db_session):
    lead = _seed(db_session)
    base = datetime.now(timezone.utc)

    # One SMS, one voice call — voice call should show up between them.
    db_session.add(
        Message(
            dealer_id="demo-dealer",
            lead_id=lead.id,
            direction="outbound",
            to_number="8135551234",
            body="Hi",
            status="delivered",
            created_at=base - timedelta(minutes=15),
        )
    )
    db_session.add(
        VoiceCall(
            lead_id=lead.id,
            dealer_id="demo-dealer",
            to_number="8135551234",
            status="completed",
            duration_seconds=92,
            turns=[
                {"role": "ai", "text": "Hi"},
                {"role": "seller", "text": "Yes still available"},
                {"role": "seller", "text": "$18000"},
            ],
            intake={"next_step": "appointment"},
            created_at=base - timedelta(minutes=10),
        )
    )
    db_session.flush()

    body = client.get(f"/leads/{lead.id}/feed").json()
    voice_entries = [e for e in body["entries"] if e["kind"] == "voice_call"]
    assert len(voice_entries) == 1
    v = voice_entries[0]
    assert v["delivery_status"] == "completed"
    assert "2 seller turns" in v["body"]
    assert "92s" in v["body"]
    assert "next: appointment" in v["body"]
    # Newest-first ordering preserved
    kinds = [e["kind"] for e in body["entries"]]
    assert kinds == ["voice_call", "message:outbound"]


def test_feed_caps_at_limit(client, db_session):
    lead = _seed(db_session)
    base = datetime.now(timezone.utc)
    for i in range(50):
        db_session.add(
            Interaction(
                lead_id=lead.id,
                kind=InteractionKind.NOTE.value,
                body=f"note {i}",
                created_at=base - timedelta(minutes=i),
            )
        )
    db_session.flush()

    body = client.get(f"/leads/{lead.id}/feed", params={"limit": 10}).json()
    assert len(body["entries"]) == 10
    # Newest first
    assert body["entries"][0]["body"] == "note 0"
