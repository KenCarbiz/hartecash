"""Dealer-likelihood signal aggregator.

Signal rulebook synthesized from the research report (Carfax curbstoning,
Bumper, AutoHunter, ACL ad-classification). Each matched signal contributes
a weight; the weighted sum is passed through a sigmoid centered at 4.0 to
produce a 0..1 likelihood.

Callers decide thresholds:
  >= 0.7  -> classify as dealer, hide from private-seller feed by default
  0.4-0.7 -> flag "suspected dealer", show with yellow badge
  <  0.4  -> treat as genuine private seller
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from fsbo.sources.base import NormalizedListing

# Each entry: (signal_key, compiled regex). Matched count feeds weights below.
_REGEX_SIGNALS: list[tuple[str, re.Pattern[str]]] = [
    ("has_dealer_term", re.compile(r"\bdealer(ship)?\b", re.I)),
    ("has_we_sell", re.compile(r"\bwe (have|sell|finance|offer|accept)\b", re.I)),
    ("has_financing", re.compile(r"\bfinanc(ing|e)\s+(available|options|wac|for all)\b", re.I)),
    ("has_bhph", re.compile(r"\bb\.?h\.?p\.?h\b|buy[-\s]?here[-\s]?pay[-\s]?here", re.I)),
    ("has_trade_in", re.compile(r"\btrade[-\s]?ins? (welcome|accepted|ok)\b", re.I)),
    ("has_stock_number", re.compile(r"\bstock\s*#", re.I)),
    ("has_warranty", re.compile(r"\bwarranty (available|included|extended)\b", re.I)),
    ("has_inventory_cta", re.compile(
        r"\b(more (inventory|vehicles|cars)|over\s+\d+\s+in stock|visit our (lot|showroom))\b",
        re.I,
    )),
    ("has_doc_fee", re.compile(r"\bdoc(ument(ation)?)?\s*fee|dmv fees?\b", re.I)),
    ("has_apr_or_oac", re.compile(r"\bapr\b|\bo\.?a\.?c\.?\b", re.I)),
    ("has_price_plus_fees", re.compile(r"\+\s*(tax|title|doc|fees)", re.I)),
    ("has_open_7_days", re.compile(r"\bopen\s+7\s+days\b", re.I)),
    ("has_call_sales", re.compile(r"\bcall\s+(our\s+)?(sales|lot|office)\b", re.I)),
    ("has_spanish_financing", re.compile(r"\bfinanciamiento|cr[eé]dito (f[aá]cil|aprobado)\b", re.I)),
    ("has_spanish_multi_inv", re.compile(r"\btenemos m[aá]s (carros|veh[ií]culos)\b", re.I)),
    ("has_se_habla_espanol", re.compile(r"\bse habla espa[nñ]ol\b", re.I)),
    ("has_sin_credito", re.compile(r"\bsin (cr[eé]dito|ssn|licencia)\b", re.I)),
    ("has_lote", re.compile(r"\blote\b", re.I)),
    ("has_third_person_we_our", re.compile(r"\b(we|our)\s+(team|staff|location|lot|dealership|business)\b", re.I)),
]

_SCAM_REGEX: list[tuple[str, re.Pattern[str]]] = [
    ("scam_shipping_only", re.compile(r"\bshipping only\b", re.I)),
    ("scam_wire", re.compile(r"\b(wire transfer|western union|moneygram)\b", re.I)),
    ("scam_ebay_motors_protection", re.compile(r"\bebay motors protection\b", re.I)),
    ("scam_gift_card", re.compile(r"\bgift card\b", re.I)),
    ("scam_overseas", re.compile(r"\boverseas\b", re.I)),
    ("scam_military_deployment", re.compile(r"\b(military )?deploy(ment|ed)\b", re.I)),
    ("scam_email_only", re.compile(r"\bemail only\b", re.I)),
]

_DEALER_WEIGHTS: dict[str, float] = {
    "has_dealer_term": 2.5,
    "has_we_sell": 1.2,
    "has_financing": 2.5,
    "has_bhph": 3.0,
    "has_trade_in": 1.5,
    "has_stock_number": 2.0,
    "has_warranty": 1.5,
    "has_inventory_cta": 2.5,
    "has_doc_fee": 2.0,
    "has_apr_or_oac": 1.8,
    "has_price_plus_fees": 1.5,
    "has_open_7_days": 1.0,
    "has_call_sales": 2.2,
    "has_spanish_financing": 2.5,
    "has_spanish_multi_inv": 2.5,
    "has_se_habla_espanol": 1.2,
    "has_sin_credito": 2.5,
    "has_lote": 2.0,
    "has_third_person_we_our": 1.2,
    # Cross-listing signals (computed by caller, added into signals dict).
    "phone_on_3plus_listings_30d": 3.0,
    "phone_on_5plus_listings_90d": 4.0,
    "listing_len_over_600": 0.6,
    "all_caps_ratio_high": 0.5,
}

_SIGMOID_THRESHOLD = 4.0


@dataclass
class DealerAssessment:
    likelihood: float
    scam_score: float
    signals: dict[str, bool]


def extract_signals(listing: NormalizedListing, extra: dict[str, bool] | None = None) -> dict[str, bool]:
    """Run the regex rulebook against the listing text and return matched signals."""
    blob = " ".join(filter(None, [listing.title, listing.description]))
    signals: dict[str, bool] = {}
    if blob:
        for key, pattern in _REGEX_SIGNALS:
            if pattern.search(blob):
                signals[key] = True
        for key, pattern in _SCAM_REGEX:
            if pattern.search(blob):
                signals[key] = True
        if len(blob) > 600:
            signals["listing_len_over_600"] = True
        letters = [c for c in blob if c.isalpha()]
        if letters:
            caps = sum(1 for c in letters if c.isupper())
            if caps / len(letters) > 0.3 and len(letters) > 40:
                signals["all_caps_ratio_high"] = True
    if extra:
        signals.update(extra)
    return signals


def assess(listing: NormalizedListing, extra: dict[str, bool] | None = None) -> DealerAssessment:
    signals = extract_signals(listing, extra)
    x = sum(_DEALER_WEIGHTS.get(key, 0.0) for key, present in signals.items() if present)
    likelihood = 1.0 / (1.0 + math.exp(-(x - _SIGMOID_THRESHOLD)))

    scam_hits = sum(1 for k in signals if k.startswith("scam_"))
    if scam_hits >= 2:
        scam_score = 0.9
    elif scam_hits == 1:
        scam_score = 0.6
    else:
        scam_score = 0.0

    return DealerAssessment(likelihood=likelihood, scam_score=scam_score, signals=signals)
