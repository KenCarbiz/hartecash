"""Twilio Lookup v2 — carrier + line-type check.

Per-lookup cost ~$0.005. Used to flag VoIP/toll-free lines on seller
phones (weak-but-useful scam tell) and to verify a number is reachable
before a dealer wastes an opener on a dead line.

We gate this behind lead_score >= 50 in the caller so we don't spend
on obviously-rejected leads.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from fsbo.config import settings


@dataclass
class PhoneInfo:
    phone: str
    valid: bool
    line_type: str | None = None  # mobile | landline | voip | toll-free | unknown
    carrier_name: str | None = None
    country_code: str | None = None
    error: str | None = None


async def lookup_phone(phone: str) -> PhoneInfo:
    """Look up carrier + line-type for a phone. No-op if Twilio isn't configured."""
    if not (settings.twilio_account_sid and settings.twilio_auth_token):
        return PhoneInfo(phone=phone, valid=False, error="Twilio not configured")

    # v2 endpoint. Fields=line_type_intelligence requires the Intelligence
    # add-on (enabled at account level; ~$0.005/lookup).
    url = f"https://lookups.twilio.com/v2/PhoneNumbers/{phone}"
    params = {"Fields": "line_type_intelligence"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                url,
                params=params,
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            )
        except httpx.HTTPError as e:
            return PhoneInfo(phone=phone, valid=False, error=str(e)[:200])

    if resp.status_code >= 400:
        return PhoneInfo(
            phone=phone,
            valid=False,
            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )

    payload = resp.json()
    lti = payload.get("line_type_intelligence") or {}
    return PhoneInfo(
        phone=phone,
        valid=bool(payload.get("valid", True)),
        line_type=lti.get("type"),
        carrier_name=lti.get("carrier_name"),
        country_code=payload.get("country_code"),
    )


def line_type_signal(info: PhoneInfo | None) -> int:
    """Score contribution from carrier info.

    Private sellers use mobile/landline; curbstoners and overseas
    scammers use VoIP/virtual/toll-free. Tune conservatively — carrier
    data is noisy.
    """
    if not info or not info.valid or not info.line_type:
        return 0
    t = info.line_type.lower()
    if t == "mobile":
        return 2
    if t == "landline":
        return 1
    if t in ("voip", "nonFixedVoip", "nonfixedvoip"):
        return -8
    if "toll" in t:
        return -5
    return 0
