"""Structured-output extractor for FSBO seller voice calls.

The wedge over VAN: every voice call writes back a TYPED schema, not
a free-text transcript. Next rep / appraiser / recon manager all read
the same JSON.

The extractor takes the conversation history (list of {role, text}
turns) and returns a SellerIntake dataclass. Skipped silently when
no Anthropic key is configured (dev / CI).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Literal

from anthropic import Anthropic

from fsbo.config import settings
from fsbo.logging import get_logger

log = get_logger(__name__)

_MODEL = "claude-haiku-4-5-20251001"

TitleStatus = Literal[
    "in_hand", "lien_on_it", "lost", "in_mail", "unknown"
]
DrivableStatus = Literal["yes", "no", "unknown"]
SellerMotivation = Literal["high", "medium", "low", "unknown"]


@dataclass
class SellerIntake:
    """Structured fields extracted from a seller conversation.

    Every field defaults to its 'unknown' / None equivalent so partial
    extracts merge cleanly. Mileage_confirmed differs from listing
    mileage when the seller corrects it on the call.
    """

    mileage_confirmed: int | None = None
    asking_price_floor: float | None = None
    title_status: TitleStatus = "unknown"
    lien_balance: float | None = None
    drivable: DrivableStatus = "unknown"
    accidents_disclosed: list[str] = field(default_factory=list)
    mechanical_issues: list[str] = field(default_factory=list)
    body_damage_disclosed: list[str] = field(default_factory=list)
    aftermarket_mods: list[str] = field(default_factory=list)
    keys_count: int | None = None
    second_owner_records: bool | None = None
    willing_to_meet_when: str | None = None
    location_for_inspection: str | None = None
    motivation_level: SellerMotivation = "unknown"
    motivation_reason: str | None = None
    next_step: str | None = None  # "appointment", "callback", "ghost", "no_deal"

    def as_dict(self) -> dict:
        return asdict(self)


_PROMPT = """You are extracting structured facts from a phone conversation
between a used-car dealer's AI agent and a private-party seller. Read the
turns and pull ONLY what's directly stated by the seller.

Return JSON ONLY in this exact shape (use null / "unknown" / empty list
when a field isn't covered in the conversation):

{
  "mileage_confirmed": int|null,
  "asking_price_floor": number|null,
  "title_status": "in_hand"|"lien_on_it"|"lost"|"in_mail"|"unknown",
  "lien_balance": number|null,
  "drivable": "yes"|"no"|"unknown",
  "accidents_disclosed": ["...short phrase..."],
  "mechanical_issues": ["..."],
  "body_damage_disclosed": ["..."],
  "aftermarket_mods": ["..."],
  "keys_count": int|null,
  "second_owner_records": true|false|null,
  "willing_to_meet_when": "...",
  "location_for_inspection": "...",
  "motivation_level": "high"|"medium"|"low"|"unknown",
  "motivation_reason": "...",
  "next_step": "appointment"|"callback"|"ghost"|"no_deal"|null
}

Rules:
- "in_hand" means seller has the title, no lien.
- motivation_level=high if seller mentions urgency (job loss, moving,
  divorce, baby, payments behind). low if "in no rush".
- Lists capped at 3 entries each, each entry <= 60 chars.
- Never guess. If the seller didn't say it, leave it empty/unknown."""


def _strip_to_json(text: str) -> str:
    """Claude sometimes wraps with ```json fences. Strip if present."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        # remove leading "json\n"
        if t.lower().startswith("json"):
            t = t[4:].lstrip("\n")
    return t.strip()


def _coerce(parsed: dict) -> SellerIntake:
    out = SellerIntake()
    for fld in (
        "mileage_confirmed",
        "asking_price_floor",
        "lien_balance",
        "keys_count",
    ):
        v = parsed.get(fld)
        if v is None:
            continue
        try:
            if fld in ("mileage_confirmed", "keys_count"):
                setattr(out, fld, int(v))
            else:
                setattr(out, fld, float(v))
        except (TypeError, ValueError):
            pass

    title = str(parsed.get("title_status", "unknown")).strip().lower()
    if title in ("in_hand", "lien_on_it", "lost", "in_mail", "unknown"):
        out.title_status = title  # type: ignore[assignment]

    driv = str(parsed.get("drivable", "unknown")).strip().lower()
    if driv in ("yes", "no", "unknown"):
        out.drivable = driv  # type: ignore[assignment]

    mot = str(parsed.get("motivation_level", "unknown")).strip().lower()
    if mot in ("high", "medium", "low", "unknown"):
        out.motivation_level = mot  # type: ignore[assignment]

    for list_fld in (
        "accidents_disclosed",
        "mechanical_issues",
        "body_damage_disclosed",
        "aftermarket_mods",
    ):
        v = parsed.get(list_fld) or []
        if isinstance(v, list):
            cleaned = [str(x).strip()[:60] for x in v if isinstance(x, str)]
            setattr(out, list_fld, cleaned[:3])

    sor = parsed.get("second_owner_records")
    if isinstance(sor, bool):
        out.second_owner_records = sor

    for str_fld in (
        "willing_to_meet_when",
        "location_for_inspection",
        "motivation_reason",
        "next_step",
    ):
        v = parsed.get(str_fld)
        if isinstance(v, str) and v.strip():
            setattr(out, str_fld, v.strip()[:200])
    return out


def merge_intake(prior: dict, fresh: SellerIntake) -> dict:
    """Merge a fresh extract over prior intake; new non-default values
    win, but never erase known fields with defaults."""
    base = dict(prior or {})
    fresh_d = fresh.as_dict()
    for k, v in fresh_d.items():
        if v is None:
            continue
        if v == "unknown":
            continue
        if isinstance(v, list) and not v:
            continue
        base[k] = v
    return base


def extract_from_turns(
    turns: list[dict], system: str | None = None
) -> SellerIntake:
    """Turns are [{"role": "ai"|"seller", "text": "..."}, ...]. Returns
    a SellerIntake (defaulted when no API key)."""
    if not settings.anthropic_api_key:
        return SellerIntake()
    if not turns:
        return SellerIntake()

    # Format the conversation as a single user message for Claude. We
    # don't use the multi-turn API here because the conversation we're
    # extracting from is the assistant's *content* — Claude's job is
    # to summarize, not to participate.
    convo = "\n".join(
        f"{t.get('role', '?')}: {t.get('text', '').strip()}" for t in turns
    )
    prompt_user = f"Conversation:\n{convo}\n\nReturn the JSON now."

    client = Anthropic(api_key=settings.anthropic_api_key)
    try:
        msg = client.messages.create(
            model=_MODEL,
            max_tokens=900,
            system=system or _PROMPT,
            messages=[{"role": "user", "content": prompt_user}],
        )
        text = "".join(
            b.text for b in msg.content if getattr(b, "type", None) == "text"
        )
    except Exception as e:  # noqa: BLE001
        log.debug("voice_intake.llm_failed", error=str(e))
        return SellerIntake()

    try:
        parsed = json.loads(_strip_to_json(text))
    except json.JSONDecodeError:
        return SellerIntake()

    return _coerce(parsed)
