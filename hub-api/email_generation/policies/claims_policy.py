"""Claim verification and safe-rewrite policy."""

from __future__ import annotations

import re
from typing import Iterable

POLICY_VERSION = "1.0.0"


_PERCENT_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%")
_NUMERIC_METRIC_PATTERN = re.compile(
    r"(?:#\s*)?\b\d+(?:,\d{3})*(?:\.\d+)?\s*(?:x|times|marketplaces?|accounts?|regions?|countries?)\b"
    r"|\b(?:compliance|accuracy)\s+rate\s+(?:of\s+)?\d+(?:\.\d+)?%?\b",
    re.IGNORECASE,
)
_ABSOLUTE_PATTERN = re.compile(r"\b(?:guarantee|guaranteed|ensure|ensures|always|never)\b", re.IGNORECASE)
_GENERAL_NUMBER_PATTERN = re.compile(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b")
_NUMERIC_SNIPPET_PATTERN = re.compile(
    r"\b\d+(?:,\d{3})*(?:\.\d+)?\+?(?:\s*(?:x|%|times?))?(?:\s+[a-zA-Z][a-zA-Z0-9&/\-]*){0,4}",
    re.IGNORECASE,
)
_NON_CLAIM_NUMERIC_CONTEXT_PATTERN = re.compile(
    r"\b(?:min|mins|minute|minutes|hour|hours|day|days|week|weeks|month|months|quarter|year|years|q[1-4]"
    r"|examples?|samples?|steps?|points?|items?|calls?|workflows?|teardowns?|audits?)\b",
    re.IGNORECASE,
)
_SPECIFIC_SOUNDING_VAGUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bhelps?\s+protect\s+growth\b", re.IGNORECASE),
    re.compile(r"\bprotects?\s+growth\b", re.IGNORECASE),
    re.compile(r"\bimproves?\s+visibility\b(?!\s+(?:into|across|for|over|on|within)\b)", re.IGNORECASE),
    re.compile(r"\bsupports?\s+expansion\b(?!\s+(?:into|across|for|of|within)\b)", re.IGNORECASE),
    re.compile(r"\breduces?\s+risk\b(?!\s+(?:for|around|from|of|across|in|within)\b)", re.IGNORECASE),
    re.compile(r"\bstrong\s+outcomes\b", re.IGNORECASE),
)

_ABSOLUTE_SOFTEN = {
    "guarantee": "aim to",
    "guaranteed": "designed to",
    "ensure": "help",
    "ensures": "helps",
    "always": "consistently",
    "never": "rarely",
}


def _compact(value: str | None) -> str:
    return " ".join(str(value or "").split())


def _normalize_numeric_snippet(value: str) -> str:
    lowered = _compact(value).lower()
    lowered = lowered.replace(",", "")
    lowered = re.sub(r"\bpercent\b", "%", lowered)
    lowered = re.sub(r"\btimes\b", "x", lowered)
    lowered = re.sub(r"[^a-z0-9%+x ]", "", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def extract_allowed_claims(*sources: str | None) -> str:
    chunks = [_compact(item) for item in sources if _compact(item)]
    return " ".join(chunks).lower()


def extract_allowed_numeric_claims(company_notes: str | None) -> set[str]:
    notes = _compact(company_notes)
    if not notes:
        return set()
    allowed: set[str] = set()
    for match in _NUMERIC_SNIPPET_PATTERN.finditer(notes):
        normalized = _normalize_numeric_snippet(match.group(0))
        if normalized:
            allowed.add(normalized)
    return allowed


def _is_allowed(match_text: str, allowed_claim_source: str) -> bool:
    claim = _compact(match_text).lower()
    if not claim:
        return True
    return claim in allowed_claim_source


def _is_allowed_numeric_claim(match_text: str, allowed_numeric_claims: set[str] | None) -> bool:
    if allowed_numeric_claims is None:
        return True
    if not allowed_numeric_claims:
        return False
    candidate = _normalize_numeric_snippet(match_text)
    if not candidate:
        return True
    for allowed in allowed_numeric_claims:
        if candidate == allowed or candidate in allowed or allowed in candidate:
            return True
    return False


def _is_non_claim_numeric(match_text: str) -> bool:
    snippet = _compact(match_text).lower()
    if not snippet:
        return True
    return _NON_CLAIM_NUMERIC_CONTEXT_PATTERN.search(snippet) is not None


def _append_once(violations: list[str], value: str) -> None:
    cleaned = _compact(value)
    if not cleaned:
        return
    if cleaned not in violations:
        violations.append(cleaned)


def find_unverified_claims(
    text: str,
    allowed_claim_source: str,
    *,
    allowed_numeric_claims: set[str] | None = None,
) -> list[str]:
    body = _compact(text)
    allowed = (allowed_claim_source or "").lower()
    violations: list[str] = []

    for pattern in (_PERCENT_PATTERN, _NUMERIC_METRIC_PATTERN):
        for match in pattern.finditer(body):
            snippet = _compact(match.group(0))
            if not snippet:
                continue
            if _is_non_claim_numeric(snippet):
                continue
            if _is_allowed_numeric_claim(snippet, allowed_numeric_claims):
                continue
            _append_once(violations, snippet)

    for match in _NUMERIC_SNIPPET_PATTERN.finditer(body):
        snippet = _compact(match.group(0))
        if not snippet:
            continue
        if not re.search(r"[a-zA-Z]", snippet):
            continue
        if _is_non_claim_numeric(snippet):
            continue
        if _is_allowed_numeric_claim(snippet, allowed_numeric_claims):
            continue
        _append_once(violations, snippet)

    for match in _ABSOLUTE_PATTERN.finditer(body):
        snippet = _compact(match.group(0))
        if snippet and not _is_allowed(snippet, allowed):
            _append_once(violations, snippet)
    return violations


def _soften_absolute(match: re.Match[str]) -> str:
    token = match.group(0)
    replacement = _ABSOLUTE_SOFTEN.get(token.lower(), "help")
    if token[0].isupper():
        return replacement.capitalize()
    return replacement


def _rewrite_numeric_metric(match: re.Match[str]) -> str:
    text = match.group(0).lower()
    if "marketplace" in text:
        return "marketplace coverage"
    if "compliance rate" in text:
        return "compliance support"
    if "accuracy rate" in text:
        return "accuracy-focused workflows"
    if "x" in text or "times" in text:
        return "workflow improvement"
    return "operational improvement"


def _rewrite_numeric_snippet(match_text: str) -> str:
    text = _compact(match_text).lower()
    if "marketplace" in text:
        return "marketplace coverage"
    if "fortune" in text:
        return "large enterprise teams"
    if "customer" in text:
        return "customer teams"
    if "roi" in text:
        return "commercial upside"
    if "compliance" in text:
        return "compliance support"
    if "accuracy" in text:
        return "accuracy-focused workflows"
    if any(token in text for token in ("accounts", "regions", "countries")):
        return "broader coverage"
    return "operational support"


def find_specific_sounding_vagueness(text: str) -> list[str]:
    body = _compact(text)
    if not body:
        return []
    violations: list[str] = []
    for pattern in _SPECIFIC_SOUNDING_VAGUE_PATTERNS:
        for match in pattern.finditer(body):
            _append_once(violations, match.group(0))
    return violations


def has_specific_sounding_vagueness(text: str) -> bool:
    return bool(find_specific_sounding_vagueness(text))


def rewrite_specific_sounding_vagueness(text: str) -> str:
    normalized = _compact(text)
    if not normalized:
        return normalized
    replacements: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"\bhelps?\s+protect\s+growth\b", re.IGNORECASE), "can help teams stay ahead of issues"),
        (re.compile(r"\bprotects?\s+growth\b", re.IGNORECASE), "can help protect momentum"),
        (re.compile(r"\bimproves?\s+visibility\b", re.IGNORECASE), "gives teams a clearer review path"),
        (re.compile(r"\bsupports?\s+expansion\b", re.IGNORECASE), "can support broader coverage"),
        (re.compile(r"\breduces?\s+risk\b", re.IGNORECASE), "can help teams catch issues earlier"),
        (re.compile(r"\bstrong\s+outcomes\b", re.IGNORECASE), "operational priorities"),
    )
    rewritten = normalized
    for pattern, replacement in replacements:
        rewritten = pattern.sub(replacement, rewritten)
    rewritten = re.sub(r"\bover\s+operational priorities\b", "at scale", rewritten, flags=re.IGNORECASE)
    rewritten = re.sub(r"\boperational priorities\s+operational priorities\b", "operational priorities", rewritten, flags=re.IGNORECASE)
    rewritten = re.sub(r"\s{2,}", " ", rewritten).strip()
    return rewritten


def rewrite_unverified_claims(
    text: str,
    allowed_claim_source: str,
    *,
    allowed_numeric_claims: set[str] | None = None,
) -> str:
    normalized = _compact(text)
    if not normalized:
        return normalized
    allowed = (allowed_claim_source or "").lower()

    def _rewrite_if_unallowed(match: re.Match[str], replacement: str) -> str:
        snippet = _compact(match.group(0))
        if _is_allowed(snippet, allowed):
            return match.group(0)
        return replacement

    rewritten = _PERCENT_PATTERN.sub(
        lambda m: m.group(0)
        if (_is_non_claim_numeric(m.group(0)) or _is_allowed_numeric_claim(m.group(0), allowed_numeric_claims))
        else "meaningful",
        normalized,
    )
    rewritten = _NUMERIC_METRIC_PATTERN.sub(
        lambda m: m.group(0)
        if (_is_non_claim_numeric(m.group(0)) or _is_allowed_numeric_claim(m.group(0), allowed_numeric_claims))
        else _rewrite_numeric_metric(m),
        rewritten,
    )
    rewritten = _NUMERIC_SNIPPET_PATTERN.sub(
        lambda m: m.group(0)
        if (
            _is_non_claim_numeric(m.group(0))
            or _is_allowed_numeric_claim(m.group(0), allowed_numeric_claims)
            or not re.search(r"[a-zA-Z]", m.group(0))
        )
        else _rewrite_numeric_snippet(m.group(0)),
        rewritten,
    )
    rewritten = _ABSOLUTE_PATTERN.sub(
        lambda m: m.group(0) if _is_allowed(m.group(0), allowed) else _soften_absolute(m),
        rewritten,
    )

    def _remove_general_number(match: re.Match[str]) -> str:
        snippet = match.group(0)
        if _is_allowed(snippet, allowed):
            return snippet
        return "many"

    if not allowed and not allowed_numeric_claims:
        rewritten = _GENERAL_NUMBER_PATTERN.sub(_remove_general_number, rewritten)

    rewritten = rewrite_specific_sounding_vagueness(rewritten)
    rewritten = re.sub(r"\s{2,}", " ", rewritten).strip()
    return rewritten


def has_unverified_claims(
    text: str,
    allowed_claim_source: str,
    *,
    allowed_numeric_claims: set[str] | None = None,
) -> bool:
    return bool(find_unverified_claims(text, allowed_claim_source, allowed_numeric_claims=allowed_numeric_claims))


def merge_claim_sources(parts: Iterable[str | None]) -> str:
    return extract_allowed_claims(*list(parts))


def check_claims_violations(
    draft: str,
    research_claim_source: str,
    *,
    allowed_numeric_claims: set[str] | None = None,
) -> list[str]:
    """Return violation codes for unverified claims in draft."""
    violations: list[str] = []
    unverified = find_unverified_claims(draft, research_claim_source, allowed_numeric_claims=allowed_numeric_claims)
    for claim in unverified:
        if re.search(r"\d|%|rate|marketplace|accuracy|compliance|x", claim, re.IGNORECASE):
            violations.append("unsubstantiated_statistical_claim")
        else:
            violations.append(f"unsubstantiated_claim:{claim[:60]}")
    return violations
