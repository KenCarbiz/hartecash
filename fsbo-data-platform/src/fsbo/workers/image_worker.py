"""Background image-phash worker.

Walks recent listings that have images but no computed image_bg_phashes,
downloads up to N images per listing, computes perceptual hashes, and
stores them on the listing. Once written, the seller_graph will pick up
the hashes next time register_listing_identities() runs (we re-run it
here so new clusters get linked immediately).

Runs in the scheduler every 5 minutes. Budget: ~$0 (pure compute +
bandwidth) so the cost gate is lenient compared to the vision worker.

    python -m fsbo.workers.image_worker --max 50
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import and_, or_, select

from fsbo.db import session_scope
from fsbo.enrichment.image_hash import fetch_and_hash
from fsbo.enrichment.seller_graph import register_listing_identities
from fsbo.logging import configure, get_logger
from fsbo.models import Listing

log = get_logger(__name__)

MAX_IMAGES_PER_LISTING = 3
RETRY_AFTER_DAYS = 14


async def run(max_listings: int = 50, min_score: int = 0) -> dict[str, int]:
    """Pick candidates + hash their images. Returns counts for logging."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETRY_AFTER_DAYS)
    stats = {"candidates": 0, "attempted": 0, "hashed": 0, "errors": 0}

    with session_scope() as db:
        candidates = db.scalars(
            select(Listing).where(
                and_(
                    or_(
                        Listing.lead_quality_score.is_(None),
                        Listing.lead_quality_score >= min_score,
                    ),
                    Listing.auto_hidden.is_(False),
                )
            ).limit(max_listings * 3)
        ).all()
        stats["candidates"] = len(candidates)

        selected = []
        for c in candidates:
            if not c.images:
                continue
            raw = c.raw or {}
            if isinstance(raw, dict) and isinstance(raw.get("image_bg_phashes"), list):
                # Already computed — skip unless the retry window has elapsed.
                attempted = raw.get("image_hash_attempted_at")
                if attempted:
                    try:
                        when = datetime.fromisoformat(str(attempted))
                        if when.tzinfo is None:
                            when = when.replace(tzinfo=timezone.utc)
                        if when > cutoff:
                            continue
                    except ValueError:
                        pass
            selected.append(c.id)
            if len(selected) >= max_listings:
                break

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for listing_id in selected:
            stats["attempted"] += 1
            hashes: list[str] = []
            with session_scope() as db:
                row = db.get(Listing, listing_id)
                if row is None or not row.images:
                    continue
                urls = row.images[:MAX_IMAGES_PER_LISTING]

            for url in urls:
                try:
                    h = await fetch_and_hash(url, client=client)
                except Exception as e:  # noqa: BLE001
                    log.warning("image_hash.failed", url=url, error=str(e))
                    h = None
                if h:
                    hashes.append(h)

            with session_scope() as db:
                row = db.get(Listing, listing_id)
                if row is None:
                    continue
                raw = dict(row.raw or {})
                raw["image_bg_phashes"] = hashes
                raw["image_hash_attempted_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
                row.raw = raw
                if hashes:
                    stats["hashed"] += 1
                    # Re-register identities so the new phash clusters land.
                    register_listing_identities(db, row)
                else:
                    stats["errors"] += 1

    return stats


def main() -> None:
    configure()
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=50)
    parser.add_argument("--min-score", type=int, default=0)
    args = parser.parse_args()

    stats = asyncio.run(run(args.max, args.min_score))
    log.info("image_worker.done", **stats)


if __name__ == "__main__":
    main()
