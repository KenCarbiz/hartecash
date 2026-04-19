"""Classify listings as private_seller | dealer | scam | uncertain.

Two-stage:
  1. Cheap regex/keyword heuristics — catch obvious dealer/scam listings without API cost.
  2. LLM fallback (Claude Haiku) for ambiguous cases.
"""

import json
import re
from dataclasses import dataclass

from anthropic import Anthropic

from fsbo.config import settings
from fsbo.models import Classification
from fsbo.sources.base import NormalizedListing

_DEALER_KEYWORDS = [
    r"\bfinancing available\b",
    r"\btrade[- ]?ins? (welcome|accepted)\b",
    r"\bwe finance\b",
    r"\bbuy here pay here\b",
    r"\bno credit\b",
    r"\bbad credit\b",
    r"\b\$?0 down\b",
    r"\bdealer\b",
    r"\bauto sales\b",
    r"\bmotors? (llc|inc)\b",
    r"\bwarranty (available|included)\b",
    r"\bapply online\b",
]

_SCAM_KEYWORDS = [
    r"\bshipping only\b",
    r"\bebay motors protection\b",
    r"\bwestern union\b",
    r"\bmoneygram\b",
    r"\boverseas\b",
    r"\bmilitary deployment\b",
    r"\bgift card\b",
]

_DEALER_RE = re.compile("|".join(_DEALER_KEYWORDS), re.I)
_SCAM_RE = re.compile("|".join(_SCAM_KEYWORDS), re.I)


@dataclass
class ClassificationResult:
    label: str
    confidence: float
    reason: str


def classify_heuristic(listing: NormalizedListing) -> ClassificationResult | None:
    """Fast path. Returns None if heuristics can't decide confidently."""
    blob = " ".join(filter(None, [listing.title, listing.description]))
    if not blob:
        return None

    dealer_hits = _DEALER_RE.findall(blob)
    scam_hits = _SCAM_RE.findall(blob)

    if scam_hits:
        return ClassificationResult(
            label=Classification.SCAM.value,
            confidence=0.9,
            reason=f"scam keywords: {scam_hits[:3]}",
        )
    if len(dealer_hits) >= 2:
        return ClassificationResult(
            label=Classification.DEALER.value,
            confidence=0.85,
            reason=f"dealer keywords: {dealer_hits[:3]}",
        )
    return None


_PROMPT = """You classify used-vehicle FSBO listings. Output STRICT JSON only.

Categories:
- private_seller: individual selling their own car
- dealer: any dealer/broker/wholesaler ad (look for financing, trade-ins, dealer branding, multi-car lot photos, "we", Spanish-language dealer boilerplate)
- scam: shipping-only, overseas, wire-transfer, gift-card, stolen photos, deployed-military tropes
- uncertain: can't tell

Return JSON: {"label": "...", "confidence": 0.0-1.0, "reason": "brief"}"""


def classify_llm(listing: NormalizedListing) -> ClassificationResult:
    """LLM classification via Claude Haiku. Fallback to uncertain if no API key."""
    if not settings.anthropic_api_key:
        return ClassificationResult(
            label=Classification.UNCERTAIN.value,
            confidence=0.0,
            reason="no ANTHROPIC_API_KEY configured; heuristics inconclusive",
        )

    client = Anthropic(api_key=settings.anthropic_api_key)
    user = (
        f"Source: {listing.source}\n"
        f"Title: {listing.title or ''}\n"
        f"Price: {listing.price or ''}\n"
        f"Year/Make/Model: {listing.year or ''} {listing.make or ''} {listing.model or ''}\n"
        f"Description:\n{(listing.description or '')[:2000]}"
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=_PROMPT,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    ).strip()
    try:
        parsed = json.loads(_extract_json(text))
        return ClassificationResult(
            label=parsed.get("label", Classification.UNCERTAIN.value),
            confidence=float(parsed.get("confidence", 0.5)),
            reason=str(parsed.get("reason", "")),
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        return ClassificationResult(
            label=Classification.UNCERTAIN.value,
            confidence=0.0,
            reason=f"llm parse error: {text[:200]}",
        )


def classify(listing: NormalizedListing) -> ClassificationResult:
    heuristic = classify_heuristic(listing)
    if heuristic:
        return heuristic
    return classify_llm(listing)


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text
