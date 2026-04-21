"""Notification preferences for the logged-in user."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from fsbo.auth.tokens import SESSION_COOKIE_NAME, verify
from fsbo.db import get_session
from fsbo.models import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


class PreferencesOut(BaseModel):
    alerts_enabled: bool
    alert_min_score: int


class PreferencesPatch(BaseModel):
    alerts_enabled: bool | None = None
    alert_min_score: int | None = Field(None, ge=0, le=100)


def _current_user(request: Request, db: Session) -> User:
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    claims = verify(cookie) if cookie else None
    if not claims:
        raise HTTPException(status_code=401, detail="not authenticated")
    user_id = int(claims.get("sub") or 0)
    user = db.get(User, user_id) if user_id else None
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="user not found")
    return user


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(
    request: Request, db: Annotated[Session, Depends(get_session)]
) -> PreferencesOut:
    user = _current_user(request, db)
    return PreferencesOut(
        alerts_enabled=user.alerts_enabled,
        alert_min_score=user.alert_min_score,
    )


@router.patch("/preferences", response_model=PreferencesOut)
def patch_preferences(
    payload: PreferencesPatch,
    request: Request,
    db: Annotated[Session, Depends(get_session)],
) -> PreferencesOut:
    user = _current_user(request, db)
    if payload.alerts_enabled is not None:
        user.alerts_enabled = payload.alerts_enabled
    if payload.alert_min_score is not None:
        user.alert_min_score = payload.alert_min_score
    db.flush()
    return PreferencesOut(
        alerts_enabled=user.alerts_enabled,
        alert_min_score=user.alert_min_score,
    )
