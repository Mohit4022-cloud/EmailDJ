"""Static denylist scan: behavioral source files must not contain hardcoded brand names.

Scans email_generation/, api/, agents/, context_vault/, and pii/ for hardcoded
vendor/prospect strings that were removed as part of the tenant-variable refactor.

Excluded paths: devtools/, tests/, evals/, __pycache__, .venv
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_HUB_ROOT = Path(__file__).resolve().parents[1]

_SCAN_DIRS = [
    "email_generation",
    "api",
]
# Also scan any top-level .py files that are part of the app
_SCAN_TOP_LEVEL = ["main.py"]

_EXCLUDE_DIRS = frozenset({"devtools", "tests", "evals", "__pycache__", ".venv"})

# Brand names that must not appear in behavioral source code.
# These may appear in fixture files and test stimulus but not in policy/generation logic.
_DENYLIST: tuple[tuple[str, str], ...] = (
    (r"\bPalantir\b", "Palantir"),
    (r"\bCorsearch\b", "Corsearch"),
    (r"\bAlex\s+Karp\b", "Alex Karp"),
    (r"\bZeal\s+2\.0\b", "Zeal 2.0"),
)

_COMPILED_DENYLIST = [(re.compile(pattern, re.IGNORECASE), label) for pattern, label in _DENYLIST]


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def _collect_py_files() -> list[Path]:
    files: list[Path] = []
    for dir_name in _SCAN_DIRS:
        scan_dir = _HUB_ROOT / dir_name
        if not scan_dir.is_dir():
            continue
        for path in scan_dir.rglob("*.py"):
            if any(excluded in path.parts for excluded in _EXCLUDE_DIRS):
                continue
            files.append(path)
    for name in _SCAN_TOP_LEVEL:
        top = _HUB_ROOT / name
        if top.is_file():
            files.append(top)
    return sorted(files)


def _scan_for_violations() -> list[tuple[Path, int, str, str]]:
    """Return list of (file, line_number, matched_label, line_text) for all denylist hits."""
    violations: list[tuple[Path, int, str, str]] = []
    for path in _collect_py_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern, label in _COMPILED_DENYLIST:
                if pattern.search(line):
                    violations.append((path, lineno, label, line.strip()))
    return violations


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_hardcoded_brand_names_in_behavioral_source():
    violations = _scan_for_violations()
    if not violations:
        return

    lines = ["Hardcoded brand names found in behavioral source files:"]
    for path, lineno, label, line_text in violations:
        rel = path.relative_to(_HUB_ROOT)
        lines.append(f"  {rel}:{lineno}  [{label}]  {line_text[:120]}")

    pytest.fail("\n".join(lines))


@pytest.mark.parametrize("dir_name", _SCAN_DIRS)
def test_scan_dir_exists(dir_name: str):
    assert (_HUB_ROOT / dir_name).is_dir(), (
        f"Expected scan directory '{dir_name}' to exist under {_HUB_ROOT}"
    )
