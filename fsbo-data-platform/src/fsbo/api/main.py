from fastapi import FastAPI

from fsbo.api.routes import (
    activity,
    admin,
    ai,
    analytics,
    api_keys,
    auth,
    billing,
    extension_ingest,
    extension_onboarding,
    invitations,
    leads,
    listings,
    messages,
    notifications,
    saved_searches,
    source_health,
    tcpa,
    templates,
    valuation,
    webhooks,
)
from fsbo.config import settings
from fsbo.logging import configure

configure()


def _enforce_production_safety() -> None:
    """Refuse to boot in production with insecure defaults.

    The default jwt_secret + cookie_secure=False would silently let
    anyone forge a session cookie or sniff one over HTTP. Fail loud
    instead of letting a misconfigured deploy go live.
    """
    if settings.env_mode != "production":
        return
    if "change-me" in settings.jwt_secret or len(settings.jwt_secret) < 32:
        raise RuntimeError(
            "JWT_SECRET must be set to a >=32-byte random value in production"
        )
    if not settings.cookie_secure:
        raise RuntimeError(
            "COOKIE_SECURE must be true in production (HTTPS-only cookies)"
        )


_enforce_production_safety()


app = FastAPI(
    title="fsbo-data-platform",
    version="0.0.1",
    description="FSBO vehicle listing aggregation API",
)
app.include_router(listings.router)
app.include_router(webhooks.router)
app.include_router(leads.router)
app.include_router(templates.router)
app.include_router(ai.router)
app.include_router(activity.router)
app.include_router(extension_ingest.router)
app.include_router(extension_onboarding.router)
app.include_router(saved_searches.router)
app.include_router(valuation.router)
app.include_router(admin.router)
app.include_router(messages.router)
app.include_router(source_health.router)
app.include_router(api_keys.router)
app.include_router(auth.router)
app.include_router(invitations.router)
app.include_router(notifications.router)
app.include_router(analytics.router)
app.include_router(billing.router)
app.include_router(tcpa.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/sources/registered")
def sources() -> dict[str, list[str]]:
    from fsbo.sources import REGISTRY

    return {"sources": list(REGISTRY.keys())}
