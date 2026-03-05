from __future__ import annotations

from app.engine.tracer import Trace


def test_trace_preserves_failed_artifact_in_raw_payloads() -> None:
    trace = Trace("trace-1", "test", debug_trace_raw=True)
    trace.start_stage(stage="CONTEXT_SYNTHESIS", model="gpt-5-nano")
    trace.fail_stage_with_artifact(
        stage="CONTEXT_SYNTHESIS",
        model="gpt-5-nano",
        error_code="STAGE_JSON_OR_VALIDATION_FAILED",
        details={"codes": ["fact_placeholder_text"]},
        artifact_status="failed_artifact_present",
        output={"version": "1", "brief_id": "brief_1"},
        raw_output='{"version":"1","brief_id":"brief_1"}',
        attempt_count=2,
    )

    payload = trace.finalize(outcome={"ok": False}, write_debug=False)

    assert payload["stage_stats"][-1]["artifact_status"] == "failed_artifact_present"
    assert trace.raw_stage_payloads[-1]["output"]["brief_id"] == "brief_1"
    assert trace.raw_stage_payloads[-1]["raw_output"] == '{"version":"1","brief_id":"brief_1"}'
