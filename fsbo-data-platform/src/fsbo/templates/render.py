"""Message template rendering.

Replaces {{placeholder}} tokens in a template body using a dict of values
pulled from the listing + lead context. Missing values render as an empty
string rather than the raw token so dealers don't accidentally send
"{{trim}}" to a customer.
"""

import re
from typing import Any

from fsbo.models import Lead, Listing

_TOKEN_RE = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", re.I)


def build_context(listing: Listing, lead: Lead | None = None) -> dict[str, str]:
    price = f"${int(listing.price):,}" if listing.price else ""
    mileage = f"{listing.mileage:,}" if listing.mileage else ""
    offer = (
        f"${int(lead.offered_price):,}" if lead and lead.offered_price else ""
    )
    return {
        "year": str(listing.year) if listing.year else "",
        "make": listing.make or "",
        "model": listing.model or "",
        "trim": listing.trim or "",
        "price": price,
        "mileage": mileage,
        "vin": listing.vin or "",
        "city": listing.city or "",
        "state": listing.state or "",
        "zip": listing.zip_code or "",
        "url": listing.url or "",
        "offer": offer,
        "dealer_name": "our dealership",
    }


def render(body: str, context: dict[str, Any]) -> str:
    def sub(match: re.Match[str]) -> str:
        key = match.group(1).lower()
        value = context.get(key, "")
        return str(value) if value is not None else ""

    rendered = _TOKEN_RE.sub(sub, body)
    # Collapse double spaces introduced by empty substitutions.
    rendered = re.sub(r"[ \t]{2,}", " ", rendered)
    rendered = re.sub(r" +\n", "\n", rendered)
    return rendered.strip()


# VAN's FSBO guide mentions "three greeting scripts, three VIN request
# scripts, and three offer formats." We seed dealers with that baseline.
SEED_TEMPLATES: list[dict[str, str]] = [
    {
        "name": "Opener — short & direct",
        "category": "outreach",
        "body": (
            "Hi! Saw your {{year}} {{make}} {{model}} listed. "
            "Still available? I'm a buyer and can move quickly if the condition checks out."
        ),
    },
    {
        "name": "Opener — VIN-first",
        "category": "outreach",
        "body": (
            "Hi — interested in your {{year}} {{make}} {{model}}. "
            "If you can text me the VIN I'll pull the history and circle back with a number today."
        ),
    },
    {
        "name": "Opener — local buyer",
        "category": "outreach",
        "body": (
            "Hey, I saw your {{make}} {{model}} listed in {{city}}. "
            "If it's still available I'd love to come see it this week. What's the best number to reach you?"
        ),
    },
    {
        "name": "VIN request — polite",
        "category": "vin_request",
        "body": (
            "Thanks for the quick reply! Can you send over the VIN so I can run the history and "
            "make sure there are no surprises? It's usually on the lower left of the windshield."
        ),
    },
    {
        "name": "VIN request — with photo offer",
        "category": "vin_request",
        "body": (
            "Appreciate it. If it's easier, just snap a pic of the driver-side windshield "
            "where the VIN is stamped. I'll run the report on my end."
        ),
    },
    {
        "name": "VIN request — ready with offer",
        "category": "vin_request",
        "body": (
            "Before I come out, send me the VIN and I'll have a cash offer ready when I arrive."
        ),
    },
    {
        "name": "Offer — firm number",
        "category": "offer",
        "body": (
            "Ran the report and looked at comps — I can do {{offer}} cash today, pickup by end of week. "
            "Let me know if that works."
        ),
    },
    {
        "name": "Offer — contingent on inspection",
        "category": "offer",
        "body": (
            "If everything checks out when I see it in person, I'm at {{offer}} cash. "
            "Title in hand and I can pick up today."
        ),
    },
    {
        "name": "Offer — best-and-final",
        "category": "offer",
        "body": (
            "Appreciate you working with me. My best is {{offer}}. If that works I'll come get it today "
            "with a cashier's check — no financing, no trade, no drama."
        ),
    },
]
