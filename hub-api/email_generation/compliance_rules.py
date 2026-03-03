"""Shared compliance constants and helpers — shim re-exporting from policies/.

All logic has moved to:
  email_generation.policies.leakage_policy  — leakage terms + patterns
  email_generation.policies.cta_policy      — CTA detection patterns
  email_generation.text_utils               — _contains_term, _word_count, _collapse_ws

This module re-exports all original names for backward compatibility.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Re-exports from leakage_policy (keep original underscore names)
# ---------------------------------------------------------------------------

from email_generation.policies.leakage_policy import (
    NO_LEAKAGE_TERMS as _NO_LEAKAGE_TERMS,
    _CASH_CTA_PATTERN,
    _GUARANTEED_CLAIM_PATTERN,
    _ABSOLUTE_REVENUE_PATTERN,
    _STAT_CLAIM_PATTERN,
    _META_COMMENTARY_PATTERN,
    _GENERIC_CLOSER_PATTERNS,
)

# ---------------------------------------------------------------------------
# Re-exports from cta_policy (keep original underscore names)
# ---------------------------------------------------------------------------

from email_generation.policies.cta_policy import (
    _CTA_DURATION_PATTERN,
    _CTA_CHANNEL_HINTS,
    _CTA_ASK_CUES,
)

# ---------------------------------------------------------------------------
# Re-exports from text_utils (keep original underscore names)
# ---------------------------------------------------------------------------

from email_generation.text_utils import (
    contains_term as _contains_term,
    word_count as _word_count,
    collapse_ws as _collapse_ws,
)

__all__ = [
    "_NO_LEAKAGE_TERMS",
    "_CASH_CTA_PATTERN",
    "_GUARANTEED_CLAIM_PATTERN",
    "_ABSOLUTE_REVENUE_PATTERN",
    "_STAT_CLAIM_PATTERN",
    "_META_COMMENTARY_PATTERN",
    "_GENERIC_CLOSER_PATTERNS",
    "_CTA_DURATION_PATTERN",
    "_CTA_CHANNEL_HINTS",
    "_CTA_ASK_CUES",
    "_contains_term",
    "_word_count",
    "_collapse_ws",
]
