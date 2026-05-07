"""Context-safety policy for seller notes and proof candidates."""

from __future__ import annotations

import re

from email_generation.policies.leakage_policy import NO_LEAKAGE_TERMS
from email_generation.text_utils import compact, contains_term, dedupe_sentence_list, split_sentences

POLICY_VERSION = "1.0.0"

_INSTRUCTIONAL_NOTE_PHRASES = (
    "avoid internal terminology",
    "do not leak",
    "don't leak",
    "follow the instructions",
    "follow these instructions",
    "hold the lock",
    "internal instructions",
    "internal terminology",
    "keep claims grounded",
    "locked offer",
    "never leak",
    "offer lock",
    "position the locked offer",
    "system prompt",
    "use the locked offer",
)

_UNIT_SPLIT_PATTERN = re.compile(r"\n+|(?:^|\s)[-*]\s+", re.MULTILINE)


def _context_units(value: str | None) -> list[str]:
    units: list[str] = []
    for chunk in _UNIT_SPLIT_PATTERN.split(value or ""):
        cleaned = compact(chunk)
        if not cleaned:
            continue
        sentences = split_sentences(cleaned)
        units.extend(sentences or [cleaned])
    return units


def context_sentence_is_output_unsafe(sentence: str, *, allowed_text: str = "") -> bool:
    """Return true when a context sentence should not be copied into output."""
    cleaned = compact(sentence)
    if not cleaned:
        return True

    lower = cleaned.lower()
    if any(phrase in lower for phrase in _INSTRUCTIONAL_NOTE_PHRASES):
        return True

    allowed_lower = compact(allowed_text).lower()
    for term in NO_LEAKAGE_TERMS:
        if term in allowed_lower:
            continue
        if contains_term(lower, term):
            return True
    return False


def sanitize_company_notes_for_generation(company_notes: str | None, *, allowed_text: str = "") -> str:
    """Strip seller-note sentences that are instructions or internal-leakage risks."""
    safe_units = [
        unit
        for unit in _context_units(company_notes)
        if not context_sentence_is_output_unsafe(unit, allowed_text=allowed_text)
    ]
    return " ".join(dedupe_sentence_list(safe_units)).strip()
