"""Authenticity signals: telltale marks of a real private seller.

Counterintuitively, typos, run-ons, and regional slang are *positive*
signals — dealer boilerplate and AI-generated copy are too clean. We
approximate with a cheap rulebook rather than a full spellchecker so
we don't add a heavy dependency.
"""

from __future__ import annotations

import re

# Common English misspellings and typos that appear frequently in
# real FSBO copy. Not exhaustive — this is a signal, not a grader.
_COMMON_TYPO_PATTERNS = [
    r"\b(thier|recieve|seperate|occured|untill|alot|definately|wierd)\b",
    r"\b(tommorrow|tomarrow|loose engine|brakes aren?t)\b",
    r"\b(it's a great car|its a great car)\b",  # often mixed
    r"\b(looks an drives|runs an drives)\b",  # "and" → "an"
    r"\b(everythings|doesnt|cant|wont|im|ive|shes|hes|youre)\b",  # missing apostrophes
    r"\b(to much|alot of|peice|definatly|forsale)\b",
    r"\bwants to sale\b",  # "wants to sell" mangled
    r"\bsells? for cheap\b",
]

_TYPO_RE = re.compile("|".join(_COMMON_TYPO_PATTERNS), re.I)

# Regional slang / colloquialisms that signal a real person
_COLLOQUIAL_PATTERNS = [
    r"\bruns like a top\b",
    r"\brun like new\b",
    r"\bbeater\b",
    r"\bgrandma'?s car\b",
    r"\bsunday driver\b",
    r"\bshe'?s a beaut\b",
    r"\bya know\b",
    r"\b(lol|imo|tbh|idk)\b",
    r"\bcuz\b|\b'?cause\b",
    r"\bfirst come first serve\b",
    r"\bno b[s\*]\b",
]
_COLLOQ_RE = re.compile("|".join(_COLLOQUIAL_PATTERNS), re.I)

# Boilerplate "too clean" markers — zero typos + corporate phrasing
_CORPORATE_PATTERNS = [
    r"\bthis vehicle (is|has)\b",
    r"\bplease feel free to\b",
    r"\bat your earliest convenience\b",
    r"\bwe are pleased to offer\b",
    r"\bplease do not hesitate\b",
    r"\bkindly (contact|reach out|provide)\b",
]
_CORPORATE_RE = re.compile("|".join(_CORPORATE_PATTERNS), re.I)


def score_authenticity(text: str | None) -> dict[str, int | bool]:
    """Return a small dict summarizing authenticity signals.

    Keys:
      - typo_hits:       count of matched common-typo patterns
      - colloquial_hits: count of matched regional-slang markers
      - corporate_hits:  count of matched corporate/AI-boilerplate phrases
      - authenticity_score: net positive = likely real seller
    """
    if not text:
        return {
            "typo_hits": 0,
            "colloquial_hits": 0,
            "corporate_hits": 0,
            "authenticity_score": 0,
        }
    typo_hits = len(_TYPO_RE.findall(text))
    colloq_hits = len(_COLLOQ_RE.findall(text))
    corporate_hits = len(_CORPORATE_RE.findall(text))

    # Net authenticity: each typo or colloquialism = +1; corporate phrase = -2
    net = typo_hits + colloq_hits - 2 * corporate_hits
    return {
        "typo_hits": typo_hits,
        "colloquial_hits": colloq_hits,
        "corporate_hits": corporate_hits,
        "authenticity_score": max(-5, min(5, net)),
    }
