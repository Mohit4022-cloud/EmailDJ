from __future__ import annotations

from evals.ci_gate import evaluate_ci_gate, render_summary


def _report(
    *,
    hard_fail_payloads: list[str] | None = None,
    regressed_payloads: list[str] | None = None,
    c0_rate: float = 0.6,
) -> dict:
    hard_fail_payloads = hard_fail_payloads or []
    regressed_payloads = regressed_payloads or []
    return {
        "payload_count": 5,
        "overall_pass_rate": 0.0,
        "stage_pass_rates": {"ONE_LINER_COMPRESSOR": c0_rate},
        "payload_results": [
            {"payload_id": f"emaildj_0{index}", "hard_fail_triggered": f"emaildj_0{index}" in hard_fail_payloads}
            for index in range(1, 6)
        ],
        "regression_vs_golden": {
            "regressed": regressed_payloads,
            "improved": [],
            "unchanged": [],
            "net_delta": -len(regressed_payloads),
        }
        if regressed_payloads
        else None,
    }


def test_no_golden_hard_fail_is_advisory() -> None:
    result = evaluate_ci_gate(
        _report(hard_fail_payloads=["emaildj_02"]),
        report_path="backend/evals/reports/ci_emaildj.json",
        golden_present=False,
    )

    assert result["passed"] is True
    assert result["gate_mode"] == "advisory_no_golden"
    assert result["hard_fail_payloads"] == ["emaildj_02"]
    assert result["warnings"] == ["hard_fail_triggered without golden baseline; advisory only"]
    assert result["failures"] == []


def test_golden_hard_fail_blocks() -> None:
    result = evaluate_ci_gate(
        _report(hard_fail_payloads=["emaildj_01"]),
        report_path="backend/evals/reports/ci_emaildj_golden.json",
        golden_present=True,
    )

    assert result["passed"] is False
    assert result["gate_mode"] == "golden_regression"
    assert "hard_fail_triggered on emaildj payloads" in result["failures"]


def test_regression_vs_golden_blocks() -> None:
    result = evaluate_ci_gate(
        _report(regressed_payloads=["emaildj_03"]),
        report_path="backend/evals/reports/ci_emaildj_golden.json",
        golden_present=True,
    )

    assert result["passed"] is False
    assert result["regressed_payloads"] == ["emaildj_03"]
    assert "regression_vs_golden detected" in result["failures"]


def test_no_golden_one_liner_floor_is_advisory() -> None:
    result = evaluate_ci_gate(
        _report(c0_rate=0.4),
        report_path="backend/evals/reports/ci_emaildj.json",
        golden_present=False,
    )

    assert result["passed"] is True
    assert "ONE_LINER_COMPRESSOR pass rate below 0.6 without golden baseline; advisory only" in result["warnings"]


def test_golden_one_liner_floor_blocks() -> None:
    result = evaluate_ci_gate(
        _report(c0_rate=0.4),
        report_path="backend/evals/reports/ci_emaildj_golden.json",
        golden_present=True,
    )

    assert result["passed"] is False
    assert "ONE_LINER_COMPRESSOR pass rate below 0.6" in result["failures"]


def test_summary_names_gate_mode_and_warnings() -> None:
    result = evaluate_ci_gate(
        _report(hard_fail_payloads=["emaildj_02"]),
        report_path="backend/evals/reports/ci_emaildj.json",
        golden_present=False,
    )

    summary = render_summary(result)

    assert "Gate mode: advisory_no_golden" in summary
    assert "Hard-fail payloads: emaildj_02" in summary
    assert "Warnings:" in summary
