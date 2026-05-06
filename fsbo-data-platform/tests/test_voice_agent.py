"""AI voice agent — outbound initiation + TwiML conversation flow.

Tests run in dev mode (no Twilio creds), so /voice/calls reports the
call as 'simulated' and TwiML endpoints work directly. The structured-
intake extractor is bypassed by Anthropic-key=empty (returns a default
SellerIntake). Functional tests pin the schema + the conversation
state machine.
"""

from datetime import datetime, timezone

from sqlalchemy import select

from fsbo.models import Lead, Listing, VoiceCall
from fsbo.voice.intake import SellerIntake, merge_intake


def _seed(db_session, phone="(813) 555-0101"):
    listing = Listing(
        source="craigslist",
        external_id="cl-voice-1",
        url="http://x",
        title="2018 Honda Accord",
        seller_phone=phone,
        zip_code="33607",
        year=2018,
        make="Honda",
        model="Accord",
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()
    lead = Lead(dealer_id="demo-dealer", listing_id=listing.id, status="contacted")
    db_session.add(lead)
    db_session.flush()
    return lead, listing


def test_start_call_simulated_when_twilio_unconfigured(client, db_session):
    lead, listing = _seed(db_session)
    r = client.post("/voice/calls", json={"lead_id": lead.id})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "simulated"
    assert body["twilio_call_sid"] is None
    assert body["call_id"] > 0


def test_start_call_blocks_on_tcpa_opt_out(client, db_session):
    lead, listing = _seed(db_session)
    from fsbo.messaging.tcpa import record_opt_out

    record_opt_out(db_session, "demo-dealer", "8135550101", source="manual")
    db_session.flush()

    r = client.post("/voice/calls", json={"lead_id": lead.id})
    assert r.status_code == 451
    assert "opted_out" in r.json()["detail"]


def test_start_call_404s_for_other_dealers_lead(client, db_session):
    listing = Listing(
        source="craigslist",
        external_id="cl-other-2",
        url="http://x",
        title="x",
        seller_phone="(813) 555-9999",
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()
    db_session.add(Lead(dealer_id="other-dealer", listing_id=listing.id))
    db_session.flush()
    other_lead = db_session.scalar(
        select(Lead).where(Lead.dealer_id == "other-dealer")
    )
    r = client.post("/voice/calls", json={"lead_id": other_lead.id})
    assert r.status_code == 404


def test_twiml_start_returns_opening_line(client, db_session):
    lead, listing = _seed(db_session)
    r = client.post("/voice/calls", json={"lead_id": lead.id})
    call_id = r.json()["call_id"]

    r = client.post(f"/voice/twiml/start/{call_id}")
    assert r.status_code == 200
    xml = r.text
    assert "<Response>" in xml
    assert "Honda" in xml  # opening line includes vehicle make
    assert "<Gather" in xml  # waits for speech
    db_session.refresh(db_session.get(VoiceCall, call_id))
    call = db_session.get(VoiceCall, call_id)
    assert any(t["role"] == "ai" for t in call.turns)
    assert call.status == "in_progress"


def test_twiml_turn_ladders_to_next_question(client, db_session):
    lead, listing = _seed(db_session)
    r = client.post("/voice/calls", json={"lead_id": lead.id})
    call_id = r.json()["call_id"]
    client.post(f"/voice/twiml/start/{call_id}")

    # Seller answers "yes still available"
    r = client.post(
        f"/voice/twiml/turn/{call_id}",
        data={"SpeechResult": "Yes still available"},
    )
    xml = r.text
    # Next ladder rung is the price ask
    assert "lowest" in xml.lower() or "cash" in xml.lower()


def test_twiml_turn_wraps_when_enough_info_collected(client, db_session):
    lead, listing = _seed(db_session)
    r = client.post("/voice/calls", json={"lead_id": lead.id})
    call_id = r.json()["call_id"]
    client.post(f"/voice/twiml/start/{call_id}")

    # Cover the must-have signals in one rich seller turn.
    r = client.post(
        f"/voice/twiml/turn/{call_id}",
        data={
            "SpeechResult": (
                "I'd take $18000 cash, it's at 92000 miles, title in hand "
                "no lien, runs and drives clean"
            )
        },
    )
    xml = r.text
    assert "<Hangup" in xml
    db_session.refresh(db_session.get(VoiceCall, call_id))
    call = db_session.get(VoiceCall, call_id)
    assert call.status == "wrapping"


def test_twiml_status_finalizes_call(client, db_session):
    lead, listing = _seed(db_session)
    r = client.post("/voice/calls", json={"lead_id": lead.id})
    call_id = r.json()["call_id"]

    r = client.post(
        f"/voice/twiml/status/{call_id}",
        data={"CallStatus": "completed", "CallDuration": "45"},
    )
    assert r.status_code == 200
    db_session.refresh(db_session.get(VoiceCall, call_id))
    call = db_session.get(VoiceCall, call_id)
    assert call.status == "completed"
    assert call.duration_seconds == 45


def test_get_call_returns_404_for_other_dealer(client, db_session):
    lead, listing = _seed(db_session)
    r = client.post("/voice/calls", json={"lead_id": lead.id})
    call_id = r.json()["call_id"]
    # Read it as a different dealer (use the dev-mode header)
    r = client.get(
        f"/voice/calls/{call_id}",
        headers={"X-Dealer-Id": "other-dealer"},
    )
    assert r.status_code == 404


def test_list_calls_for_lead(client, db_session):
    lead, listing = _seed(db_session)
    r1 = client.post("/voice/calls", json={"lead_id": lead.id})
    r2 = client.post("/voice/calls", json={"lead_id": lead.id})

    r = client.get(f"/leads/{lead.id}/voice-calls")
    assert r.status_code == 200
    body = r.json()
    assert {c["id"] for c in body} == {r1.json()["call_id"], r2.json()["call_id"]}


# -- intake schema -----------------------------------------------------


def test_seller_intake_default_shape():
    out = SellerIntake().as_dict()
    assert out["title_status"] == "unknown"
    assert out["drivable"] == "unknown"
    assert out["motivation_level"] == "unknown"
    assert out["accidents_disclosed"] == []


def test_merge_intake_keeps_known_fields():
    prior = {"asking_price_floor": 18500.0, "title_status": "in_hand"}
    fresh = SellerIntake(
        title_status="unknown",  # default — should not erase prior
        mileage_confirmed=92000,
    )
    merged = merge_intake(prior, fresh)
    assert merged["asking_price_floor"] == 18500.0
    assert merged["title_status"] == "in_hand"  # preserved
    assert merged["mileage_confirmed"] == 92000  # added


def test_merge_intake_appends_new_fields():
    fresh = SellerIntake(
        accidents_disclosed=["minor fender bender 2022"],
        mechanical_issues=["AC needs recharge"],
    )
    merged = merge_intake({}, fresh)
    assert merged["accidents_disclosed"] == ["minor fender bender 2022"]
    assert merged["mechanical_issues"] == ["AC needs recharge"]
