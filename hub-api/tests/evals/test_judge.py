from __future__ import annotations

from evals.judge.client import JudgeClient, JudgeRuntime
from evals.judge.reliability import calibration_metrics, deterministic_order_swap
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
    first = deterministic_order_swap("lc_001")
    second = deterministic_order_swap("lc_001")
    assert first == second


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

