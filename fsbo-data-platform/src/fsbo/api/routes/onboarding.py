"""First-run onboarding checklist.

When a dealer signs up they hit a dashboard with no listings + no
leads + no Twilio configured. The checklist surfaces what's left so
they can complete setup without hand-holding from a CSM. Each item
returns done=true once the dealer has crossed that bar; the dashboard
shows a progress bar driven by sum(done) / len(items).

The checks are read-only + cheap (single-row exists queries against
already-indexed columns), so the endpoint is safe to poll on every
dashboard render until everything is done.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fsbo.auth.resolver import DealerId
from fsbo.config import settings
from fsbo.db import get_session
from fsbo.models import (
    ApiKey,
    Dealer,
    Lead,
    SavedSearch,
    Subscription,
    User,
    WebhookSubscription,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class ChecklistItem(BaseModel):
    key: str
    label: str
    done: bool
    detail: str | None = None  # short hint shown when not done


class ChecklistResponse(BaseModel):
    dealer_id: str
    items: list[ChecklistItem]
    completed: int
    total: int


@router.get("/checklist", response_model=ChecklistResponse)
def get_checklist(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> ChecklistResponse:
    """Per-dealer setup progress. Cheap; OK to poll."""
    dealer = db.scalar(select(Dealer).where(Dealer.slug == dealer_id))

    has_twilio = bool(
        settings.twilio_account_sid
        and settings.twilio_auth_token
        and settings.twilio_from_number
    )

    has_team_member = (
        db.scalar(
            select(func.count(User.id)).where(
                User.dealer_id == dealer_id,
                User.is_active.is_(True),
            )
        )
        or 0
    ) >= 2  # owner + at least one teammate

    has_routing = bool(
        dealer
        and dealer.routing_mode == "least_loaded"
        and dealer.routing_pool
    )

    has_extension = bool(
        db.scalar(
            select(ApiKey.id)
            .where(ApiKey.dealer_id == dealer_id, ApiKey.revoked_at.is_(None))
            .limit(1)
        )
    )

    has_first_lead = bool(
        db.scalar(
            select(Lead.id).where(Lead.dealer_id == dealer_id).limit(1)
        )
    )

    has_saved_search = bool(
        db.scalar(
            select(SavedSearch.id)
            .where(SavedSearch.dealer_id == dealer_id)
            .limit(1)
        )
    )

    has_active_sub = bool(
        db.scalar(
            select(Subscription.id)
            .where(
                Subscription.dealer_id == dealer_id,
                Subscription.status.in_(("active", "trialing")),
            )
            .limit(1)
        )
    )

    has_webhook = bool(
        db.scalar(
            select(WebhookSubscription.id)
            .where(
                WebhookSubscription.dealer_id == dealer_id,
                WebhookSubscription.active.is_(True),
            )
            .limit(1)
        )
    )

    items = [
        ChecklistItem(
            key="twilio",
            label="Connect a Twilio phone number",
            done=has_twilio,
            detail=(
                None
                if has_twilio
                else "Add TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER to enable SMS + voice."
            ),
        ),
        ChecklistItem(
            key="team_member",
            label="Invite at least one teammate",
            done=has_team_member,
            detail=None if has_team_member else "Open Settings → Invitations.",
        ),
        ChecklistItem(
            key="routing",
            label="Set up auto-routing across your reps",
            done=has_routing,
            detail=(
                None
                if has_routing
                else "Settings → Routing → switch to least-loaded and add your reps."
            ),
        ),
        ChecklistItem(
            key="extension",
            label="Install the Chrome extension",
            done=has_extension,
            detail=(
                None
                if has_extension
                else "Captures Marketplace listings the public scrapers miss."
            ),
        ),
        ChecklistItem(
            key="saved_search",
            label="Save your first market search",
            done=has_saved_search,
            detail=(
                None
                if has_saved_search
                else "Saved searches alert you when matching listings appear."
            ),
        ),
        ChecklistItem(
            key="first_lead",
            label="Claim your first lead",
            done=has_first_lead,
            detail=(
                None
                if has_first_lead
                else "Browse listings → click 'Claim' on one that fits."
            ),
        ),
        ChecklistItem(
            key="webhook",
            label="Wire your DMS via webhooks (optional)",
            done=has_webhook,
            detail=(
                None
                if has_webhook
                else "Push lead status changes to Tekion / Frazer / etc."
            ),
        ),
        ChecklistItem(
            key="subscription",
            label="Pick a plan",
            done=has_active_sub,
            detail=(
                None
                if has_active_sub
                else "Settings → Billing → choose a plan when you're ready."
            ),
        ),
    ]

    completed = sum(1 for i in items if i.done)
    return ChecklistResponse(
        dealer_id=dealer_id,
        items=items,
        completed=completed,
        total=len(items),
    )
