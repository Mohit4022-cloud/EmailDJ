from __future__ import annotations

from dataclasses import dataclass

RUBRIC_VERSION = "enterprise_outbound_v1"

CRITERIA = (
    "relevance_to_prospect",
    "clarity_and_structure",
    "credibility_no_overclaim",
    "personalization_quality",
    "cta_quality",
    "tone_match",
    "conciseness_signal_density",
    "value_prop_specificity",
)

CRITERIA_WEIGHTS: dict[str, float] = {
    "relevance_to_prospect": 0.18,
    "clarity_and_structure": 0.12,
    "credibility_no_overclaim": 0.20,
    "personalization_quality": 0.14,
    "cta_quality": 0.12,
    "tone_match": 0.10,
    "conciseness_signal_density": 0.07,
    "value_prop_specificity": 0.07,
}

AUTO_FAIL_FLAGS = {
    "auto_fail_pii_leakage",
    "auto_fail_bribery_or_gift",
    "auto_fail_guaranteed_outcome",
    "auto_fail_policy_or_compliance_risk",
}

PASS_THRESHOLD_OVERALL = 3.8
PASS_THRESHOLD_CREDIBILITY = 4.2

ALL_FLAGS = (
    "auto_fail_pii_leakage",
    "auto_fail_bribery_or_gift",
    "auto_fail_guaranteed_outcome",
    "auto_fail_policy_or_compliance_risk",
    "judge_pandering_detected",
    "verbosity_padding_detected",
    "insufficient_personalization",
    "weak_cta",
    "tone_mismatch",
    "possible_hallucination",
)


@dataclass(frozen=True)
class JudgeConfig:
    model: str
    mode: str
    sample_count: int
    secondary_model: str | None = None


def weighted_overall(scores: dict[str, int]) -> float:
    total = 0.0
    for criterion, weight in CRITERIA_WEIGHTS.items():
        total += float(scores.get(criterion, 0)) * weight
    return round(total, 4)


def should_pass(scores: dict[str, int], overall: float, flags: list[str]) -> bool:
    if any(flag in AUTO_FAIL_FLAGS for flag in flags):
        return False
    if overall < PASS_THRESHOLD_OVERALL:
        return False
    credibility = float(scores.get("credibility_no_overclaim", 0))
    if credibility < PASS_THRESHOLD_CREDIBILITY:
        return False
    return True

