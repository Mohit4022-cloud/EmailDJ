"""Deterministic SDR garbage detectors — no LLM required.

Each detector takes (body: str, metadata: dict) and returns evidence strings.
The scorecard() function runs all checks and returns a structured result.

Metadata keys used:
  prospect_company   str   e.g. "Acme"
  prospect_name      str   e.g. "Jordan Smith"
  prospect_title     str   e.g. "VP Sales"
  seller_company     str   e.g. "EmailDJ"
  offer_lock         str   e.g. "Remix Studio"
  offer_category     str   e.g. "revenue_intelligence"  (optional)
  preset_id          str   e.g. "straight_shooter"
  cta_offer_lock     str   e.g. "Open to a quick 15-minute chat next week?"
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from email_generation.offer_domain import infer_offer_domain, offer_keywords_from_lock

# ---------------------------------------------------------------------------
# Shared helpers (logic mirrors evals/sdr_quality.py — avoids circular import)
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "your", "their",
    "have", "has", "into", "across", "teams", "team", "are", "was", "were",
    "its", "our", "their", "which", "will", "can", "not", "all",
}

_EXEC_TITLES_RE = re.compile(
    r"\b(ceo|chief executive officer|founder|co-founder|president|chief of staff)\b",
    re.IGNORECASE,
)

_WEAK_CTA_PRESETS = {"giver", "challenger"}
_GREETING_TOKENS = {"hi", "hello", "hey"}


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def _max_ngram_repetition(text: str, n: int = 3) -> int:
    """Return max occurrence count of any n-gram in text."""
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    if len(words) < n:
        return 0
    counts = Counter(" ".join(words[i : i + n]) for i in range(len(words) - n + 1))
    return max(counts.values(), default=0)


def _sentences(text: str) -> list[str]:
    """Split text into sentences on .!? boundaries."""
    raw = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [s.strip() for s in raw if s.strip()]


def _has_fragment_ending(text: str) -> bool:
    compact = " ".join((text or "").split())
    if not compact:
        return True
    if compact.endswith(("...", ",", ";", ":", "-", "/", "(")):
        return True
    return (
        re.search(
            r"(?:\b(?:and|or|to|with|for|of|from|that|which|while|because|so)\b)\s*$",
            compact,
            flags=re.IGNORECASE,
        )
        is not None
    )


# ---------------------------------------------------------------------------
# 1. FAIL_PROSPECT_OWNS_OFFER
# ---------------------------------------------------------------------------


def _check_prospect_owns_offer(body: str, meta: dict) -> list[str]:
    """Detect patterns like "<ProspectCo>'s <offer>" or "your <offer>".

    Keywords are derived from meta["offer_lock"] at call time — no hardcoded
    domain vocabulary. Works for any seller: brand protection, HR tech, AI
    platform, retail partnerships, etc.
    """
    notes: list[str] = []
    prospect_co = (meta.get("prospect_company") or "").strip()
    if not prospect_co:
        return notes

    offer_lock = (meta.get("offer_lock") or "").strip()
    offer_keywords = offer_keywords_from_lock(offer_lock)
    if not offer_keywords:
        return notes

    body_lower = (body or "").lower()
    co_lower = prospect_co.lower()
    co_safe = re.escape(co_lower)
    seller_co = (meta.get("seller_company") or meta.get("vendor_company") or "").strip().lower()
    vendor_differs = bool(seller_co and seller_co != co_lower)

    for keyword in offer_keywords:
        kw_lower = keyword.lower()
        kw_safe = re.escape(kw_lower)
        # Pattern: "Acme's <offer>" (possessive)
        if re.search(rf"\b{co_safe}'s\s+{kw_safe}", body_lower):
            notes.append(f"Possessive: found '{prospect_co}'s {keyword}'")
        # Pattern: "Acme <offer>" (adjacent without possessive)
        elif re.search(rf"\b{co_safe}\s+{kw_safe}", body_lower):
            notes.append(f"Adjacent: found '{prospect_co} {keyword}'")

    # Generic preposition ownership framing — check all keywords
    for kw in offer_keywords:
        kw_lower = kw.lower()
        kw_safe = re.escape(kw_lower)
        for prep in ("for", "at"):
            if re.search(rf"\b{kw_safe}\s+{prep}\s+{co_safe}\b", body_lower):
                notes.append(f"Ownership framing: found '{kw} {prep} {prospect_co}'")
        if re.search(rf"\b{co_safe}\s+uses\s+{kw_safe}\b", body_lower):
            notes.append(f"Ownership framing: found '{prospect_co} uses {kw}'")

    # "your <offer>" framing — only flagged when seller != prospect
    if vendor_differs:
        for keyword in offer_keywords:
            if re.search(rf"\byour\s+{re.escape(keyword.lower())}", body_lower):
                notes.append(f"Ownership: found 'your {keyword}' (vendor != prospect)")
                break

    return notes


# ---------------------------------------------------------------------------
# 2. FAIL_WIKIPEDIA_OPENER
# ---------------------------------------------------------------------------

_WIKIPEDIA_PATTERNS = [
    re.compile(r"\bis an? (American|British|Canadian|German|French|global|international|leading|publicly traded)\b", re.IGNORECASE),
    re.compile(r"\bwas founded in\b", re.IGNORECASE),
    re.compile(r"\bheadquartered in\b", re.IGNORECASE),
    re.compile(r"\bfounded in \d{4}\b", re.IGNORECASE),
    re.compile(r"\bspecializ(?:es?|ing) in\b.*\b(company|firm|corporation|organization)\b", re.IGNORECASE),
    re.compile(r"\b(company|firm|corporation) that\b", re.IGNORECASE),
    re.compile(r"^(I noticed|I saw|I came across|I read|Looking at your|Your company)", re.IGNORECASE),
]


def _check_wikipedia_opener(body: str, _meta: dict) -> list[str]:
    """First sentence should NOT be a company bio or generic opener."""
    sents = _sentences(body or "")
    if not sents:
        return []
    first = sents[0]
    notes: list[str] = []
    for pattern in _WIKIPEDIA_PATTERNS:
        if pattern.search(first):
            notes.append(f"Wikipedia opener: '{first[:80]}...' matches /{pattern.pattern}/")
            break
    return notes


# ---------------------------------------------------------------------------
# 3. FAIL_CATEGORY_MISMATCH
# ---------------------------------------------------------------------------

_DATA_SECURITY_TERMS = [
    re.compile(r"\b(data\s+security|cybersecurity|cyber\s+security|data\s+breach|ransomware|malware|phishing|endpoint\s+protection)\b", re.IGNORECASE),
]

def _check_category_mismatch(body: str, meta: dict) -> list[str]:
    """Flag when the email body uses vocabulary from a different product domain than the offer.

    Domain is derived from meta["offer_category"] (explicit) or inferred from
    meta["offer_lock"] keywords. Unknown domains are skipped — no false positives
    for sellers outside the known domain map.
    """
    notes: list[str] = []
    offer_lock = (meta.get("offer_lock") or "").strip()
    offer_category = (meta.get("offer_category") or "").strip() or None
    domain = infer_offer_domain(offer_lock, offer_category)
    if not domain:
        return notes

    body_lower = (body or "").lower()

    if domain == "brand_protection":
        for pattern in _DATA_SECURITY_TERMS:
            match = pattern.search(body_lower)
            if match:
                notes.append(
                    f"Category mismatch: offer domain is brand_protection but body uses "
                    f"data-security framing: '{match.group()}'"
                )
                break
    elif domain == "data_security":
        _BRAND_TERMS_RE = re.compile(
            r"\b(trademark|brand protection|counterfeit|ip enforcement)\b", re.IGNORECASE
        )
        match = _BRAND_TERMS_RE.search(body_lower)
        if match:
            notes.append(
                f"Category mismatch: offer domain is data_security but body uses "
                f"brand-protection framing: '{match.group()}'"
            )

    return notes


# ---------------------------------------------------------------------------
# 4. FAIL_EXEC_TOO_LONG
# ---------------------------------------------------------------------------

_EXEC_WORD_LIMIT = 90


def _check_exec_too_long(body: str, meta: dict) -> list[str]:
    title = (meta.get("prospect_title") or "").strip()
    if not _EXEC_TITLES_RE.search(title):
        return []
    wc = _word_count(body or "")
    if wc > _EXEC_WORD_LIMIT:
        return [f"Exec email {wc} words (title='{title}', limit={_EXEC_WORD_LIMIT})"]
    return []


# ---------------------------------------------------------------------------
# 5. FAIL_PROOF_DUMP
# ---------------------------------------------------------------------------

# Match "trusted by X, Y, and Z" or "customers include X, Y"
_TRUSTED_BY_RE = re.compile(
    r"\b(trusted by|used by|customers include|clients include|brands like|companies like)\b",
    re.IGNORECASE,
)
_COMPANY_NAME_RE = re.compile(
    # Named entities: Title-cased or ALL-CAPS words ≥ 3 chars (rough heuristic)
    r"\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,})*|[A-Z]{3,})\b"
)
_COMMON_CAPS = {
    "You", "Your", "We", "Our", "Their", "The", "This", "That", "These", "Those",
    "It", "If", "In", "On", "At", "For", "To", "And", "But", "Or", "A", "An",
    "Hi", "Dear", "Best", "Thanks", "Thank", "Hope", "Would", "Could", "Should",
    "Let", "Open", "Happy", "Glad", "Given", "Based", "When", "While", "Since",
    "With", "From", "By", "As", "Is", "Are", "Was", "Were", "Be", "Have",
    "Has", "Had", "Do", "Does", "Did", "Will", "Can", "May", "Might", "Must",
}


def _count_company_names_in_sentence(sentence: str) -> list[str]:
    """Rough count of company-name-like tokens in a sentence."""
    candidates = _COMPANY_NAME_RE.findall(sentence)
    return [c for c in candidates if c not in _COMMON_CAPS and len(c) >= 3]


def _check_proof_dump(body: str, _meta: dict) -> list[str]:
    notes: list[str] = []
    sents = _sentences(body or "")

    for sent in sents:
        # Check for trusted-by pattern with multiple names
        if _TRUSTED_BY_RE.search(sent):
            names = _count_company_names_in_sentence(sent)
            if len(names) >= 2:
                notes.append(f"Proof dump via 'trusted by' pattern: '{sent[:100]}'")
            continue

        # Check for 3+ company-name-like tokens in one sentence
        names = _count_company_names_in_sentence(sent)
        if len(names) >= 4:  # allow up to 3 (e.g., Our + Product + Company)
            notes.append(f"Proof dump: {len(names)} capitalized tokens in one sentence: '{sent[:100]}'")

    return notes


# ---------------------------------------------------------------------------
# 6. FAIL_WEAK_CTA
# ---------------------------------------------------------------------------

_WEAK_CTA_RE = re.compile(r"\b(worth a look|not a priority)\b", re.IGNORECASE)


def _check_weak_cta(body: str, meta: dict) -> list[str]:
    """Weak CTAs only allowed in specific presets for non-exec personas."""
    match = _WEAK_CTA_RE.search(body or "")
    if not match:
        return []

    preset = (meta.get("preset_id") or "").strip().lower()
    title = (meta.get("prospect_title") or "").strip()
    is_exec = _EXEC_TITLES_RE.search(title) is not None
    is_allowed_preset = preset in _WEAK_CTA_PRESETS
    phrase = match.group().strip().lower()

    if "worth a look" in phrase and "not a priority" in phrase and (preset == "straight_shooter" or is_exec):
        reason = "exec persona" if is_exec else "preset 'straight_shooter'"
        return ["Weak CTA phrase 'Worth a look / Not a priority?' not allowed for " + reason]

    if not is_allowed_preset or is_exec:
        reason = "exec persona" if is_exec else f"preset '{preset}' not in allowed set {_WEAK_CTA_PRESETS}"
        return [f"Weak CTA '{match.group()}' not allowed for {reason}"]
    return []


# ---------------------------------------------------------------------------
# 7. FAIL_REPETITION
# ---------------------------------------------------------------------------

_REPETITION_NGRAM_N = 3
_REPETITION_NGRAM_THRESHOLD = 3  # max allowed repeats of any trigram


def _check_repetition(body: str, _meta: dict) -> list[str]:
    notes: list[str] = []

    # Check verbatim sentence repetition
    sents = _sentences(body or "")
    seen: set[str] = set()
    for sent in sents:
        normalized = " ".join(sent.lower().split())
        if normalized in seen and len(normalized) > 10:
            notes.append(f"Verbatim sentence repeated: '{sent[:80]}'")
        seen.add(normalized)

    # Check trigram repetition
    max_ngram = _max_ngram_repetition(body, n=_REPETITION_NGRAM_N)
    if max_ngram > _REPETITION_NGRAM_THRESHOLD:
        notes.append(f"Trigram repeat count {max_ngram} > threshold {_REPETITION_NGRAM_THRESHOLD}")

    return notes


# ---------------------------------------------------------------------------
# 8. FAIL_DOUBLE_GREETING
# ---------------------------------------------------------------------------

def _check_double_greeting(body: str, _meta: dict) -> list[str]:
    """Detect duplicate greeting cues in first 12 tokens (e.g., 'Hi Alex, Hello ...')."""
    tokens = re.findall(r"[A-Za-z0-9']+", body or "")
    lower = [token.lower() for token in tokens[:12]]
    if len(lower) < 2:
        return []
    if lower[0] not in _GREETING_TOKENS:
        return []
    for token in lower[1:]:
        if token in _GREETING_TOKENS:
            snippet = " ".join(tokens[:12])
            return [f"Double greeting in first 12 tokens: '{snippet}'"]
    return []


# ---------------------------------------------------------------------------
# 9. FAIL_FRAGMENT
# ---------------------------------------------------------------------------

def _check_fragment(body: str, _meta: dict) -> list[str]:
    """Detect abrupt fragment endings or unmatched parentheses."""
    notes: list[str] = []
    text = (body or "").strip()

    if _has_fragment_ending(text):
        tail = text[-60:] if len(text) > 60 else text
        notes.append(f"Fragment ending detected: '...{tail}'")

    # Unmatched parentheses
    opens = text.count("(")
    closes = text.count(")")
    if opens != closes:
        notes.append(f"Unmatched parentheses: {opens} '(' vs {closes} ')'")

    return notes


# ---------------------------------------------------------------------------
# Required-fields check (not a fail tag — informational)
# ---------------------------------------------------------------------------

def _has_required_fields(body: str, meta: dict) -> dict[str, bool]:
    body_lower = (body or "").lower()
    prospect_name = (meta.get("prospect_name") or "").strip()
    prospect_first = prospect_name.split()[0] if prospect_name else ""
    company = (meta.get("prospect_company") or "").strip()
    offer = (meta.get("offer_lock") or "").strip()
    cta = (meta.get("cta_offer_lock") or "").strip()

    return {
        "prospect_name": bool(prospect_first and prospect_first.lower() in body_lower),
        "company": bool(company and company.lower() in body_lower),
        "offer": bool(offer and any(kw.lower() in body_lower for kw in offer.split()[:3] if len(kw) > 3)),
        "cta": bool(cta and len(cta) >= 5 and cta[:10].lower() in body_lower[:len(body_lower)]),
    }


# ---------------------------------------------------------------------------
# Public API — scorecard()
# ---------------------------------------------------------------------------

FAIL_TAGS = [
    "FAIL_PROSPECT_OWNS_OFFER",
    "FAIL_WIKIPEDIA_OPENER",
    "FAIL_CATEGORY_MISMATCH",
    "FAIL_EXEC_TOO_LONG",
    "FAIL_PROOF_DUMP",
    "FAIL_WEAK_CTA",
    "FAIL_REPETITION",
    "FAIL_DOUBLE_GREETING",
    "FAIL_FRAGMENT",
]

_DETECTORS: dict[str, Any] = {
    "FAIL_PROSPECT_OWNS_OFFER": _check_prospect_owns_offer,
    "FAIL_WIKIPEDIA_OPENER": _check_wikipedia_opener,
    "FAIL_CATEGORY_MISMATCH": _check_category_mismatch,
    "FAIL_EXEC_TOO_LONG": _check_exec_too_long,
    "FAIL_PROOF_DUMP": _check_proof_dump,
    "FAIL_WEAK_CTA": _check_weak_cta,
    "FAIL_REPETITION": _check_repetition,
    "FAIL_DOUBLE_GREETING": _check_double_greeting,
    "FAIL_FRAGMENT": _check_fragment,
}


def scorecard(case_id: str, body: str, meta: dict) -> dict[str, Any]:
    """Run all deterministic checks and return a structured scorecard.

    Args:
        case_id: Unique identifier for this email case.
        body:    The email body text to evaluate.
        meta:    Dict with keys: prospect_company, prospect_name, prospect_title,
                 offer_lock, preset_id, cta_offer_lock.

    Returns:
        {
            case_id: str,
            pass: bool,
            fail_tags: list[str],
            word_count: int,
            has_required_fields: dict[str, bool],
            notes: list[str],
        }
    """
    fail_tags: list[str] = []
    notes: list[str] = []

    for tag, detector in _DETECTORS.items():
        evidence = detector(body, meta)
        if evidence:
            fail_tags.append(tag)
            notes.extend(evidence)

    required = _has_required_fields(body, meta)

    return {
        "case_id": case_id,
        "pass": len(fail_tags) == 0,
        "fail_tags": fail_tags,
        "word_count": _word_count(body),
        "has_required_fields": required,
        "notes": notes,
    }
