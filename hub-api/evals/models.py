from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


REQUIRED_VIOLATION_CODES = (
    "GREET_FULL_NAME",
    "GREET_MISSING",
    "OFFER_MISSING",
    "OFFER_DRIFT",
    "CTA_MISMATCH",
    "CTA_NOT_FINAL",
    "FORBIDDEN_OTHER_PRODUCT",
    "RESEARCH_INJECTION_FOLLOWED",
    "INTERNAL_LEAKAGE",
    "UNSUPPORTED_OBJECTIVE_CLAIM",
)


@dataclass
class EvalExpected:
    must_include: list[str]
    must_not_include: list[str]
    greeting_first_name: str


@dataclass
class EvalCase:
    id: str
    tags: list[str]
    prospect: dict[str, str]
    seller: dict[str, str]
    offer_lock: str
    cta_lock: str
    cta_type: str | None
    style_profile: dict[str, float]
    research_text: str
    other_products: list[str]
    expected: EvalExpected
    approved_proof_points: list[str] = field(default_factory=list)


@dataclass
class Violation:
    code: str
    reason: str
    snippet: str = ""


@dataclass
class EvalResult:
    id: str
    tags: list[str]
    passed: bool
    duration_ms: int
    mode: str
    subject: str
    body: str
    draft: str
    violations: list[Violation]
    generation_meta: dict[str, Any] = field(default_factory=dict)
    judge: dict[str, Any] = field(default_factory=dict)
    actionable_feedback: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


@dataclass
class ScorecardSummary:
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    violation_count: int
    failure_count_by_code: dict[str, int]
    greeting_pass_rate: float
    offer_binding_pass_rate: float
    cta_lock_pass_rate: float
    research_containment_pass_rate: float
    internal_leakage_pass_rate: float
    claim_safety_pass_rate: float
    provider_source: str = "provider_stub"
    failure_bucket_counts: dict[str, int] = field(default_factory=dict)
    transport_failure_count: int = 0
    route_pass_fail_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    preset_pass_fail_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    top_violation_codes: dict[str, int] = field(default_factory=dict)
    required_field_miss_count: int = 0
    under_length_miss_count: int = 0
    claims_policy_intervention_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JudgeSummary:
    enabled: bool
    model: str
    model_version: str
    mode: str
    schema_version: str
    evaluated_cases: int
    skipped_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    mean_overall: float
    mean_relevance: float
    mean_credibility: float
    overclaim_fail_count: int
    failure_count_by_flag: dict[str, int]
    prompt_contract_hash: str
    threshold_overall: float = 0.0
    threshold_credibility: float = 0.0
    cache_hits: int = 0
    cache_lookups: int = 0
    cache_hit_rate: float = 0.0
    calibration_examples: int = 0
    calibration_pass_fail_agreement: float | None = None
    calibration_score_rank_correlation: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
