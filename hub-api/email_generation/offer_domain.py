"""Offer domain inference and keyword extraction utilities.

Provides vendor-agnostic helpers for deriving the product domain and ownership
check keywords from session offer data. All detection logic that formerly
relied on hardcoded brand-protection vocabulary should import from here.

Usage:
    from email_generation.offer_domain import infer_offer_domain, offer_keywords_from_lock

    domain = infer_offer_domain(offer_lock="Rippling HR Platform", offer_category="hr_tech")
    # -> "hr_tech"

    keywords = offer_keywords_from_lock("Trademark Search, Screening, and Brand Protection")
    # -> ["Trademark Search, Screening, and Brand Protection", "Trademark Search", "Screening", "Brand Protection"]
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Domain inference
# ---------------------------------------------------------------------------

_DOMAIN_KEYWORD_MAP: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "brand_protection",
        frozenset({"trademark", "brand protection", "counterfeit", "ip enforcement", "brand integrity", "ip protection"}),
    ),
    (
        "data_security",
        frozenset({"cybersecurity", "cyber security", "endpoint protection", "ransomware", "siem", "soc", "data breach"}),
    ),
    (
        "hr_tech",
        frozenset({"payroll", "hris", "hr platform", "workforce management", "people ops", "total rewards"}),
    ),
    (
        "ai_platform",
        frozenset({"llm", "large language model", "ai platform", "foundation model", "claude", "gpt", "generative ai"}),
    ),
    (
        "revenue_intelligence",
        frozenset({"outbound quality", "sequence qa", "email quality", "sales intelligence", "revenue operations"}),
    ),
    (
        "retail_partnership",
        frozenset({"wholesale", "partner program", "retail partner", "merchandising", "vendor program"}),
    ),
)


def infer_offer_domain(offer_lock: str, offer_category: str | None = None) -> str | None:
    """Return a coarse domain string for the seller's offer.

    Priority:
    1. Explicit ``offer_category`` field — trusted as authoritative.
    2. Keyword sniff of ``offer_lock`` — fallback for callers that pre-date
       the ``offer_category`` field.
    3. ``None`` — unknown domain; callers should skip domain-specific logic.

    Args:
        offer_lock:     The offer name/lock string, e.g. "Rippling HR Platform".
        offer_category: Optional explicit domain from SellerProfile, e.g. "hr_tech".

    Returns:
        Domain string (e.g. "brand_protection", "hr_tech", "ai_platform") or None.
    """
    if offer_category:
        return offer_category.lower().strip()

    if not offer_lock:
        return None

    offer_lower = offer_lock.lower()
    for domain, keywords in _DOMAIN_KEYWORD_MAP:
        if any(kw in offer_lower for kw in keywords):
            return domain

    return None


# ---------------------------------------------------------------------------
# Keyword extraction
# ---------------------------------------------------------------------------

_SPLIT_CHARS = re.compile(r"[,/]")
_CONJUNCTION_PREFIX = re.compile(r"^(?:and|or)\s+", re.IGNORECASE)
_WORD_SPLIT = re.compile(r"[\s,/]+")
_MIN_KEYWORD_LEN = 4
_MIN_WORD_LEN = 6  # Minimum length for individual words extracted from offer_lock

# Common words to skip when tokenizing offer_lock into individual keywords
_OFFER_WORD_STOPWORDS = frozenset({
    "and", "or", "the", "for", "of", "in", "at", "by", "to", "a", "an",
    "our", "your", "their", "its", "this", "that", "with", "from",
    "search", "screening",  # generic product-name components
})


def offer_keywords_from_lock(offer_lock: str) -> list[str]:
    """Derive ownership-check keywords from an offer_lock string.

    Returns keywords in this order:
    1. The full offer_lock (primary keyword — always first)
    2. Sub-phrases from comma/slash splits (stripping leading conjunctions)
    3. Individual significant words from the offer_lock (length >= 6, non-stopword)

    Example:
        "Trademark Search, Screening, and Brand Protection" →
        ["Trademark Search, Screening, and Brand Protection",
         "Trademark Search", "Brand Protection",
         "Trademark", "Protection"]

    Args:
        offer_lock: The offer name/lock string.

    Returns:
        List of keywords with the full offer_lock first. Empty list if input is blank.
    """
    stripped = (offer_lock or "").strip()
    if not stripped:
        return []

    keywords: list[str] = [stripped]
    seen_lower: set[str] = {stripped.lower()}

    # Level 2: comma/slash sub-phrases (strip leading conjunctions)
    for part in _SPLIT_CHARS.split(stripped):
        part = _CONJUNCTION_PREFIX.sub("", part.strip()).strip()
        if len(part) >= _MIN_KEYWORD_LEN and part.lower() not in seen_lower:
            keywords.append(part)
            seen_lower.add(part.lower())

    # Level 3: individual significant words (min 6 chars, not in stopwords)
    for word in _WORD_SPLIT.split(stripped):
        word = word.strip()
        word_lower = word.lower()
        if (
            len(word) >= _MIN_WORD_LEN
            and word_lower not in _OFFER_WORD_STOPWORDS
            and word_lower not in seen_lower
        ):
            keywords.append(word)
            seen_lower.add(word_lower)

    return keywords
