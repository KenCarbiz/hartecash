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
    license_plate: str | None = None
    license_plate_state: str | None = None
    color: str | None = None
    drivable: bool | None = None

    city: str | None
    state: str | None
    zip_code: str | None

    seller_phone: str | None

    classification: str
    classification_confidence: float | None
    classification_reason: str | None

    dealer_likelihood: float | None = None
    scam_score: float | None = None
    lead_quality_score: int | None = None
    quality_breakdown: dict = {}
    auto_hidden: bool = False
    auto_hide_reason: str | None = None

    images: list[str]
    posted_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime


class ListingsPage(BaseModel):
    items: list[ListingOut]
    total: int
    limit: int
    offset: int
