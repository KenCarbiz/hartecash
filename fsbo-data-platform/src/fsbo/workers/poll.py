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
from fsbo.enrichment.dealer_signals import assess as assess_dealer
from fsbo.enrichment.dedup import compute_dedup_key
from fsbo.enrichment.phone_graph import count_other_listings
from fsbo.enrichment.price_tracking import count_drops, record_price
from fsbo.enrichment.quality import score_listing
from fsbo.enrichment.vin import decode_vin
from fsbo.logging import configure, get_logger
from fsbo.models import Classification, Listing, ScrapeRun
from fsbo.sources import REGISTRY
from fsbo.sources.base import NormalizedListing
from fsbo.valuation.market import estimate as estimate_market
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
            existing.mileage = norm.mileage or existing.mileage
            if norm.price is not None and norm.price > 0:
                # Log any price change before overwriting the current price.
                if record_price(db, existing, norm.price):
                    existing.price = norm.price
                    drops = count_drops(db, existing.id)
                    dom = int(
                        (
                            now
                            - (existing.posted_at or existing.first_seen_at).replace(
                                tzinfo=existing.posted_at.tzinfo
                                if existing.posted_at and existing.posted_at.tzinfo
                                else timezone.utc
                            )
                        ).total_seconds()
                        / 86400
                    )
                    market = estimate_market(db, existing)
                    q = score_listing(
                        existing,
                        market={"median": market.median, "sample_size": market.sample_size},
                        phone_listing_count=count_other_listings(
                            db, existing.seller_phone, exclude_id=existing.id
                        ),
                        dealer_likelihood=existing.dealer_likelihood,
                        scam_score=existing.scam_score,
                        price_drops=drops,
                        days_on_market=dom,
                    )
                    existing.lead_quality_score = q.score
                    existing.quality_breakdown = q.breakdown
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

        # --- Phone cross-listing check ---
        phone_count = count_other_listings(
            db, norm.seller_phone, exclude_id=row.id, within_days=30
        )

        # --- Dealer signal aggregation (research-backed rulebook) ---
        extras: dict[str, bool] = {}
        if phone_count >= 3:
            extras["phone_on_3plus_listings_30d"] = True
        if phone_count >= 5:
            extras["phone_on_5plus_listings_90d"] = True
        dealer = assess_dealer(norm, extras)
        row.dealer_likelihood = dealer.likelihood
        row.scam_score = dealer.scam_score

        # --- Classification: prefer signal-based when confident, else LLM ---
        if dealer.scam_score >= 0.6:
            row.classification = Classification.SCAM.value
            row.classification_confidence = dealer.scam_score
            row.classification_reason = "scam signals matched"
        elif dealer.likelihood >= 0.7:
            row.classification = Classification.DEALER.value
            row.classification_confidence = dealer.likelihood
            row.classification_reason = (
                f"dealer likelihood {dealer.likelihood:.2f}; "
                f"signals={[k for k,v in dealer.signals.items() if v][:5]}"
            )
        else:
            result = classify(norm)
            row.classification = result.label
            row.classification_confidence = result.confidence
            row.classification_reason = result.reason

        # --- Initial price history entry (drop count will be 0) ---
        if norm.price is not None and norm.price > 0:
            record_price(db, row, norm.price)

        # --- Lead quality score ---
        market = estimate_market(db, row)
        market_ctx = {"median": market.median, "sample_size": market.sample_size}
        q = score_listing(
            row,
            market=market_ctx,
            phone_listing_count=phone_count,
            dealer_likelihood=row.dealer_likelihood,
            scam_score=row.scam_score,
            price_drops=0,
            days_on_market=0,
        )
        row.lead_quality_score = q.score
        row.quality_breakdown = q.breakdown

        if row.classification == Classification.PRIVATE_SELLER.value:
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
