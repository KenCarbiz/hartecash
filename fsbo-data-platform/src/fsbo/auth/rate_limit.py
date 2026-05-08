"""In-process rate limiter for sensitive endpoints.

Today this is a per-process in-memory counter — fine at our launch
scale (single uvicorn worker per dyno) and avoids a Redis dep. When we
horizontal-scale beyond one worker, swap the backing store for Redis
without changing the call sites.

Usage:
    from fsbo.auth.rate_limit import check_rate

    if not check_rate(f"login:{ip}:{email}", limit=5, window_seconds=900):
        raise HTTPException(429, "too many attempts; try again later")
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

# Last-N-events deque per key. Bounded by deque maxlen so a single
# key can't blow memory. The lock guards both the dict and the deques.
_LOCK = threading.Lock()
_HITS: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=100))


def check_rate(key: str, *, limit: int, window_seconds: float) -> bool:
    """Record one hit for `key`; return True if still under the limit
    (i.e. the caller is allowed). Returns False when the window already
    contains `limit` or more hits — the caller should refuse the action.
    """
    now = time.monotonic()
    cutoff = now - window_seconds
    with _LOCK:
        bucket = _HITS[key]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


def reset(key: str) -> None:
    """Clear all hits for `key` — used after a successful login so a
    user with prior failures isn't penalized once they get the password
    right."""
    with _LOCK:
        _HITS.pop(key, None)


def _client_ip(request) -> str:  # type: ignore[no-untyped-def]
    """Best-effort client IP extraction. Honors X-Forwarded-For when set
    (we run behind a reverse proxy in production); falls back to the
    socket peer."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"
