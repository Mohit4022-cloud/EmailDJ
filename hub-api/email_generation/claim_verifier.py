"""Claim verification and safe-rewrite helpers."""

from __future__ import annotations

import re
from typing import Iterable


_PERCENT_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%")
_NUMERIC_METRIC_PATTERN = re.compile(
    r"(?:#\s*)?\b\d+(?:,\d{3})*(?:\.\d+)?\s*(?:x|times|marketplaces?|accounts?|regions?|countries?)\b"
    r"|\b(?:compliance|accuracy)\s+rate\s+(?:of\s+)?\d+(?:\.\d+)?%?\b",
    re.IGNORECASE,
)
_ABSOLUTE_PATTERN = re.compile(r"\b(?:guarantee|guaranteed|ensure|ensures|always|never)\b", re.IGNORECASE)
_GENERAL_NUMBER_PATTERN = re.compile(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b")

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


def extract_allowed_claims(*sources: str | None) -> str:
    chunks = [_compact(item) for item in sources if _compact(item)]
    return " ".join(chunks).lower()


def _is_allowed(match_text: str, allowed_claim_source: str) -> bool:
    claim = _compact(match_text).lower()
    if not claim:
        return True
    return claim in allowed_claim_source


def find_unverified_claims(text: str, allowed_claim_source: str) -> list[str]:
    body = _compact(text)
    allowed = (allowed_claim_source or "").lower()
    violations: list[str] = []
    for pattern in (_PERCENT_PATTERN, _NUMERIC_METRIC_PATTERN, _ABSOLUTE_PATTERN):
        for match in pattern.finditer(body):
            snippet = _compact(match.group(0))
            if snippet and not _is_allowed(snippet, allowed):
                violations.append(snippet)
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
        return "many marketplaces"
    if "compliance rate" in text:
        return "strong compliance"
    if "accuracy rate" in text:
        return "strong accuracy"
    if "x" in text or "times" in text:
        return "meaningful improvement"
    return "significant improvement"


def rewrite_unverified_claims(text: str, allowed_claim_source: str) -> str:
    normalized = _compact(text)
    if not normalized:
        return normalized
    allowed = (allowed_claim_source or "").lower()

    def _rewrite_if_unallowed(match: re.Match[str], replacement: str) -> str:
        snippet = _compact(match.group(0))
        if _is_allowed(snippet, allowed):
            return match.group(0)
        return replacement

    rewritten = _PERCENT_PATTERN.sub(lambda m: _rewrite_if_unallowed(m, "significant"), normalized)
    rewritten = _NUMERIC_METRIC_PATTERN.sub(
        lambda m: _rewrite_if_unallowed(m, _rewrite_numeric_metric(m)),
        rewritten,
    )
    rewritten = _ABSOLUTE_PATTERN.sub(
        lambda m: m.group(0) if _is_allowed(m.group(0), allowed) else _soften_absolute(m),
        rewritten,
    )

    # Last safety pass: remove orphan numbers attached to claim language if unsupported.
    def _remove_general_number(match: re.Match[str]) -> str:
        snippet = match.group(0)
        if _is_allowed(snippet, allowed):
            return snippet
        return "many"

    if not allowed:
        rewritten = _GENERAL_NUMBER_PATTERN.sub(_remove_general_number, rewritten)

    rewritten = re.sub(r"\s{2,}", " ", rewritten).strip()
    return rewritten


def has_unverified_claims(text: str, allowed_claim_source: str) -> bool:
    return bool(find_unverified_claims(text, allowed_claim_source))


def merge_claim_sources(parts: Iterable[str | None]) -> str:
    return extract_allowed_claims(*list(parts))

