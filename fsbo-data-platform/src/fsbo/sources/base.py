from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class NormalizedListing:
    """Source-agnostic vehicle listing shape. Each Source adapter maps into this."""

    source: str
    external_id: str
    url: str

    title: str | None = None
    description: str | None = None

    year: int | None = None
    make: str | None = None
    model: str | None = None
    trim: str | None = None
    mileage: int | None = None
    price: float | None = None
    vin: str | None = None
    license_plate: str | None = None
    license_plate_state: str | None = None
    color: str | None = None
    drivable: bool | None = None

    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    seller_name: str | None = None
    seller_phone: str | None = None

    images: list[str] = field(default_factory=list)
    posted_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class Source(ABC):
    """Abstract source adapter. Each marketplace implements fetch()."""

    name: str

    @abstractmethod
    async def fetch(self, **params: Any) -> AsyncIterator[NormalizedListing]:
        """Yield normalized listings for the given search params."""
        if False:
            yield  # pragma: no cover
