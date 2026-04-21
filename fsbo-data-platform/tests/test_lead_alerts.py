from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from fsbo.models import (
    Listing,
    NotificationDelivery,
    SavedSearch,
    User,
)


def _register(client, email="alerts@example.com", dealer_name="Alert Co"):
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "supersecret123",
            "dealer_name": dealer_name,
        },
    )
    assert r.status_code == 201
    return r.json()


def test_preferences_get_and_patch(client):
    _register(client, email="prefs@example.com")
    r = client.get("/notifications/preferences")
    assert r.status_code == 200
    body = r.json()
    assert body["alerts_enabled"] is True
    assert body["alert_min_score"] == 80

    patch = client.patch(
        "/notifications/preferences",
        json={"alerts_enabled": False, "alert_min_score": 65},
    )
    assert patch.status_code == 200
    assert patch.json()["alerts_enabled"] is False
    assert patch.json()["alert_min_score"] == 65


def test_preferences_require_auth(client):
    r = client.get("/notifications/preferences")
    assert r.status_code == 401


# ---- Lead alerts worker ----


@pytest.fixture
def _patch_worker_session(db_session, monkeypatch):
    @contextmanager
    def fake_scope():
        yield db_session

    monkeypatch.setattr(
        "fsbo.workers.lead_alerts_worker.session_scope", fake_scope
    )


@pytest.fixture
def _stub_email(monkeypatch):
    calls: list[dict] = []

    async def fake_send_email(to, subject, text, html_body=None, from_address=None):
        from fsbo.messaging.email_client import EmailResult

        calls.append(
            {
                "to": to,
                "subject": subject,
                "text": text,
                "html": html_body,
            }
        )
        return EmailResult(backend="test", sent=True)

    monkeypatch.setattr(
        "fsbo.workers.lead_alerts_worker.send_email",
        fake_send_email,
        raising=True,
    )
    return calls


def _seed_user(db, client, email="buyer@acme.com", dealer_name="Acme"):
    """Register via the API so the session scope commits, then grab the row."""
    reg = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "supersecret123",
            "dealer_name": dealer_name,
        },
    )
    uid = reg.json()["id"]
    user = db.get(User, uid)
    return user


def _seed_saved_search(db, dealer_id: str, query: dict, name="alert-1"):
    ss = SavedSearch(
        dealer_id=dealer_id,
        name=name,
        query=query,
        alerts_enabled=True,
    )
    db.add(ss)
    db.flush()
    return ss


def _seed_listing(db, **overrides):
    defaults = {
        "source": "facebook_marketplace",
        "external_id": f"ext-{id(overrides)}",
        "url": "http://x",
        "title": "2019 Ford F-150",
        "year": 2019,
        "make": "Ford",
        "model": "F-150",
        "mileage": 40000,
        "price": 22000,
        "classification": "private_seller",
        "lead_quality_score": 85,
        "auto_hidden": False,
        "first_seen_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    row = Listing(**defaults)
    db.add(row)
    db.flush()
    return row


@pytest.mark.asyncio
async def test_worker_sends_for_matching_search(
    db_session, client, _patch_worker_session, _stub_email
):
    user = _seed_user(db_session, client, email="match@acme.com")
    _seed_saved_search(
        db_session, user.dealer_id, {"make": "Ford", "min_score": 80}
    )
    _seed_listing(db_session, external_id="hot-1", make="Ford", lead_quality_score=90)

    from fsbo.workers.lead_alerts_worker import run

    stats = await run()
    assert stats["candidates"] == 1
    assert stats["matches"] == 1
    assert stats["sent"] == 1
    assert len(_stub_email) == 1
    assert _stub_email[0]["to"] == "match@acme.com"
    assert "Ford" in _stub_email[0]["subject"]


@pytest.mark.asyncio
async def test_worker_dedups_second_run(
    db_session, client, _patch_worker_session, _stub_email
):
    user = _seed_user(db_session, client, email="dedup@acme.com")
    _seed_saved_search(db_session, user.dealer_id, {"make": "Ford"})
    _seed_listing(db_session, external_id="hot-dedup", make="Ford", lead_quality_score=90)

    from fsbo.workers.lead_alerts_worker import run

    await run()
    first_count = len(_stub_email)
    assert first_count == 1

    await run()
    # Second run must not re-send
    assert len(_stub_email) == first_count


@pytest.mark.asyncio
async def test_worker_respects_user_min_score(
    db_session, client, _patch_worker_session, _stub_email
):
    user = _seed_user(db_session, client, email="min@acme.com")
    user.alert_min_score = 95
    db_session.flush()
    _seed_saved_search(db_session, user.dealer_id, {"make": "Ford"})
    _seed_listing(db_session, external_id="low-score", make="Ford", lead_quality_score=85)

    from fsbo.workers.lead_alerts_worker import run

    stats = await run()
    assert stats["sent"] == 0


@pytest.mark.asyncio
async def test_worker_skips_auto_hidden(
    db_session, client, _patch_worker_session, _stub_email
):
    user = _seed_user(db_session, client, email="hidden@acme.com")
    _seed_saved_search(db_session, user.dealer_id, {"make": "Ford"})
    _seed_listing(
        db_session,
        external_id="hidden",
        make="Ford",
        lead_quality_score=95,
        auto_hidden=True,
    )

    from fsbo.workers.lead_alerts_worker import run

    stats = await run()
    assert stats["sent"] == 0


@pytest.mark.asyncio
async def test_worker_respects_user_alerts_disabled(
    db_session, client, _patch_worker_session, _stub_email
):
    user = _seed_user(db_session, client, email="off@acme.com")
    user.alerts_enabled = False
    db_session.flush()
    _seed_saved_search(db_session, user.dealer_id, {"make": "Ford"})
    _seed_listing(db_session, external_id="disabled", make="Ford", lead_quality_score=90)

    from fsbo.workers.lead_alerts_worker import run

    stats = await run()
    assert stats["sent"] == 0


@pytest.mark.asyncio
async def test_worker_skips_non_matching_search(
    db_session, client, _patch_worker_session, _stub_email
):
    user = _seed_user(db_session, client, email="nomatch@acme.com")
    # Save a search for Honda; listing is a Ford
    _seed_saved_search(db_session, user.dealer_id, {"make": "Honda"})
    _seed_listing(
        db_session, external_id="no-match", make="Ford", lead_quality_score=90
    )

    from fsbo.workers.lead_alerts_worker import run

    stats = await run()
    assert stats["sent"] == 0


@pytest.mark.asyncio
async def test_email_failure_rolls_back_delivery(
    db_session, client, _patch_worker_session, monkeypatch
):
    """If email send fails, the NotificationDelivery row is removed so the
    next run retries."""
    user = _seed_user(db_session, client, email="retry@acme.com")
    _seed_saved_search(db_session, user.dealer_id, {"make": "Ford"})
    _seed_listing(db_session, external_id="retry-1", make="Ford", lead_quality_score=90)

    async def failing_send(to, subject, text, html_body=None, from_address=None):
        from fsbo.messaging.email_client import EmailResult

        return EmailResult(backend="test", sent=False, error="simulated")

    monkeypatch.setattr(
        "fsbo.workers.lead_alerts_worker.send_email", failing_send, raising=True
    )

    from fsbo.workers.lead_alerts_worker import run

    stats = await run()
    assert stats["sent"] == 0
    assert stats["skipped"] >= 1

    # Delivery row should NOT exist (rolled back)
    row = (
        db_session.query(NotificationDelivery)
        .filter_by(user_id=user.id, kind="hot_lead")
        .first()
    )
    assert row is None
