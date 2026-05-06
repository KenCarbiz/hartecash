"""Notify a rep when a lead lands in their queue.

Triggered from POST /leads (auto-routing), /leads/bulk-claim
(auto-routing), and /leads/bulk-assign (manual reassign). The
recipient is the User whose email matches Lead.assigned_to — the
routing pool stores email handles, so when a lead is assigned the
handle is the address we email.

Best-effort: honors User.alerts_enabled, swallows transport errors
(SendGrid hiccups must not break lead creation).
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.logging import get_logger
from fsbo.messaging.email_client import send_email
from fsbo.models import Lead, Listing, User

log = get_logger(__name__)


def notify_assignment(
    db: Session, lead: Lead, *, prev_owner: str | None = None
) -> bool:
    """Email the rep that lead.assigned_to was just assigned to them.

    Returns True if a send was attempted (regardless of backend
    success), False when there's no recipient or alerts are off.
    """
    if not lead.assigned_to:
        return False
    user = db.scalar(
        select(User).where(
            User.email == lead.assigned_to,
            User.dealer_id == lead.dealer_id,
            User.is_active.is_(True),
        )
    )
    if not user or not user.alerts_enabled:
        return False
    listing = db.get(Listing, lead.listing_id)
    if not listing:
        return False

    subject, text = _render(lead, listing, prev_owner=prev_owner)
    try:
        asyncio.run(send_email(user.email, subject, text))
    except Exception as e:  # noqa: BLE001 — best-effort, never raise
        log.warning(
            "assignment_notify.send_failed",
            lead_id=lead.id,
            user_email=user.email,
            error=str(e)[:160],
        )
    return True


def _render(
    lead: Lead, listing: Listing, *, prev_owner: str | None
) -> tuple[str, str]:
    title = (
        listing.title
        or " ".join(
            x for x in [str(listing.year or ""), listing.make or "", listing.model or ""] if x
        ).strip()
        or f"Listing #{listing.id}"
    )
    lines = [f"You've been assigned a new lead: {title}."]
    if listing.price:
        lines.append(f"Asking: ${listing.price:,.0f}")
    loc = ", ".join(x for x in [listing.city or "", listing.state or ""] if x)
    if loc:
        lines.append(f"Location: {loc}")
    if prev_owner and prev_owner != "(unassigned)":
        lines.append(f"Reassigned from: {prev_owner}")
    lines.append("")
    lines.append(f"Open in dashboard: /leads/{lead.id}")
    text = "\n".join(lines)
    subject = f"New lead: {title}"
    return subject, text
