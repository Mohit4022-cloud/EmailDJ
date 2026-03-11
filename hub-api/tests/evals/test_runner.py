from __future__ import annotations

from evals.models import EvalResult, Violation
from evals.runner import _compute_summary, _failure_bucket_for_error


def test_failure_bucket_for_transport_error() -> None:
    bucket = _failure_bucket_for_error("all_cascade_providers_failed:openai,anthropic,groq")
    assert bucket == "transport_or_provider"


def test_compute_summary_preserves_external_provider_on_transport_failures() -> None:
    result = EvalResult(
        id="lc_001",
        tags=["offer_binding"],
        passed=False,
        duration_ms=12,
        mode="real",
        subject="",
        body="",
        draft="",
        generation_meta={
            "provider_source": "external_provider",
            "route": "generate",
            "failure_bucket": "transport_or_provider",
        },
        violations=[Violation(code="OFFER_MISSING", reason="Pipeline error: all_cascade_providers_failed:openai,anthropic,groq")],
        error="all_cascade_providers_failed:openai,anthropic,groq",
    )

    summary, top_failures = _compute_summary([result])

    assert summary.provider_source == "external_provider"
    assert summary.transport_failure_count == 1
    assert summary.failure_bucket_counts == {"transport_or_provider": 1}
    assert top_failures == [{"code": "OFFER_MISSING", "count": 1, "cases": ["lc_001"]}]
