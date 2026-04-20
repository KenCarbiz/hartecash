from fastapi import FastAPI

from fsbo.api.routes import (
    activity,
    admin,
    ai,
    extension_ingest,
    leads,
    listings,
    saved_searches,
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/sources")
def sources() -> dict[str, list[str]]:
    from fsbo.sources import REGISTRY

    return {"sources": list(REGISTRY.keys())}
