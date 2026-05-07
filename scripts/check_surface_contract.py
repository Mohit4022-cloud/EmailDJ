#!/usr/bin/env python3
"""Validate the repo's launch-owned surface contract.

This is intentionally a static guard. It prevents legacy surfaces from being
treated as launch evidence and keeps the CI/Makefile/docs story aligned.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRIMARY_TARGETS = {
    "test": {"hub-api-test", "web-app-test", "chrome-extension-test"},
    "build": {"hub-api-build", "web-app-build", "chrome-extension-build"},
    "launch-gates-local": {
        "surface-contract",
        "hub-api-test",
        "web-app-test",
        "chrome-extension-test",
        "eval-smoke",
        "eval-parity",
        "eval-adversarial",
        "eval-full",
        "launch-check",
    },
    "launch-verify-deployed": set(),
    "launch-verify-web-app": set(),
    "launch-verify-extension": set(),
    "launch-preflight": set(),
}

LEGACY_TARGETS = {"legacy-setup", "legacy-backend-test", "legacy-frontend-test", "legacy-build"}


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _target_prereqs(makefile_text: str, target: str) -> set[str]:
    match = re.search(rf"^{re.escape(target)}:\s*(?P<deps>.*)$", makefile_text, re.MULTILINE)
    if not match:
        raise AssertionError(f"Missing Makefile target: {target}")
    return {item for item in re.split(r"\s+", match.group("deps").strip()) if item}


def _require_snippet(text: str, snippet: str, path: str) -> None:
    if snippet not in text:
        raise AssertionError(f"Missing required snippet in {path}: {snippet}")


def _require_ordered_snippets(text: str, snippets: list[str], path: str) -> None:
    cursor = -1
    for snippet in snippets:
        index = text.find(snippet, cursor + 1)
        if index == -1:
            raise AssertionError(f"Missing ordered snippet in {path}: {snippet}")
        cursor = index


def _check_makefile() -> list[str]:
    failures: list[str] = []
    makefile = _read("Makefile")
    for target, expected in PRIMARY_TARGETS.items():
        try:
            prereqs = _target_prereqs(makefile, target)
        except AssertionError as exc:
            failures.append(str(exc))
            continue
        missing = sorted(expected - prereqs)
        legacy = sorted(prereqs & LEGACY_TARGETS)
        if missing:
            failures.append(f"Makefile target `{target}` is missing primary prerequisite(s): {', '.join(missing)}")
        if legacy:
            failures.append(f"Makefile target `{target}` includes legacy prerequisite(s): {', '.join(legacy)}")
    return failures


def _check_deployed_gate() -> list[str]:
    failures: list[str] = []
    path = "scripts/launch-verify-deployed.sh"
    try:
        script = _read(path)
        for snippet in [
            'RELEASE_HUB_URL="${EMAILDJ_EXPECTED_HUB_URL:-${STAGING_BASE_URL:-}}"',
            'RELEASE_BETA_KEY="${EMAILDJ_EXPECTED_BETA_KEY:-${BETA_KEY:-}}"',
            "python scripts/launch_preflight.py",
            "make launch-verify-web-app",
            "make launch-verify-extension",
            "python scripts/capture_runtime_snapshot.py",
            "./scripts/eval:full --real --mode smoke",
            "python -m devtools.http_smoke_runner",
            "python scripts/merge_http_smoke_summaries.py",
            "python scripts/launch_check.py",
        ]:
            _require_snippet(script, snippet, path)
        _require_ordered_snippets(
            script,
            [
                "python scripts/launch_preflight.py",
                "make launch-verify-web-app",
                "make launch-verify-extension",
                "python scripts/capture_runtime_snapshot.py",
                "./scripts/eval:full --real --mode smoke",
                "python -m devtools.http_smoke_runner",
                "python scripts/merge_http_smoke_summaries.py",
                "python scripts/launch_check.py",
            ],
            path,
        )
    except (AssertionError, FileNotFoundError) as exc:
        failures.append(str(exc))
    return failures


def _check_localhost_smoke() -> list[str]:
    failures: list[str] = []
    path = "scripts/localhost-smoke.sh"
    try:
        script = _read(path)
        for snippet in [
            'FLOWS="${EMAILDJ_SMOKE_FLOWS:-${EMAILDJ_SMOKE_FLOW:-generate,remix}}"',
            "-m devtools.http_smoke_runner",
            "python scripts/merge_http_smoke_summaries.py",
            "python scripts/launch_check.py",
        ]:
            _require_snippet(script, snippet, path)
        _require_ordered_snippets(
            script,
            [
                "-m devtools.http_smoke_runner",
                "python scripts/merge_http_smoke_summaries.py",
                "python scripts/launch_check.py",
            ],
            path,
        )
    except (AssertionError, FileNotFoundError) as exc:
        failures.append(str(exc))
    return failures


def _check_docs() -> list[str]:
    failures: list[str] = []
    required = {
        "README.md": [
            "`web-app/` primary",
            "`hub-api/` primary",
            "`frontend/` legacy parity UI",
            "`backend/` legacy backend",
            "make launch-preflight",
            "make launch-verify-deployed",
            "make launch-verify-web-app",
            "make launch-verify-extension",
        ],
        "docs/ops/deployment.md": [
            "Frontend: deploy [`web-app`]",
            "Hub API: deploy [`hub-api`]",
            "Legacy parity:",
            "make launch-preflight",
            "make launch-verify-deployed",
            "make launch-verify-web-app",
            "make launch-verify-extension",
        ],
        "docs/ops/surface_contract.md": [
            "Launch-Owned Surfaces",
            "Legacy Surfaces",
            "These surfaces do not produce launch-readiness evidence",
            "make launch-preflight",
            "make launch-verify-deployed",
            "make launch-verify-web-app",
            "make launch-verify-extension",
        ],
        "docs/ops/release_checklist.md": [
            "Surface contract",
            "Web app tests",
            "Web app build",
            "make launch-preflight",
            "make launch-verify-web-app",
            "make launch-verify-extension",
        ],
    }
    for path, snippets in required.items():
        try:
            text = _read(path)
            for snippet in snippets:
                _require_snippet(text, snippet, path)
        except (AssertionError, FileNotFoundError) as exc:
            failures.append(str(exc))
    return failures


def _check_ci() -> list[str]:
    failures: list[str] = []
    ci = _read(".github/workflows/ci.yml")
    legacy_eval = _read(".github/workflows/eval_regression.yml")
    required_ci_snippets = [
        "Surface contract gate",
        "python3 scripts/check_surface_contract.py",
        "Install web app deps",
        "Run web app unit tests and build",
        "npm run check:syntax",
        "npm run build",
    ]
    for snippet in required_ci_snippets:
        if snippet not in ci:
            failures.append(f"CI checks job is missing `{snippet}`")

    required_legacy_snippets = [
        "name: Legacy Backend Eval Regression",
        "paths:",
        "backend/**",
        ".github/workflows/eval_regression.yml",
        "legacy-backend-eval-regression",
    ]
    for snippet in required_legacy_snippets:
        if snippet not in legacy_eval:
            failures.append(f"Legacy eval workflow is missing `{snippet}`")
    return failures


def main() -> int:
    failures = (
        _check_makefile()
        + _check_deployed_gate()
        + _check_localhost_smoke()
        + _check_docs()
        + _check_ci()
    )
    if failures:
        print("Surface contract check FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Surface contract check passed.")
    print("Primary launch evidence: hub-api, web-app, chrome-extension.")
    print("Legacy backend/frontend are explicit-only parity surfaces.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
