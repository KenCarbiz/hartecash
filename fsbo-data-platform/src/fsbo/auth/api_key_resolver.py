"""Low-level API-key-to-dealer lookup.

Lives in the auth package (not in api/routes/) so the resolver can import
it without pulling FastAPI route modules and creating a circular import.
"""

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.models import ApiKey

TOKEN_PREFIX = "ac_live_"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def resolve_dealer_from_token(db: Session, token: str | None) -> str | None:
    """Return dealer_id for a valid bearer token; touches last_used_at."""
    if not token or not token.startswith(TOKEN_PREFIX):
        return None
    key = db.scalar(
        select(ApiKey).where(
            ApiKey.token_hash == hash_token(token), ApiKey.revoked_at.is_(None)
        )
    )
    if not key:
        return None
    key.last_used_at = datetime.now(timezone.utc)
    return key.dealer_id
