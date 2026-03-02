"""Shared compliance constants and helpers for CTCO validation and preset preview checks."""

from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Leakage terms — must never appear in generated output
# ---------------------------------------------------------------------------

_NO_LEAKAGE_TERMS = (
    "emaildj",
    "remix",
    "mapping",
    "template",
    "templates",
    "slider",
    "sliders",
    "prompt",
    "prompts",
    "llm",
    "llms",
    "openai",
    "gemini",
    "codex",
    "generated",
    "automation tooling",
)

# ---------------------------------------------------------------------------
# CTA detection patterns — used to identify additional/secondary CTAs
# ---------------------------------------------------------------------------

_CTA_DURATION_PATTERN = re.compile(r"\b\d+\s*(?:-|to)?\s*\d*\s*(?:min|minute|minutes)\b")

_CTA_CHANNEL_HINTS = (
    "virtual coffee",
    "call",
    "quick call",
    "meeting",
    "demo",
    "walkthrough",
    "pilot",
    "book time",
    "chat",
    "deck",
    "next week",
)

_CTA_ASK_CUES = (
    "open to",
    "are you open",
    "would you",
    "could we",
    "can we",
    "worth",
    "if useful",
    "if helpful",
    "want me to send",
    "can i send",
    "should i send",
    "happy to share",
    "happy to hop",
    "if this is on your radar",
    "if this is relevant",
)

# ---------------------------------------------------------------------------
# Compliance hardening patterns (new in Batch 3)
# ---------------------------------------------------------------------------

# Cash-equivalent CTA: gift cards, prepaid cards, cash rewards
_CASH_CTA_PATTERN = re.compile(
    r"\b(?:"
    r"gift\s+card|"
    r"amazon\s+(?:gift\s+)?card|"
    r"e-gift|"
    r"egift|"
    r"\$\s*\d+\s+gift|"
    r"cash\s+(?:reward|prize|bonus)|"
    r"gift\s+certificate|"
    r"prepaid\s+(?:card|visa)|"
    r"starbucks\s+card|"
    r"doordash\s+credit"
    r")\b",
    re.IGNORECASE,
)

# Guaranteed/proven ROI claims (unsubstantiated unless in research)
_GUARANTEED_CLAIM_PATTERN = re.compile(
    r"\b(?:guaranteed?\s+(?:results?|roi|improvement|success)|proven\s+roi)\b",
    re.IGNORECASE,
)

# Absolute revenue/pipeline dollar claims (e.g. "$2M in pipeline")
_ABSOLUTE_REVENUE_PATTERN = re.compile(
    r"\$\s*\d+(?:[KkMmBb])?\s+(?:in\s+)?(?:revenue|pipeline|savings?|value)\b",
    re.IGNORECASE,
)

# Percentage or multiplier performance claims (e.g. "40% increase", "3x faster")
_STAT_CLAIM_PATTERN = re.compile(
    r"\b\d+\s*%\s*(?:increase|improvement|lift|more|better|faster|higher|reduction|decrease)\b"
    r"|\b\d+[xX]\s+(?:more|better|faster|improvement)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Shared helper functions
# ---------------------------------------------------------------------------


def _contains_term(text_lower: str, term: str) -> bool:
    """Check if a term appears as a whole word (or phrase) in lowercase text."""
    if " " in term:
        return term in text_lower
    return re.search(rf"\b{re.escape(term)}\b", text_lower) is not None


def _word_count(text: str) -> int:
    """Count word tokens (alphanumeric + apostrophes)."""
    return len(re.findall(r"[A-Za-z0-9']+", text))


def _collapse_ws(value: str) -> str:
    """Collapse all whitespace to single spaces and strip."""
    return " ".join(value.split())
