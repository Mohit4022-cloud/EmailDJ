"""Offer lock presence and keyword drift compliance policy."""

from __future__ import annotations

import re

from email_generation.text_utils import collapse_ws, contains_term

POLICY_VERSION = "1.0.0"

_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "for", "with",
    "by", "on", "at", "from", "as", "is", "was", "are", "be", "this",
    "that", "it", "its", "our", "your", "we", "you", "i",
}


def check_offer_lock_violations(
    draft_lower: str,
    body_lower: str,
    offer_lock: str,
) -> list[str]:
    """Check that offer_lock appears verbatim in draft and body, and detect semantic drift.

    Args:
        draft_lower: Lowercased full draft (subject + body).
        body_lower: Lowercased, whitespace-collapsed body text.
        offer_lock: The offer lock string (original case, will be compared lowercased).

    Returns:
        List of violation code strings.
    """
    violations: list[str] = []
    offer_key = collapse_ws(offer_lock).lower()

    if not offer_key or offer_key not in draft_lower:
        violations.append("offer_lock_missing")

    if offer_key and offer_key not in body_lower:
        violations.append("offer_lock_body_verbatim_missing")
        # Semantic drift: check keyword overlap between offer_lock and body
        offer_keywords = [
            w.lower() for w in re.findall(r"[A-Za-z0-9']+", offer_lock)
            if w.lower() not in _STOPWORDS and len(w) > 2
        ]
        if len(offer_keywords) >= 2:
            overlap = sum(1 for kw in offer_keywords if kw in body_lower)
            if overlap / len(offer_keywords) < 0.4:
                violations.append("offer_drift_keyword_overlap_low")

    return violations


def check_banned_phrases(
    draft_lower: str,
    banned_phrases: tuple[str, ...],
) -> list[str]:
    """Check for banned phrases in draft.

    Args:
        draft_lower: Lowercased full draft text.
        banned_phrases: Tuple of phrase strings that must not appear.

    Returns:
        List of violation code strings, one per matched phrase.
    """
    violations: list[str] = []
    for phrase in banned_phrases:
        if phrase in draft_lower:
            violations.append(f"banned_phrase:{phrase}")
    return violations


def check_forbidden_product_terms(
    draft_lower: str,
    forbidden_terms: list[str],
    offer_lock: str,
) -> list[str]:
    """Check that competitor/other-product names are not mentioned.

    Args:
        draft_lower: Lowercased full draft text.
        forbidden_terms: List of competitor product names to exclude.
        offer_lock: The offer lock string (excluded from checks).

    Returns:
        List of violation code strings.
    """
    violations: list[str] = []
    offer_key = collapse_ws(offer_lock.lower().strip())
    for forbidden in forbidden_terms:
        key = collapse_ws(forbidden.lower().strip())
        if not key or key == offer_key:
            continue
        if contains_term(draft_lower, key):
            violations.append(f"forbidden_other_product_mentioned:{forbidden}")
    return violations
