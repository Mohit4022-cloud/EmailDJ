#!/usr/bin/env python3
"""Run the Hub API backend test suite and write launch evidence."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / "reports" / "launch" / "backend_suite.json"
DEFAULT_COMMAND = [sys.executable, "-m", "pytest", "-q", "tests"]


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _summary_line(output: str) -> str:
    for line in reversed(output.splitlines()):
        text = line.strip()
        if not text:
            continue
        if any(token in text for token in (" passed", " failed", " error", " errors", " skipped")):
            return text
    return ""


def _output_tail(output: str, *, max_lines: int = 20) -> list[str]:
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    return lines[-max_lines:]


def _command_text(command: list[str]) -> str:
    parts = list(command)
    if parts and Path(parts[0]) == Path(sys.executable):
        parts[0] = "python"
    return " ".join(parts)


def _write_artifact(
    *,
    ok: bool,
    exit_code: int,
    duration_seconds: float,
    output: str,
    command: list[str],
) -> None:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": _utc_now_text(),
        "backend_green": "green" if ok else "red",
        "ok": ok,
        "error": None if ok else "pytest_failed",
        "command": _command_text(command),
        "exit_code": exit_code,
        "duration_seconds": round(duration_seconds, 3),
        "summary": _summary_line(output),
        "output_tail": _output_tail(output),
    }
    ARTIFACT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    start = time.monotonic()
    completed = subprocess.run(
        DEFAULT_COMMAND,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    duration_seconds = time.monotonic() - start
    output = "\n".join(
        part for part in (completed.stdout.strip(), completed.stderr.strip()) if part
    ).strip()
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    _write_artifact(
        ok=completed.returncode == 0,
        exit_code=completed.returncode,
        duration_seconds=duration_seconds,
        output=output,
        command=DEFAULT_COMMAND,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
