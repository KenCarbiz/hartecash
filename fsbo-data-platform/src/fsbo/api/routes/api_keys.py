"""API key management.

Tokens look like `ac_live_<random>` and are shown to the dealer only once
at creation. The server stores a SHA-256 hash; callers authenticate by
sending `Authorization: Bearer ac_live_...` or `X-Api-Key: ac_live_...`.
A valid key sets the dealer context in lieu of `X-Dealer-Id`.
"""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.db import get_session
from fsbo.models import ApiKey

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

DealerIdHeader = Annotated[str, Header(alias="X-Dealer-Id")]

TOKEN_PREFIX = "ac_live_"


class ApiKeyIn(BaseModel):
    name: str


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dealer_id: str
    name: str
    token_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    token: str  # shown ONCE on creation


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def resolve_dealer_from_token(db: Session, token: str | None) -> str | None:
    """Look up dealer_id for a bearer token; touches last_used_at on hit."""
    if not token or not token.startswith(TOKEN_PREFIX):
        return None
    key = db.scalar(
        select(ApiKey).where(
            ApiKey.token_hash == _hash_token(token), ApiKey.revoked_at.is_(None)
        )
    )
    if not key:
        return None
    key.last_used_at = datetime.now(timezone.utc)
    return key.dealer_id


@router.post("", response_model=ApiKeyCreated, status_code=201)
def create_key(
    payload: ApiKeyIn,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> ApiKeyCreated:
    secret = secrets.token_urlsafe(32)
    token = f"{TOKEN_PREFIX}{secret}"
    key = ApiKey(
        dealer_id=dealer_id,
        name=payload.name,
        token_hash=_hash_token(token),
        token_prefix=token[:14],  # e.g. "ac_live_abc123"
    )
    db.add(key)
    db.flush()
    return ApiKeyCreated(
        id=key.id,
        dealer_id=key.dealer_id,
        name=key.name,
        token_prefix=key.token_prefix,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        revoked_at=key.revoked_at,
        token=token,
    )


@router.get("", response_model=list[ApiKeyOut])
def list_keys(
    dealer_id: DealerIdHeader, db: Annotated[Session, Depends(get_session)]
) -> list[ApiKeyOut]:
    rows = db.scalars(
        select(ApiKey)
        .where(ApiKey.dealer_id == dealer_id)
        .order_by(ApiKey.created_at.desc())
    ).all()
    return [ApiKeyOut.model_validate(r) for r in rows]


@router.post("/{key_id}/revoke", response_model=ApiKeyOut)
def revoke_key(
    key_id: int,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> ApiKeyOut:
    key = db.get(ApiKey, key_id)
    if not key or key.dealer_id != dealer_id:
        raise HTTPException(404, "api key not found")
    if not key.revoked_at:
        key.revoked_at = datetime.now(timezone.utc)
    db.flush()
    return ApiKeyOut.model_validate(key)
