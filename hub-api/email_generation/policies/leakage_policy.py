"""Internal leakage and meta-commentary compliance policy."""

from __future__ import annotations

import re

from email_generation.text_utils import collapse_ws, contains_term, split_sentences

POLICY_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Leakage terms — must never appear in generated output
# ---------------------------------------------------------------------------

NO_LEAKAGE_TERMS = (
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
# Compliance hardening patterns
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

# Meta-commentary patterns — sentences where the model describes the email's
# own compliance or construction (should never appear in final output)
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

# Generic closer patterns — boilerplate AI sign-off / closing phrases
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
# Output helpers
# ---------------------------------------------------------------------------


def remove_generic_closers(text: str) -> str:
    """Remove sentences that match known generic AI closer/sign-off patterns."""
    sentences = split_sentences(text)
    kept = [s for s in sentences if not any(p.search(s) for p in _GENERIC_CLOSER_PATTERNS)]
    return " ".join(kept).strip()


# ---------------------------------------------------------------------------
# Violation check helpers
# ---------------------------------------------------------------------------


def check_leakage_violations(
    draft_lower: str,
    *,
    allowed_text: str = "",
) -> list[str]:
    """Check for internal tool leakage terms and meta-commentary.

    Args:
        draft_lower: Lowercased full draft text.
        allowed_text: Text where leakage terms are acceptable (seller name + offer lock).

    Returns:
        List of violation code strings.
    """
    violations: list[str] = []
    for term in NO_LEAKAGE_TERMS:
        if term in allowed_text:
            continue
        if contains_term(draft_lower, term):
            violations.append(f"internal_leakage_term:{term}")
    return violations


def check_meta_commentary(body_lines: list[str]) -> list[str]:
    """Check for meta-commentary sentences in body lines."""
    violations: list[str] = []
    for line in body_lines:
        if _META_COMMENTARY_PATTERN.search(line):
            violations.append(f"meta_commentary:{line[:80]}")
            break
    return violations


def check_cash_cta_violation(draft_lower: str) -> list[str]:
    """Check for cash-equivalent CTA patterns."""
    if _CASH_CTA_PATTERN.search(draft_lower):
        return ["cash_equivalent_cta_detected"]
    return []


def check_guaranteed_claims(draft_lower: str, research_claim_source: str) -> list[str]:
    """Check for unsubstantiated guaranteed/proven claim phrases."""
    violations: list[str] = []
    for match in _GUARANTEED_CLAIM_PATTERN.finditer(draft_lower):
        claim = collapse_ws(match.group(0))
        if claim and claim not in research_claim_source:
            violations.append(f"unsubstantiated_claim:{claim[:60]}")
            break
    return violations


def check_absolute_revenue_claims(draft_lower: str, research_claim_source: str) -> list[str]:
    """Check for unsubstantiated absolute revenue/pipeline dollar claims."""
    violations: list[str] = []
    for match in _ABSOLUTE_REVENUE_PATTERN.finditer(draft_lower):
        claim = collapse_ws(match.group(0))
        if claim and claim not in research_claim_source:
            violations.append(f"unsubstantiated_claim:{claim[:60]}")
            break
    return violations
