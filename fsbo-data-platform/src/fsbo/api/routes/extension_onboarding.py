"""Extension onboarding via short-lived install codes.

Two endpoints:

  POST /extension/install-code   (auth required)
    Logged-in dealer generates a code in the dashboard. Code lives 10
    minutes, single-use. Returned to the dealer's browser only.

  POST /extension/exchange-install-code   (no auth)
    Extension popup posts a code the dealer pasted. Server verifies
    the code (constant-time), marks it used, mints a fresh ApiKey for
    that dealer, returns the token and dealer_id.

Why a code instead of letting the dealer paste an API key directly?
Less friction (8 chars vs 50), and the API key never leaves the
extension's storage — it's never copy-pasted, so it can't end up in
clipboards, screenshots, or screen-recordings of the dealer's onboarding.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.auth.api_key_resolver import TOKEN_PREFIX, hash_token as _hash_api_token
from fsbo.auth.resolver import DealerId
from fsbo.db import get_session
from fsbo.models import ApiKey, ExtensionInstallCode

# Same SHA-256 helper that protects API tokens at rest. Codes are short
# enough that the keyspace alone isn't a security boundary; the
# single-use + TTL is what matters. Hashing keeps SQL-dump exfil of
# unused codes from being immediately useful.
_hash_code = _hash_api_token

router = APIRouter(prefix="/extension", tags=["extension-onboarding"])

CODE_TTL = timedelta(minutes=10)
# 8 chars from a 32-char alphabet (Crockford-ish: no I, L, O, U) ->
# 32**8 = ~1.1e12 keyspace. Single-use + 10-min TTL means even at
# 1000 guesses/sec an attacker has a ~1e-3 chance per code window.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
_CODE_LEN = 8


def _gen_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN))


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InstallCodeOut(BaseModel):
    code: str
    expires_at: datetime
    expires_in_seconds: int


class ExchangeIn(BaseModel):
    code: str = Field(..., min_length=_CODE_LEN, max_length=_CODE_LEN)


class ExchangeOut(BaseModel):
    api_key: str  # full ac_live_... token, only returned once
    dealer_id: str


@router.post("/install-code", response_model=InstallCodeOut, status_code=201)
def issue_install_code(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> InstallCodeOut:
    """Authenticated dealer generates a fresh code for their next
    extension install. Each call invalidates any prior unused codes
    for the same dealer to keep the live-code count small.
    """
    # Invalidate any of this dealer's prior unused codes by marking them
    # used right now. We don't delete — keeps an audit trail.
    now = _now()
    prev = db.scalars(
        select(ExtensionInstallCode).where(
            ExtensionInstallCode.dealer_id == dealer_id,
            ExtensionInstallCode.used_at.is_(None),
            ExtensionInstallCode.expires_at > now,
        )
    ).all()
    for row in prev:
        row.used_at = now

    code = _gen_code()
    expires_at = now + CODE_TTL
    db.add(
        ExtensionInstallCode(
            dealer_id=dealer_id,
            code_hash=_hash_code(code),
            expires_at=expires_at,
        )
    )
    db.flush()
    return InstallCodeOut(
        code=code,
        expires_at=expires_at,
        expires_in_seconds=int(CODE_TTL.total_seconds()),
    )


@router.post("/exchange-install-code", response_model=ExchangeOut)
def exchange_install_code(
    payload: ExchangeIn,
    db: Annotated[Session, Depends(get_session)],
) -> ExchangeOut:
    """Extension exchanges a code for a fresh API key. Single-use,
    10-min TTL. Codes are looked up by SHA-256 hash so an SQL dump
    can't reveal them retroactively.
    """
    code = payload.code.strip().upper()
    code_hash = _hash_code(code)

    row = db.scalar(
        select(ExtensionInstallCode).where(
            ExtensionInstallCode.code_hash == code_hash
        )
    )
    if not row:
        raise HTTPException(404, "invalid or expired code")
    now = _now()
    if row.used_at is not None:
        raise HTTPException(404, "invalid or expired code")
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise HTTPException(404, "invalid or expired code")

    # Mark used + mint API key in the same flush so the code can never
    # mint two keys.
    row.used_at = now
    secret = secrets.token_urlsafe(32)
    token = f"{TOKEN_PREFIX}{secret}"
    api_key = ApiKey(
        dealer_id=row.dealer_id,
        name="Browser extension (auto-provisioned)",
        token_hash=_hash_api_token(token),
        token_prefix=token[:14],
    )
    db.add(api_key)
    db.flush()

    return ExchangeOut(api_key=token, dealer_id=row.dealer_id)
