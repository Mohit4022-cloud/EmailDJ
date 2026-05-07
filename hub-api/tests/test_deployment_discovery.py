from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))


def test_build_discovery_payload_marks_vercel_url_as_candidate_only():
    import scripts.discover_deployment_metadata as discovery

    payload = discovery.build_discovery_payload(
        repo_slug="Mohit4022-cloud/EmailDJ",
        current_sha="4f323ae5ee8530886f267733f85c3c2061d27ca1",
        deployments=[
            {
                "id": 4614098730,
                "environment": "Preview",
                "ref": "codex/mvp-webapp-sliders",
                "sha": "4f323ae5ee8530886f267733f85c3c2061d27ca1",
                "task": "deploy",
                "created_at": "2026-05-07T20:26:54Z",
            },
            {
                "id": 4514253986,
                "environment": "Production",
                "ref": "main",
                "sha": "older-sha",
                "task": "deploy",
                "created_at": "2026-05-01T00:00:00Z",
            },
        ],
        statuses_by_deployment_id={
            "4614098730": [
                {
                    "state": "success",
                    "environment_url": "https://email-pbkwcngj2-mohits-projects-e629a988.vercel.app",
                    "target_url": "https://vercel.com/mohits-projects-e629a988/email-dj/64q2U",
                    "created_at": "2026-05-07T20:26:54Z",
                }
            ],
            "4514253986": [
                {
                    "state": "success",
                    "environment_url": "https://email-d8fx2u7jp-mohits-projects-e629a988.vercel.app",
                    "created_at": "2026-05-01T00:00:00Z",
                }
            ],
        },
        generated_at="2026-05-07T20:30:00Z",
    )

    assert payload["found"] is True
    assert payload["candidate_web_app_origin"] == "https://email-pbkwcngj2-mohits-projects-e629a988.vercel.app"
    assert payload["usable_as_web_app_origin_candidate"] is True
    assert payload["clears_launch_blockers"] is False
    assert "does not clear launch blockers" in payload["launch_blocker_note"]
    assert payload["current_head_deployments"][0]["id"] == 4614098730
    assert payload["historical_production_candidates"][0]["operator_label"] == "historical_candidate_only"
