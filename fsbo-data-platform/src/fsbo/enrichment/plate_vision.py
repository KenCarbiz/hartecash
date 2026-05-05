"""Extract license-plate state + number from listing photos.

Sibling of vin_vision. Plates are a stronger curbstoner signal than
VINs — a plate that appears on multiple listings under different
sellers is almost always a curbstoner. Capturing the plate also
lets dealers verify the seller really owns the car (registration
lookup) before driving over.

Cost: ~$0.003-0.01 per image with Claude Haiku 4.5 vision. Cap to
the first N images so we don't burn budget on listings with 30
photos. We stop early when we find a plate that looks valid.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass

import httpx
from anthropic import Anthropic

from fsbo.config import settings
from fsbo.logging import get_logger

log = get_logger(__name__)

_MAX_IMAGES_PER_LISTING = 4

# Loose plate validator: 4-8 alphanumeric chars, allow space/hyphen.
# Lots of state-specific formats; we don't try to enforce them. Fail
# obviously bogus values (digit-only > 8, "PLATE", "NONE").
_PLATE_RE = re.compile(r"^[A-Z0-9][A-Z0-9 \-]{2,9}[A-Z0-9]$")
_BAD_PLATE_VALUES = {"PLATE", "NONE", "UNKNOWN", "TEMP", "FORD", "TOYOTA"}

_PROMPT = """You're looking at a used-car listing photo. Find the rear or
front license plate if one is visible. Read the plate number and identify
the issuing state from any visible state name, motto, or color scheme.

Return JSON only, no prose:
  {"plate": "ABC1234", "state": "FL"}
or {"plate": null, "state": null} if you can't read one clearly.

Be conservative — partial reads or guesses cause real-world bad data.
If you only see the state but not the number, still return null for plate.
"""


@dataclass
class VisionPlateResult:
    plate: str | None
    state: str | None
    checked_images: int
    source_image: str | None


def _looks_valid_plate(plate: str) -> bool:
    p = plate.strip().upper()
    if p in _BAD_PLATE_VALUES:
        return False
    if not _PLATE_RE.match(p):
        return False
    return True


async def extract_plate_from_images(image_urls: list[str]) -> VisionPlateResult:
    if not settings.anthropic_api_key:
        return VisionPlateResult(
            plate=None, state=None, checked_images=0, source_image=None
        )

    client = Anthropic(api_key=settings.anthropic_api_key)
    checked = 0

    async with httpx.AsyncClient(timeout=20.0) as http:
        for url in image_urls[:_MAX_IMAGES_PER_LISTING]:
            try:
                resp = await http.get(url)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                log.debug("plate_vision.fetch_failed", url=url, error=str(e))
                continue

            media_type = (
                resp.headers.get("content-type", "image/jpeg").split(";")[0]
            )
            b64 = base64.b64encode(resp.content).decode()
            checked += 1

            try:
                msg = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=80,
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
                                },
                            ],
                        }
                    ],
                )
                text = "".join(
                    b.text for b in msg.content if getattr(b, "type", None) == "text"
                )
            except Exception as e:
                log.debug("plate_vision.llm_failed", error=str(e))
                continue

            try:
                parsed = json.loads(text.strip())
            except json.JSONDecodeError:
                continue

            plate = parsed.get("plate")
            state = parsed.get("state")
            if not plate:
                continue
            plate = str(plate).strip().upper()
            if not _looks_valid_plate(plate):
                continue
            return VisionPlateResult(
                plate=plate,
                state=str(state).strip().upper()[:2] if state else None,
                checked_images=checked,
                source_image=url,
            )

    return VisionPlateResult(
        plate=None, state=None, checked_images=checked, source_image=None
    )
