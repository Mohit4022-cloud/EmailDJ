from __future__ import annotations

import json


def test_backend_suite_artifact_captures_pytest_summary(monkeypatch, tmp_path):
    import scripts.run_backend_suite as runner

    artifact_path = tmp_path / "reports" / "launch" / "backend_suite.json"
    monkeypatch.setattr(runner, "ARTIFACT_PATH", artifact_path)

    output = """
....                                                                     [100%]
4 passed, 1 warning in 0.12s
""".strip()

    runner._write_artifact(
        ok=True,
        exit_code=0,
        duration_seconds=0.12345,
        output=output,
        command=["python", "-m", "pytest", "-q", "tests"],
    )

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["backend_green"] == "green"
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["command"] == "python -m pytest -q tests"
    assert payload["exit_code"] == 0
    assert payload["duration_seconds"] == 0.123
    assert payload["summary"] == "4 passed, 1 warning in 0.12s"
    assert payload["output_tail"][-1] == "4 passed, 1 warning in 0.12s"
