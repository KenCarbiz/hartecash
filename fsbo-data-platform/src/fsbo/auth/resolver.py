"""Dealer resolution for every request.

Priority:
  1. Session cookie (autocurb_session JWT) — normal dashboard flow
  2. Bearer token / X-Api-Key — Chrome extension + integrations
  3. X-Dealer-Id header — DEV ONLY, for tests and local development

In env_mode="production", (3) is rejected with 401 to prevent anyone
from spoofing a dealer ID.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from fsbo.auth.api_key_resolver import resolve_dealer_from_token
from fsbo.auth.tokens import SESSION_COOKIE_NAME, verify
from fsbo.config import settings
from fsbo.db import get_session


def _token_from_request(request: Request) -> str | None:
    """Extract an API token from the Authorization header or X-Api-Key."""
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return request.headers.get("x-api-key")


def resolve_dealer_id(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    x_dealer_id: Annotated[str | None, Header(alias="X-Dealer-Id")] = None,
) -> str:
    # (1) session cookie
    session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if session_cookie:
        claims = verify(session_cookie)
        if claims and claims.get("dealer_id"):
            return str(claims["dealer_id"])

    # (2) API token (extension / integrations)
    token = _token_from_request(request)
    if token:
        dealer_id = resolve_dealer_from_token(db, token)
        if dealer_id:
            return dealer_id

    # (3) dev-only: raw X-Dealer-Id header
    if settings.env_mode != "production" and x_dealer_id:
        return x_dealer_id

    raise HTTPException(status_code=401, detail="authentication required")


DealerId = Annotated[str, Depends(resolve_dealer_id)]
