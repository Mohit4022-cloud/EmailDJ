"""CTA template helpers — shim re-exporting from policies/cta_policy.py.

All logic has moved to email_generation.policies.cta_policy.
This module re-exports all original names for backward compatibility.
"""

from __future__ import annotations

from email_generation.policies.cta_policy import (
    has_specific_cta_shape,
    render_cta,
    resolve_cta_lock,
)

__all__ = [
    "has_specific_cta_shape",
    "render_cta",
    "resolve_cta_lock",
]
