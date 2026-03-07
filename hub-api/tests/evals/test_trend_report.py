from __future__ import annotations

from evals.judge.trend_report import _current_vs_previous, _most_regressed_cases, _rising_failure_flags


def test_rising_failure_flags_and_case_regressions() -> None:
    previous = {
        "candidate_id": "prev",
        "overall_mean": 4.2,
        "relevance_mean": 4.1,
        "credibility_mean": 4.3,
        "overclaim_fail_count": 0,
        "pass_rate": 0.9,
        "failure_signal_counts": {
            "filler_padding_present": 1,
            "verbosity_padding_detected": 1,
            "clarity_violation_present": 0,
            "clarity_violation_detected": 0,
            "judge_pandering_detected": 0,
        },
        "cases": [
            {
                "id": "lc_001",
                "overall": 4.5,
                "relevance": 4.0,
                "credibility": 4.5,
                "pass_fail": "pass",
                "body_snippet": "prev snippet",
                "rationale": "prev rationale",
            },
            {
                "id": "lc_002",
                "overall": 4.2,
                "relevance": 4.0,
                "credibility": 4.2,
                "pass_fail": "pass",
                "body_snippet": "prev snippet 2",
                "rationale": "prev rationale 2",
            },
        ],
    }
    current = {
        "candidate_id": "curr",
        "overall_mean": 4.0,
        "relevance_mean": 3.9,
        "credibility_mean": 4.0,
        "overclaim_fail_count": 2,
        "pass_rate": 0.8,
        "failure_signal_counts": {
            "filler_padding_present": 3,
            "verbosity_padding_detected": 4,
            "clarity_violation_present": 1,
            "clarity_violation_detected": 2,
            "judge_pandering_detected": 0,
        },
        "cases": [
            {
                "id": "lc_001",
                "overall": 3.8,
                "relevance": 3.6,
                "credibility": 3.9,
                "pass_fail": "fail",
                "body_snippet": "curr snippet",
                "rationale": "curr rationale",
            },
            {
                "id": "lc_002",
                "overall": 4.1,
                "relevance": 3.9,
                "credibility": 4.1,
                "pass_fail": "pass",
                "body_snippet": "curr snippet 2",
                "rationale": "curr rationale 2",
            },
        ],
    }

    rising = _rising_failure_flags(current=current, previous=previous)
    assert rising
    assert rising[0]["signal"] == "verbosity_padding_detected"
    assert rising[0]["delta"] == 3

    regressed = _most_regressed_cases(current=current, previous=previous)
    assert regressed
    assert regressed[0]["id"] == "lc_001"
    assert regressed[0]["pass_fail_transition"] == "pass->fail"

    delta = _current_vs_previous(current=current, previous=previous)
    metrics = {row["metric"]: row for row in delta["metrics"]}
    assert metrics["overall_mean"]["delta"] == -0.2
    assert metrics["overclaim_fail_count"]["delta"] == 2
