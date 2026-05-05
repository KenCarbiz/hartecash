"""Read vehicle condition signals off listing photos with Claude Vision.

This is the "VAN moat" piece — VAN's killer demo is showing a dealer
that AI flagged "front bumper has a fresh scrape" before the dealer
drives 30 minutes to look at the car. We use one vision call per
listing (against the best-quality photo) to extract a structured
condition signal set.

Output schema is intentionally narrow: every field has a known
discrete value space the dashboard can render as a chip. Free-text
goes in `notes` for nuance.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Literal

import httpx
from anthropic import Anthropic

from fsbo.config import settings
from fsbo.logging import get_logger

log = get_logger(__name__)

_MAX_IMAGES_PER_LISTING = 3

ConditionRating = Literal["excellent", "good", "fair", "poor", "unknown"]
DamageLevel = Literal["none", "cosmetic", "moderate", "heavy", "unknown"]


@dataclass
class ConditionAssessment:
    overall: ConditionRating = "unknown"
    body_damage: DamageLevel = "unknown"
    paint: ConditionRating = "unknown"
    interior: ConditionRating = "unknown"
    tires: ConditionRating = "unknown"
    notes: str = ""
    flags: list[str] = field(default_factory=list)
    checked_images: int = 0
    source_image: str | None = None

    def as_dict(self) -> dict:
        return {
            "overall": self.overall,
            "body_damage": self.body_damage,
            "paint": self.paint,
            "interior": self.interior,
            "tires": self.tires,
            "notes": self.notes,
            "flags": self.flags,
            "checked_images": self.checked_images,
            "source_image": self.source_image,
        }


_PROMPT = """You are a used-car appraiser looking at one photo of a vehicle
listed on a private-seller marketplace. Rate what you can SEE in this single
photo. Do not speculate beyond what's visible.

Return JSON ONLY in this exact shape:
{
  "overall": "excellent" | "good" | "fair" | "poor" | "unknown",
  "body_damage": "none" | "cosmetic" | "moderate" | "heavy" | "unknown",
  "paint": "excellent" | "good" | "fair" | "poor" | "unknown",
  "interior": "excellent" | "good" | "fair" | "poor" | "unknown",
  "tires": "excellent" | "good" | "fair" | "poor" | "unknown",
  "notes": "<one short sentence on what's most notable>",
  "flags": ["<short tag>", ...]
}

Use "unknown" liberally — if a part of the vehicle isn't in this photo,
say so via "unknown". Notable flags include "rust", "fresh_scrape",
"misaligned_panel", "cracked_windshield", "aftermarket_wheels",
"damaged_bumper", "fading_paint", "torn_seat". Pick at most 3 flags.

Body damage tiers: "cosmetic" = scratches/scuffs only; "moderate" = clear
dents or panel damage; "heavy" = bent frame or major collision damage."""


async def assess_condition(image_urls: list[str]) -> ConditionAssessment:
    """Run vision over the first photo (or first 1-2 if the first fails).

    Single-photo MVP: real version would aggregate multiple photos and
    weight by which body section each shows. For now we assume photo[0]
    is the primary listing photo and most representative.
    """
    if not settings.anthropic_api_key:
        return ConditionAssessment()

    client = Anthropic(api_key=settings.anthropic_api_key)
    out = ConditionAssessment()

    async with httpx.AsyncClient(timeout=20.0) as http:
        for url in image_urls[:_MAX_IMAGES_PER_LISTING]:
            try:
                resp = await http.get(url)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                log.debug("condition_vision.fetch_failed", url=url, error=str(e))
                continue

            media_type = (
                resp.headers.get("content-type", "image/jpeg").split(";")[0]
            )
            b64 = base64.b64encode(resp.content).decode()
            out.checked_images += 1

            try:
                msg = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=300,
                    system=_PROMPT,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": b64,
                                    },
                                }
                            ],
                        }
                    ],
                )
                text = "".join(
                    b.text for b in msg.content if getattr(b, "type", None) == "text"
                ).strip()
            except Exception as e:
                log.debug("condition_vision.llm_failed", error=str(e))
                continue

            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue

            # Accept whatever it returned, falling back to "unknown" so the
            # dashboard doesn't break when the model invents a new tier.
            allowed_overall = {"excellent", "good", "fair", "poor", "unknown"}
            allowed_damage = {"none", "cosmetic", "moderate", "heavy", "unknown"}

            def _pick(field_name: str, allowed: set[str]) -> str:
                v = str(parsed.get(field_name, "")).strip().lower()
                return v if v in allowed else "unknown"

            out.overall = _pick("overall", allowed_overall)  # type: ignore[assignment]
            out.body_damage = _pick("body_damage", allowed_damage)  # type: ignore[assignment]
            out.paint = _pick("paint", allowed_overall)  # type: ignore[assignment]
            out.interior = _pick("interior", allowed_overall)  # type: ignore[assignment]
            out.tires = _pick("tires", allowed_overall)  # type: ignore[assignment]
            out.notes = str(parsed.get("notes", ""))[:400]
            flags = parsed.get("flags", [])
            if isinstance(flags, list):
                out.flags = [
                    str(f).strip().lower()[:32]
                    for f in flags
                    if isinstance(f, str)
                ][:3]
            out.source_image = url
            return out

    return out
