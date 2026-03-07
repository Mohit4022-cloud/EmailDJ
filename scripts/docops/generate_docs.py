#!/usr/bin/env python3
"""Generate repository docs from source-of-truth code and config artifacts.

Generated outputs:
- docs/ops/env_matrix.md
- docs/contracts/openapi_summary.md
- docs/contracts/openapi_diff.md
- docs/contracts/openapi_snapshot.json
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = ROOT / "docs"
ENV_EXAMPLE_PATH = ROOT / "hub-api" / ".env.example"
OPENAPI_PATH = ROOT / "hub-api" / "openapi.json"

GENERATED_FILES = {
    DOCS_ROOT / "ops" / "env_matrix.md": "env_matrix",
    DOCS_ROOT / "contracts" / "openapi_summary.md": "openapi_summary",
    DOCS_ROOT / "contracts" / "openapi_diff.md": "openapi_diff",
    DOCS_ROOT / "contracts" / "openapi_snapshot.json": "openapi_snapshot",
}

IGNORE_PARTS = {
    ".git",
    "node_modules",
    ".venv",
    "dist",
    "reports",
    "__pycache__",
    ".pytest_cache",
}

ENV_PATTERNS = [
    re.compile(r"os\.environ\.get\(\s*['\"]([A-Z][A-Z0-9_]+)['\"]"),
    re.compile(r"os\.environ\.setdefault\(\s*['\"]([A-Z][A-Z0-9_]+)['\"]"),
    re.compile(r"os\.environ\[\s*['\"]([A-Z][A-Z0-9_]+)['\"]\s*\]"),
    re.compile(r"os\.getenv\(\s*['\"]([A-Z][A-Z0-9_]+)['\"]"),
    re.compile(r"process\.env\.([A-Z][A-Z0-9_]+)"),
    re.compile(r"import\.meta\.env\.([A-Z][A-Z0-9_]+)"),
    re.compile(r"secrets\.([A-Z][A-Z0-9_]+)"),
]


def _iter_source_files() -> list[Path]:
    roots = [ROOT / "hub-api", ROOT / "web-app", ROOT / ".github"]
    suffixes = {".py", ".js", ".ts", ".tsx", ".sh", ".yml", ".yaml"}
    files: list[Path] = []
    for base in roots:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in suffixes:
                continue
            if any(part in IGNORE_PARTS for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _parse_env_example(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]+", key):
            continue
        result[key] = value.strip()
    return result


def _collect_env_usage() -> dict[str, set[str]]:
    usage: dict[str, set[str]] = {}
    for src in _iter_source_files():
        text = src.read_text(encoding="utf-8", errors="ignore")
        rel = _relative(src)
        for pattern in ENV_PATTERNS:
            for match in pattern.findall(text):
                usage.setdefault(match, set()).add(rel)
    return usage


def _md_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _truncate(value: str, max_chars: int = 80) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def _build_env_matrix_markdown(env_example: dict[str, str], usage: dict[str, set[str]]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    keys = sorted(set(env_example) | set(usage))

    lines: list[str] = []
    lines.append("# Environment Matrix")
    lines.append("")
    lines.append(f"Generated from `hub-api/.env.example` + repository env usage on **{now}**.")
    lines.append("")
    lines.append("| Variable | In `.env.example` | Example / Default | Observed in code | Sample locations |")
    lines.append("|---|---|---|---|---|")

    for key in keys:
        in_example = "yes" if key in env_example else "no"
        value = env_example.get(key, "")
        observed = usage.get(key, set())
        observed_count = str(len(observed))
        sample = ", ".join(sorted(observed)[:3]) if observed else "-"
        sample = _truncate(sample, 120)
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_escape(key),
                    in_example,
                    _md_escape(_truncate(value, 60) if value else "-"),
                    observed_count,
                    _md_escape(sample),
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- `In .env.example = no` means code references a variable not declared in `hub-api/.env.example`.")
    lines.append("- `Observed in code = 0` means variable is documented but currently not referenced in scanned files.")
    return "\n".join(lines) + "\n"


def _schema_name(schema: object) -> str:
    if not isinstance(schema, dict):
        return "-"
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref:
        return ref.split("/")[-1]
    schema_type = schema.get("type")
    if isinstance(schema_type, str) and schema_type:
        return schema_type
    return "inline"


def _load_openapi() -> dict:
    if not OPENAPI_PATH.exists():
        raise FileNotFoundError(f"Missing OpenAPI file: {OPENAPI_PATH}")
    return json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))


def _build_openapi_snapshot(openapi_doc: dict) -> dict:
    endpoints: dict[str, dict] = {}
    paths = openapi_doc.get("paths", {})
    if isinstance(paths, dict):
        for path, path_item in sorted(paths.items()):
            if not isinstance(path_item, dict):
                continue
            for method, operation in sorted(path_item.items()):
                if method.lower() not in {"get", "post", "put", "patch", "delete", "options", "head"}:
                    continue
                if not isinstance(operation, dict):
                    continue
                key = f"{method.upper()} {path}"

                request_schema = "-"
                request_body = operation.get("requestBody")
                if isinstance(request_body, dict):
                    content = request_body.get("content", {})
                    if isinstance(content, dict):
                        app_json = content.get("application/json", {})
                        if isinstance(app_json, dict):
                            request_schema = _schema_name(app_json.get("schema"))

                response_schemas: dict[str, str] = {}
                responses = operation.get("responses", {})
                if isinstance(responses, dict):
                    for code, response in sorted(responses.items()):
                        schema_name = "-"
                        if isinstance(response, dict):
                            content = response.get("content", {})
                            if isinstance(content, dict):
                                app_json = content.get("application/json", {})
                                if isinstance(app_json, dict):
                                    schema_name = _schema_name(app_json.get("schema"))
                        response_schemas[str(code)] = schema_name

                endpoints[key] = {
                    "method": method.upper(),
                    "path": path,
                    "tags": operation.get("tags", []),
                    "operation_id": operation.get("operationId", ""),
                    "request_schema": request_schema,
                    "response_schemas": response_schemas,
                }

    schemas: dict[str, dict] = {}
    components = openapi_doc.get("components", {})
    component_schemas = components.get("schemas", {}) if isinstance(components, dict) else {}
    if isinstance(component_schemas, dict):
        for name, schema in sorted(component_schemas.items()):
            if not isinstance(schema, dict):
                continue
            props = schema.get("properties", {})
            props_list = sorted(props.keys()) if isinstance(props, dict) else []
            required = sorted(schema.get("required", [])) if isinstance(schema.get("required", []), list) else []
            schemas[name] = {
                "property_count": len(props_list),
                "required_count": len(required),
                "properties": props_list,
                "required": required,
            }

    return {
        "source": "hub-api/openapi.json",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endpoint_count": len(endpoints),
        "schema_count": len(schemas),
        "endpoints": endpoints,
        "schemas": schemas,
    }


def _build_openapi_summary_markdown(snapshot: dict) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    lines: list[str] = []
    lines.append("# OpenAPI Contract Summary")
    lines.append("")
    lines.append(f"Generated from `hub-api/openapi.json` on **{now}**.")
    lines.append("")
    lines.append(f"- Endpoints: **{snapshot.get('endpoint_count', 0)}**")
    lines.append(f"- Schemas: **{snapshot.get('schema_count', 0)}**")
    lines.append("")
    lines.append("## Endpoints")
    lines.append("")
    lines.append("| Method | Path | Tags | Request Schema | Response Schemas |")
    lines.append("|---|---|---|---|---|")

    endpoints = snapshot.get("endpoints", {})
    for key in sorted(endpoints):
        record = endpoints[key]
        tags = ", ".join(record.get("tags") or []) or "-"
        response_schemas = record.get("response_schemas") or {}
        response_str = ", ".join(f"{code}:{schema}" for code, schema in response_schemas.items()) or "-"
        lines.append(
            f"| {record.get('method','-')} | {record.get('path','-')} | "
            f"{_md_escape(tags)} | {record.get('request_schema','-')} | {_md_escape(response_str)} |"
        )

    lines.append("")
    lines.append("## Schemas")
    lines.append("")
    lines.append("| Schema | Properties | Required |")
    lines.append("|---|---:|---:|")
    schemas = snapshot.get("schemas", {})
    for name in sorted(schemas):
        record = schemas[name]
        lines.append(f"| {name} | {record.get('property_count', 0)} | {record.get('required_count', 0)} |")

    return "\n".join(lines) + "\n"


def _stable_without_generated_at(snapshot: dict | None) -> dict:
    if not snapshot:
        return {}
    data = json.loads(json.dumps(snapshot))
    data.pop("generated_at", None)
    return data


def _build_openapi_diff_markdown(previous_snapshot: dict | None, current_snapshot: dict) -> str:
    previous = _stable_without_generated_at(previous_snapshot)
    current = _stable_without_generated_at(current_snapshot)

    prev_endpoints = previous.get("endpoints", {}) if isinstance(previous, dict) else {}
    curr_endpoints = current.get("endpoints", {}) if isinstance(current, dict) else {}
    prev_schemas = previous.get("schemas", {}) if isinstance(previous, dict) else {}
    curr_schemas = current.get("schemas", {}) if isinstance(current, dict) else {}

    added_endpoints = sorted(set(curr_endpoints) - set(prev_endpoints))
    removed_endpoints = sorted(set(prev_endpoints) - set(curr_endpoints))
    changed_endpoints = sorted(
        key
        for key in (set(curr_endpoints) & set(prev_endpoints))
        if curr_endpoints[key] != prev_endpoints[key]
    )

    added_schemas = sorted(set(curr_schemas) - set(prev_schemas))
    removed_schemas = sorted(set(prev_schemas) - set(curr_schemas))
    changed_schemas = sorted(
        key
        for key in (set(curr_schemas) & set(prev_schemas))
        if curr_schemas[key] != prev_schemas[key]
    )

    lines: list[str] = []
    lines.append("# OpenAPI Contract Diff")
    lines.append("")
    if not previous_snapshot:
        lines.append("No prior snapshot found. This file establishes the initial baseline.")
        lines.append("")
        return "\n".join(lines)

    lines.append("Diff computed against previous committed `docs/contracts/openapi_snapshot.json`.")
    lines.append("")
    lines.append("## Endpoint changes")
    lines.append("")
    lines.append(f"- Added: {len(added_endpoints)}")
    lines.append(f"- Removed: {len(removed_endpoints)}")
    lines.append(f"- Changed: {len(changed_endpoints)}")
    lines.append("")

    for title, items in (
        ("Added endpoints", added_endpoints),
        ("Removed endpoints", removed_endpoints),
        ("Changed endpoints", changed_endpoints),
    ):
        lines.append(f"### {title}")
        lines.append("")
        if not items:
            lines.append("- None")
        else:
            for item in items[:80]:
                lines.append(f"- `{item}`")
            if len(items) > 80:
                lines.append(f"- ... and {len(items) - 80} more")
        lines.append("")

    lines.append("## Schema changes")
    lines.append("")
    lines.append(f"- Added: {len(added_schemas)}")
    lines.append(f"- Removed: {len(removed_schemas)}")
    lines.append(f"- Changed: {len(changed_schemas)}")
    lines.append("")

    for title, items in (
        ("Added schemas", added_schemas),
        ("Removed schemas", removed_schemas),
        ("Changed schemas", changed_schemas),
    ):
        lines.append(f"### {title}")
        lines.append("")
        if not items:
            lines.append("- None")
        else:
            for item in items[:80]:
                lines.append(f"- `{item}`")
            if len(items) > 80:
                lines.append(f"- ... and {len(items) - 80} more")
        lines.append("")

    return "\n".join(lines)


def _read_existing(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _build_patch_text(changes: dict[Path, str]) -> str:
    patch_chunks: list[str] = []
    for path in sorted(changes.keys()):
        new_text = changes[path]
        old_text = _read_existing(path)
        rel = path.relative_to(ROOT).as_posix()
        diff = difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
        patch_chunks.append("".join(diff))
    return "\n".join(chunk for chunk in patch_chunks if chunk)


def _compute_outputs() -> dict[Path, str]:
    env_example = _parse_env_example(ENV_EXAMPLE_PATH)
    env_usage = _collect_env_usage()
    openapi_doc = _load_openapi()

    snapshot_path = DOCS_ROOT / "contracts" / "openapi_snapshot.json"
    previous_snapshot = None
    if snapshot_path.exists():
        try:
            previous_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous_snapshot = None

    current_snapshot = _build_openapi_snapshot(openapi_doc)

    outputs: dict[Path, str] = {}
    outputs[DOCS_ROOT / "ops" / "env_matrix.md"] = _build_env_matrix_markdown(env_example, env_usage)
    outputs[DOCS_ROOT / "contracts" / "openapi_summary.md"] = _build_openapi_summary_markdown(current_snapshot)
    outputs[DOCS_ROOT / "contracts" / "openapi_diff.md"] = _build_openapi_diff_markdown(previous_snapshot, current_snapshot)
    outputs[DOCS_ROOT / "contracts" / "openapi_snapshot.json"] = json.dumps(current_snapshot, indent=2, sort_keys=True) + "\n"
    return outputs


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate or verify repository docs artifacts.")
    parser.add_argument("--check", action="store_true", help="Do not write files; fail if generated outputs are stale.")
    parser.add_argument(
        "--write-patch",
        type=Path,
        default=None,
        help="Optional patch output path when --check fails (unified diff).",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    outputs = _compute_outputs()

    stale: dict[Path, str] = {}
    for path, content in outputs.items():
        if _read_existing(path) != content:
            stale[path] = content

    if args.check:
        if not stale:
            print("Doc generators are fresh.")
            return 0

        print("Generated docs are stale. Regenerate with:")
        print("  python3 scripts/docops/generate_docs.py")
        for path in sorted(stale):
            print(f"  - {path.relative_to(ROOT).as_posix()}")

        if args.write_patch:
            args.write_patch.parent.mkdir(parents=True, exist_ok=True)
            args.write_patch.write_text(_build_patch_text(stale), encoding="utf-8")
            print(f"Wrote patch: {args.write_patch}")
        return 1

    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT).as_posix()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
