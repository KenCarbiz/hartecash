"""First-response timing helpers.

Lead.first_responded_at is stamped exactly once — the first time the
dealer makes any kind of outbound contact (SMS, email, voice call,
status flip to 'contacted'). Powers per-lead response-SLA reporting +
manager coaching ("rep took 3 hours to first-touch this lead"). Once
stamped, it never moves; subsequent outreach doesn't update it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fsbo.models import Lead


def mark_first_response(lead: Lead, when: datetime | None = None) -> bool:
    """Stamp lead.first_responded_at if currently None.

    Returns True if we just stamped it, False when already set. Caller
    is responsible for db.flush(). No-op when lead is None.
    """
    if lead is None:
        return False
    if lead.first_responded_at is not None:
        return False
    lead.first_responded_at = when or datetime.now(timezone.utc)
    return True
