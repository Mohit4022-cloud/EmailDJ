#!/usr/bin/env python3
"""PR/push doc freshness gate based on code-path -> docs coverage rules."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCMAP_PATH = ROOT / "docs" / "_meta" / "docmap.yaml"


def _run(cmd: list[str]) -> str:
    out = subprocess.check_output(cmd, cwd=ROOT, text=True)
    return out.strip()


def _git_ref_exists(ref: str) -> bool:
    try:
        subprocess.check_output(["git", "rev-parse", "--verify", ref], cwd=ROOT, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False


def _default_base_ref() -> str:
    pr_base = os.environ.get("GITHUB_BASE_REF", "").strip()
    if pr_base and _git_ref_exists(f"origin/{pr_base}"):
        return f"origin/{pr_base}"
    if _git_ref_exists("origin/main"):
        return "origin/main"
    if _git_ref_exists("origin/master"):
        return "origin/master"
    return "HEAD~1"


def _changed_files(base: str, head: str) -> list[str]:
    try:
        raw = _run(["git", "diff", "--name-only", f"{base}...{head}"])
        if not raw:
            return []
        return [line.strip() for line in raw.splitlines() if line.strip()]
    except subprocess.CalledProcessError:
        raw = _run(["git", "diff", "--name-only", head])
        if not raw:
            return []
        return [line.strip() for line in raw.splitlines() if line.strip()]


def _match_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch(path, pat) for pat in patterns)


def _load_docmap() -> dict:
    if not DOCMAP_PATH.exists():
        raise FileNotFoundError(f"Missing doc map: {DOCMAP_PATH}")
    text = DOCMAP_PATH.read_text(encoding="utf-8")
    # The file uses JSON-compatible YAML so stdlib json is enough.
    return json.loads(text)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check docs freshness against repository code changes.")
    parser.add_argument("--base", default=None, help="Base git ref for diff (default: auto-detected).")
    parser.add_argument("--head", default="HEAD", help="Head git ref for diff (default: HEAD).")
    parser.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="Optional explicit changed file list (skips git diff).",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    docmap = _load_docmap()

    if args.changed_files is not None and len(args.changed_files) > 0:
        changed = sorted(set(args.changed_files))
        base_ref = "<provided>"
    else:
        base_ref = args.base or _default_base_ref()
        changed = sorted(set(_changed_files(base_ref, args.head)))

    if not changed:
        print("No changed files detected; doc freshness check skipped.")
        return 0

    doc_changes = [path for path in changed if path.startswith("docs/")]
    failures: list[str] = []

    coverage_rules = docmap.get("coverage_rules", [])
    for rule in coverage_rules:
        rule_id = rule.get("id", "unnamed-rule")
        code_paths = rule.get("paths", [])
        required_docs = rule.get("docs", [])
        matched_code = [path for path in changed if _match_any(path, code_paths)]
        if not matched_code:
            continue
        matched_docs = [path for path in doc_changes if _match_any(path, required_docs)]
        if matched_docs:
            continue
        message = [
            f"[{rule_id}] changed code paths require docs updates.",
            f"  Changed code (sample): {', '.join(matched_code[:5])}",
            f"  Update at least one of: {', '.join(required_docs)}",
        ]
        failures.append("\n".join(message))

    generators = docmap.get("generators", [])
    for gen in generators:
        gen_id = gen.get("id", "unnamed-generator")
        triggers = gen.get("triggers", [])
        outputs = gen.get("outputs", [])
        matched = [path for path in changed if _match_any(path, triggers)]
        if not matched:
            continue
        if any(path in changed for path in outputs):
            continue
        failures.append(
            "\n".join(
                [
                    f"[{gen_id}] generated docs missing from change set.",
                    f"  Triggering file(s): {', '.join(matched[:5])}",
                    f"  Expected output(s): {', '.join(outputs)}",
                    "  Run: python3 scripts/docops/generate_docs.py",
                ]
            )
        )

    adr = docmap.get("adr", {})
    core_paths = adr.get("core_paths", [])
    required_pattern = adr.get("required_pattern", "docs/adr/*.md")
    core_touched = [path for path in changed if _match_any(path, core_paths)]
    adr_changed = [
        path
        for path in doc_changes
        if fnmatch(path, required_pattern)
        and not path.endswith("0000-template.md")
        and not path.endswith("README.md")
    ]

    if core_touched and not adr_changed:
        failures.append(
            "\n".join(
                [
                    "[adr-required] core invariants/policy paths changed without ADR update.",
                    f"  Changed core files (sample): {', '.join(core_touched[:6])}",
                    "  Add/update an ADR in docs/adr/ (copy docs/adr/0000-template.md).",
                ]
            )
        )

    if failures:
        print("Doc freshness check FAILED")
        print(f"Base ref: {base_ref}")
        print("\n" + "\n\n".join(failures))
        print("\nFix tips:")
        print("- Update mapped docs listed above.")
        print("- Regenerate automation docs: python3 scripts/docops/generate_docs.py")
        print("- If core policy changed, add ADR under docs/adr/.")
        return 1

    print("Doc freshness check passed.")
    print(f"Base ref: {base_ref}")
    print(f"Changed files checked: {len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
