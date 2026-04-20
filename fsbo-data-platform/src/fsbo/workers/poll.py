"""One-shot poller: fetch a source, upsert into Postgres, classify new rows.

Usage:
    python -m fsbo.workers.poll --source craigslist --city tampa
    python -m fsbo.workers.poll --source ebay_motors --q "ford f150" --zip 33607
"""

import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from fsbo.db import session_scope
from fsbo.enrichment.classifier import classify
from fsbo.enrichment.dedup import compute_dedup_key
from fsbo.enrichment.vin import decode_vin
from fsbo.logging import configure, get_logger
from fsbo.models import Classification, Listing, ScrapeRun
from fsbo.sources import REGISTRY
from fsbo.sources.base import NormalizedListing
from fsbo.webhooks.delivery import enqueue_for_listing

log = get_logger(__name__)


async def run(source_name: str, **params: object) -> None:
    source_cls = REGISTRY.get(source_name)
    if not source_cls:
        raise SystemExit(f"unknown source: {source_name}. known: {list(REGISTRY)}")

    source = source_cls()
    fetched = inserted = updated = 0
    run_id: int | None = None

    with session_scope() as db:
        sr = ScrapeRun(source=source_name, params=params)
        db.add(sr)
        db.flush()
        run_id = sr.id

    try:
        async for norm in source.fetch(**params):
            fetched += 1
            did_insert = await upsert(norm)
            if did_insert:
                inserted += 1
            else:
                updated += 1
    except Exception as e:
        log.exception("poll.failed", source=source_name, error=str(e))
        with session_scope() as db:
            sr = db.get(ScrapeRun, run_id)
            if sr:
                sr.error = str(e)
                sr.finished_at = datetime.now(timezone.utc)
        raise
    finally:
        aclose = getattr(source, "aclose", None)
        if aclose:
            await aclose()

    with session_scope() as db:
        sr = db.get(ScrapeRun, run_id)
        if sr:
            sr.fetched_count = fetched
            sr.inserted_count = inserted
            sr.updated_count = updated
            sr.finished_at = datetime.now(timezone.utc)

    log.info(
        "poll.done",
        source=source_name,
        fetched=fetched,
        inserted=inserted,
        updated=updated,
    )


async def upsert(norm: NormalizedListing) -> bool:
    """Returns True if the listing was newly inserted."""
    # VIN decode happens outside the DB session so we don't hold the connection
    # over a network call.
    if norm.vin and not (norm.year and norm.make and norm.model):
        decoded = await decode_vin(norm.vin)
        if decoded and not decoded.error_code:
            norm.year = norm.year or decoded.year
            norm.make = norm.make or decoded.make
            norm.model = norm.model or decoded.model
            norm.trim = norm.trim or decoded.trim

    with session_scope() as db:
        existing = db.scalar(
            select(Listing).where(
                Listing.source == norm.source,
                Listing.external_id == norm.external_id,
            )
        )
        now = datetime.now(timezone.utc)
        if existing:
            existing.last_seen_at = now
            existing.price = norm.price or existing.price
            existing.mileage = norm.mileage or existing.mileage
            return False

        row = Listing(
            source=norm.source,
            external_id=norm.external_id,
            url=norm.url,
            title=norm.title,
            description=norm.description,
            year=norm.year,
            make=norm.make,
            model=norm.model,
            trim=norm.trim,
            mileage=norm.mileage,
            price=norm.price,
            vin=norm.vin,
            city=norm.city,
            state=norm.state,
            zip_code=norm.zip_code,
            latitude=norm.latitude,
            longitude=norm.longitude,
            seller_name=norm.seller_name,
            seller_phone=norm.seller_phone,
            images=norm.images,
            posted_at=norm.posted_at,
            raw=norm.raw,
            dedup_key=compute_dedup_key(norm),
            classification=Classification.UNCLASSIFIED.value,
        )
        db.add(row)
        db.flush()

        result = classify(norm)
        row.classification = result.label
        row.classification_confidence = result.confidence
        row.classification_reason = result.reason

        if result.label == Classification.PRIVATE_SELLER.value:
            enqueue_for_listing(db, row)
        return True


def main() -> None:
    configure()
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, choices=list(REGISTRY))
    parser.add_argument("--city", default="tampa", help="Craigslist city subdomain")
    parser.add_argument("--category", default="cta")
    parser.add_argument("--q", help="eBay search query")
    parser.add_argument("--zip", dest="zip_code")
    parser.add_argument("--radius", type=int, default=100)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    params: dict[str, object] = {}
    if args.source == "craigslist":
        params = {"city": args.city, "category": args.category}
    elif args.source == "ebay_motors":
        params = {"q": args.q, "zip_code": args.zip_code, "radius_miles": args.radius, "limit": args.limit}

    asyncio.run(run(args.source, **params))


if __name__ == "__main__":
    main()
