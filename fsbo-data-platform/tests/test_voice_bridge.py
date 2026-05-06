"""Click-to-call dealer bridge.

POST /voice/bridge rings the rep first, then bridges them to the seller.
TwiML lives at /voice/twiml/bridge/{call_id} and returns <Dial> with the
dealership's Twilio number as callerId.

Tests run in dev mode (no Twilio creds) so the route returns a
'simulated' VoiceCall row + we can hit the TwiML endpoint directly.
"""

from itertools import count

from fsbo.models import Lead, Listing, VoiceCall


_ext = count(1)


def _seed(db_session, phone="(813) 555-0102", dealer="demo-dealer"):
    listing = Listing(
        source="craigslist",
        external_id=f"cl-bridge-{next(_ext)}",
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
    lead = Lead(dealer_id=dealer, listing_id=listing.id, status="contacted")
    db_session.add(lead)
    db_session.flush()
    return lead, listing


def test_bridge_simulated_when_twilio_unconfigured(client, db_session):
    lead, _ = _seed(db_session)
    r = client.post(
        "/voice/bridge",
        json={"lead_id": lead.id, "rep_phone": "(813) 555-7777"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "simulated"
    assert body["twilio_call_sid"] is None
    assert body["call_id"] > 0

    # Logged as a VoiceCall with direction="bridge" so the dashboard can
    # tell rep calls apart from AI calls.
    call = db_session.get(VoiceCall, body["call_id"])
    assert call is not None
    assert call.direction == "bridge"
    assert call.dealer_id == "demo-dealer"
    assert call.lead_id == lead.id


def test_bridge_blocks_on_tcpa_opt_out(client, db_session):
    lead, _ = _seed(db_session)
    from fsbo.messaging.tcpa import record_opt_out

    record_opt_out(db_session, "demo-dealer", "8135550102", source="manual")
    db_session.flush()

    r = client.post(
        "/voice/bridge",
        json={"lead_id": lead.id, "rep_phone": "(813) 555-7777"},
    )
    assert r.status_code == 451
    assert "opted_out" in r.json()["detail"]


def test_bridge_404s_for_other_dealers_lead(client, db_session):
    lead, _ = _seed(db_session, dealer="other-dealer")
    r = client.post(
        "/voice/bridge",
        json={"lead_id": lead.id, "rep_phone": "(813) 555-7777"},
    )
    assert r.status_code == 404


def test_bridge_400s_when_listing_has_no_phone(client, db_session):
    listing = Listing(
        source="craigslist",
        external_id=f"cl-bridge-{next(_ext)}",
        url="http://x",
        title="No phone listing",
        seller_phone=None,
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()
    lead = Lead(dealer_id="demo-dealer", listing_id=listing.id, status="new")
    db_session.add(lead)
    db_session.flush()

    r = client.post(
        "/voice/bridge",
        json={"lead_id": lead.id, "rep_phone": "(813) 555-7777"},
    )
    assert r.status_code == 400
    assert "seller phone" in r.json()["detail"]


def test_bridge_400s_when_rep_phone_blank(client, db_session):
    lead, _ = _seed(db_session)
    r = client.post(
        "/voice/bridge",
        json={"lead_id": lead.id, "rep_phone": "   "},
    )
    assert r.status_code == 400
    assert "rep_phone" in r.json()["detail"]


def test_twiml_bridge_returns_dial_to_seller(client, db_session):
    lead, _ = _seed(db_session)
    r = client.post(
        "/voice/bridge",
        json={"lead_id": lead.id, "rep_phone": "(813) 555-7777"},
    )
    call_id = r.json()["call_id"]

    r = client.post(f"/voice/twiml/bridge/{call_id}")
    assert r.status_code == 200
    xml = r.text
    assert "<Response>" in xml
    assert "<Dial" in xml
    assert "callerId=" in xml
    # Seller's number gets dialed (numbers escaped, but the digits stay)
    assert "555-0102" in xml
    # Recording is on by default for compliance / coaching
    assert 'record="record-from-answer"' in xml


def test_twiml_bridge_for_unknown_call_hangs_up(client):
    r = client.post("/voice/twiml/bridge/999999")
    assert r.status_code == 200
    assert "<Hangup" in r.text
