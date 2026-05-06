"""Vehicle-history report shape.

Common-denominator schema across CARFAX / AutoCheck / NMVTIS / Bumper
so the dashboard can render a single component regardless of which
provider answered. Each provider adapter normalizes its native shape
into this dataclass; the source field tells the UI which logo to show
+ whether to add a "view full report" deep link.

Title-brand vocabulary is the NMVTIS list (the federal source of
truth) so quality.py's existing scorer can consume it directly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Literal

# NMVTIS-aligned title brands.
TitleBrand = Literal[
    "clean",
    "salvage",
    "rebuilt",
    "flood",
    "lemon",
    "junk",
    "theft_reported",
    "manufacturer_buyback",
    "odometer_rollback",
    "unknown",
]


@dataclass
class HistoryEvent:
    """One row in the timeline (an accident, owner change, service
    record, registration, etc.). Free-text date because providers
    sometimes return only year-month."""

    kind: str  # "accident" | "owner_change" | "service" | "registration" | "title_event" | "other"
    when: str  # ISO yyyy-mm-dd or yyyy-mm
    location: str | None = None
    description: str = ""


@dataclass
class HistoryReport:
    vin: str | None
    source: str  # "carfax" | "autocheck" | "nmvtis" | "bumper" | "stub"
    fetched_at: str  # ISO timestamp
    title_brand: TitleBrand = "unknown"
    accident_count: int | None = None
    open_recall_count: int | None = None
    owner_count: int | None = None
    service_record_count: int | None = None
    last_reported_mileage: int | None = None
    last_reported_mileage_date: str | None = None
    use_type: str | None = None  # "personal" | "fleet" | "rental" | "lease"
    events: list[HistoryEvent] = field(default_factory=list)
    # The "view in [provider]" deep-link the dealer can click.
    full_report_url: str | None = None
    # Free-text "no key configured" / "VIN not found" / etc. when we
    # have nothing else to return.
    status: str = "ok"
    error_detail: str | None = None

    def as_dict(self) -> dict:
        d = asdict(self)
        d["events"] = [asdict(e) for e in self.events]
        return d
