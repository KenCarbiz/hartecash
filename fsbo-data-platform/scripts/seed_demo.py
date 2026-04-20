"""Seed the database with realistic fake FSBO listings for demos.

Populates every enrichment field (classification, quality score, market
estimate, attributes, price history) so a new dashboard renders fully
populated the moment this runs.

Usage:
    python scripts/seed_demo.py              # default 60 listings
    python scripts/seed_demo.py --count 200
    python scripts/seed_demo.py --wipe
"""

import argparse
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from fsbo.db import session_scope
from fsbo.enrichment.attributes import extract as extract_attrs
from fsbo.enrichment.dealer_signals import assess as assess_dealer
from fsbo.enrichment.dedup import compute_dedup_key
from fsbo.enrichment.quality import score_listing
from fsbo.logging import configure, get_logger
from fsbo.models import Classification, Listing, PriceHistory
from fsbo.sources.base import NormalizedListing
from fsbo.valuation.market import estimate as estimate_market

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
    "Selling my daily driver. One owner, clean title, non-smoker, all maintenance records. Text preferred. OBO.",
    "Wife wants a new car so this has to go. Runs great, no issues. Clean Carfax. Cash only please.",
    "Moving out of state, need to sell quick. Great condition, highway miles. Heated seats, bluetooth, backup camera.",
    "Inherited from my father, barely driven. Clean title inside and out, non-smoker. Leather interior, sunroof.",
    "Had this truck for years, great work vehicle. Time to upgrade. 4x4, tow package, no accidents. Serious inquiries only.",
    "Just hit 60k miles, all services done at the dealer. Clean Carfax available. Turbo, Apple CarPlay.",
    "New brakes last month, new tires. Priced to sell. One owner. No low balls please.",
    "2nd owner, manual transmission. Service records from day one. Navigation and remote start. OBO.",
]

_DEALER_DESCRIPTIONS = [
    "Financing available! No credit needed! Trade-ins welcome! Call our sales office today!",
    "We finance everyone! Bad credit, no credit, no problem! $0 down! Stock # 48291. APR starting 5.99%",
    "Clean Carfax, certified, warranty included. Apply online for instant approval. Visit our showroom.",
    "Buy here pay here. Easy financing. Over 200 vehicles in stock at our lot. Open 7 days.",
    "Financiamiento fácil. Sin crédito OK. Tenemos más carros en nuestro lote. Aceptamos cambios.",
]

_SCAM_DESCRIPTIONS = [
    "Must sell, deployed military, shipping only. eBay Motors Protection payment. Email only.",
    "Overseas buyer OK. Western Union. Gift card accepted as partial payment.",
    "Price firm, shipping available worldwide. Wire transfer only. MoneyGram accepted.",
]


def _realistic_price(year: int, mileage: int) -> int:
    base = 45_000
    age = max(0, datetime.now().year - year)
    price = base * (0.82**age)
    price *= max(0.25, 1 - mileage / 250_000)
    price *= random.uniform(0.8, 1.2)
    return max(1500, int(round(price / 500) * 500))


def _generate(count: int, now: datetime) -> list[tuple[Listing, list[tuple[float, int]]]]:
    """Return (listing, price_history_offsets) tuples so we can write the
    price_history table after inserting the listing.
    """
    out: list[tuple[Listing, list[tuple[float, int]]]] = []
    for i in range(count):
        make, models = random.choice(_MAKES_MODELS)
        model = random.choice(models)
        year = random.randint(2008, 2024)
        mileage = random.randint(15_000, 180_000)
        city, state, zip_code = random.choice(_CITIES)

        roll = random.random()
        if roll < 0.70:
            classification = Classification.PRIVATE_SELLER.value
            description = random.choice(_PRIVATE_DESCRIPTIONS)
        elif roll < 0.90:
            classification = Classification.DEALER.value
            description = random.choice(_DEALER_DESCRIPTIONS)
        else:
            classification = Classification.SCAM.value
            description = random.choice(_SCAM_DESCRIPTIONS)

        price = _realistic_price(year, mileage)
        source = random.choice(_SOURCES)
        # Spread posted_at across the past 60 days to exercise days-on-market buckets.
        days_ago = random.choices(
            [0, 1, 3, 7, 14, 30, 60], weights=[20, 15, 20, 15, 10, 10, 10], k=1
        )[0]
        posted_at = now - timedelta(days=days_ago, hours=random.randint(0, 23))

        title = f"{year} {make} {model} - ${price:,}"
        if classification == Classification.PRIVATE_SELLER.value and random.random() < 0.4:
            title += " - By Owner"

        phone = None
        if classification == Classification.PRIVATE_SELLER.value and random.random() < 0.6:
            phone = f"({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"

        # Simulate price drops for ~25% of older listings.
        price_history_offsets: list[tuple[float, int]] = [(float(price + random.randint(500, 3000)), days_ago)]
        if days_ago >= 14 and random.random() < 0.30:
            n_drops = random.choice([1, 1, 2, 3])
            # Walk the price down in steps from initial to final.
            initial = price_history_offsets[0][0]
            step = (initial - price) / (n_drops + 1)
            for d in range(n_drops):
                drop_days_ago = max(
                    1, days_ago - int((d + 1) * days_ago / (n_drops + 1))
                )
                price_history_offsets.append(
                    (initial - step * (d + 1), drop_days_ago)
                )
        # Always add the current price.
        price_history_offsets.append((float(price), 0))

        listing = Listing(
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
            images=[],
            posted_at=posted_at,
            raw={"demo": True},
        )
        out.append((listing, price_history_offsets))
    return out


def main() -> None:
    configure()
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--wipe", action="store_true")
    args = parser.parse_args()

    random.seed()
    now = datetime.now(timezone.utc)

    with session_scope() as db:
        if args.wipe:
            # Clean out demo rows + their price history.
            demo_ids = [
                row.id
                for row in db.query(Listing).all()
                if isinstance(row.raw, dict) and row.raw.get("demo")
            ]
            if demo_ids:
                db.execute(delete(PriceHistory).where(PriceHistory.listing_id.in_(demo_ids)))
                db.execute(delete(Listing).where(Listing.id.in_(demo_ids)))
                log.info("seed.wiped", rows=len(demo_ids))

        generated = _generate(args.count, now)
        for listing, _ in generated:
            db.add(listing)
        db.flush()

        # Pass 1: dedup keys + dealer likelihood + attributes
        for listing, _history in generated:
            norm = NormalizedListing(
                source=listing.source,
                external_id=listing.external_id,
                url=listing.url,
                title=listing.title,
                description=listing.description,
                year=listing.year,
                make=listing.make,
                model=listing.model,
                mileage=listing.mileage,
                price=listing.price,
                city=listing.city,
                state=listing.state,
                zip_code=listing.zip_code,
                seller_phone=listing.seller_phone,
            )
            dealer = assess_dealer(norm)
            listing.dealer_likelihood = dealer.likelihood
            listing.scam_score = dealer.scam_score
            attrs = extract_attrs(norm)
            enriched = dict(listing.raw or {})
            enriched["attributes"] = attrs.as_dict()
            listing.raw = enriched
            listing.dedup_key = compute_dedup_key(norm)

            if dealer.scam_score >= 0.6:
                listing.classification_confidence = dealer.scam_score
                listing.classification_reason = "scam signals matched"
            elif dealer.likelihood >= 0.7:
                listing.classification_confidence = dealer.likelihood
                listing.classification_reason = (
                    f"dealer likelihood {dealer.likelihood:.2f}"
                )
            else:
                listing.classification_confidence = 0.9
                listing.classification_reason = "heuristics: private seller"
        db.flush()

        # Pass 2: write price history rows
        for listing, history in generated:
            for price, days_ago in history:
                db.add(
                    PriceHistory(
                        listing_id=listing.id,
                        price=price,
                        delta=None,
                        observed_at=now - timedelta(days=days_ago),
                    )
                )
        db.flush()

        # Pass 3: market + quality score (needs the market comps to exist first)
        for listing, _ in generated:
            market = estimate_market(db, listing)
            drops = db.query(PriceHistory).filter(
                PriceHistory.listing_id == listing.id
            ).count() - 1  # subtract initial
            days_on_market = (
                (now - listing.posted_at).days if listing.posted_at else None
            )
            q = score_listing(
                listing,
                market={"median": market.median, "sample_size": market.sample_size},
                dealer_likelihood=listing.dealer_likelihood,
                scam_score=listing.scam_score,
                price_drops=max(0, drops),
                days_on_market=days_on_market,
                now=now,
            )
            listing.lead_quality_score = q.score
            listing.quality_breakdown = q.breakdown

    log.info("seed.done", inserted=len(generated))


if __name__ == "__main__":
    main()
