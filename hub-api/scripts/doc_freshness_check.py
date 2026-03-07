#!/usr/bin/env python3
"""
Doc freshness check — CI gate for EmailDJ documentation.

Reads docs/_meta/docmap.yaml and for each binding with freshness: on_change,
checks whether the bound code paths changed without a corresponding doc change.

Usage:
    # In CI (PR context)
    python hub-api/scripts/doc_freshness_check.py \
        --base ${{ github.event.pull_request.base.sha }} \
        --head ${{ github.sha }}

    # Locally (compare against main)
    python hub-api/scripts/doc_freshness_check.py --base origin/main --head HEAD

    # Advisory mode (no exit 1)
    python hub-api/scripts/doc_freshness_check.py --base origin/main --head HEAD --warn-only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCMAP_PATH = REPO_ROOT / "docs" / "_meta" / "docmap.yaml"


def get_changed_files(base: str, head: str) -> set[str]:
    """Return set of file paths changed between base and head."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        # Fallback: try two-dot diff
        result = subprocess.run(
            ["git", "diff", "--name-only", base, head],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
    if result.returncode != 0:
        print(f"WARNING: git diff failed: {result.stderr.strip()}", file=sys.stderr)
        return set()
    return set(result.stdout.splitlines())


def path_matches_pattern(changed_files: set[str], pattern: str) -> bool:
    """Check if any changed file matches the given path pattern (prefix or glob-like)."""
    import fnmatch

    for f in changed_files:
        if fnmatch.fnmatch(f, pattern):
            return True
        # Also match if the changed file starts with the pattern (directory prefix)
        if pattern.endswith("/") and f.startswith(pattern):
            return True
        # Match exact path
        if f == pattern:
            return True
        # Match directory: "hub-api/infra/" matches "hub-api/infra/db.py"
        if not pattern.endswith("*") and not pattern.endswith("/"):
            # treat as prefix if no glob chars and no trailing slash
            pass
    return False


def bound_paths_changed(changed_files: set[str], bound_to: list[str]) -> list[str]:
    """Return list of bound_to patterns that have changed files."""
    import fnmatch

    matched = []
    for pattern in bound_to:
        for f in changed_files:
            # Exact match
            if f == pattern:
                matched.append(pattern)
                break
            # fnmatch glob
            if fnmatch.fnmatch(f, pattern):
                matched.append(pattern)
                break
            # Directory prefix (e.g., "hub-api/infra/" matches "hub-api/infra/db.py")
            clean = pattern.rstrip("/")
            if f.startswith(clean + "/") or f.startswith(clean.rstrip("*")):
                matched.append(pattern)
                break
    return matched


def main() -> int:
    parser = argparse.ArgumentParser(description="EmailDJ doc freshness gate")
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Base git ref (default: origin/main)",
    )
    parser.add_argument(
        "--head",
        default="HEAD",
        help="Head git ref (default: HEAD)",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Print warnings but exit 0 (advisory mode)",
    )
    args = parser.parse_args()

    if not DOCMAP_PATH.exists():
        print(f"ERROR: docmap not found at {DOCMAP_PATH}", file=sys.stderr)
        return 0 if args.warn_only else 1

    with DOCMAP_PATH.open() as f:
        docmap = yaml.safe_load(f)

    bindings = docmap.get("bindings", [])
    if not bindings:
        print("WARNING: No bindings found in docmap.yaml", file=sys.stderr)
        return 0

    changed_files = get_changed_files(args.base, args.head)
    if not changed_files:
        print("No changed files detected — skipping freshness check.")
        return 0

    failures: list[str] = []
    warnings: list[str] = []

    for binding in bindings:
        doc = binding.get("doc", "")
        freshness = binding.get("freshness", "manual")
        bound_to = binding.get("bound_to", [])

        if freshness not in ("on_change", "on_major_change"):
            continue  # manual bindings are not checked automatically

        matched_patterns = bound_paths_changed(changed_files, bound_to)
        if not matched_patterns:
            continue  # bound code did not change

        # Check if the doc itself changed
        doc_changed = any(
            f == doc or f.startswith(doc.rstrip("/"))
            for f in changed_files
        )

        if not doc_changed:
            msg = (
                f"{'❌' if freshness == 'on_change' else '⚠️ '} STALE: {doc}\n"
                f"   Bound code changed: {', '.join(matched_patterns)}\n"
                f"   Doc was NOT updated."
            )
            if freshness == "on_change":
                failures.append(msg)
            else:
                # on_major_change is advisory
                warnings.append(msg)

    # Print results
    if warnings:
        print("\n".join(warnings))

    if failures:
        print("\n".join(failures))
        if args.warn_only:
            print(f"\n⚠️  {len(failures)} freshness failure(s) detected (warn-only mode — not blocking).")
            return 0
        else:
            print(f"\n❌ {len(failures)} freshness failure(s). Update the docs listed above before merging.")
            return 1

    if not warnings:
        print(f"✅ All doc freshness checks passed ({len(bindings)} bindings checked).")
    else:
        print(f"✅ No blocking failures. {len(warnings)} advisory warning(s) above.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
