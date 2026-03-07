"""Golden scenario tests — drive policy_runner.run() against fixture JSON files.

Each fixture defines a draft, session, style_sliders, expected_violations (prefixes),
and expected_pass. Tests assert that every expected_violation code appears in the report
and that the pass/fail outcome matches.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from email_generation.policies import run

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "golden"


def _load_scenario(filename: str) -> dict[str, Any]:
    path = GOLDEN_DIR / filename
    with open(path) as fh:
        return json.load(fh)


def _all_golden_files() -> list[str]:
    return sorted(f for f in os.listdir(GOLDEN_DIR) if f.endswith(".json"))


def _violations_contain(all_violations: list[str], expected: list[str]) -> list[str]:
    """Return expected violation codes that were NOT found in actual violations.

    Matching is prefix-based: 'meta_commentary' matches 'meta_commentary:some detail'.
    """
    missing: list[str] = []
    for expected_code in expected:
        found = any(actual == expected_code or actual.startswith(f"{expected_code}:") for actual in all_violations)
        if not found:
            missing.append(expected_code)
    return missing


# ---------------------------------------------------------------------------
# Parametrized golden scenario tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename", _all_golden_files())
def test_golden_scenario(filename: str) -> None:
    scenario = _load_scenario(filename)
    scenario_id = scenario["scenario_id"]
    description = scenario["description"]

    report = run(
        draft=scenario["draft"],
        session=scenario["session"],
        style_sliders=scenario["style_sliders"],
        session_id=scenario_id,
    )

    expected_pass: bool = scenario["expected_pass"]
    expected_violations: list[str] = scenario.get("expected_violations", [])

    # 1. Pass/fail outcome
    assert report.passed == expected_pass, (
        f"[{scenario_id}] {description}\n"
        f"Expected passed={expected_pass} but got passed={report.passed}.\n"
        f"All violations: {report.all_violations}"
    )

    # 2. Each expected violation code appears in the report
    if expected_violations:
        missing = _violations_contain(report.all_violations, expected_violations)
        assert not missing, (
            f"[{scenario_id}] {description}\n"
            f"Expected violations not found: {missing}\n"
            f"All violations: {report.all_violations}"
        )

    # 3. ViolationReport structure is always valid
    assert report.policy_version_snapshot, f"[{scenario_id}] policy_version_snapshot should not be empty"
    assert isinstance(report.rules, list), f"[{scenario_id}] rules should be a list"
    assert all(isinstance(v, str) for v in report.all_violations), f"[{scenario_id}] violations should be strings"


# ---------------------------------------------------------------------------
# Specific scenario assertions
# ---------------------------------------------------------------------------


def test_greeting_missing_001() -> None:
    scenario = _load_scenario("greeting_missing_001.json")
    report = run(**{k: scenario[k] for k in ("draft", "session", "style_sliders")})
    assert not report.passed
    rule = next(r for r in report.rules if r.rule_name == "greeting")
    assert "greeting_missing_or_invalid" in rule.violations


def test_greeting_first_name_mismatch_001() -> None:
    scenario = _load_scenario("greeting_first_name_mismatch_001.json")
    report = run(**{k: scenario[k] for k in ("draft", "session", "style_sliders")})
    assert not report.passed
    rule = next(r for r in report.rules if r.rule_name == "greeting")
    assert "greeting_first_name_mismatch" in rule.violations


def test_cta_lock_absent_001() -> None:
    scenario = _load_scenario("cta_lock_absent_001.json")
    report = run(**{k: scenario[k] for k in ("draft", "session", "style_sliders")})
    assert not report.passed
    rule = next(r for r in report.rules if r.rule_name == "cta")
    assert "cta_lock_not_used_exactly_once" in rule.violations


def test_leakage_openai_001() -> None:
    scenario = _load_scenario("leakage_openai_001.json")
    report = run(**{k: scenario[k] for k in ("draft", "session", "style_sliders")})
    assert not report.passed
    rule = next(r for r in report.rules if r.rule_name == "leakage")
    assert any(v.startswith("internal_leakage_term:openai") for v in rule.violations)


def test_meta_commentary_001() -> None:
    scenario = _load_scenario("meta_commentary_001.json")
    report = run(**{k: scenario[k] for k in ("draft", "session", "style_sliders")})
    assert not report.passed
    rule = next(r for r in report.rules if r.rule_name == "leakage")
    assert any(v.startswith("meta_commentary:") for v in rule.violations)


def test_offer_lock_missing_001() -> None:
    scenario = _load_scenario("offer_lock_missing_001.json")
    report = run(**{k: scenario[k] for k in ("draft", "session", "style_sliders")})
    assert not report.passed
    rule = next(r for r in report.rules if r.rule_name == "offer_lock")
    assert "offer_lock_missing" in rule.violations


def test_offer_drift_001() -> None:
    scenario = _load_scenario("offer_drift_001.json")
    report = run(**{k: scenario[k] for k in ("draft", "session", "style_sliders")})
    assert not report.passed
    rule = next(r for r in report.rules if r.rule_name == "offer_lock")
    assert any(v in ("offer_lock_body_verbatim_missing", "offer_drift_keyword_overlap_low") for v in rule.violations)


def test_unverified_claim_stat_001() -> None:
    scenario = _load_scenario("unverified_claim_stat_001.json")
    report = run(**{k: scenario[k] for k in ("draft", "session", "style_sliders")})
    assert not report.passed
    rule = next(r for r in report.rules if r.rule_name == "claims")
    assert "unsubstantiated_statistical_claim" in rule.violations


def test_length_out_of_range_001() -> None:
    scenario = _load_scenario("length_out_of_range_001.json")
    report = run(**{k: scenario[k] for k in ("draft", "session", "style_sliders")})
    assert not report.passed
    rule = next(r for r in report.rules if r.rule_name == "length")
    assert any(v.startswith("length_out_of_range:") for v in rule.violations)


def test_golden_pass_001() -> None:
    scenario = _load_scenario("golden_pass_001.json")
    report = run(**{k: scenario[k] for k in ("draft", "session", "style_sliders")})
    assert report.passed, f"Expected no violations but got: {report.all_violations}"
    assert report.all_violations == []
