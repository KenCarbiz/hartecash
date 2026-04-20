"""Extract a VIN from a listing image using Claude Vision.

Research-picked approach: cheap cascade — Tesseract/Google Vision first
when we have them, Claude Vision for the 15% of hard cases (angled
windshield photos, partial views, glare). Here we implement the Claude
Vision pass directly since it's the one we can ship without a second
vendor integration.

Cost: ~$0.003-0.01 per image with Claude Haiku 4.5 vision. We cap the
pipeline at the first N images per listing to keep cost bounded.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass

import httpx
from anthropic import Anthropic

from fsbo.config import settings
from fsbo.enrichment.vin_checksum import valid_vin
from fsbo.logging import get_logger

log = get_logger(__name__)

_VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
_MAX_IMAGES_PER_LISTING = 4

_PROMPT = """You are looking at a photo from a used-car listing. If you can see
a clear 17-character VIN (vehicle identification number) visible anywhere in the
image — windshield corner, door jamb, dashboard, or a registration/title card —
return it.

Return JSON only, no prose:
{"vin": "1HGBH41JXMN109186"} if you see one, otherwise {"vin": null}.

Never guess. If the VIN is partially obscured or blurry, return null."""


@dataclass
class VisionVinResult:
    vin: str | None
    checked_images: int
    source_image: str | None


async def extract_vin_from_images(image_urls: list[str]) -> VisionVinResult:
    """Walk the first few images and try to pull a valid VIN."""
    if not settings.anthropic_api_key:
        return VisionVinResult(vin=None, checked_images=0, source_image=None)

    client = Anthropic(api_key=settings.anthropic_api_key)
    checked = 0
    async with httpx.AsyncClient(timeout=20.0) as http:
        for url in image_urls[:_MAX_IMAGES_PER_LISTING]:
            try:
                resp = await http.get(url)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                log.debug("vin_vision.fetch_failed", url=url, error=str(e))
                continue

            media_type = resp.headers.get("content-type", "image/jpeg").split(";")[0]
            b64 = base64.b64encode(resp.content).decode()
            checked += 1

            try:
                msg = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=120,
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
                log.debug("vin_vision.llm_failed", error=str(e))
                continue

            match = _VIN_RE.search(text.upper())
            if match and valid_vin(match.group(0)):
                return VisionVinResult(
                    vin=match.group(0), checked_images=checked, source_image=url
                )

    return VisionVinResult(vin=None, checked_images=checked, source_image=None)
