"""Extension onboarding via short-lived install codes."""

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from fsbo.models import ApiKey, ExtensionInstallCode


def test_issue_code_returns_8_char_alphanumeric(client):
    r = client.post("/extension/install-code")
    assert r.status_code == 201
    body = r.json()
    code = body["code"]
    assert len(code) == 8
    assert code.isalnum()
    assert body["expires_in_seconds"] >= 540  # ~10 min minus tiny clock skew


def test_exchange_returns_api_key_and_marks_code_used(client, db_session):
    issue = client.post("/extension/install-code").json()
    code = issue["code"]

    r = client.post(
        "/extension/exchange-install-code",
        json={"code": code},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["api_key"].startswith("ac_live_")
    assert body["dealer_id"] == "demo-dealer"

    # The same code can't be used twice.
    r2 = client.post(
        "/extension/exchange-install-code",
        json={"code": code},
    )
    assert r2.status_code == 404

    # And the issued ApiKey row exists for this dealer.
    keys = db_session.scalars(
        select(ApiKey).where(ApiKey.dealer_id == "demo-dealer")
    ).all()
    assert len(keys) == 1
    assert keys[0].name == "Browser extension (auto-provisioned)"


def test_exchange_rejects_unknown_code(client):
    r = client.post(
        "/extension/exchange-install-code",
        json={"code": "AAAAAAAA"},
    )
    assert r.status_code == 404


def test_exchange_rejects_expired_code(client, db_session):
    issue = client.post("/extension/install-code").json()
    code = issue["code"]

    # Force expiry by rewriting the row's expires_at into the past.
    row = db_session.scalar(select(ExtensionInstallCode))
    assert row is not None
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.flush()

    r = client.post(
        "/extension/exchange-install-code",
        json={"code": code},
    )
    assert r.status_code == 404


def test_issuing_a_new_code_invalidates_the_prior_unused_one(client):
    first = client.post("/extension/install-code").json()
    second = client.post("/extension/install-code").json()
    assert first["code"] != second["code"]

    # The first code can no longer be exchanged.
    r1 = client.post(
        "/extension/exchange-install-code",
        json={"code": first["code"]},
    )
    assert r1.status_code == 404

    # The second still works.
    r2 = client.post(
        "/extension/exchange-install-code",
        json={"code": second["code"]},
    )
    assert r2.status_code == 200
