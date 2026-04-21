"""JWT issuance + verification for session cookies.

Cookie flow:
  POST /auth/login -> issue HS256 JWT, set Set-Cookie: autocurb_session=<jwt>
  Every request      -> middleware reads cookie, verifies, sets request.state
  POST /auth/logout  -> clear cookie

Claims:
  sub       user id (int)
  dealer_id dealer slug (str) — used for row scoping
  email     user email
  iat, exp  standard

We deliberately keep claims small so the cookie fits comfortably.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from fsbo.config import settings

SESSION_COOKIE_NAME = "autocurb_session"


def issue(user_id: int, dealer_id: str, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "dealer_id": dealer_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.session_days)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


def verify(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
    except jwt.PyJWTError:
        return None
