"""Auth endpoints: register, login, logout, me, forgot/reset password."""

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.auth.password import hash_password, verify_password
from fsbo.auth.tokens import SESSION_COOKIE_NAME, issue, verify
from fsbo.config import settings
from fsbo.db import get_session
from fsbo.messaging.email_client import send_email
from fsbo.models import Dealer, PasswordResetToken, User

router = APIRouter(prefix="/auth", tags=["auth"])


RESET_TTL_HOURS = 1


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str | None = None
    # Either join an existing dealer by slug or create a new one.
    dealer_slug: str | None = None
    dealer_name: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class MeOut(BaseModel):
    id: int
    email: str
    name: str | None
    dealer_id: str
    role: str


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:64] or "dealer"


def _set_cookie(response: Response, token: str) -> None:
    kwargs: dict = {
        "key": SESSION_COOKIE_NAME,
        "value": token,
        "httponly": True,
        "samesite": "lax",
        "secure": settings.cookie_secure,
        "max_age": settings.session_days * 86400,
        "path": "/",
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    response.set_cookie(**kwargs)


@router.post("/register", response_model=MeOut, status_code=201)
def register(
    payload: RegisterIn,
    response: Response,
    db: Annotated[Session, Depends(get_session)],
) -> MeOut:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="email already registered")

    # Resolve or create the dealer.
    slug = payload.dealer_slug or _slugify(
        payload.dealer_name or payload.email.split("@")[1]
    )
    dealer = db.scalar(select(Dealer).where(Dealer.slug == slug))
    if not dealer:
        dealer = Dealer(slug=slug, name=payload.dealer_name or slug)
        db.add(dealer)
        db.flush()

    # First user at a dealer is the admin.
    first_user = db.scalar(
        select(User).where(User.dealer_id == dealer.slug).limit(1)
    )
    role = "admin" if first_user is None else "member"

    user = User(
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        name=payload.name,
        dealer_id=dealer.slug,
        role=role,
    )
    db.add(user)
    db.flush()

    token = issue(user.id, user.dealer_id, user.email)
    _set_cookie(response, token)

    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        dealer_id=user.dealer_id,
        role=user.role,
    )


@router.post("/login", response_model=MeOut)
def login(
    payload: LoginIn,
    response: Response,
    db: Annotated[Session, Depends(get_session)],
) -> MeOut:
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if not user or not user.is_active or not verify_password(
        payload.password, user.password_hash
    ):
        raise HTTPException(status_code=401, detail="invalid email or password")

    user.last_login_at = datetime.now(timezone.utc)
    db.flush()

    token = issue(user.id, user.dealer_id, user.email)
    _set_cookie(response, token)
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        dealer_id=user.dealer_id,
        role=user.role,
    )


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=MeOut)
def me(
    request: Request, db: Annotated[Session, Depends(get_session)]
) -> MeOut:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    claims = verify(token) if token else None
    if not claims:
        raise HTTPException(status_code=401, detail="not authenticated")
    user_id = int(claims.get("sub") or 0)
    user = db.get(User, user_id) if user_id else None
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="user not found")
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        dealer_id=user.dealer_id,
        role=user.role,
    )


# ---- Password reset ----


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=8)


@router.post("/forgot", status_code=202)
async def forgot_password(
    payload: ForgotIn,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    """Always returns 202 regardless of whether the email exists — prevents
    account enumeration. Sends a reset link if the account is real."""
    email = str(payload.email).lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if user and user.is_active:
        raw_token = "rst_" + secrets.token_urlsafe(32)
        row = PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(raw_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(hours=RESET_TTL_HOURS),
        )
        db.add(row)
        db.flush()

        origin = (settings.app_origin or "").rstrip("/")
        reset_url = (
            f"{origin}/reset-password?token={raw_token}"
            if origin
            else f"/reset-password?token={raw_token}"
        )
        subject = "Reset your AutoCurb password"
        text = (
            f"Hi{(' ' + user.name) if user.name else ''},\n\n"
            f"Use the link below to reset your AutoCurb password. It expires "
            f"in {RESET_TTL_HOURS} hour.\n\n"
            f"{reset_url}\n\n"
            f"If you didn't request this, you can ignore this email.\n"
        )
        html = (
            f"<p>Hi{(' ' + user.name) if user.name else ''},</p>"
            f"<p>Use the button below to reset your AutoCurb password. "
            f"It expires in {RESET_TTL_HOURS} hour.</p>"
            f'<p><a href="{reset_url}" '
            f'style="display:inline-block;padding:10px 16px;'
            f'background:#4f46e5;color:#fff;text-decoration:none;'
            f'border-radius:6px;font-weight:500">Reset password</a></p>'
            f'<p style="color:#64748b;font-size:12px">'
            f"If the button doesn't work, paste this into your browser:<br>"
            f'<code>{reset_url}</code></p>'
            f"<p>If you didn't request this, you can safely ignore this email.</p>"
        )
        background_tasks.add_task(
            send_email, email, subject, text, html
        )
    return {"status": "accepted"}


@router.post("/reset", status_code=200)
def reset_password(
    payload: ResetIn,
    response: Response,
    db: Annotated[Session, Depends(get_session)],
) -> MeOut:
    row = db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == _hash_token(payload.token)
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="invalid or expired token")
    if row.used_at:
        raise HTTPException(status_code=410, detail="token already used")
    now = datetime.now(timezone.utc)
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(status_code=410, detail="token expired")

    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="user not found")

    user.password_hash = hash_password(payload.password)
    row.used_at = now
    db.flush()

    # Auto-login after successful reset.
    token = issue(user.id, user.dealer_id, user.email)
    _set_cookie(response, token)
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        dealer_id=user.dealer_id,
        role=user.role,
    )
