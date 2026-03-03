"""Policy runner — orchestrates all compliance policies and returns ViolationReport.

Pure function: no I/O. Each rule is wrapped in try/except for resilience.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import email_generation.policies.claims_policy as _claims_mod
import email_generation.policies.cta_policy as _cta_mod
import email_generation.policies.greeting_policy as _greeting_mod
import email_generation.policies.leakage_policy as _leakage_mod
import email_generation.policies.length_policy as _length_mod
import email_generation.policies.offer_lock_policy as _offer_mod
from email_generation.text_utils import collapse_ws

POLICY_VERSION = "1.0.0"

# Banned phrases mirrored from remix_engine._BANNED_PHRASES to keep policy_runner pure.
_BANNED_PHRASES: tuple[str, ...] = (
    "ai services",
    "ai consulting",
    "we build ai",
    "ai transformation services",
    "pipeline outcomes",
    "reply lift",
    "conversion lift",
    "measurable results",
)

_POLICY_ORDER = [
    "greeting",
    "cta",
    "offer_lock",
    "banned",
    "leakage",
    "claims",
    "length",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RuleResult:
    rule_name: str
    passed: bool
    violations: list[str]
    policy_version: str


@dataclass
class ViolationReport:
    session_id: str | None
    draft: str
    passed: bool
    rules: list[RuleResult]
    all_violations: list[str]
    violation_codes: list[str]
    policy_version_snapshot: dict[str, str]
    repair_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_subject_and_body(draft: str) -> tuple[str, str]:
    """Extract subject and body from a 'Subject: ...\nBody:\n...' formatted draft."""
    subject = ""
    body = ""
    if draft.startswith("Subject:") and "\nBody:\n" in draft:
        parts = draft.split("\nBody:\n", 1)
        subject = parts[0].removeprefix("Subject:").strip()
        body = parts[1].strip() if len(parts) > 1 else ""
    return subject, body


def _expected_first_name(session: dict[str, Any]) -> str:
    """Derive expected prospect first name from session."""
    first = str(session.get("prospect_first_name") or "").strip()
    if first:
        return _greeting_mod.derive_first_name(first)
    raw = str((session.get("prospect") or {}).get("name") or "").strip()
    return _greeting_mod.derive_first_name(raw)


def _catalog_items(value: Any) -> list[str]:
    """Coerce a product list field to a list of strings."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _offer_lock_forbidden_items(session: dict[str, Any]) -> list[str]:
    """Return competitor/other-product names that must not appear in the draft."""
    offer_lock = collapse_ws((session.get("offer_lock") or "").lower())
    company_context = session.get("company_context") or {}
    other_products = _catalog_items(company_context.get("other_products"))
    forbidden: list[str] = []
    for item in other_products:
        key = collapse_ws(item.lower())
        if not key or key == offer_lock:
            continue
        forbidden.append(item)
    return forbidden


def _dedupe(violations: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in violations:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _violation_codes(violations: list[str]) -> list[str]:
    """Strip detail suffix from violation strings to get category codes."""
    codes: list[str] = []
    seen: set[str] = set()
    for v in violations:
        code = v.split(":")[0]
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def _safe_run(rule_name: str, policy_version: str, fn: Any, *args: Any, **kwargs: Any) -> RuleResult:
    """Run a policy check function, catching exceptions for resilience."""
    try:
        violations = fn(*args, **kwargs)
        return RuleResult(
            rule_name=rule_name,
            passed=not violations,
            violations=violations,
            policy_version=policy_version,
        )
    except Exception as exc:  # noqa: BLE001
        return RuleResult(
            rule_name=rule_name,
            passed=False,
            violations=[f"{rule_name}_policy_error:{str(exc)[:80]}"],
            policy_version=policy_version,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(
    draft: str,
    session: dict[str, Any],
    style_sliders: dict[str, int],
    *,
    session_id: str | None = None,
    repair_count: int = 0,
) -> ViolationReport:
    """Run all compliance policies and return a ViolationReport.

    Pure function — no I/O. Safe to call from any context.

    Args:
        draft: Full draft text ("Subject: ...\nBody:\n...").
        session: Session dict containing prospect, offer_lock, company_context, etc.
        style_sliders: Dict with length_short_long and other slider values.
        session_id: Optional session identifier for tracing.
        repair_count: Number of repair attempts already made (for metadata).

    Returns:
        ViolationReport with all rule results and aggregated violation data.
    """
    _subject, body = _extract_subject_and_body(draft)
    draft_lower = draft.lower()
    body_lower = collapse_ws(body).lower()
    body_lines = [line.strip() for line in body.splitlines() if line.strip()]

    offer_lock = collapse_ws(session.get("offer_lock") or "")
    expected_first_name = _expected_first_name(session)
    expected_cta = str(session.get("cta_lock_effective") or "Open to a quick chat to see if this is relevant?").strip()

    seller_name = ((session.get("company_context") or {}).get("company_name") or "").lower()
    allowed_leakage_text = f"{seller_name} {offer_lock.lower()}"

    research_claim_source = _claims_mod.merge_claim_sources(
        [
            session.get("research_text_raw"),
            session.get("research_text"),
            (session.get("company_context") or {}).get("company_notes"),
            " ".join(session.get("allowed_facts") or []),
        ]
    )
    allowed_numeric_claims = _claims_mod.extract_allowed_numeric_claims(
        (session.get("company_context") or {}).get("company_notes")
    )

    rules: list[RuleResult] = []

    # Greeting
    rules.append(
        _safe_run(
            "greeting",
            _greeting_mod.POLICY_VERSION,
            _greeting_mod.check_greeting_violations,
            body,
            expected_first_name,
        )
    )

    # CTA
    rules.append(
        _safe_run(
            "cta",
            _cta_mod.POLICY_VERSION,
            _cta_mod.check_cta_violations,
            body,
            expected_cta,
        )
    )

    # Offer lock
    rules.append(
        _safe_run(
            "offer_lock",
            _offer_mod.POLICY_VERSION,
            _offer_mod.check_offer_lock_violations,
            draft_lower,
            body_lower,
            offer_lock,
        )
    )

    # Banned phrases
    rules.append(
        _safe_run(
            "banned",
            _offer_mod.POLICY_VERSION,
            _offer_mod.check_banned_phrases,
            draft_lower,
            _BANNED_PHRASES,
        )
    )

    # Leakage + meta-commentary
    def _leakage_combined(draft_lower: str, body_lines: list[str], allowed_text: str) -> list[str]:
        v = _leakage_mod.check_leakage_violations(draft_lower, allowed_text=allowed_text)
        v += _leakage_mod.check_meta_commentary(body_lines)
        v += _leakage_mod.check_cash_cta_violation(draft_lower)
        v += _leakage_mod.check_guaranteed_claims(draft_lower, research_claim_source)
        v += _leakage_mod.check_absolute_revenue_claims(draft_lower, research_claim_source)
        return v

    rules.append(
        _safe_run(
            "leakage",
            _leakage_mod.POLICY_VERSION,
            _leakage_combined,
            draft_lower,
            body_lines,
            allowed_leakage_text,
        )
    )

    # Claims
    rules.append(
        _safe_run(
            "claims",
            _claims_mod.POLICY_VERSION,
            _claims_mod.check_claims_violations,
            draft,
            research_claim_source,
            allowed_numeric_claims=allowed_numeric_claims,
        )
    )

    # Length
    def _length_check(body: str, length_short_long: int) -> list[str]:
        v = _length_mod.check_length_violation(body, length_short_long)
        return [v] if v else []

    rules.append(
        _safe_run(
            "length",
            _length_mod.POLICY_VERSION,
            _length_check,
            body,
            style_sliders.get("length_short_long", 50),
        )
    )

    all_violations = _dedupe([v for rule in rules for v in rule.violations])
    return ViolationReport(
        session_id=session_id,
        draft=draft,
        passed=not all_violations,
        rules=rules,
        all_violations=all_violations,
        violation_codes=_violation_codes(all_violations),
        policy_version_snapshot=aggregate_versions(),
        repair_count=repair_count,
    )


def aggregate_versions() -> dict[str, str]:
    """Return version snapshot for all policies without running them.

    Useful for attaching policy metadata to session or SSE done event without
    incurring the cost of running all rules.
    """
    return {
        "policy_runner": POLICY_VERSION,
        "greeting": _greeting_mod.POLICY_VERSION,
        "cta": _cta_mod.POLICY_VERSION,
        "offer_lock": _offer_mod.POLICY_VERSION,
        "leakage": _leakage_mod.POLICY_VERSION,
        "claims": _claims_mod.POLICY_VERSION,
        "length": _length_mod.POLICY_VERSION,
    }
