"""Seed the database with realistic fake FSBO listings for demos.

Usage:
    python scripts/seed_demo.py              # default 50 listings
    python scripts/seed_demo.py --count 200
    python scripts/seed_demo.py --wipe       # truncate first
"""

import argparse
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from fsbo.db import session_scope
from fsbo.logging import configure, get_logger
from fsbo.models import Classification, Listing

log = get_logger(__name__)

_MAKES_MODELS = [
    ("Ford", ["F-150", "F-250", "Explorer", "Escape", "Mustang", "Ranger"]),
    ("Chevrolet", ["Silverado", "Tahoe", "Suburban", "Equinox", "Camaro", "Traverse"]),
    ("Toyota", ["Tacoma", "Tundra", "4Runner", "Camry", "RAV4", "Highlander"]),
    ("Honda", ["Civic", "Accord", "CR-V", "Pilot", "Odyssey"]),
    ("Jeep", ["Wrangler", "Grand Cherokee", "Cherokee", "Gladiator"]),
    ("Ram", ["1500", "2500", "3500"]),
    ("GMC", ["Sierra", "Yukon", "Acadia"]),
    ("Nissan", ["Titan", "Frontier", "Altima", "Rogue"]),
    ("Subaru", ["Outback", "Forester", "Crosstrek"]),
    ("BMW", ["3 Series", "X3", "X5"]),
]

_CITIES = [
    ("Tampa", "FL", "33607"),
    ("Orlando", "FL", "32801"),
    ("Miami", "FL", "33101"),
    ("Jacksonville", "FL", "32202"),
    ("Atlanta", "GA", "30301"),
    ("Charlotte", "NC", "28201"),
    ("Nashville", "TN", "37201"),
    ("Dallas", "TX", "75201"),
    ("Houston", "TX", "77001"),
    ("Austin", "TX", "78701"),
    ("Phoenix", "AZ", "85001"),
    ("Denver", "CO", "80201"),
]

_SOURCES = ["craigslist", "ebay_motors", "facebook_marketplace", "offerup"]

_PRIVATE_DESCRIPTIONS = [
    "Selling my daily driver. One owner, clean title, all maintenance records. Text preferred.",
    "Wife wants a new car so this has to go. Runs great, no issues. Cash only please.",
    "Moving out of state, need to sell quick. Great condition, highway miles.",
    "Inherited from my father, barely driven. Clean inside and out, non-smoker.",
    "Had this truck for years, great work vehicle. Time to upgrade. Serious inquiries only.",
    "Just hit 60k miles, all services done at the dealer. Clean Carfax available.",
    "New brakes last month, new tires. Priced to sell. Please no lowballs.",
]

_DEALER_DESCRIPTIONS = [
    "Financing available! No credit needed! Trade-ins welcome! Call today!",
    "We finance everyone! Bad credit, no credit, no problem! $0 down!",
    "Clean Carfax, certified, warranty included. Apply online for instant approval.",
    "Buy here pay here. Easy financing. Over 200 vehicles in stock at our lot.",
]

_SCAM_DESCRIPTIONS = [
    "Must sell, deployed military, shipping only. eBay Motors Protection payment. Email only.",
    "Overseas buyer OK. Western Union. Gift card accepted as partial payment.",
    "Price firm, shipping available worldwide. Wire transfer only.",
]


def _generate(count: int, now: datetime) -> list[Listing]:
    rows = []
    for i in range(count):
        make, models = random.choice(_MAKES_MODELS)
        model = random.choice(models)
        year = random.randint(2008, 2023)
        mileage = random.randint(15_000, 180_000)
        city, state, zip_code = random.choice(_CITIES)

        # 70% private, 20% dealer, 10% scam — realistic FSBO marketplace mix
        roll = random.random()
        if roll < 0.70:
            classification = Classification.PRIVATE_SELLER.value
            description = random.choice(_PRIVATE_DESCRIPTIONS)
            confidence = round(random.uniform(0.75, 0.98), 2)
            reason = "heuristics: no dealer/scam keywords"
        elif roll < 0.90:
            classification = Classification.DEALER.value
            description = random.choice(_DEALER_DESCRIPTIONS)
            confidence = round(random.uniform(0.85, 0.99), 2)
            reason = "heuristics: dealer keywords (financing, trade-ins)"
        else:
            classification = Classification.SCAM.value
            description = random.choice(_SCAM_DESCRIPTIONS)
            confidence = round(random.uniform(0.80, 0.95), 2)
            reason = "heuristics: scam keywords (shipping only, wire transfer)"

        price = _realistic_price(year, mileage)
        source = random.choice(_SOURCES)
        posted_at = now - timedelta(
            hours=random.randint(0, 72), minutes=random.randint(0, 59)
        )

        title = f"{year} {make} {model} - ${price:,}"
        if classification == Classification.PRIVATE_SELLER.value and random.random() < 0.4:
            title += " - By Owner"

        phone = None
        if classification == Classification.PRIVATE_SELLER.value and random.random() < 0.6:
            phone = f"({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"

        rows.append(
            Listing(
                source=source,
                external_id=f"demo-{i}-{random.randint(1_000_000, 9_999_999)}",
                url=f"https://example.com/listing/demo-{i}",
                title=title,
                description=description,
                year=year,
                make=make,
                model=model,
                mileage=mileage,
                price=float(price),
                vin=None,
                city=city,
                state=state,
                zip_code=zip_code,
                seller_phone=phone,
                classification=classification,
                classification_confidence=confidence,
                classification_reason=reason,
                images=[],
                posted_at=posted_at,
                raw={"demo": True},
            )
        )
    return rows


def _realistic_price(year: int, mileage: int) -> int:
    """Very rough depreciation model — good enough for demo data."""
    base = 45_000
    age = max(0, datetime.now().year - year)
    price = base * (0.82**age)
    price *= max(0.25, 1 - mileage / 250_000)
    price *= random.uniform(0.8, 1.2)
    return max(1500, int(round(price / 500) * 500))


def main() -> None:
    configure()
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--wipe", action="store_true", help="Delete demo rows first")
    args = parser.parse_args()

    random.seed()
    now = datetime.now(timezone.utc)

    with session_scope() as db:
        if args.wipe:
            removed = db.execute(
                delete(Listing).where(Listing.raw["demo"].as_boolean().is_(True))
            )
            log.info("seed.wiped", rows=removed.rowcount)

        rows = _generate(args.count, now)
        db.add_all(rows)

    log.info("seed.done", inserted=len(rows))


if __name__ == "__main__":
    main()
