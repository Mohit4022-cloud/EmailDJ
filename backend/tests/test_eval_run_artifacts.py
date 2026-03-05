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
