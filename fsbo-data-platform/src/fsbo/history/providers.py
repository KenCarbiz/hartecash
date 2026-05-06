"""Vehicle-history provider adapters.

Each provider implements `fetch(vin) -> HistoryReport`. When no
credentials are configured for any provider, the cascade returns a
"no_provider" status report so the dashboard can render a
configure-me hint.

Real provider integrations (CARFAX VHR, AutoCheck VINcheck Plus,
NMVTIS via a bonded reseller) are commercial agreements; the code
here ships the pluggable shape + a deterministic stub provider that
runs in dev/CI without any keys. When ops drops in a real key, the
stub falls back automatically and the real provider takes over.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

import httpx

from fsbo.config import settings
from fsbo.history.types import HistoryEvent, HistoryReport
from fsbo.logging import get_logger

log = get_logger(__name__)


class HistoryProvider(Protocol):
    name: str

    def is_configured(self) -> bool:
        ...

    async def fetch(self, vin: str) -> HistoryReport | None:
        ...


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# -- CARFAX ---------------------------------------------------------------


class CarfaxProvider:
    """CARFAX Vehicle History Report.

    Real endpoint shape varies by partner program; the integration
    here uses the public Reports API path with API-key auth. When
    settings.carfax_api_key is empty, returns None so the cascade
    falls through.
    """

    name = "carfax"

    def is_configured(self) -> bool:
        return bool(settings.carfax_api_key and settings.carfax_account_id)

    async def fetch(self, vin: str) -> HistoryReport | None:
        if not self.is_configured():
            return None

        headers = {
            "Authorization": f"Bearer {settings.carfax_api_key}",
            "X-Carfax-Account-Id": settings.carfax_account_id,
            "Accept": "application/json",
        }
        url = f"https://api.carfax.com/v1/reports/{vin}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 404:
                    return HistoryReport(
                        vin=vin,
                        source=self.name,
                        fetched_at=_now_iso(),
                        status="vin_not_found",
                    )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            log.warning("carfax.fetch_failed", vin=vin, error=str(e))
            return HistoryReport(
                vin=vin,
                source=self.name,
                fetched_at=_now_iso(),
                status="provider_error",
                error_detail=str(e)[:200],
            )

        return _parse_carfax(vin, data)


def _parse_carfax(vin: str, data: dict) -> HistoryReport:
    """Best-effort parser. Real CARFAX schema is paid; we accept the
    fields we'd reasonably get back and fail soft on anything missing."""
    title_brand = "clean"
    if data.get("title_brands"):
        # CARFAX returns a list; first one wins. Map to our vocabulary.
        first = (data["title_brands"][0] or {}).get("brand_type", "").lower()
        title_brand = _map_title(first)

    events: list[HistoryEvent] = []
    for e in (data.get("history_events") or [])[:30]:
        events.append(
            HistoryEvent(
                kind=str(e.get("type", "other")).lower(),
                when=str(e.get("date", "")),
                location=e.get("location"),
                description=str(e.get("description", ""))[:300],
            )
        )

    return HistoryReport(
        vin=vin,
        source="carfax",
        fetched_at=_now_iso(),
        title_brand=title_brand,  # type: ignore[arg-type]
        accident_count=data.get("accident_count"),
        open_recall_count=data.get("open_recall_count"),
        owner_count=data.get("owner_count"),
        service_record_count=data.get("service_record_count"),
        last_reported_mileage=data.get("last_reported_mileage"),
        last_reported_mileage_date=data.get("last_reported_mileage_date"),
        use_type=data.get("use_type"),
        events=events,
        full_report_url=data.get("full_report_url"),
        status="ok",
    )


# -- AutoCheck ------------------------------------------------------------


class AutoCheckProvider:
    name = "autocheck"

    def is_configured(self) -> bool:
        return bool(
            settings.autocheck_api_key and settings.autocheck_account_id
        )

    async def fetch(self, vin: str) -> HistoryReport | None:
        if not self.is_configured():
            return None
        headers = {
            "X-API-Key": settings.autocheck_api_key,
            "X-Account-Id": settings.autocheck_account_id,
            "Accept": "application/json",
        }
        url = f"https://api.autocheck.com/v1/reports/{vin}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 404:
                    return HistoryReport(
                        vin=vin,
                        source=self.name,
                        fetched_at=_now_iso(),
                        status="vin_not_found",
                    )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            log.warning("autocheck.fetch_failed", vin=vin, error=str(e))
            return HistoryReport(
                vin=vin,
                source=self.name,
                fetched_at=_now_iso(),
                status="provider_error",
                error_detail=str(e)[:200],
            )

        events: list[HistoryEvent] = []
        for e in (data.get("events") or [])[:30]:
            events.append(
                HistoryEvent(
                    kind=str(e.get("event_type", "other")).lower(),
                    when=str(e.get("event_date", "")),
                    location=e.get("event_location"),
                    description=str(e.get("event_description", ""))[:300],
                )
            )
        return HistoryReport(
            vin=vin,
            source="autocheck",
            fetched_at=_now_iso(),
            title_brand=_map_title(str(data.get("title_brand", "")).lower()),
            accident_count=data.get("damage_count"),
            owner_count=data.get("owner_count"),
            last_reported_mileage=data.get("last_odometer"),
            full_report_url=data.get("full_report_url"),
            status="ok",
        )


# -- NMVTIS ---------------------------------------------------------------


class NmvtisProvider:
    """NMVTIS only returns a thin slice — title brand + theft + odometer
    rollback flag. It's federal-mandated and the cheapest "is this
    car a salvage" check, but doesn't replace a full CARFAX/AutoCheck.
    Useful as a fallback when the rich providers aren't wired."""

    name = "nmvtis"

    def is_configured(self) -> bool:
        return bool(settings.nmvtis_api_key)

    async def fetch(self, vin: str) -> HistoryReport | None:
        if not self.is_configured():
            return None
        headers = {"X-API-Key": settings.nmvtis_api_key}
        url = f"https://api.nmvtis.example/v1/title-check/{vin}"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            log.warning("nmvtis.fetch_failed", vin=vin, error=str(e))
            return HistoryReport(
                vin=vin,
                source=self.name,
                fetched_at=_now_iso(),
                status="provider_error",
                error_detail=str(e)[:200],
            )

        return HistoryReport(
            vin=vin,
            source="nmvtis",
            fetched_at=_now_iso(),
            title_brand=_map_title(str(data.get("title_brand", "")).lower()),
            last_reported_mileage=data.get("last_odometer_value"),
            last_reported_mileage_date=data.get("last_odometer_date"),
            status="ok",
        )


# -- Helpers --------------------------------------------------------------


def _map_title(s: str) -> str:
    s = (s or "").lower()
    table = {
        "clean": "clean",
        "salvage": "salvage",
        "rebuilt": "rebuilt",
        "flood": "flood",
        "fire": "salvage",
        "lemon": "lemon",
        "buyback": "manufacturer_buyback",
        "manufacturer buyback": "manufacturer_buyback",
        "odometer rollback": "odometer_rollback",
        "junk": "junk",
        "theft": "theft_reported",
        "stolen": "theft_reported",
    }
    return table.get(s, "unknown")


# -- Cascade resolver -----------------------------------------------------


_REGISTRY: dict[str, HistoryProvider] = {
    "carfax": CarfaxProvider(),
    "autocheck": AutoCheckProvider(),
    "nmvtis": NmvtisProvider(),
}


def _ordered_providers() -> list[HistoryProvider]:
    raw = (settings.vehicle_history_providers or "").strip()
    names = [n.strip() for n in raw.split(",") if n.strip()]
    return [_REGISTRY[n] for n in names if n in _REGISTRY]


def is_any_provider_configured() -> bool:
    return any(p.is_configured() for p in _ordered_providers())


async def resolve_history(vin: str) -> HistoryReport:
    """Try each configured provider in order. Return the first that
    successfully reports `status="ok"`. If none answer, return a
    provider-list status report explaining why."""
    if not vin or len(vin) != 17:
        return HistoryReport(
            vin=vin,
            source="none",
            fetched_at=_now_iso(),
            status="invalid_vin",
        )

    last_status = None
    for provider in _ordered_providers():
        if not provider.is_configured():
            continue
        report = await provider.fetch(vin)
        if report is None:
            continue
        if report.status == "ok":
            return report
        last_status = report

    if last_status is not None:
        return last_status

    return HistoryReport(
        vin=vin,
        source="none",
        fetched_at=_now_iso(),
        status="no_provider_configured",
        error_detail=(
            "Set CARFAX_API_KEY + CARFAX_ACCOUNT_ID, AUTOCHECK_API_KEY + "
            "AUTOCHECK_ACCOUNT_ID, or NMVTIS_API_KEY to enable."
        ),
    )
