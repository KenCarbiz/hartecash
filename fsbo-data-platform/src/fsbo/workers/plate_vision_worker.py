"""Background plate-vision enrichment.

Sibling of vin_vision_worker. License plates that appear on multiple
listings under different sellers are a stronger curbstoner signal than
VINs (a curbstoner can change phones easily; the plate sticks with the
car). This worker scans candidate listings for plate + state and feeds
the result back into the seller graph.

Run as:
    python -m fsbo.workers.plate_vision_worker --max 50
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select

from fsbo.db import session_scope
from fsbo.enrichment.plate_vision import extract_plate_from_images
from fsbo.enrichment.seller_graph import (
    find_corpus_vin_for_plate,
    register_listing_identities,
)
from fsbo.enrichment.vin import decode_vin
from fsbo.logging import configure, get_logger
from fsbo.models import Listing

log = get_logger(__name__)

DEFAULT_MIN_SCORE = 50  # less strict than VIN — plates are easier
DEFAULT_MIN_PRICE = 3000
RETRY_AFTER_DAYS = 14


async def run(
    max_listings: int = 50,
    min_score: int = DEFAULT_MIN_SCORE,
    min_price: float = DEFAULT_MIN_PRICE,
) -> dict[str, int]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETRY_AFTER_DAYS)
    stats = {"candidates": 0, "attempted": 0, "plate_found": 0, "errors": 0}

    with session_scope() as db:
        candidates = db.scalars(
            select(Listing).where(
                and_(
                    Listing.license_plate.is_(None),
                    Listing.classification == "private_seller",
                    Listing.auto_hidden.is_(False),
                    Listing.lead_quality_score >= min_score,
                    or_(Listing.price.is_(None), Listing.price >= min_price),
                )
            ).limit(max_listings * 2)
        ).all()
        stats["candidates"] = len(candidates)

        selected = []
        for c in candidates:
            raw = dict(c.raw or {})
            last_attempt = raw.get("plate_vision_attempted_at")
            if last_attempt:
                try:
                    when = datetime.fromisoformat(str(last_attempt))
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                    if when > cutoff:
                        continue
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
            result = await extract_plate_from_images(listing.images)
        except Exception as e:  # noqa: BLE001
            log.warning(
                "plate_vision.unexpected_error",
                listing_id=listing.id,
                error=str(e),
            )
            stats["errors"] += 1
            result = None

        with session_scope() as db:
            row = db.get(Listing, listing.id)
            if row is None:
                continue
            raw = dict(row.raw or {})
            raw["plate_vision_attempted_at"] = datetime.now(timezone.utc).isoformat()
            if result and result.plate:
                stats["plate_found"] += 1
                if not row.license_plate:
                    row.license_plate = result.plate
                if result.state and not row.license_plate_state:
                    row.license_plate_state = result.state
                raw["plate_vision_source_image"] = result.source_image

                # Plate-to-corpus VIN lookup. When we previously saw
                # the same plate on a listing that did have a VIN,
                # back-fill ours. Cheap, no external API.
                if not row.vin:
                    found_vin = find_corpus_vin_for_plate(
                        db, result.plate, exclude_listing_id=row.id
                    )
                    if found_vin:
                        row.vin = found_vin
                        raw["vin_source"] = "plate_corpus_lookup"
                        # NHTSA decode to fill year/make/model gaps.
                        try:
                            decoded = await decode_vin(found_vin)
                            if decoded and not decoded.error_code:
                                row.year = row.year or decoded.year
                                row.make = row.make or decoded.make
                                row.model = row.model or decoded.model
                                row.trim = row.trim or decoded.trim
                        except Exception:  # noqa: BLE001
                            pass

                # Re-link the seller-graph identities so the new plate
                # contributes to the curbstoner cluster.
                try:
                    register_listing_identities(db, row)
                except Exception:  # noqa: BLE001
                    pass
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
    log.info("plate_vision.done", **stats)


if __name__ == "__main__":
    main()
