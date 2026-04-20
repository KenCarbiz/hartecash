"""Continuous scheduler.

Polls Craigslist across a configurable list of cities + eBay Motors queries at
a fixed interval, and drains the webhook delivery queue in the background.

Run as a long-lived process:
    python -m fsbo.workers.scheduler

For production, split these into separate workers behind a proper queue
(Redis + RQ/Celery). This single-process scheduler is fine through ~10k
listings/day.
"""

import asyncio
import json
import os
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from fsbo.db import session_scope
from fsbo.logging import configure, get_logger
from fsbo.webhooks.delivery import deliver_pending
from fsbo.workers.poll import run as run_poll

log = get_logger(__name__)

_DEFAULT_CITIES = [
    "tampa",
    "orlando",
    "miami",
    "jacksonville",
    "atlanta",
    "charlotte",
    "raleigh",
    "dallas",
    "houston",
    "austin",
    "phoenix",
    "lasvegas",
    "losangeles",
    "sfbay",
    "seattle",
]


def _load_plan() -> dict:
    """Optional JSON plan at $FSBO_POLL_PLAN overrides defaults.

    Shape:
      {
        "craigslist": {"cities": ["tampa", ...], "interval_minutes": 15},
        "ebay_motors": {"queries": [{"q": "ford f150", "zip_code": "33607"}],
                        "interval_minutes": 30}
      }
    """
    path = os.getenv("FSBO_POLL_PLAN")
    if path and Path(path).exists():
        return json.loads(Path(path).read_text())
    return {
        "craigslist": {"cities": _DEFAULT_CITIES, "interval_minutes": 15},
        "ebay_motors": {"queries": [], "interval_minutes": 30},
    }


async def _poll_craigslist(cities: list[str]) -> None:
    for city in cities:
        try:
            await run_poll("craigslist", city=city, category="cta")
        except Exception as e:
            log.warning("scheduler.craigslist_poll_failed", city=city, error=str(e))


async def _poll_ebay(queries: list[dict]) -> None:
    for q in queries:
        try:
            await run_poll("ebay_motors", **q)
        except Exception as e:
            log.warning("scheduler.ebay_poll_failed", query=q, error=str(e))


async def _drain_webhooks() -> None:
    with session_scope() as db:
        try:
            await deliver_pending(db, batch_size=50)
        except Exception as e:
            log.warning("scheduler.webhook_drain_failed", error=str(e))


async def main() -> None:
    configure()
    plan = _load_plan()
    scheduler = AsyncIOScheduler()

    cl = plan.get("craigslist", {})
    if cl.get("cities"):
        scheduler.add_job(
            _poll_craigslist,
            IntervalTrigger(minutes=cl.get("interval_minutes", 15)),
            kwargs={"cities": cl["cities"]},
            id="craigslist",
            max_instances=1,
            coalesce=True,
        )

    eb = plan.get("ebay_motors", {})
    if eb.get("queries"):
        scheduler.add_job(
            _poll_ebay,
            IntervalTrigger(minutes=eb.get("interval_minutes", 30)),
            kwargs={"queries": eb["queries"]},
            id="ebay_motors",
            max_instances=1,
            coalesce=True,
        )

    scheduler.add_job(
        _drain_webhooks,
        IntervalTrigger(seconds=30),
        id="webhooks",
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    log.info("scheduler.started", jobs=[j.id for j in scheduler.get_jobs()])

    stop = asyncio.Event()
    try:
        await stop.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
