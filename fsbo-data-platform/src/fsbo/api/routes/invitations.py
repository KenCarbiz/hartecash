"""Team-invitation endpoints.

Admin POSTs to /invitations with a teammate's email. The response is a
one-time invite URL (raw token shown once). The recipient opens the
URL, sees the invite preview (dealer name, inviting admin), sets a
password, and gets auto-logged-in as a member of that dealer.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.auth.password import hash_password
from fsbo.auth.resolver import DealerId
from fsbo.auth.tokens import issue
from fsbo.config import settings
from fsbo.db import get_session
from fsbo.models import Dealer, Invitation, User

router = APIRouter(prefix="/invitations", tags=["invitations"])

INVITE_DAYS = 14
COOKIE_NAME = "autocurb_session"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class InvitationIn(BaseModel):
    email: EmailStr
    role: str = "member"


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dealer_id: str
    email: str
    role: str
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None


class InvitationCreated(InvitationOut):
    token: str  # shown once
    accept_url_hint: str


class InvitationPreview(BaseModel):
    email: str
    role: str
    dealer_id: str
    dealer_name: str | None
    invited_by_email: str | None
    expires_at: datetime


class AcceptInvitationIn(BaseModel):
    token: str
    password: str
    name: str | None = None


def _current_user(request: Request, db: Session) -> User:
    """Helper used by admin-gated routes; resolves via session cookie."""
    from fsbo.auth.tokens import verify

    cookie = request.cookies.get(COOKIE_NAME)
    claims = verify(cookie) if cookie else None
    if not claims:
        raise HTTPException(status_code=401, detail="not authenticated")
    user_id = int(claims.get("sub") or 0)
    user = db.get(User, user_id) if user_id else None
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="user not found")
    return user


@router.post("", response_model=InvitationCreated, status_code=201)
def create_invite(
    payload: InvitationIn,
    request: Request,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> InvitationCreated:
    user = _current_user(request, db)
    if user.dealer_id != dealer_id or user.role != "admin":
        raise HTTPException(
            status_code=403, detail="only admins can invite teammates"
        )

    # If the email already belongs to a user, don't issue an invite.
    existing_user = db.scalar(
        select(User).where(User.email == str(payload.email).lower())
    )
    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="a user with that email already exists",
        )

    raw_token = "inv_" + secrets.token_urlsafe(32)
    invite = Invitation(
        dealer_id=dealer_id,
        email=str(payload.email).lower(),
        role=payload.role,
        invited_by=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_DAYS),
    )
    db.add(invite)
    db.flush()

    return InvitationCreated(
        id=invite.id,
        dealer_id=invite.dealer_id,
        email=invite.email,
        role=invite.role,
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        accepted_at=None,
        revoked_at=None,
        token=raw_token,
        accept_url_hint=f"/invite?token={raw_token}",
    )


@router.get("", response_model=list[InvitationOut])
def list_invites(
    request: Request,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> list[InvitationOut]:
    user = _current_user(request, db)
    if user.dealer_id != dealer_id:
        raise HTTPException(status_code=403, detail="forbidden")
    rows = db.scalars(
        select(Invitation)
        .where(Invitation.dealer_id == dealer_id)
        .order_by(Invitation.created_at.desc())
    ).all()
    return [InvitationOut.model_validate(r) for r in rows]


@router.post("/{invite_id}/revoke", response_model=InvitationOut)
def revoke_invite(
    invite_id: int,
    request: Request,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> InvitationOut:
    user = _current_user(request, db)
    invite = db.get(Invitation, invite_id)
    if not invite or invite.dealer_id != dealer_id or user.role != "admin":
        raise HTTPException(status_code=404, detail="invite not found")
    if not invite.revoked_at:
        invite.revoked_at = datetime.now(timezone.utc)
    db.flush()
    return InvitationOut.model_validate(invite)


# ---- Unauthenticated accept flow ----


@router.get("/preview", response_model=InvitationPreview)
def preview_invite(
    token: str, db: Annotated[Session, Depends(get_session)]
) -> InvitationPreview:
    invite = db.scalar(
        select(Invitation).where(Invitation.token_hash == _hash_token(token))
    )
    _assert_active(invite)
    assert invite is not None

    dealer = db.scalar(select(Dealer).where(Dealer.slug == invite.dealer_id))
    inviter = db.get(User, invite.invited_by)
    return InvitationPreview(
        email=invite.email,
        role=invite.role,
        dealer_id=invite.dealer_id,
        dealer_name=dealer.name if dealer else None,
        invited_by_email=inviter.email if inviter else None,
        expires_at=invite.expires_at,
    )


@router.post("/accept", status_code=201)
def accept_invite(
    payload: AcceptInvitationIn,
    response: Response,
    db: Annotated[Session, Depends(get_session)],
) -> dict:
    if len(payload.password) < 8:
        raise HTTPException(
            status_code=400, detail="password must be at least 8 characters"
        )
    invite = db.scalar(
        select(Invitation).where(Invitation.token_hash == _hash_token(payload.token))
    )
    _assert_active(invite)
    assert invite is not None

    existing_user = db.scalar(select(User).where(User.email == invite.email))
    if existing_user:
        raise HTTPException(
            status_code=409, detail="user with that email already exists"
        )

    user = User(
        email=invite.email,
        password_hash=hash_password(payload.password),
        name=payload.name,
        dealer_id=invite.dealer_id,
        role=invite.role,
    )
    db.add(user)
    invite.accepted_at = datetime.now(timezone.utc)
    db.flush()

    token = issue(user.id, user.dealer_id, user.email)
    _set_cookie(response, token)
    return {
        "id": user.id,
        "email": user.email,
        "dealer_id": user.dealer_id,
        "role": user.role,
    }


def _assert_active(invite: Invitation | None) -> None:
    if not invite:
        raise HTTPException(status_code=404, detail="invitation not found")
    if invite.revoked_at:
        raise HTTPException(status_code=410, detail="invitation revoked")
    if invite.accepted_at:
        raise HTTPException(status_code=410, detail="invitation already accepted")
    now = datetime.now(timezone.utc)
    expires = invite.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(status_code=410, detail="invitation expired")


def _set_cookie(response: Response, token: str) -> None:
    kwargs: dict = {
        "key": COOKIE_NAME,
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
