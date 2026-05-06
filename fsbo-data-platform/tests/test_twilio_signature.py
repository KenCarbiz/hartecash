"""Twilio webhook HMAC verification.

The dependency is skipped entirely when TWILIO_AUTH_TOKEN is not
configured (default in dev/CI). When set, Twilio's documented HMAC-
SHA1 of (full URL + sorted form pairs) keyed by the auth token must
match the X-Twilio-Signature header.
"""

import base64
import hashlib
import hmac

import pytest


def _sign(url: str, form: dict[str, str], auth_token: str) -> str:
    payload = url
    for k in sorted(form.keys()):
        payload += k + form[k]
    digest = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


@pytest.fixture
def signed_client(client, monkeypatch):
    monkeypatch.setattr("fsbo.config.settings.twilio_auth_token", "test_auth_token")
    return client


def test_status_webhook_rejects_missing_signature(signed_client):
    r = signed_client.post(
        "/webhooks/twilio/status",
        data={"MessageSid": "SM1", "MessageStatus": "delivered"},
    )
    assert r.status_code == 403
    assert "missing twilio signature" in r.json()["detail"].lower()


def test_status_webhook_rejects_bad_signature(signed_client):
    r = signed_client.post(
        "/webhooks/twilio/status",
        data={"MessageSid": "SM1", "MessageStatus": "delivered"},
        headers={"X-Twilio-Signature": "deadbeef"},
    )
    assert r.status_code == 403
    assert "invalid" in r.json()["detail"].lower()


def test_status_webhook_accepts_valid_signature(signed_client):
    form = {"MessageSid": "SM1", "MessageStatus": "delivered"}
    # The signature dep reconstructs the URL Twilio saw; in TestClient
    # that's the same as the request URL.
    sig = _sign("http://testserver/webhooks/twilio/status", form, "test_auth_token")
    r = signed_client.post(
        "/webhooks/twilio/status",
        data=form,
        headers={"X-Twilio-Signature": sig},
    )
    assert r.status_code == 200


def test_inbound_webhook_rejects_bad_signature(signed_client):
    r = signed_client.post(
        "/webhooks/twilio/inbound",
        data={
            "From": "+18135551234",
            "To": "+18135559999",
            "Body": "Yes still available",
            "MessageSid": "SM2",
        },
        headers={"X-Twilio-Signature": "wrong"},
    )
    assert r.status_code == 403


def test_dev_mode_skips_signature_check(client):
    """When TWILIO_AUTH_TOKEN is empty, the dep is a no-op so dev/CI
    doesn't need to compute a signature."""
    r = client.post(
        "/webhooks/twilio/status",
        data={"MessageSid": "SM3", "MessageStatus": "delivered"},
    )
    assert r.status_code == 200
