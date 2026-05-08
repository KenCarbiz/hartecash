"""Per-dealer quiet-hours override.

GET /tcpa/quiet-hours returns the active window (federal default
8 AM - 8 PM, or the dealer's override). PUT /tcpa/quiet-hours
tightens; loosening past federal is rejected.
"""

from datetime import datetime, time
from itertools import count
from zoneinfo import ZoneInfo

import pytest

from fsbo.messaging.tcpa import in_quiet_hours
from fsbo.models import Dealer, Listing


_ext = count(1)


@pytest.fixture
def _disable_autopatch(monkeypatch):
    """Undo conftest's autouse 'always allow quiet hours' patch — these
    tests need to actually exercise the gate."""
    import fsbo.messaging.tcpa as tcpa_module

    # Restore the real implementation by re-importing the module's
    # bound name from itself (we just monkeypatched it in conftest).
    monkeypatch.setattr(
        tcpa_module,
        "in_quiet_hours",
        in_quiet_hours.__wrapped__ if hasattr(in_quiet_hours, "__wrapped__") else in_quiet_hours,
    )


def _seed_dealer(db, slug="demo-dealer", **overrides) -> Dealer:
    base = dict(slug=slug, name=slug.title())
    base.update(overrides)
    dealer = Dealer(**base)
    db.add(dealer)
    db.flush()
    return dealer


def test_default_window_when_no_override(client, db_session):
    _seed_dealer(db_session)
    body = client.get("/tcpa/quiet-hours").json()
    assert body["start"] == "08:00"
    assert body["end"] == "20:00"
    assert body["is_override"] is False


def test_put_override_tightens_window(client, db_session):
    _seed_dealer(db_session)
    r = client.put(
        "/tcpa/quiet-hours", json={"start": "09:00", "end": "18:00"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["start"] == "09:00"
    assert body["end"] == "18:00"
    assert body["is_override"] is True

    # GET round-trips the saved override.
    body = client.get("/tcpa/quiet-hours").json()
    assert body["start"] == "09:00"


def test_put_clears_override_with_null(client, db_session):
    _seed_dealer(db_session)
    client.put("/tcpa/quiet-hours", json={"start": "09:00", "end": "18:00"})
    cleared = client.put("/tcpa/quiet-hours", json={"start": None, "end": None})
    assert cleared.status_code == 200
    assert cleared.json()["is_override"] is False


def test_loosening_below_federal_start_400s(client, db_session):
    _seed_dealer(db_session)
    r = client.put(
        "/tcpa/quiet-hours", json={"start": "07:00", "end": "20:00"}
    )
    assert r.status_code == 400
    assert "08:00" in r.json()["detail"]


def test_loosening_past_federal_end_400s(client, db_session):
    _seed_dealer(db_session)
    r = client.put(
        "/tcpa/quiet-hours", json={"start": "08:00", "end": "21:00"}
    )
    assert r.status_code == 400
    assert "20:00" in r.json()["detail"]


def test_invalid_format_400s(client, db_session):
    _seed_dealer(db_session)
    r = client.put("/tcpa/quiet-hours", json={"start": "9am", "end": "18:00"})
    assert r.status_code == 400


def test_start_after_end_400s(client, db_session):
    _seed_dealer(db_session)
    r = client.put(
        "/tcpa/quiet-hours", json={"start": "19:00", "end": "10:00"}
    )
    assert r.status_code == 400
    assert "before end" in r.json()["detail"]


def test_in_quiet_hours_helper_honors_override():
    """Helper-level test — bypasses the gate's autouse patch by calling
    in_quiet_hours directly with an explicit `when`."""
    eastern = ZoneInfo("America/New_York")
    # 7 AM Eastern is INSIDE federal quiet hours (before 8 AM)
    when = datetime(2026, 5, 6, 7, 0, tzinfo=eastern)
    assert in_quiet_hours("33607", when=when) is True
    # 9 AM Eastern is OUTSIDE federal quiet hours
    when = datetime(2026, 5, 6, 9, 0, tzinfo=eastern)
    assert in_quiet_hours("33607", when=when) is False
    # But with a 10 AM start override, 9 AM is back inside quiet hours.
    assert (
        in_quiet_hours("33607", when=when, start="10:00", end="20:00")
        is True
    )
    # And with a 17:00 end override, 6 PM is also quiet.
    when = datetime(2026, 5, 6, 18, 0, tzinfo=eastern)
    assert in_quiet_hours("33607", when=when, end="17:00") is True


def test_check_send_allowed_uses_dealer_override(monkeypatch, db_session):
    """When the dealer has tightened to 10 AM start, a 9 AM Eastern call
    blocks even though federal default would allow it."""
    _seed_dealer(db_session, quiet_hours_start="10:00", quiet_hours_end="20:00")
    listing = Listing(
        source="craigslist",
        external_id=f"cl-qh-{next(_ext)}",
        url="http://x",
        title="x",
        seller_phone="(813) 555-0100",
        zip_code="33607",
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()

    # Pin "now" to 9 AM Eastern by patching the tcpa module-level helper
    # back to the real one + injecting a fake _local_now.
    import fsbo.messaging.tcpa as tcpa_module

    eastern = ZoneInfo("America/New_York")
    fake_now = datetime(2026, 5, 6, 9, 0, tzinfo=eastern)
    monkeypatch.setattr(
        tcpa_module,
        "in_quiet_hours",
        lambda zip_code, when=None, *, start=None, end=None: not (
            time(int((start or "08:00").split(":")[0]),
                 int((start or "08:00").split(":")[1]))
            <= fake_now.astimezone(eastern).time()
            < time(int((end or "20:00").split(":")[0]),
                   int((end or "20:00").split(":")[1]))
        ),
    )

    from fsbo.messaging.tcpa import check_send_allowed

    result = check_send_allowed(
        db_session,
        dealer_id="demo-dealer",
        phone="(813) 555-0100",
        zip_code="33607",
    )
    assert result.allowed is False
    assert result.blocked_reason == "quiet_hours"
    assert "10:00" in result.detail
