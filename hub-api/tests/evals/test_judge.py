from __future__ import annotations

from evals.judge.actions import derive_repair_actions
from evals.judge.client import JudgeClient, JudgeRuntime
from evals.judge.reliability import calibration_metrics, deterministic_order_swap
from evals.judge.scoring import normalize_scored_output
from evals.judge.schemas import validate_judge_output
from evals.models import EvalCase, EvalExpected


def _case() -> EvalCase:
    return EvalCase(
        id="lc_judge_001",
        tags=["judge"],
        prospect={"full_name": "Alex Karp", "title": "VP Sales", "company": "Acme"},
        seller={"company_name": "EmailDJ", "company_url": "https://emaildj.ai", "company_notes": ""},
        offer_lock="Brand Protection",
        cta_lock="Open to a 15-min chat next week?",
        cta_type="time_ask",
        style_profile={"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0},
        research_text="Acme is updating outbound process controls this quarter.",
        other_products=["Pipeline Copilot"],
        approved_proof_points=[],
        expected=EvalExpected(
            must_include=["Brand Protection", "Open to a 15-min chat next week?"],
            must_not_include=["Pipeline Copilot"],
            greeting_first_name="Alex",
        ),
    )


def test_mock_judge_scores_email() -> None:
    case = _case()
    client = JudgeClient(
        cache=None,
        runtime=JudgeRuntime(mode="mock", model="mock-judge", timeout_seconds=5.0, sample_count=3),
    )
    scored = client.evaluate_email(
        case=case,
        subject="Brand Protection for Acme",
        body=(
            "Hi Alex, Acme teams managing outbound quality often need cleaner controls. "
            "Brand Protection helps reduce risky language while preserving personalization.\n\n"
            "Open to a 15-min chat next week?"
        ),
        candidate_id="test",
        eval_mode="smoke",
    )
    assert scored["status"] == "scored"
    assert scored["sample_count"] == 3
    assert set(scored["scores"].keys()) == {
        "relevance_to_prospect",
        "clarity_and_structure",
        "credibility_no_overclaim",
        "personalization_quality",
        "cta_quality",
        "tone_match",
        "conciseness_signal_density",
        "value_prop_specificity",
    }
    assert set(scored["binary_checks"].keys()) == {
        "overclaim_present",
        "filler_padding_present",
        "clarity_violation_present",
    }
    assert scored["pass_fail"] in {"pass", "fail"}


def test_mock_pairwise_returns_winner_or_tie() -> None:
    case = _case()
    client = JudgeClient(
        cache=None,
        runtime=JudgeRuntime(mode="mock", model="mock-judge", timeout_seconds=5.0, sample_count=1),
    )
    pair = client.evaluate_pairwise(
        case=case,
        draft_a=(
            "Subject: Brand Protection for Acme\n"
            "Body:\n"
            "Hi Alex, Brand Protection helps reduce risky outbound phrasing while preserving personalization.\n\n"
            "Open to a 15-min chat next week?"
        ),
        draft_b=(
            "Subject: Generic idea\n"
            "Body:\n"
            "Hi there, we help lots of teams and can discuss.\n\n"
            "Let me know."
        ),
        eval_mode="pairwise",
    )
    assert pair["status"] == "scored"
    assert pair["winner"] in {"A", "B", "tie"}
    assert len(pair["votes"]) == 2


def test_deterministic_order_swap_is_stable() -> None:
    first = deterministic_order_swap("lc_001", seed="fixed")
    second = deterministic_order_swap("lc_001", seed="fixed")
    assert first == second
    third = deterministic_order_swap("lc_001", seed="different")
    # Seed changes should produce deterministic but potentially different order plans.
    assert isinstance(third, bool)


def test_calibration_metrics() -> None:
    expected = [
        {"id": "c1", "expected_pass_fail": "pass", "expected_overall": 4.2},
        {"id": "c2", "expected_pass_fail": "fail", "expected_overall": 1.3},
    ]
    predicted = [
        {"id": "c1", "pass_fail": "pass", "overall": 4.0},
        {"id": "c2", "pass_fail": "fail", "overall": 1.8},
    ]
    metrics = calibration_metrics(expected=expected, predicted=predicted)
    assert metrics["compared"] == 2
    assert metrics["pass_fail_agreement"] == 1.0
    assert metrics["score_rank_correlation"] is not None


def test_repair_actions_mapping() -> None:
    actions = derive_repair_actions(
        {
            "status": "scored",
            "scores": {
                "relevance_to_prospect": 2,
                "clarity_and_structure": 3,
                "credibility_no_overclaim": 2,
                "personalization_quality": 2,
                "cta_quality": 2,
                "tone_match": 2,
                "conciseness_signal_density": 3,
                "value_prop_specificity": 2,
            },
            "flags": ["auto_fail_guaranteed_outcome", "weak_cta", "tone_mismatch"],
        }
    )
    tags = {item["tag"] for item in actions}
    assert "HOOK_TOO_GENERIC" in tags
    assert "CREDIBILITY_OVERCLAIM" in tags
    assert "CTA_WEAK" in tags
    assert "TONE_MISMATCH" in tags


def test_binary_overclaim_forces_fail_even_with_high_scores() -> None:
    normalized = normalize_scored_output(
        {
            "scores": {
                "relevance_to_prospect": 5,
                "clarity_and_structure": 5,
                "credibility_no_overclaim": 5,
                "personalization_quality": 5,
                "cta_quality": 5,
                "tone_match": 5,
                "conciseness_signal_density": 5,
                "value_prop_specificity": 5,
            },
            "binary_checks": {
                "overclaim_present": True,
                "filler_padding_present": False,
                "clarity_violation_present": False,
            },
            "pass_fail": "pass",
            "overall": 5,
            "rationale_bullets": ["x", "y", "z"],
            "flags": [],
        }
    )
    assert normalized["pass_fail"] == "fail"
    assert "auto_fail_overclaim_present" in normalized["flags"]


def test_judge_schema_requires_binary_checks() -> None:
    try:
        validate_judge_output(
            {
                "scores": {
                    "relevance_to_prospect": 4,
                    "clarity_and_structure": 4,
                    "credibility_no_overclaim": 4,
                    "personalization_quality": 4,
                    "cta_quality": 4,
                    "tone_match": 4,
                    "conciseness_signal_density": 4,
                    "value_prop_specificity": 4,
                },
                "overall": 4,
                "pass_fail": "pass",
                "rationale_bullets": ["ok"],
                "flags": [],
            }
        )
        assert False, "validate_judge_output should reject missing binary_checks"
    except ValueError as exc:
        assert str(exc) == "judge_binary_checks_missing"
