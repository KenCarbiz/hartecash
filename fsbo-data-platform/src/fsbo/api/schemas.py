from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    external_id: str
    url: str

    title: str | None
    description: str | None

    year: int | None
    make: str | None
    model: str | None
    trim: str | None
    mileage: int | None
    price: float | None
    vin: str | None

    city: str | None
    state: str | None
    zip_code: str | None

    seller_phone: str | None

    classification: str
    classification_confidence: float | None
    classification_reason: str | None

    images: list[str]
    posted_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime


class ListingsPage(BaseModel):
    items: list[ListingOut]
    total: int
    limit: int
    offset: int
