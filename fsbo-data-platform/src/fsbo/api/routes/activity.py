"""Battle tracker — daily acquisition activity + goals per user.

Inspired by the military-style "battle tracking" workflow VAN promotes.
Dealers hit daily outreach goals; we show progress and streaks.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fsbo.db import get_session
from fsbo.models import DailyActivity

router = APIRouter(prefix="/activity", tags=["activity"])

DealerIdHeader = Annotated[str, Header(alias="X-Dealer-Id")]


class ActivityBump(BaseModel):
    user_id: str = "me"
    messages_sent: int = 0
    calls_made: int = 0
    offers_made: int = 0
    appointments: int = 0
    purchases: int = 0


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dealer_id: str
    user_id: str
    date: str
    messages_sent: int
    calls_made: int
    offers_made: int
    appointments: int
    purchases: int
    goal_messages: int


class BattleSummary(BaseModel):
    today: ActivityOut
    goal_pct: int
    streak_days: int
    week_totals: dict[str, int]


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _get_or_create(
    db: Session, dealer_id: str, user_id: str, day: str
) -> DailyActivity:
    row = db.scalar(
        select(DailyActivity).where(
            DailyActivity.dealer_id == dealer_id,
            DailyActivity.user_id == user_id,
            DailyActivity.date == day,
        )
    )
    if row:
        return row
    row = DailyActivity(dealer_id=dealer_id, user_id=user_id, date=day)
    db.add(row)
    db.flush()
    return row


@router.post("/bump", response_model=ActivityOut)
def bump_activity(
    payload: ActivityBump,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> ActivityOut:
    row = _get_or_create(db, dealer_id, payload.user_id, _today_iso())
    row.messages_sent += payload.messages_sent
    row.calls_made += payload.calls_made
    row.offers_made += payload.offers_made
    row.appointments += payload.appointments
    row.purchases += payload.purchases
    return ActivityOut.model_validate(row)


@router.get("/today", response_model=ActivityOut)
def today(
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
    user_id: str = "me",
) -> ActivityOut:
    row = _get_or_create(db, dealer_id, user_id, _today_iso())
    return ActivityOut.model_validate(row)


@router.get("/summary", response_model=BattleSummary)
def summary(
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
    user_id: str = "me",
) -> BattleSummary:
    today_iso = _today_iso()
    today_row = _get_or_create(db, dealer_id, user_id, today_iso)

    goal_pct = 0
    if today_row.goal_messages > 0:
        goal_pct = min(
            100, int(round(today_row.messages_sent / today_row.goal_messages * 100))
        )

    # Streak: consecutive prior days where messages_sent >= goal.
    streak = 0
    d = datetime.now(timezone.utc).date()
    while True:
        d = d - timedelta(days=1)
        row = db.scalar(
            select(DailyActivity).where(
                DailyActivity.dealer_id == dealer_id,
                DailyActivity.user_id == user_id,
                DailyActivity.date == d.isoformat(),
            )
        )
        if not row or row.messages_sent < row.goal_messages:
            break
        streak += 1
        if streak >= 60:  # safety cap
            break

    # Week totals (last 7 days including today).
    week_start = (datetime.now(timezone.utc).date() - timedelta(days=6)).isoformat()
    totals = db.execute(
        select(
            func.coalesce(func.sum(DailyActivity.messages_sent), 0),
            func.coalesce(func.sum(DailyActivity.calls_made), 0),
            func.coalesce(func.sum(DailyActivity.offers_made), 0),
            func.coalesce(func.sum(DailyActivity.appointments), 0),
            func.coalesce(func.sum(DailyActivity.purchases), 0),
        ).where(
            DailyActivity.dealer_id == dealer_id,
            DailyActivity.user_id == user_id,
            DailyActivity.date >= week_start,
        )
    ).one()
    week_totals = {
        "messages_sent": int(totals[0]),
        "calls_made": int(totals[1]),
        "offers_made": int(totals[2]),
        "appointments": int(totals[3]),
        "purchases": int(totals[4]),
    }

    return BattleSummary(
        today=ActivityOut.model_validate(today_row),
        goal_pct=goal_pct,
        streak_days=streak,
        week_totals=week_totals,
    )


# Used by the dashboard date picker sanity check.
@router.get("/valid-date/{d}")
def valid_date(d: str) -> dict[str, bool]:
    try:
        date.fromisoformat(d)
        return {"valid": True}
    except ValueError:
        return {"valid": False}
