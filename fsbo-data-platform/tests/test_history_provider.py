"""Vehicle-history provider cascade.

When no provider is configured (the dev / CI default), resolve_history
returns a no_provider_configured status so the dashboard can render a
configure-me hint instead of a hard error.
"""

from datetime import datetime, timezone

import pytest

from fsbo.history.providers import (
    AutoCheckProvider,
    CarfaxProvider,
    NmvtisProvider,
    is_any_provider_configured,
    resolve_history,
)
from fsbo.history.types import HistoryReport


def test_no_providers_configured_in_default_env():
    """Default settings have empty keys; cascade returns a stub."""
    assert not is_any_provider_configured()


def test_carfax_unconfigured_returns_none(monkeypatch):
    monkeypatch.setattr("fsbo.config.settings.carfax_api_key", "")
    monkeypatch.setattr("fsbo.config.settings.carfax_account_id", "")
    p = CarfaxProvider()
    assert not p.is_configured()


def test_carfax_needs_both_key_and_account(monkeypatch):
    monkeypatch.setattr("fsbo.config.settings.carfax_api_key", "k")
    monkeypatch.setattr("fsbo.config.settings.carfax_account_id", "")
    assert not CarfaxProvider().is_configured()
    monkeypatch.setattr("fsbo.config.settings.carfax_account_id", "a")
    assert CarfaxProvider().is_configured()


def test_autocheck_needs_both_key_and_account(monkeypatch):
    monkeypatch.setattr("fsbo.config.settings.autocheck_api_key", "k")
    monkeypatch.setattr("fsbo.config.settings.autocheck_account_id", "")
    assert not AutoCheckProvider().is_configured()


def test_nmvtis_only_needs_api_key(monkeypatch):
    monkeypatch.setattr("fsbo.config.settings.nmvtis_api_key", "k")
    assert NmvtisProvider().is_configured()


@pytest.mark.asyncio
async def test_resolve_invalid_vin_short_circuits():
    r = await resolve_history("ABC123")
    assert isinstance(r, HistoryReport)
    assert r.status == "invalid_vin"


@pytest.mark.asyncio
async def test_resolve_no_provider_returns_configure_hint():
    r = await resolve_history("1HGBH41JXMN109186")
    assert r.status == "no_provider_configured"
    assert r.error_detail and "CARFAX" in r.error_detail


@pytest.mark.asyncio
async def test_endpoint_400s_without_vin(client, db_session):
    from fsbo.models import Listing

    db_session.add(
        Listing(
            source="craigslist",
            external_id="cl-no-vin",
            url="http://x",
            title="No VIN here",
            classification="private_seller",
        )
    )
    db_session.flush()
    listing = db_session.query(Listing).first()

    r = client.post(f"/listings/{listing.id}/history/refresh")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_endpoint_returns_no_provider_status(client, db_session):
    from fsbo.models import Listing

    db_session.add(
        Listing(
            source="craigslist",
            external_id="cl-vin-1",
            url="http://x",
            title="2018 Honda Accord",
            vin="1HGBH41JXMN109186",
            classification="private_seller",
        )
    )
    db_session.flush()
    listing = db_session.query(Listing).first()

    r = client.post(f"/listings/{listing.id}/history/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "no_provider_configured"
    # And it's now cached on the listing
    db_session.refresh(listing)
    assert listing.history_report["status"] == "no_provider_configured"
    assert listing.history_report_fetched_at is not None


@pytest.mark.asyncio
async def test_get_cached_returns_empty_dict_when_unfetched(client, db_session):
    from fsbo.models import Listing

    db_session.add(
        Listing(
            source="craigslist",
            external_id="cl-vin-2",
            url="http://x",
            title="x",
            vin="1HGBH41JXMN109187",
            classification="private_seller",
        )
    )
    db_session.flush()
    listing = db_session.query(Listing).first()

    r = client.get(f"/listings/{listing.id}/history")
    assert r.status_code == 200
    assert r.json() == {}


@pytest.mark.asyncio
async def test_endpoint_404s_for_unknown_listing(client):
    r = client.post("/listings/99999/history/refresh")
    assert r.status_code == 404
    r2 = client.get("/listings/99999/history")
    assert r2.status_code == 404
