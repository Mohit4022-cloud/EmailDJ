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
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ModuleNotFoundError:
        pass

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _load_docmap_subset(text)


def _clean_yaml_value(value: str) -> str:
    value = value.strip()
    if value.startswith(("'", '"')) and value.endswith(("'", '"')):
        return value[1:-1]
    return value


def _load_docmap_subset(text: str) -> dict:
    """Parse the subset of docmap.yaml needed by this checker without PyYAML."""

    data: dict[str, object] = {"coverage_rules": [], "generators": [], "adr": {}}
    current_section: str | None = None
    current_item: dict[str, object] | None = None
    current_key: str | None = None

    def finish_item() -> None:
        nonlocal current_item
        if current_section in {"coverage_rules", "generators"} and current_item is not None:
            section = data.setdefault(current_section, [])
            assert isinstance(section, list)
            section.append(current_item)
        current_item = None

    for raw_line in text.splitlines():
        line_without_comment = raw_line.split("#", 1)[0].rstrip()
        if not line_without_comment.strip():
            continue
        indent = len(line_without_comment) - len(line_without_comment.lstrip(" "))
        stripped = line_without_comment.strip()

        if indent == 0 and stripped.endswith(":"):
            finish_item()
            current_section = stripped[:-1]
            current_key = None
            continue

        if current_section in {"coverage_rules", "generators"}:
            if stripped.startswith("- ") and current_key and indent > 2 and current_item is not None:
                values = current_item.setdefault(current_key, [])
                assert isinstance(values, list)
                values.append(_clean_yaml_value(stripped[2:]))
                continue
            if stripped.startswith("- "):
                finish_item()
                current_item = {}
                rest = stripped[2:].strip()
                if rest and ":" in rest:
                    key, value = rest.split(":", 1)
                    current_item[key.strip()] = _clean_yaml_value(value)
                    current_key = None
                continue
            if current_item is None:
                continue
            if stripped.endswith(":"):
                current_key = stripped[:-1]
                current_item[current_key] = []
                continue
            if ":" in stripped:
                key, value = stripped.split(":", 1)
                current_item[key.strip()] = _clean_yaml_value(value)
                current_key = None
            continue

        if current_section == "adr":
            adr = data.setdefault("adr", {})
            assert isinstance(adr, dict)
            if stripped.endswith(":"):
                current_key = stripped[:-1]
                adr[current_key] = []
                continue
            if stripped.startswith("- ") and current_key:
                values = adr.setdefault(current_key, [])
                assert isinstance(values, list)
                values.append(_clean_yaml_value(stripped[2:]))
                continue
            if ":" in stripped:
                key, value = stripped.split(":", 1)
                adr[key.strip()] = _clean_yaml_value(value)

    finish_item()
    return data


def _generator_check(script: str, cache: dict[str, tuple[bool, str]]) -> tuple[bool, str]:
    if script in cache:
        return cache[script]
    try:
        output = subprocess.check_output(
            [sys.executable, script, "--check"],
            cwd=ROOT,
            stderr=subprocess.STDOUT,
            text=True,
        )
        result = (True, output.strip())
    except subprocess.CalledProcessError as exc:
        result = (False, (exc.output or "").strip())
    cache[script] = result
    return result


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
    generator_check_cache: dict[str, tuple[bool, str]] = {}
    for gen in generators:
        gen_id = gen.get("id", "unnamed-generator")
        script = gen.get("script", "")
        triggers = gen.get("triggers", [])
        outputs = gen.get("outputs", [])
        matched = [path for path in changed if _match_any(path, triggers)]
        if not matched:
            continue
        if any(path in changed for path in outputs):
            continue
        check_output = "n/a"
        if script:
            ok, check_output = _generator_check(script, generator_check_cache)
            if ok:
                continue
        failures.append(
            "\n".join(
                [
                    f"[{gen_id}] generated docs missing from change set.",
                    f"  Triggering file(s): {', '.join(matched[:5])}",
                    f"  Expected output(s): {', '.join(outputs)}",
                    "  Run: python3 scripts/docops/generate_docs.py",
                    f"  Generator check output: {check_output or 'n/a'}",
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
