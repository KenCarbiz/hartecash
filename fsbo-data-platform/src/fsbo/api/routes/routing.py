"""Lead-routing configuration.

Two modes today:

  manual         — Lead.assigned_to stays exactly what the dealer
                   passed (or null). Default.
  least_loaded   — When a Lead is created without an explicit
                   assigned_to, we pick the rep in routing_pool with
                   the fewest active leads (status in: new, contacted,
                   negotiating, appointment) in the last 30 days.

The pool itself is a list of free-text handles. Today these are emails
or display names; we don't gate on User-table membership so a dealer
can pre-load a pool before inviting their team.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fsbo.auth.resolver import DealerId
from fsbo.db import get_session
from fsbo.models import Dealer, Lead

router = APIRouter(prefix="/routing", tags=["routing"])

ACTIVE_STATUSES = ("new", "contacted", "negotiating", "appointment")
LOAD_WINDOW_DAYS = 30


class RoutingConfig(BaseModel):
    mode: Literal["manual", "least_loaded"]
    pool: list[str] = Field(default_factory=list, max_length=50)


@router.get("", response_model=RoutingConfig)
def get_routing_config(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> RoutingConfig:
    dealer = db.scalar(select(Dealer).where(Dealer.slug == dealer_id))
    if not dealer:
        # Legacy dealers (predates the Dealer table) fall back to defaults
        return RoutingConfig(mode="manual", pool=[])
    return RoutingConfig(
        mode=dealer.routing_mode if dealer.routing_mode in ("manual", "least_loaded") else "manual",  # type: ignore[arg-type]
        pool=list(dealer.routing_pool or []),
    )


@router.put("", response_model=RoutingConfig)
def update_routing_config(
    payload: RoutingConfig,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> RoutingConfig:
    dealer = db.scalar(select(Dealer).where(Dealer.slug == dealer_id))
    if not dealer:
        raise HTTPException(404, "dealer not found")
    # Cap pool size + dedupe + drop blanks
    seen: list[str] = []
    for raw in payload.pool:
        h = (raw or "").strip()
        if h and h not in seen:
            seen.append(h)
        if len(seen) >= 50:
            break
    dealer.routing_mode = payload.mode
    dealer.routing_pool = seen
    db.flush()
    return RoutingConfig(mode=payload.mode, pool=seen)


# ---- Internal helper ------------------------------------------------


def assign_next(db: Session, dealer_id: str) -> str | None:
    """Pick the rep in this dealer's routing_pool with the lightest
    active load. Returns None when routing is manual / pool is empty.

    Caller (POST /leads, /leads/bulk-claim) only invokes this when
    the request didn't include an explicit assigned_to."""
    dealer = db.scalar(select(Dealer).where(Dealer.slug == dealer_id))
    if not dealer:
        return None
    if dealer.routing_mode != "least_loaded":
        return None
    pool = list(dealer.routing_pool or [])
    if not pool:
        return None

    # Count active leads per pool member in the last 30 days.
    since = datetime.now(timezone.utc) - timedelta(days=LOAD_WINDOW_DAYS)
    rows = db.execute(
        select(Lead.assigned_to, func.count(Lead.id))
        .where(
            Lead.dealer_id == dealer_id,
            Lead.assigned_to.in_(pool),
            Lead.status.in_(ACTIVE_STATUSES),
            Lead.created_at >= since,
        )
        .group_by(Lead.assigned_to)
    ).all()
    load = {handle: 0 for handle in pool}
    for handle, n in rows:
        if handle in load:
            load[handle] = int(n)

    # Tie-break by pool order so the same rep doesn't win every tie.
    return min(pool, key=lambda h: (load.get(h, 0), pool.index(h)))
