"""Cheap regex-based intent classifier for inbound seller replies.

Five intents matter for the acquisition workflow:

  sold       — seller says they already sold it. Auto-hide listing.
  not_for_sale — seller says they removed the listing / changed their mind.
  interested — seller wants to engage (asks question, gives price).
  negative   — seller is hostile or asks us to stop. Don't auto-opt-out
               here (STOP keyword is its own path); just don't escalate.
  unknown    — anything we can't classify. Default; human handles.

This is the cheap-cascade tier. Phase 4 plan was to swap in a Claude
Haiku call for ambiguous cases. For now, a 30-line regex catches ~80%
of obvious replies and that's enough to add real workflow value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Intent = Literal["sold", "not_for_sale", "interested", "negative", "unknown"]

# Order matters: more specific patterns checked first.
SOLD_PATTERNS = (
    re.compile(r"\b(?:already|just)\s+sold\b", re.I),
    re.compile(r"\bit'?s\s+(?:been\s+)?sold\b", re.I),
    re.compile(r"\bcar\s+(?:has\s+been\s+|is\s+)?sold\b", re.I),
    re.compile(r"\bno\s+longer\s+(?:available|for\s+sale)\b", re.I),
    re.compile(r"\bsold\s+it\s+(?:already|yesterday|today|last\s+week)\b", re.I),
    re.compile(r"\b(?:i\s+)?found\s+a\s+buyer\b", re.I),
    re.compile(r"\b(?:already\s+)?gone\b", re.I),
    re.compile(r"\bsold\s+(?:already|now|out)\b", re.I),
    # Plain "sold" must be a near-standalone sentence to catch "Yes,
    # sold" without false-matching "sold for top dollar etc"
    re.compile(r"^\s*(?:yes,?\s+)?sold[!.\s]*$", re.I),
)

NOT_FOR_SALE_PATTERNS = (
    re.compile(r"\bdecided\s+(?:to\s+)?keep\b", re.I),
    re.compile(r"\bnot\s+for\s+sale\b", re.I),
    re.compile(r"\btook\s+it\s+(?:off|down)\s+the\s+market\b", re.I),
    re.compile(r"\bremoved\s+the\s+listing\b", re.I),
    re.compile(r"\bchanged\s+my\s+mind\b", re.I),
)

NEGATIVE_PATTERNS = (
    re.compile(r"\bnot\s+interested\b", re.I),
    re.compile(r"\bdon'?t\s+(?:contact|message|call|text)\s+me\b", re.I),
    re.compile(r"\bleave\s+me\s+alone\b", re.I),
    re.compile(r"\bwrong\s+number\b", re.I),
)

INTERESTED_PATTERNS = (
    re.compile(r"\b(?:still\s+)?(?:available|for\s+sale)\b", re.I),
    re.compile(r"\$\d", re.I),  # any price quote
    re.compile(r"\bcome\s+(?:see|look\s+at)\s+it\b", re.I),
    re.compile(r"\bhow\s+much\b", re.I),
    re.compile(r"\bwhen\s+can\s+(?:you|we)\b", re.I),
    re.compile(r"\bcash\s+(?:offer|price)\b", re.I),
)


@dataclass
class IntentResult:
    intent: Intent
    matched_pattern: str | None = None


def classify_inbound(body: str | None) -> IntentResult:
    """Single-pass classifier. Empty body -> unknown."""
    if not body or not body.strip():
        return IntentResult(intent="unknown")
    text = body.strip()

    for p in SOLD_PATTERNS:
        if p.search(text):
            return IntentResult(intent="sold", matched_pattern=p.pattern)

    for p in NOT_FOR_SALE_PATTERNS:
        if p.search(text):
            return IntentResult(intent="not_for_sale", matched_pattern=p.pattern)

    for p in NEGATIVE_PATTERNS:
        if p.search(text):
            return IntentResult(intent="negative", matched_pattern=p.pattern)

    for p in INTERESTED_PATTERNS:
        if p.search(text):
            return IntentResult(intent="interested", matched_pattern=p.pattern)

    return IntentResult(intent="unknown")
