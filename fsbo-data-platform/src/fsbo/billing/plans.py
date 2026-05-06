"""Plan catalog.

Three SKUs at launch:

  starter      $249/mo per dealership — 1 rooftop, 1 user, AI voice
                 capped at 100 outbound calls/day, AI vision over the
                 first 5 photos per listing. Self-serve signup; no demo.

  pro          $799/mo per rooftop — voice unlimited, DMS push,
                 multi-user, full TCPA compliance suite, photo-mirror
                 to S3 (when we move off local FS), priority support.

  performance  $0/mo + $250/acquired vehicle — usage-metered. Removes
                 the platform-fee objection for indies that VAN's
                 $1,695/mo terrifies. Limit: 50 acquisitions / month.

The product code is the source of truth here; Stripe price IDs are
populated at deploy time via env. Plan capabilities are intentionally
expressed as a flat dict so the dashboard can render "what's included"
side-by-side without a custom DSL.
"""

from __future__ import annotations

from dataclasses import dataclass

from fsbo.config import settings


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    monthly_price_cents: int
    description: str
    capabilities: dict[str, bool | int | str]


PLANS: list[Plan] = [
    Plan(
        code="starter",
        name="Starter",
        monthly_price_cents=24900,
        description="Single dealership · solo operator · self-serve",
        capabilities={
            "rooftops": 1,
            "users": 2,
            "ai_voice_calls_per_day": 100,
            "ai_vision_photos_per_listing": 5,
            "fb_marketplace_extension": True,
            "dms_push": False,
            "multi_rooftop_dashboard": False,
            "compliance_audit_export": False,
        },
    ),
    Plan(
        code="pro",
        name="Pro",
        monthly_price_cents=79900,
        description="Per-rooftop · multi-user · DMS integration · TCPA suite",
        capabilities={
            "rooftops": 1,
            "users": 25,
            "ai_voice_calls_per_day": 0,  # 0 = unlimited
            "ai_vision_photos_per_listing": 0,
            "fb_marketplace_extension": True,
            "dms_push": True,
            "multi_rooftop_dashboard": True,
            "compliance_audit_export": True,
        },
    ),
    Plan(
        code="performance",
        name="Performance",
        monthly_price_cents=0,
        description="$0 platform fee + $250 per acquired vehicle",
        capabilities={
            "rooftops": 1,
            "users": 5,
            "ai_voice_calls_per_day": 100,
            "ai_vision_photos_per_listing": 5,
            "fb_marketplace_extension": True,
            "dms_push": False,
            "multi_rooftop_dashboard": False,
            "compliance_audit_export": False,
            "metered_per_acquisition_cents": 25000,
            "monthly_acquisition_cap": 50,
        },
    ),
]


def by_code(code: str) -> Plan | None:
    for p in PLANS:
        if p.code == code:
            return p
    return None


def stripe_price_for(code: str) -> str | None:
    """Resolve the Stripe price ID for a plan code, configured via env.
    Returns None when the price isn't configured yet (dev / pre-launch)."""
    return {
        "starter": settings.stripe_price_starter,
        "pro": settings.stripe_price_pro,
        "performance": settings.stripe_price_performance,
    }.get(code) or None
