"""AI-generated first-contact opener for a listing.

This is the VAN-differentiating feature: the message is written specifically
for the listing's exact words, condition details, and quirks — not a
templated mail-merge. Dealers get a ready-to-send draft in <2s.
"""

from anthropic import Anthropic

from fsbo.config import settings
from fsbo.models import Listing

_SYSTEM = """You are a used-car buyer writing a first-contact message to a private
seller. You work for a dealership's acquisition team. Your job is to write a short
text message (under 350 chars) that feels human, specific to the listing, and
invites reply. Never use emojis, never use ALL CAPS, never sound like a bot.

Rules:
- Mention one specific detail from the listing to prove you read it
- Ask exactly one clear question
- Never mention price until the seller engages
- Never sound pushy or scripted
- No multiple exclamation points
- End with a simple question or a reason to reply

Return JSON only: {"message": "..."}"""


def generate_opener(listing: Listing, tone: str = "direct") -> str:
    """Generate a tailored opener. Falls back to a safe default if no API key."""
    if not settings.anthropic_api_key:
        return _fallback(listing)

    client = Anthropic(api_key=settings.anthropic_api_key)
    prompt = _prompt(listing, tone)

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()
        import json
        import re

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            msg = parsed.get("message", "").strip()
            if msg:
                return msg
    except Exception:
        pass
    return _fallback(listing)


def _prompt(listing: Listing, tone: str) -> str:
    vehicle = " ".join(
        str(v) for v in (listing.year, listing.make, listing.model, listing.trim) if v
    )
    location = ", ".join(v for v in (listing.city, listing.state) if v)
    return f"""Listing source: {listing.source}
Vehicle: {vehicle}
Mileage: {listing.mileage or "unknown"}
Location: {location or "unknown"}
Tone: {tone} (options: direct, friendly, cash-buyer)

Original listing text:
\"\"\"
Title: {listing.title or ""}

{(listing.description or "")[:1500]}
\"\"\"

Write the opener as JSON."""


def _fallback(listing: Listing) -> str:
    vehicle = " ".join(
        str(v) for v in (listing.year, listing.make, listing.model) if v
    )
    return (
        f"Hi — saw your {vehicle or 'listing'} and I'm interested if it's still "
        f"available. Would you be open to a cash offer?"
    )
