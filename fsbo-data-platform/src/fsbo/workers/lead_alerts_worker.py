"""Lead alerts worker.

For every user with alerts_enabled=True, match recent high-score
private-seller listings against that dealer's saved searches (with
alerts_enabled=True). Send one email per (user, listing) pair, deduped
via NotificationDelivery so the same hot lead never pings twice.

Runs every 2 minutes from the scheduler.

    python -m fsbo.workers.lead_alerts_worker --max 200 --lookback 30
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, select

from fsbo.config import settings
from fsbo.db import session_scope
from fsbo.logging import configure, get_logger
from fsbo.messaging.email_client import send_email
from fsbo.models import (
    Listing,
    NotificationDelivery,
    SavedSearch,
    User,
)

log = get_logger(__name__)


def _listing_matches_query(listing: Listing, query: dict[str, Any]) -> bool:
    """Apply the subset of /listings filters a saved search supports."""

    def _lower_eq(field: str, key: str) -> bool:
        expected = query.get(key)
        if expected is None or expected == "":
            return True
        actual = getattr(listing, field, None)
        if actual is None:
            return False
        return str(actual).lower() == str(expected).lower()

    def _ge(field: str, key: str) -> bool:
        expected = query.get(key)
        if expected is None:
            return True
        actual = getattr(listing, field, None)
        if actual is None:
            return False
        try:
            return float(actual) >= float(expected)
        except (TypeError, ValueError):
            return False

    def _le(field: str, key: str) -> bool:
        expected = query.get(key)
        if expected is None:
            return True
        actual = getattr(listing, field, None)
        if actual is None:
            return False
        try:
            return float(actual) <= float(expected)
        except (TypeError, ValueError):
            return False

    if not _lower_eq("make", "make"):
        return False
    if not _lower_eq("model", "model"):
        return False
    if not _ge("year", "year_min"):
        return False
    if not _le("year", "year_max"):
        return False
    if not _ge("price", "price_min"):
        return False
    if not _le("price", "price_max"):
        return False
    if not _le("mileage", "mileage_max"):
        return False
    zip_code = query.get("zip")
    if zip_code and str(listing.zip_code or "") != str(zip_code):
        return False
    # Optional min_score gate on the saved search itself.
    min_score = query.get("min_score")
    if min_score is not None:
        try:
            if listing.lead_quality_score is None or listing.lead_quality_score < int(min_score):
                return False
        except (TypeError, ValueError):
            pass
    # Text search (q) — simple case-insensitive over title/description.
    q = query.get("q")
    if q:
        blob = " ".join(filter(None, [listing.title or "", listing.description or ""])).lower()
        if str(q).lower().strip() not in blob:
            return False
    return True


def _format_price(price: float | None) -> str:
    if price is None:
        return "—"
    return f"${int(price):,}"


def _render_email(user: User, listing: Listing) -> tuple[str, str, str]:
    vehicle = " ".join(
        str(v) for v in (listing.year, listing.make, listing.model) if v
    ) or (listing.title or "Private-party listing")
    loc = ", ".join(v for v in (listing.city, listing.state) if v) or "—"

    origin = (settings.app_origin or "").rstrip("/")
    url = (
        f"{origin}/listings/{listing.id}"
        if origin
        else f"/listings/{listing.id}"
    )

    score = listing.lead_quality_score
    subject = f"Hot lead · {vehicle} · {_format_price(listing.price)} · score {score}"

    text = (
        f"Hi{(' ' + user.name) if user.name else ''},\n\n"
        f"A new private-party listing just scored {score} in your watch.\n\n"
        f"{vehicle}\n"
        f"{_format_price(listing.price)} · {loc}\n"
        f"Mileage: {listing.mileage:,} mi\n" if listing.mileage else ""
    )
    text += f"\nOpen the lead in AutoCurb:\n{url}\n"

    html = f"""
      <p>Hi{(' ' + user.name) if user.name else ''},</p>
      <p>A new private-party listing just scored
        <strong style="color:#0369a1">{score}</strong> in your watch.</p>
      <table cellpadding="0" cellspacing="0" style="margin:16px 0;font-family:Inter,system-ui,sans-serif">
        <tr>
          <td style="padding:12px 16px;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc">
            <div style="font-weight:600;font-size:16px;color:#0f172a">{vehicle}</div>
            <div style="color:#475569;margin-top:4px">
              {_format_price(listing.price)} · {loc}
              {f" · {listing.mileage:,} mi" if listing.mileage else ""}
            </div>
          </td>
        </tr>
      </table>
      <p>
        <a href="{url}" style="display:inline-block;padding:10px 16px;background:#4f46e5;color:#fff;text-decoration:none;border-radius:6px;font-weight:500">
          Open lead
        </a>
      </p>
      <p style="color:#64748b;font-size:12px">
        You're receiving this because alerts are on and your min-score is
        {user.alert_min_score}. Adjust in settings.
      </p>
    """

    return subject, text, html.strip()


async def run(max_listings: int = 200, lookback_minutes: int = 30) -> dict[str, int]:
    """Scan recent high-score listings, email matching users. Returns stats."""
    stats = {"candidates": 0, "users": 0, "matches": 0, "sent": 0, "skipped": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)

    # ---- Fetch candidate listings ----
    with session_scope() as db:
        candidates: list[Listing] = list(
            db.scalars(
                select(Listing)
                .where(
                    and_(
                        Listing.auto_hidden.is_(False),
                        Listing.classification == "private_seller",
                        Listing.first_seen_at >= cutoff,
                        Listing.lead_quality_score.is_not(None),
                    )
                )
                .order_by(Listing.lead_quality_score.desc())
                .limit(max_listings)
            ).all()
        )
    stats["candidates"] = len(candidates)
    if not candidates:
        return stats

    # ---- Build per-dealer user + saved-search table ----
    dealer_targets: dict[str, list[tuple[User, list[SavedSearch]]]] = {}
    with session_scope() as db:
        users = list(
            db.scalars(
                select(User).where(User.is_active.is_(True), User.alerts_enabled.is_(True))
            ).all()
        )
        stats["users"] = len(users)
        for u in users:
            searches = list(
                db.scalars(
                    select(SavedSearch).where(
                        SavedSearch.dealer_id == u.dealer_id,
                        SavedSearch.alerts_enabled.is_(True),
                    )
                ).all()
            )
            if not searches:
                continue
            dealer_targets.setdefault(u.dealer_id, []).append((u, searches))

    if not dealer_targets:
        return stats

    # ---- Match + send ----
    for listing in candidates:
        for _dealer_id, user_searches in dealer_targets.items():
            for user, searches in user_searches:
                if listing.lead_quality_score is None:
                    continue
                if listing.lead_quality_score < user.alert_min_score:
                    continue
                # Must match at least ONE saved search for this user's dealer
                matched = next(
                    (s for s in searches if _listing_matches_query(listing, s.query)),
                    None,
                )
                if not matched:
                    continue

                stats["matches"] += 1

                # Dedup check + send + record in one session scope
                sent = await _deliver(user, listing, source=matched.name)
                if sent:
                    stats["sent"] += 1
                else:
                    stats["skipped"] += 1

    return stats


async def _deliver(user: User, listing: Listing, source: str) -> bool:
    """Send one alert email if not already delivered. Returns True if sent."""
    kind = "hot_lead"

    # Precheck + row insertion inside a session.
    with session_scope() as db:
        existing = db.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.user_id == user.id,
                NotificationDelivery.listing_id == listing.id,
                NotificationDelivery.kind == kind,
            )
        )
        if existing:
            return False
        # Reserve the slot optimistically so a racing worker doesn't double-send.
        db.add(
            NotificationDelivery(
                user_id=user.id, listing_id=listing.id, kind=kind
            )
        )

    subject, text, html = _render_email(user, listing)
    result = await send_email(user.email, subject, text, html_body=html)

    if not result.sent:
        log.warning(
            "lead_alert.email_failed",
            user_id=user.id,
            listing_id=listing.id,
            backend=result.backend,
            error=result.error,
        )
        # Roll back the slot so a later run can retry.
        with session_scope() as db:
            row = db.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.user_id == user.id,
                    NotificationDelivery.listing_id == listing.id,
                    NotificationDelivery.kind == kind,
                )
            )
            if row:
                db.delete(row)
        return False

    log.info(
        "lead_alert.sent",
        user_id=user.id,
        listing_id=listing.id,
        score=listing.lead_quality_score,
        backend=result.backend,
        saved_search=source,
    )
    return True


def main() -> None:
    configure()
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=200)
    parser.add_argument("--lookback", type=int, default=30, help="Minutes")
    args = parser.parse_args()

    stats = asyncio.run(run(args.max, args.lookback))
    log.info("lead_alerts.done", **stats)


if __name__ == "__main__":
    main()
