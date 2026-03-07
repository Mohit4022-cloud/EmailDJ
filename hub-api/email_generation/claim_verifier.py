"""Claim verification helpers — shim re-exporting from policies/claims_policy.py.

All logic has moved to email_generation.policies.claims_policy.
This module re-exports all original names for backward compatibility.
"""

from __future__ import annotations

from email_generation.policies.claims_policy import (
    extract_allowed_claims,
    extract_allowed_numeric_claims,
    find_unverified_claims,
    find_specific_sounding_vagueness,
    has_unverified_claims,
    has_specific_sounding_vagueness,
    merge_claim_sources,
    rewrite_specific_sounding_vagueness,
    rewrite_unverified_claims,
)

__all__ = [
    "extract_allowed_claims",
    "extract_allowed_numeric_claims",
    "find_unverified_claims",
    "find_specific_sounding_vagueness",
    "has_unverified_claims",
    "has_specific_sounding_vagueness",
    "merge_claim_sources",
    "rewrite_specific_sounding_vagueness",
    "rewrite_unverified_claims",
]
