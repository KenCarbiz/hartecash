from fsbo.models import Lead, Listing, Message


def _seed_lead(db, phone="(813) 555-0101"):
    listing = Listing(
        source="craigslist",
        external_id="cl-1",
        url="http://x",
        title="2019 F-150",
        year=2019,
        make="Ford",
        model="F-150",
        seller_phone=phone,
        classification="private_seller",
    )
    db.add(listing)
    db.flush()
    lead = Lead(dealer_id="dealer-1", listing_id=listing.id, status="contacted")
    db.add(lead)
    db.flush()
    return lead, listing


def test_send_without_twilio_configured_records_as_skipped(client, db_session, monkeypatch):
    monkeypatch.setattr("fsbo.config.settings.twilio_account_sid", "", raising=True)
    monkeypatch.setattr("fsbo.config.settings.twilio_auth_token", "", raising=True)

    lead, _ = _seed_lead(db_session)
    r = client.post(
        "/messages/send",
        json={"lead_id": lead.id, "body": "Hi — is it still available?"},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "skipped"
    # Message row was still written so the outreach wasn't lost
    stored = db_session.query(Message).filter_by(lead_id=lead.id).all()
    assert len(stored) == 1
    assert stored[0].status == "skipped"


def test_cross_dealer_forbidden(client, db_session):
    lead, _ = _seed_lead(db_session)
    r = client.post(
        "/messages/send",
        json={"lead_id": lead.id, "body": "hi"},
        headers={"X-Dealer-Id": "dealer-other"},
    )
    assert r.status_code == 404


def test_missing_phone_errors(client, db_session):
    lead, listing = _seed_lead(db_session, phone=None)
    r = client.post(
        "/messages/send",
        json={"lead_id": lead.id, "body": "hi"},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    assert r.status_code == 400


def test_inbound_webhook_routes_to_matching_lead(client, db_session):
    lead, listing = _seed_lead(db_session, phone="(813) 555-0101")

    r = client.post(
        "/webhooks/twilio/inbound",
        data={
            "From": "+18135550101",
            "To": "+15558675309",
            "Body": "Still available",
            "MessageSid": "SMabc123",
        },
    )
    assert r.status_code == 200
    messages = db_session.query(Message).filter_by(lead_id=lead.id).all()
    assert any(m.direction == "inbound" and m.body == "Still available" for m in messages)


def test_status_webhook_updates_delivery(client, db_session):
    lead, _ = _seed_lead(db_session)
    msg = Message(
        dealer_id="dealer-1",
        lead_id=lead.id,
        direction="outbound",
        to_number="+18135550101",
        body="hi",
        status="queued",
        twilio_sid="SMxyz",
    )
    db_session.add(msg)
    db_session.flush()

    r = client.post(
        "/webhooks/twilio/status",
        data={"MessageSid": "SMxyz", "MessageStatus": "delivered"},
    )
    assert r.status_code == 200
    db_session.refresh(msg)
    assert msg.status == "delivered"
    assert msg.delivered_at is not None
