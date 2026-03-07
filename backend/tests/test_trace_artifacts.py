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


def test_trace_preserves_artifact_views_for_completed_stage() -> None:
    trace = Trace("trace-2", "test", debug_trace_raw=True)
    trace.start_stage(stage="CONTEXT_SYNTHESIS", model="gpt-5-nano")
    trace.end_stage(
        stage="CONTEXT_SYNTHESIS",
        model="gpt-5-nano",
        schema_ok=True,
        output={"version": "1", "brief_id": "brief_1"},
        attempt_count=1,
        details={"raw_hygiene_issue_count": 2},
        raw_output='{"version":"1","brief_id":"brief_1"}',
        raw_output_artifact={"version": "1", "brief_id": "brief_1"},
        artifact_views={
            "raw_stage_a_artifact": {"version": "1", "brief_id": "brief_1"},
            "sanitized_stage_a_artifact": {"version": "1", "brief_id": "brief_1"},
            "sanitation_report": {"sanitation_action_counts": {"drop_fact_placeholder_text": 1}},
        },
    )

    payload = trace.finalize(outcome={"ok": True}, write_debug=False)

    assert payload["stage_stats"][-1]["raw_hygiene_issue_count"] == 2
    assert trace.raw_stage_payloads[-1]["raw_output_artifact"]["brief_id"] == "brief_1"
    assert trace.raw_stage_payloads[-1]["artifact_views"]["sanitation_report"]["sanitation_action_counts"] == {
        "drop_fact_placeholder_text": 1
    }


def test_trace_annotation_merges_details_into_completed_stage() -> None:
    trace = Trace("trace-3", "test")
    trace.start_stage(stage="EMAIL_REWRITE", model="gpt-5-nano")
    trace.end_stage(
        stage="EMAIL_REWRITE",
        model="gpt-5-nano",
        schema_ok=True,
        output={"version": "1", "subject": "x", "body": "y"},
        attempt_count=1,
    )

    trace.annotate_stage(
        stage="EMAIL_REWRITE",
        details={"preset_id": "challenger", "salvage_applied": True, "salvage_result": "passed"},
    )

    payload = trace.finalize(outcome={"ok": True}, write_debug=False)

    assert payload["stage_stats"][-1]["preset_id"] == "challenger"
    assert payload["stage_stats"][-1]["salvage_applied"] is True
    assert payload["stage_stats"][-1]["salvage_result"] == "passed"
