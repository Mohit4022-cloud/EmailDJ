"""Shared output-enforcement helpers — partial shim.

Most logic has moved to:
  email_generation.text_utils                — compact, split_sentences, sentence_key, etc.
  email_generation.policies.greeting_policy  — derive_first_name, enforce_first_name_greeting
  email_generation.policies.leakage_policy   — remove_generic_closers
  email_generation.policies.length_policy    — long_mode_section_pool, compose_body_without_padding_loops

This module re-exports all original names and keeps sanitize_generic_ai_opener locally.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

# ---------------------------------------------------------------------------
# Re-exports from text_utils
# ---------------------------------------------------------------------------

from email_generation.text_utils import (
    _sentence_ngrams,
    _stable_pick,
    cap_repeated_ngrams,
    compact,
    dedupe_sentence_list,
    dedupe_sentences_text,
    sentence_key,
    split_sentences,
)

# ---------------------------------------------------------------------------
# Re-exports from greeting_policy
# ---------------------------------------------------------------------------

from email_generation.policies.greeting_policy import (
    derive_first_name,
    enforce_first_name_greeting,
)

# ---------------------------------------------------------------------------
# Re-exports from leakage_policy
# ---------------------------------------------------------------------------

from email_generation.policies.leakage_policy import (
    _GENERIC_CLOSER_PATTERNS,
    remove_generic_closers,
)

# ---------------------------------------------------------------------------
# Re-exports from length_policy
# ---------------------------------------------------------------------------

from email_generation.policies.length_policy import (
    compose_body_without_padding_loops,
    long_mode_section_pool,
)

# ---------------------------------------------------------------------------
# sanitize_generic_ai_opener — kept locally (not moved to a policy)
# ---------------------------------------------------------------------------

_GENERIC_AI_OPENER_PATTERN = re.compile(
    r"^(?:(?:hi|hello)\s+[^,\n]+,\s*)?as\s+[a-z0-9&.\- ]+\s+scales\s+(?:its|their)\s+(?:enterprise\s+)?ai\s+initiatives[, ]",
    re.IGNORECASE,
)
_GENERIC_AI_RESEARCH_PATTERN = re.compile(r"scales\s+(?:its|their)\s+(?:enterprise\s+)?ai\s+initiatives", re.IGNORECASE)
_SIGNOFF_LINE_PATTERN = re.compile(r"^(?:best regards|regards|sincerely|thanks|thank you|cheers)\b", re.IGNORECASE)
_CTA_LIKE_PATTERN = re.compile(
    r"\b(?:open to|worth a look|not a priority|quick chat|quick call|"
    r"15\s*(?:-|to)?\s*(?:min|minute|minutes)|20\s*(?:-|to)?\s*(?:min|minute|minutes)|"
    r"book time|schedule|calendar)\b",
    re.IGNORECASE,
)


def sanitize_generic_ai_opener(
    text: str,
    *,
    research_text: str | None,
    hook_strategy: str | None,
    company: str | None,
    risk_surface: str | None,
) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return ""

    opener_index = -1
    for index, sentence in enumerate(sentences):
        if _GENERIC_AI_OPENER_PATTERN.search(sentence):
            opener_index = index
            break
    if opener_index < 0:
        return compact(text)

    research_ok = bool(_GENERIC_AI_RESEARCH_PATTERN.search(compact(research_text)))
    if research_ok and (hook_strategy or "").strip().lower() == "research_anchored":
        return " ".join(sentences).strip()

    account = compact(company) or "your team"
    surface = compact(risk_surface) or "your enforcement workflow"
    replacements = [
        f"Brand-risk exposure usually rises when counterfeit enforcement queues stall at {account}.",
        f"Counterfeit risk is hardest to contain when detection and action workflows drift apart in {surface}.",
        "The practical win is reducing counterfeit exposure while improving enforcement throughput.",
    ]
    sentences[opener_index] = _stable_pick(replacements, f"{account}|{surface}|{hook_strategy or ''}")
    return " ".join(sentences).strip()


def enforce_cta_last_line(
    body: str,
    *,
    cta_line: str,
) -> str:
    """Deterministically normalize body text and force a single CTA as last line.

    Steps:
    - remove signoff-like lines anywhere in the body
    - remove duplicate/near-duplicate CTA-like lines
    - collapse extra spaces and blank lines
    - append exact CTA once, as final line
    """
    cta = compact(cta_line)
    if not cta:
        return compact(body)

    normalized = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = [compact(line) for line in normalized.split("\n") if compact(line)]
    cleaned: list[str] = []
    cta_norm = cta.lower()
    for line in raw_lines:
        if _SIGNOFF_LINE_PATTERN.search(line):
            continue
        line_norm = compact(line).lower()
        if not line_norm:
            continue
        ratio = SequenceMatcher(None, cta_norm, line_norm).ratio()
        if line_norm == cta_norm:
            continue
        if ratio >= 0.88 and ("?" in line or _CTA_LIKE_PATTERN.search(line)):
            continue
        if _CTA_LIKE_PATTERN.search(line) and "?" in line:
            continue
        cleaned.append(line)

    deduped: list[str] = []
    seen: set[str] = set()
    for line in cleaned:
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(line)

    return "\n".join([*deduped, cta]).strip()


__all__ = [
    # text_utils re-exports
    "compact",
    "split_sentences",
    "sentence_key",
    "dedupe_sentence_list",
    "dedupe_sentences_text",
    "_sentence_ngrams",
    "cap_repeated_ngrams",
    "_stable_pick",
    # greeting_policy re-exports
    "derive_first_name",
    "enforce_first_name_greeting",
    # leakage_policy re-exports
    "_GENERIC_CLOSER_PATTERNS",
    "remove_generic_closers",
    # length_policy re-exports
    "long_mode_section_pool",
    "compose_body_without_padding_loops",
    # local
    "sanitize_generic_ai_opener",
    "enforce_cta_last_line",
]
