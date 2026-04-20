from fastapi import FastAPI

from fsbo.api.routes import leads, listings, webhooks
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/sources")
def sources() -> dict[str, list[str]]:
    from fsbo.sources import REGISTRY

    return {"sources": list(REGISTRY.keys())}
