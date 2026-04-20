from fastapi import FastAPI

from fsbo.api.routes import activity, ai, leads, listings, templates, webhooks
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/sources")
def sources() -> dict[str, list[str]]:
    from fsbo.sources import REGISTRY

    return {"sources": list(REGISTRY.keys())}
