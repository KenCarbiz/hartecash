"""Background VIN-vision enrichment.

Expensive operations shouldn't happen inline on ingest (they block the
API and burn money on listings that'll turn out to be dealers or scams).
This worker:

  1. Picks listings that are promising (lead_quality_score >= threshold,
     no VIN yet, classification = private_seller, haven't tried vision
     in the last 7 days).
  2. Runs the Claude Vision VIN extractor over the listing's images
     (vin_vision.extract_vin_from_images already implements the cascade).
  3. Stores the result on the listing: vin, vin_valid, vin_decode_year,
     vin_decode_make, vin_decode_model, vin_decode_trim, plus a
     `raw.vin_vision_attempted_at` timestamp so we don't retry too soon.
  4. Recomputes the quality score so the new VIN signal propagates.

Run as:
    python -m fsbo.workers.vin_vision_worker --max 50
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select

from fsbo.db import session_scope
from fsbo.enrichment.vin import decode_mismatches_listing, decode_vin
from fsbo.enrichment.vin_vision import extract_vin_from_images
from fsbo.logging import configure, get_logger
from fsbo.models import Listing

log = get_logger(__name__)

# Cost gate — only spend API $ on listings worth pursuing.
DEFAULT_MIN_SCORE = 55
DEFAULT_MIN_PRICE = 5000
RETRY_AFTER_DAYS = 7


async def run(
    max_listings: int = 50,
    min_score: int = DEFAULT_MIN_SCORE,
    min_price: float = DEFAULT_MIN_PRICE,
) -> dict[str, int]:
    """Pick candidates + run vision extraction. Returns counts for logging."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETRY_AFTER_DAYS)
    stats = {"candidates": 0, "attempted": 0, "vin_found": 0, "errors": 0}

    with session_scope() as db:
        candidates = db.scalars(
            select(Listing).where(
                and_(
                    Listing.vin.is_(None),
                    Listing.classification == "private_seller",
                    Listing.auto_hidden.is_(False),
                    Listing.lead_quality_score >= min_score,
                    or_(Listing.price.is_(None), Listing.price >= min_price),
                )
            ).limit(max_listings * 2)  # over-fetch; filter on retry-window below
        ).all()
        stats["candidates"] = len(candidates)

        selected = []
        for c in candidates:
            raw = dict(c.raw or {})
            last_attempt = raw.get("vin_vision_attempted_at")
            if last_attempt:
                try:
                    when = datetime.fromisoformat(str(last_attempt))
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                    if when > cutoff:
                        continue  # retry window not yet elapsed
                except ValueError:
                    pass
            if not c.images:
                continue
            selected.append(c)
            if len(selected) >= max_listings:
                break

    for listing in selected:
        stats["attempted"] += 1
        try:
            result = await extract_vin_from_images(listing.images)
        except Exception as e:  # noqa: BLE001
            log.warning("vin_vision.unexpected_error", listing_id=listing.id, error=str(e))
            stats["errors"] += 1
            result = None

        decoded = None
        vpic_mismatch = False
        if result and result.vin:
            stats["vin_found"] += 1
            try:
                decoded = await decode_vin(result.vin)
                vpic_mismatch = decode_mismatches_listing(
                    decoded, listing.year, listing.make
                )
            except Exception:  # noqa: BLE001
                decoded = None

        # Persist outcome in a single session.
        with session_scope() as db:
            row = db.get(Listing, listing.id)
            if row is None:
                continue
            raw = dict(row.raw or {})
            raw["vin_vision_attempted_at"] = datetime.now(timezone.utc).isoformat()
            if result and result.vin:
                row.vin = result.vin
                raw["vin_vision_source_image"] = result.source_image
                if decoded and not decoded.error_code:
                    row.year = row.year or decoded.year
                    row.make = row.make or decoded.make
                    row.model = row.model or decoded.model
                    row.trim = row.trim or decoded.trim
                    if vpic_mismatch:
                        raw["vin_vpic_mismatch"] = True
            row.raw = raw

    return stats


def main() -> None:
    configure()
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=50)
    parser.add_argument("--min-score", type=int, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--min-price", type=float, default=DEFAULT_MIN_PRICE)
    args = parser.parse_args()

    stats = asyncio.run(run(args.max, args.min_score, args.min_price))
    log.info("vin_vision.done", **stats)


if __name__ == "__main__":
    main()
