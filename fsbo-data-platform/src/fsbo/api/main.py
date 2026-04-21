from fastapi import FastAPI

from fsbo.api.routes import (
    activity,
    admin,
    ai,
    api_keys,
    auth,
    extension_ingest,
    invitations,
    leads,
    listings,
    messages,
    saved_searches,
    source_health,
    templates,
    valuation,
    webhooks,
)
from fsbo.logging import configure

configure()

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
app.include_router(saved_searches.router)
app.include_router(valuation.router)
app.include_router(admin.router)
app.include_router(messages.router)
app.include_router(source_health.router)
app.include_router(api_keys.router)
app.include_router(auth.router)
app.include_router(invitations.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/sources/registered")
def sources() -> dict[str, list[str]]:
    from fsbo.sources import REGISTRY

    return {"sources": list(REGISTRY.keys())}
