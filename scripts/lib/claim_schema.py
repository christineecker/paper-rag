"""Claim fields and the checks `claims.py add` applies before storing a claim."""
from __future__ import annotations

import re
from typing import Optional

STRUCTURED_FIELDS = (
    "population",
    "intervention",
    "comparator",
    "outcome",
    "direction",
    "effect_value",
    "effect_measure",
    "uncertainty_interval",
    "study_design",
)
DIRECTIONS = ("increase", "decrease", "no_difference", "mixed")
# Stored as chroma metadata on `claim` rows and echoed on claim hits by query.py.
CLAIM_META_FIELDS = STRUCTURED_FIELDS + ("evidence_span",)
NUMERIC_FIELDS = ("effect_value", "uncertainty_interval")

_UNSET = {"", "unknown", "n/a", "na", "none", "not reported", "not stated"}
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def structured_fields(claim: dict) -> dict:
    """The claim's optional structured fields as stripped strings, unset ones dropped."""
    out = {}
    for field in STRUCTURED_FIELDS:
        value = claim.get(field)
        if value is None:
            continue
        value = str(value).strip()
        if value.lower() in _UNSET:
            continue
        out[field] = value
    return out


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def span_in_sources(span: str, source_texts: list[str]) -> bool:
    """True if `span` occurs verbatim (whitespace- and case-insensitive) in one source chunk."""
    needle = _squash(span)
    return bool(needle) and any(needle in _squash(t) for t in source_texts)


def missing_numbers(text: str, source_text: str) -> list[str]:
    """Numbers in `text` (multi-digit or decimal; lone digits are too often spelled out in
    the source) that do not appear as a whole number in `source_text`."""
    missing = []
    for num in _NUMBER_RE.findall(text):
        if len(num) < 2:
            continue
        if not re.search(rf"(?<![\d.]){re.escape(num)}(?!\d)", source_text):
            missing.append(num)
    return missing


def validate_claim(
    claim: dict,
    source_texts: list[str],
    *,
    check_span: bool = True,
    check_numbers: bool = True,
) -> Optional[tuple[str, dict]]:
    """Return None if the claim passes, else (error_code, details)."""
    fields = structured_fields(claim)
    direction = fields.get("direction")
    if direction and direction not in DIRECTIONS:
        return "invalid_direction", {"direction": direction, "allowed": list(DIRECTIONS)}

    if check_span:
        span = (claim.get("evidence_span") or "").strip()
        if not span:
            return "missing_evidence_span", {"hint": "quote the sentence from a source chunk that states the claim"}
        if not span_in_sources(span, source_texts):
            return "evidence_span_not_in_source", {"evidence_span": span}

    if check_numbers:
        joined = " ".join(source_texts)
        checked = " ".join([claim.get("text", "")] + [fields[f] for f in NUMERIC_FIELDS if f in fields])
        bad = missing_numbers(checked, joined)
        if bad:
            return "numbers_not_in_source", {"numbers": bad}
    return None
