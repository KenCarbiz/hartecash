"""Auth endpoints: register, login, logout, me."""

import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.auth.password import hash_password, verify_password
from fsbo.auth.tokens import SESSION_COOKIE_NAME, issue, verify
from fsbo.config import settings
from fsbo.db import get_session
from fsbo.models import Dealer, User

router = APIRouter(prefix="/auth", tags=["auth"])


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
