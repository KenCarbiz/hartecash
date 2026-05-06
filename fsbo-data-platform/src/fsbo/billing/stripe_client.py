"""Thin wrapper around the Stripe SDK.

Centralizes the API key + version pinning so the rest of the codebase
imports `from fsbo.billing.stripe_client import stripe` rather than
sprinkling configuration. When `STRIPE_SECRET_KEY` is empty (dev/CI),
calls into stripe will fail fast with a clear error — but we never
*reach* stripe in a normal test run because the route handlers
short-circuit on missing config.
"""

from __future__ import annotations

import stripe as _stripe

from fsbo.config import settings

# Pin a known-good API version so Stripe doesn't change the JSON shape
# under us when they ship dashboard updates.
_stripe.api_version = "2024-09-30.acacia"
_stripe.api_key = settings.stripe_secret_key or "sk_test_unset"

stripe = _stripe


def billing_enabled() -> bool:
    """True iff a real Stripe key is configured. Routes can short-
    circuit when False so dev/CI never tries to call Stripe."""
    return bool(settings.stripe_secret_key) and not settings.stripe_secret_key.endswith(
        "_unset"
    )
