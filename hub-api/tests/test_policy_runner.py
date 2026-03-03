"""Unit tests for policy_runner.run() and aggregate_versions()."""

from __future__ import annotations

import pytest

from email_generation.policies import RuleResult, ViolationReport, aggregate_versions, run
from email_generation.policies.policy_runner import POLICY_VERSION


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_session(
    *,
    first_name: str = "Alex",
    offer_lock: str = "Acme Shield Pro",
    cta_lock: str = "Open to a 15-min call to share a quick teardown and a recommended enforcement workflow? Worth a look / Not a priority?",
    company_name: str = "SellerCo",
    research_text: str = "",
) -> dict:
    return {
        "prospect": {"name": f"{first_name} Doe", "title": "VP Sales", "company": "Acme"},
        "prospect_first_name": first_name,
        "offer_lock": offer_lock,
        "cta_lock_effective": cta_lock,
        "company_context": {"company_name": company_name, "company_notes": ""},
        "research_text_raw": research_text,
        "research_text": research_text,
        "allowed_facts": [],
        "generation_plan": {},
    }


def _make_sliders(length: int = 50) -> dict:
    return {
        "tone_formal_casual": 50,
        "framing_problem_outcome": 50,
        "length_short_long": length,
        "stance_bold_diplomatic": 50,
    }


GOOD_CTA = "Open to a 15-min call to share a quick teardown and a recommended enforcement workflow? Worth a look / Not a priority?"

GOOD_BODY = (
    f"Hi Alex, counterfeit enforcement queues at Acme often stall when detection and action workflows drift apart. "
    f"Acme Shield Pro helps your team detect risky patterns, prioritize high-impact cases, and route follow-up actions without losing context. "
    f"In week one we run a focused sweep and hand over a prioritized enforcement workflow by risk tier.\n\n{GOOD_CTA}"
)

GOOD_DRAFT = f"Subject: Reduce Counterfeit Risk at Acme with Acme Shield Pro\nBody:\n{GOOD_BODY}"


# ---------------------------------------------------------------------------
# aggregate_versions
# ---------------------------------------------------------------------------


def test_aggregate_versions_returns_all_keys():
    versions = aggregate_versions()
    expected_keys = {"policy_runner", "greeting", "cta", "offer_lock", "leakage", "claims", "length"}
    assert expected_keys == set(versions.keys())


def test_aggregate_versions_values_are_strings():
    versions = aggregate_versions()
    for key, value in versions.items():
        assert isinstance(value, str), f"{key} version should be str"
        assert value, f"{key} version should not be empty"


def test_aggregate_versions_policy_runner_version():
    versions = aggregate_versions()
    assert versions["policy_runner"] == POLICY_VERSION


# ---------------------------------------------------------------------------
# ViolationReport structure
# ---------------------------------------------------------------------------


def test_run_returns_violation_report():
    session = _make_session()
    report = run(GOOD_DRAFT, session, _make_sliders())
    assert isinstance(report, ViolationReport)


def test_run_report_has_rule_results():
    session = _make_session()
    report = run(GOOD_DRAFT, session, _make_sliders())
    assert isinstance(report.rules, list)
    assert len(report.rules) > 0
    for rule in report.rules:
        assert isinstance(rule, RuleResult)


def test_run_report_version_snapshot_keys():
    session = _make_session()
    report = run(GOOD_DRAFT, session, _make_sliders())
    expected = set(aggregate_versions().keys())
    assert set(report.policy_version_snapshot.keys()) == expected


def test_run_report_all_violations_is_flat_list():
    session = _make_session()
    report = run(GOOD_DRAFT, session, _make_sliders())
    assert isinstance(report.all_violations, list)
    assert all(isinstance(v, str) for v in report.all_violations)


def test_run_report_violation_codes_are_deduplicated():
    session = _make_session()
    report = run(GOOD_DRAFT, session, _make_sliders())
    assert len(report.violation_codes) == len(set(report.violation_codes))


# ---------------------------------------------------------------------------
# Greeting violations
# ---------------------------------------------------------------------------


def test_greeting_missing_detected():
    draft = "Subject: Test\nBody:\nAcme Shield Pro helps teams reduce risk.\n\n" + GOOD_CTA
    session = _make_session()
    report = run(draft, session, _make_sliders())
    rule = next(r for r in report.rules if r.rule_name == "greeting")
    assert not rule.passed
    assert "greeting_missing_or_invalid" in rule.violations


def test_greeting_first_name_mismatch_detected():
    draft = (
        f"Subject: Test\nBody:\nHi Bob, Acme Shield Pro helps Acme reduce risk. "
        f"We run a focused sweep and hand over a prioritized enforcement workflow by risk tier.\n\n{GOOD_CTA}"
    )
    session = _make_session()
    report = run(draft, session, _make_sliders())
    rule = next(r for r in report.rules if r.rule_name == "greeting")
    assert not rule.passed
    assert "greeting_first_name_mismatch" in rule.violations


def test_no_greeting_violation_when_prospect_has_no_name():
    """Greeting check is skipped when neither prospect_first_name nor prospect.name is set."""
    session = _make_session(first_name="")
    session["prospect"] = {"name": "", "title": "VP Sales", "company": "Acme"}
    draft = f"Subject: Test\nBody:\nAcme Shield Pro helps teams.\n\n{GOOD_CTA}"
    report = run(draft, session, _make_sliders())
    rule = next(r for r in report.rules if r.rule_name == "greeting")
    assert rule.passed


# ---------------------------------------------------------------------------
# CTA violations
# ---------------------------------------------------------------------------


def test_cta_absent_detected():
    draft = (
        "Subject: Test\nBody:\nHi Alex, Acme Shield Pro helps teams reduce counterfeit risk. "
        "We run a focused sweep and hand over a prioritized enforcement workflow by risk tier.\n\nLet me know if you want to chat."
    )
    session = _make_session()
    report = run(draft, session, _make_sliders())
    rule = next(r for r in report.rules if r.rule_name == "cta")
    assert not rule.passed
    assert "cta_lock_not_used_exactly_once" in rule.violations


# ---------------------------------------------------------------------------
# Leakage violations
# ---------------------------------------------------------------------------


def test_leakage_term_detected():
    draft = (
        f"Subject: Test\nBody:\nHi Alex, we used openai to generate content with Acme Shield Pro. "
        f"We run a focused sweep and hand over a prioritized enforcement workflow by risk tier.\n\n{GOOD_CTA}"
    )
    session = _make_session()
    report = run(draft, session, _make_sliders())
    rule = next(r for r in report.rules if r.rule_name == "leakage")
    assert not rule.passed
    leakage_violations = [v for v in rule.violations if v.startswith("internal_leakage_term:")]
    assert leakage_violations


# ---------------------------------------------------------------------------
# Offer lock violations
# ---------------------------------------------------------------------------


def test_offer_lock_missing_detected():
    draft = (
        "Subject: Reduce Risk\nBody:\nHi Alex, counterfeit exposure is rising across the industry. "
        "We help brands act faster on enforcement.\n\n" + GOOD_CTA
    )
    session = _make_session()
    report = run(draft, session, _make_sliders())
    rule = next(r for r in report.rules if r.rule_name == "offer_lock")
    assert not rule.passed
    assert "offer_lock_missing" in rule.violations


# ---------------------------------------------------------------------------
# Claims violations
# ---------------------------------------------------------------------------


def test_statistical_claim_detected():
    draft = (
        f"Subject: Test\nBody:\nHi Alex, our approach delivers 40% reduction in counterfeit incidents with Acme Shield Pro. "
        f"We run a focused sweep and hand over a prioritized enforcement workflow by risk tier.\n\n{GOOD_CTA}"
    )
    session = _make_session()
    report = run(draft, session, _make_sliders())
    rule = next(r for r in report.rules if r.rule_name == "claims")
    assert not rule.passed
    assert "unsubstantiated_statistical_claim" in rule.violations


def test_statistical_claim_allowed_when_in_company_notes():
    """Numeric claims are only allowed when present in company_notes (extracted as numeric set)."""
    draft = (
        f"Subject: Test\nBody:\nHi Alex, our approach delivers 40% reduction in counterfeit incidents with Acme Shield Pro. "
        f"We run a focused sweep and hand over a prioritized enforcement workflow by risk tier.\n\n{GOOD_CTA}"
    )
    session = _make_session()
    # Put the claim in company_notes so it's extracted by extract_allowed_numeric_claims
    session["company_context"]["company_notes"] = "Clients see 40% reduction in counterfeit incidents."
    report = run(draft, session, _make_sliders())
    rule = next(r for r in report.rules if r.rule_name == "claims")
    assert rule.passed, f"Claim in company_notes should pass. Got: {rule.violations}"


# ---------------------------------------------------------------------------
# Length violations
# ---------------------------------------------------------------------------


def test_length_too_short_detected():
    draft = f"Subject: Test\nBody:\nHi Alex, Acme Shield Pro.\n\n{GOOD_CTA}"
    session = _make_session()
    report = run(draft, session, _make_sliders(length=50))
    rule = next(r for r in report.rules if r.rule_name == "length")
    assert not rule.passed
    assert any("length_out_of_range" in v for v in rule.violations)


# ---------------------------------------------------------------------------
# Clean draft passes all rules
# ---------------------------------------------------------------------------


def test_good_draft_passes_all_rules():
    session = _make_session()
    report = run(GOOD_DRAFT, session, _make_sliders())
    for rule in report.rules:
        assert rule.passed, f"Rule '{rule.rule_name}' should pass but got: {rule.violations}"
    assert report.passed


def test_report_session_id_propagated():
    session = _make_session()
    report = run(GOOD_DRAFT, session, _make_sliders(), session_id="test-session-123")
    assert report.session_id == "test-session-123"


def test_report_repair_count_propagated():
    session = _make_session()
    report = run(GOOD_DRAFT, session, _make_sliders(), repair_count=3)
    assert report.repair_count == 3


# ---------------------------------------------------------------------------
# Resilience: malformed draft does not raise
# ---------------------------------------------------------------------------


def test_malformed_draft_does_not_raise():
    session = _make_session()
    report = run("", session, _make_sliders())
    assert isinstance(report, ViolationReport)
    assert not report.passed


def test_missing_session_keys_does_not_raise():
    # Minimal session with only required keys
    session = {"offer_lock": "Acme Shield Pro"}
    report = run(GOOD_DRAFT, session, _make_sliders())
    assert isinstance(report, ViolationReport)
