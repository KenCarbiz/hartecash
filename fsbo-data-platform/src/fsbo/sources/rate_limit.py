"""Cooperative rate limiter + exponential backoff for source adapters.

In-process — not cluster-safe. For multi-worker deployments, swap the
token bucket for a Redis-backed limiter. The interface stays the same.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class TokenBucket:
    capacity: int
    refill_per_sec: float
    tokens: float = field(init=False)
    updated_at: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = float(self.capacity)
        self.updated_at = time.monotonic()

    async def acquire(self, cost: float = 1.0) -> None:
        while True:
            now = time.monotonic()
            elapsed = now - self.updated_at
            self.tokens = min(
                self.capacity, self.tokens + elapsed * self.refill_per_sec
            )
            self.updated_at = now
            if self.tokens >= cost:
                self.tokens -= cost
                return
            wait = (cost - self.tokens) / self.refill_per_sec
            await asyncio.sleep(wait)


# Per-source buckets. Conservative defaults; raise after we observe real
# block behavior in production.
_BUCKETS: dict[str, TokenBucket] = {
    "craigslist": TokenBucket(capacity=30, refill_per_sec=0.5),      # 30 burst, 1 req / 2s sustained
    "ebay_motors": TokenBucket(capacity=50, refill_per_sec=5.0),     # real API, generous
    "offerup": TokenBucket(capacity=10, refill_per_sec=0.2),         # 1 req / 5s
    "facebook_marketplace": TokenBucket(capacity=5, refill_per_sec=0.05),  # extension-driven
    "ksl": TokenBucket(capacity=20, refill_per_sec=0.5),
    "privateauto": TokenBucket(capacity=20, refill_per_sec=0.3),
    "bring_a_trailer": TokenBucket(capacity=10, refill_per_sec=0.2),
    "recycler": TokenBucket(capacity=10, refill_per_sec=0.2),
    "hemmings": TokenBucket(capacity=15, refill_per_sec=0.3),
    "classic_cars": TokenBucket(capacity=15, refill_per_sec=0.3),
    "bookoo": TokenBucket(capacity=10, refill_per_sec=0.2),
    "el_clasificado": TokenBucket(capacity=10, refill_per_sec=0.2),
    "marketcheck": TokenBucket(capacity=100, refill_per_sec=10.0),   # paid API, generous
    "default": TokenBucket(capacity=20, refill_per_sec=0.5),
}


async def throttle(source: str) -> None:
    bucket = _BUCKETS.get(source) or _BUCKETS["default"]
    await bucket.acquire()


async def with_backoff(
    fn: Callable,
    *args,
    max_attempts: int = 5,
    base_delay: float = 1.0,
    **kwargs,
):
    """Retry fn with exponential backoff + full jitter on network errors."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 — catching broadly for retry logic
            last_exc = e
            if attempt == max_attempts - 1:
                break
            delay = base_delay * (2**attempt) * random.uniform(0.5, 1.5)
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc
