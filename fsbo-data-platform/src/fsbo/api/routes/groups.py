"""Multi-rooftop dealer groups (franchise rollup).

A DealerGroup is a thin parent over multiple Dealer rows. Members
keep their own listings / leads / users / billing — the group layer
is purely a cohort analytics rollup so a GM running 3-10 stores can
see one funnel + one leaderboard across the network.

Auth model (intentionally narrow at MVP):
- Any authenticated dealer admin can CREATE a group; doing so
  implicitly adds their own dealer to it. The creating dealer
  becomes the owner_dealer_id.
- The owner can ADD or REMOVE other dealers to / from their group.
- All members can READ /analytics/group-funnel + /analytics/group-
  leaderboard for their group (separate route in analytics.py).

We don't ship a UI yet. The endpoints exist so franchise sales
demos can show the data path; UI design follows the dashboard
redesign pass.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.auth.resolver import DealerId
from fsbo.db import get_session
from fsbo.models import Dealer, DealerGroup

router = APIRouter(prefix="/groups", tags=["groups"])


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


class GroupIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    slug: str = Field(..., min_length=2, max_length=64)


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    owner_dealer_id: str
    created_at: datetime
    member_dealer_slugs: list[str] = []


def _own_dealer(db: Session, dealer_id: str) -> Dealer:
    dealer = db.scalar(select(Dealer).where(Dealer.slug == dealer_id))
    if not dealer:
        raise HTTPException(404, "dealer row not found for caller")
    return dealer


def _group_with_members(db: Session, group: DealerGroup) -> GroupOut:
    members = db.scalars(
        select(Dealer.slug)
        .where(Dealer.group_id == group.id)
        .order_by(Dealer.slug)
    ).all()
    return GroupOut(
        id=group.id,
        slug=group.slug,
        name=group.name,
        owner_dealer_id=group.owner_dealer_id,
        created_at=group.created_at,
        member_dealer_slugs=list(members),
    )


@router.post("", response_model=GroupOut, status_code=201)
def create_group(
    payload: GroupIn,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> GroupOut:
    """Create a new group. The calling dealer becomes the owner +
    auto-joins the group as the first member."""
    slug = payload.slug.strip().lower()
    if not _SLUG_RE.match(slug):
        raise HTTPException(
            400, "slug must be 2-63 chars, [a-z0-9-], starting with a letter or digit"
        )
    existing = db.scalar(select(DealerGroup).where(DealerGroup.slug == slug))
    if existing is not None:
        raise HTTPException(409, "group slug already taken")

    dealer = _own_dealer(db, dealer_id)
    if dealer.group_id is not None:
        raise HTTPException(
            409,
            "dealer already belongs to a group; leave it before creating another",
        )

    group = DealerGroup(slug=slug, name=payload.name.strip(), owner_dealer_id=dealer_id)
    db.add(group)
    db.flush()
    dealer.group_id = group.id
    db.flush()
    return _group_with_members(db, group)


@router.get("/me", response_model=GroupOut | None)
def get_my_group(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> GroupOut | None:
    """Return the group the calling dealer belongs to, or null."""
    dealer = db.scalar(select(Dealer).where(Dealer.slug == dealer_id))
    if not dealer or dealer.group_id is None:
        return None
    group = db.get(DealerGroup, dealer.group_id)
    if not group:
        return None
    return _group_with_members(db, group)


def _require_owner_membership(
    db: Session, dealer_id: str, group_slug: str
) -> DealerGroup:
    group = db.scalar(select(DealerGroup).where(DealerGroup.slug == group_slug))
    if not group:
        raise HTTPException(404, "group not found")
    if group.owner_dealer_id != dealer_id:
        raise HTTPException(
            403, "only the group owner can manage membership"
        )
    return group


class AddMemberIn(BaseModel):
    dealer_slug: str


@router.post("/{group_slug}/dealers", response_model=GroupOut)
def add_member(
    group_slug: str,
    payload: AddMemberIn,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> GroupOut:
    group = _require_owner_membership(db, dealer_id, group_slug)
    target = db.scalar(
        select(Dealer).where(Dealer.slug == payload.dealer_slug)
    )
    if not target:
        raise HTTPException(404, "dealer not found")
    if target.group_id is not None and target.group_id != group.id:
        raise HTTPException(
            409, "dealer already belongs to another group"
        )
    target.group_id = group.id
    db.flush()
    return _group_with_members(db, group)


@router.delete("/{group_slug}/dealers/{dealer_slug}", response_model=GroupOut)
def remove_member(
    group_slug: str,
    dealer_slug: str,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> GroupOut:
    group = _require_owner_membership(db, dealer_id, group_slug)
    if dealer_slug == group.owner_dealer_id:
        raise HTTPException(
            409, "can't remove the owner; transfer ownership or delete the group"
        )
    target = db.scalar(
        select(Dealer).where(Dealer.slug == dealer_slug)
    )
    if not target or target.group_id != group.id:
        raise HTTPException(404, "dealer is not a member of this group")
    target.group_id = None
    db.flush()
    return _group_with_members(db, group)
