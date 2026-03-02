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
# Meta-commentary patterns — sentences where the model describes the email's
# own compliance or construction (should never appear in final output)
# ---------------------------------------------------------------------------

_META_COMMENTARY_PATTERN = re.compile(
    r"\b(?:"
    r"this\s+email|"
    r"this\s+keeps|"
    r"this\s+message|"
    r"this\s+draft|"
    r"this\s+outreach|"
    r"as\s+requested|"
    r"per\s+your\s+instructions?|"
    r"following\s+all|"
    r"in\s+compliance\s+with|"
    r"i\s+followed|"
    r"i've?\s+followed"
    r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Generic closer patterns — boilerplate AI sign-off / closing phrases that
# dilute credibility and should be stripped from output
# ---------------------------------------------------------------------------

_GENERIC_CLOSER_PATTERNS = [
    re.compile(r"\bi\s+look\s+forward\s+to\b", re.IGNORECASE),
    re.compile(r"\bi\s+hope\s+this\s+(?:message\s+)?finds\s+you\b", re.IGNORECASE),
    re.compile(r"\bbest\s+regards\b", re.IGNORECASE),
    re.compile(r"\bkind\s+regards\b", re.IGNORECASE),
    re.compile(r"\bthis\s+keeps\s+messaging\b", re.IGNORECASE),
    re.compile(r"\beasy\s+for\s+your\s+team\s+to\s+action\b", re.IGNORECASE),
    re.compile(r"\brelevant[,\s]+credible\b", re.IGNORECASE),
    re.compile(r"\bfeel\s+free\s+to\s+(?:reach\s+out|contact)\b", re.IGNORECASE),
    re.compile(r"\bdon'?t\s+hesitate\s+to\s+(?:contact|reach)\b", re.IGNORECASE),
]

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
