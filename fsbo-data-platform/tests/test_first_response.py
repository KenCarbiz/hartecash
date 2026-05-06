"""Lead.first_responded_at stamp behavior.

Stamped exactly once on the first outbound contact:
- /messages/send (SMS)
- /messages/email/send (when send actually succeeds)
- /voice/calls (AI call initiation)
- /voice/bridge (click-to-call bridge)
- /leads/{id}/interactions with direction=outbound

Once stamped, subsequent outreach must NOT update it — that's the
whole point of the metric (first response time, not most-recent
response).
"""

from itertools import count

from fsbo.crm.response import mark_first_response
from fsbo.models import Lead, Listing, VoiceCall


_ext = count(1)


def _seed(db, dealer="demo-dealer", phone="(813) 555-0100"):
    listing = Listing(
        source="craigslist",
        external_id=f"cl-fr-{next(_ext)}",
        url="http://x",
        title="2018 Honda Accord",
        seller_phone=phone,
        zip_code="33607",
        classification="private_seller",
    )
    db.add(listing)
    db.flush()
    lead = Lead(dealer_id=dealer, listing_id=listing.id, status="new")
    db.add(lead)
    db.flush()
    return lead, listing


def test_helper_stamps_once(db_session):
    lead, _ = _seed(db_session)
    assert lead.first_responded_at is None

    assert mark_first_response(lead) is True
    db_session.flush()
    first = lead.first_responded_at
    assert first is not None

    # Second call must not update it.
    assert mark_first_response(lead) is False
    db_session.refresh(lead)
    # SQLite strips tzinfo on roundtrip; compare on naive iso instead.
    assert lead.first_responded_at.replace(tzinfo=None) == first.replace(tzinfo=None)


def test_helper_handles_none(db_session):
    assert mark_first_response(None) is False  # type: ignore[arg-type]


def test_voice_bridge_stamps_first_response(client, db_session):
    lead, _ = _seed(db_session)
    assert lead.first_responded_at is None

    r = client.post(
        "/voice/bridge",
        json={"lead_id": lead.id, "rep_phone": "(813) 555-7777"},
    )
    assert r.status_code == 201
    db_session.refresh(lead)
    assert lead.first_responded_at is not None


def test_voice_call_stamps_first_response(client, db_session):
    lead, _ = _seed(db_session)
    r = client.post("/voice/calls", json={"lead_id": lead.id})
    assert r.status_code == 201
    db_session.refresh(lead)
    assert lead.first_responded_at is not None


def test_outbound_interaction_stamps_first_response(client, db_session):
    lead, _ = _seed(db_session)
    r = client.post(
        f"/leads/{lead.id}/interactions",
        json={"kind": "note", "direction": "outbound", "body": "first touch"},
    )
    assert r.status_code == 201
    db_session.refresh(lead)
    assert lead.first_responded_at is not None


def test_inbound_interaction_does_not_stamp(client, db_session):
    """Seller texts us first — that doesn't count as our response."""
    lead, _ = _seed(db_session)
    r = client.post(
        f"/leads/{lead.id}/interactions",
        json={"kind": "text", "direction": "inbound", "body": "still available?"},
    )
    assert r.status_code == 201
    db_session.refresh(lead)
    assert lead.first_responded_at is None


def test_first_responded_at_is_immutable(client, db_session):
    """Second outbound contact does NOT bump the timestamp — it's
    intentionally measuring first response, not most-recent activity."""
    lead, _ = _seed(db_session)

    # First touch
    r = client.post("/voice/calls", json={"lead_id": lead.id})
    assert r.status_code == 201
    db_session.refresh(lead)
    first = lead.first_responded_at
    assert first is not None

    # Second touch via interaction — must not move the stamp.
    r = client.post(
        f"/leads/{lead.id}/interactions",
        json={"kind": "note", "direction": "outbound", "body": "follow up"},
    )
    assert r.status_code == 201
    db_session.refresh(lead)
    assert (
        lead.first_responded_at.replace(tzinfo=None)
        == first.replace(tzinfo=None)
    )


def test_lead_get_exposes_first_responded_at(client, db_session):
    lead, _ = _seed(db_session)
    r = client.get(f"/leads/{lead.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["first_responded_at"] is None

    client.post("/voice/calls", json={"lead_id": lead.id})

    body = client.get(f"/leads/{lead.id}").json()
    assert body["first_responded_at"] is not None


def test_lead_list_exposes_first_responded_at(client, db_session):
    lead, _ = _seed(db_session)
    client.post("/voice/calls", json={"lead_id": lead.id})

    rows = client.get("/leads").json()
    row = next(r for r in rows if r["id"] == lead.id)
    assert row["first_responded_at"] is not None
