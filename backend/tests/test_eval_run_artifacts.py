from __future__ import annotations

import json

from evals.eval_run import _extract_stage_artifacts


def test_extract_stage_artifacts_preserves_failed_emitted_payload() -> None:
    raw_trace = {
        "stage_payloads": [
            {
                "stage": "CONTEXT_SYNTHESIS",
                "status": "failed",
                "error_code": "STAGE_JSON_OR_VALIDATION_FAILED",
                "artifact_status": "failed_artifact_present",
                "output": {
                    "version": "1",
                    "brief_id": "brief_1",
                    "facts_from_input": [],
                },
            }
        ]
    }

    artifacts = _extract_stage_artifacts(raw_trace)

    assert artifacts["messaging_brief"]["status"] == "failed_artifact_present"
    assert artifacts["messaging_brief"]["artifact"]["brief_id"] == "brief_1"


def test_extract_stage_artifacts_parses_failed_raw_json_when_output_missing() -> None:
    raw_trace = {
        "stage_payloads": [
            {
                "stage": "EMAIL_GENERATION",
                "status": "failed",
                "error_code": "VALIDATION_FAILED",
                "artifact_status": "failed_artifact_present",
                "raw_output": json.dumps(
                    {
                        "version": "1",
                        "subject": "RevOps workflow note",
                        "body": "Hi Jordan.\n\nOpen to a quick chat to see if this is relevant?",
                    }
                ),
            }
        ]
    }

    artifacts = _extract_stage_artifacts(raw_trace)

    assert artifacts["email_draft"]["status"] == "failed_artifact_present"
    assert artifacts["email_draft"]["artifact"]["subject"] == "RevOps workflow note"


def test_extract_stage_artifacts_preserves_stage_a_artifact_views() -> None:
    raw_trace = {
        "stage_payloads": [
            {
                "stage": "CONTEXT_SYNTHESIS",
                "status": "complete",
                "output": {"version": "1", "brief_id": "brief_1"},
                "raw_output_artifact": {"version": "1", "brief_id": "brief_1"},
                "artifact_views": {
                    "raw_stage_a_artifact": {"version": "1", "brief_id": "brief_1"},
                    "sanitized_stage_a_artifact": {"version": "1", "brief_id": "brief_1"},
                    "raw_artifact_quality": {"issue_count": 2},
                },
            }
        ]
    }

    artifacts = _extract_stage_artifacts(raw_trace)

    assert artifacts["messaging_brief"]["artifact_views"]["raw_artifact_quality"]["issue_count"] == 2
    assert artifacts["messaging_brief"]["raw_output_artifact"]["brief_id"] == "brief_1"


def test_extract_stage_artifacts_falls_back_to_raw_output_artifact_when_output_missing() -> None:
    raw_trace = {
        "stage_payloads": [
            {
                "stage": "EMAIL_REWRITE",
                "status": "failed",
                "error_code": "VALIDATION_FAILED",
                "artifact_status": "failed_artifact_present",
                "raw_output_artifact": {
                    "version": "1",
                    "preset_id": "direct",
                    "selected_angle_id": "angle_1",
                    "used_hook_ids": ["hook_1"],
                    "subject": "RevOps workflow note",
                    "body": "Hi Alex.\n\nOpen to a quick chat to see if this is relevant?",
                },
            }
        ]
    }

    artifacts = _extract_stage_artifacts(raw_trace)

    assert artifacts["rewritten_draft"]["status"] == "failed_artifact_present"
    assert artifacts["rewritten_draft"]["artifact"]["subject"] == "RevOps workflow note"
