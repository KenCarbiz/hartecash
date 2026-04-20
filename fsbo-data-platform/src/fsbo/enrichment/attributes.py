"""Extract additional high-signal attributes from a listing's text.

Pulls flags that inform the lead quality score and the dealer UX:
- Title type (clean / salvage / rebuilt / flood / lemon / unknown)
- Transmission (manual / automatic)
- Drivetrain (4wd / awd / 2wd)
- Negotiable vs firm price
- Options / features mentioned (tow, leather, sunroof, navigation, etc.)
- Accident mentions
- Owner count ("one owner", "second owner")
- Service record claims

Fast, deterministic, zero API cost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from fsbo.sources.base import NormalizedListing


@dataclass
class Attributes:
    title_type: str | None = None
    transmission: str | None = None
    drivetrain: str | None = None
    negotiable: bool | None = None
    owner_count: int | None = None
    has_service_records: bool = False
    accident_mentioned: bool = False
    features: list[str] | None = None

    def as_dict(self) -> dict:
        return {
            "title_type": self.title_type,
            "transmission": self.transmission,
            "drivetrain": self.drivetrain,
            "negotiable": self.negotiable,
            "owner_count": self.owner_count,
            "has_service_records": self.has_service_records,
            "accident_mentioned": self.accident_mentioned,
            "features": self.features or [],
        }


_TITLE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("salvage", re.compile(r"\bsalvage\s+title\b", re.I)),
    ("rebuilt", re.compile(r"\brebuilt\s+title\b", re.I)),
    ("flood", re.compile(r"\bflood\s+(title|damage)\b", re.I)),
    ("lemon", re.compile(r"\blemon\s+(law|title)\b", re.I)),
    ("clean", re.compile(r"\bclean\s+(title|carfax)\b", re.I)),
]

_TRANS_PATTERNS = [
    ("manual", re.compile(r"\b(manual|stick|5[-\s]?speed|6[-\s]?speed\s+manual|standard\s+transmission)\b", re.I)),
    ("automatic", re.compile(r"\b(automatic|auto\s+trans)\b", re.I)),
]

_DRIVE_PATTERNS = [
    ("4wd", re.compile(r"\b(4wd|4x4|four[-\s]?wheel\s+drive)\b", re.I)),
    ("awd", re.compile(r"\b(awd|all[-\s]?wheel\s+drive)\b", re.I)),
    ("2wd", re.compile(r"\b(2wd|rear[-\s]?wheel\s+drive|rwd|front[-\s]?wheel\s+drive|fwd)\b", re.I)),
]

_FEATURE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("leather", re.compile(r"\bleather\s+(seats?|interior)\b", re.I)),
    ("sunroof", re.compile(r"\b(sunroof|moonroof|panoramic\s+roof)\b", re.I)),
    ("navigation", re.compile(r"\b(navigation|nav\s+system|gps)\b", re.I)),
    ("tow_package", re.compile(r"\btow(ing)?\s+(package|hitch)\b", re.I)),
    ("heated_seats", re.compile(r"\bheated\s+(front\s+)?seats?\b", re.I)),
    ("backup_camera", re.compile(r"\b(backup\s+camera|rear[-\s]?view\s+camera)\b", re.I)),
    ("bluetooth", re.compile(r"\bbluetooth\b", re.I)),
    ("apple_carplay", re.compile(r"\bapple\s+carplay\b|\bandroid\s+auto\b", re.I)),
    ("remote_start", re.compile(r"\bremote\s+start\b", re.I)),
    ("diesel", re.compile(r"\bdiesel\b", re.I)),
    ("turbo", re.compile(r"\bturbo(charged)?\b", re.I)),
]

_OWNER_PATTERNS = [
    (1, re.compile(r"\b(one[-\s]?owner|1\s*owner|single\s+owner)\b", re.I)),
    (2, re.compile(r"\b(two[-\s]?owner|2nd\s+owner|second\s+owner)\b", re.I)),
]

_SERVICE_RE = re.compile(
    r"\b(service\s+records|maintained?\s+(at|by)\s+dealer|all\s+services?\s+done|oil\s+changes?\s+(done|up\s+to\s+date))\b",
    re.I,
)
_ACCIDENT_RE = re.compile(r"\b(no\s+accidents?|never\s+wrecked|accident[-\s]?free|clean\s+history|one\s+minor\s+fender)\b", re.I)

_NEGOTIABLE_RE = re.compile(r"\b(obo|or\s+best\s+offer|negotiable|open\s+to\s+offers)\b", re.I)
_FIRM_RE = re.compile(r"\b(firm|price\s+is\s+firm|non[-\s]?negotiable|no\s+low\s?balls)\b", re.I)


def extract(listing: NormalizedListing) -> Attributes:
    blob = " ".join(filter(None, [listing.title, listing.description]))
    if not blob:
        return Attributes()

    attrs = Attributes(features=[])

    for label, pattern in _TITLE_PATTERNS:
        if pattern.search(blob):
            attrs.title_type = label
            break

    for label, pattern in _TRANS_PATTERNS:
        if pattern.search(blob):
            attrs.transmission = label
            break

    for label, pattern in _DRIVE_PATTERNS:
        if pattern.search(blob):
            attrs.drivetrain = label
            break

    for label, pattern in _FEATURE_PATTERNS:
        if pattern.search(blob):
            attrs.features.append(label)

    for count, pattern in _OWNER_PATTERNS:
        if pattern.search(blob):
            attrs.owner_count = count
            break

    attrs.has_service_records = bool(_SERVICE_RE.search(blob))
    attrs.accident_mentioned = bool(_ACCIDENT_RE.search(blob))

    if _FIRM_RE.search(blob):
        attrs.negotiable = False
    elif _NEGOTIABLE_RE.search(blob):
        attrs.negotiable = True

    return attrs
