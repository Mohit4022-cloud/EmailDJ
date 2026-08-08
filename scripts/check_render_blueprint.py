#!/usr/bin/env python3
"""Validate the repo-local Render Blueprint launch handoff.

This is a deterministic contract check, not a replacement for Render's own
Blueprint validator. It catches repo-specific launch risks before an operator
has Render CLI/API access: local defaults, hardcoded secrets, missing managed
datastore references, and drift from the Hub API launch contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BLUEPRINT = ROOT / "render.yaml"

FORBIDDEN_LOCAL_VALUES = (
    "dev-beta-key",
    "localhost",
    "127.0.0.1",
    "sqlite+aiosqlite",
    "chrome-extension://dev",
)

LAUNCH_DEFAULTS = {
    "APP_ENV": "staging",
    "EMAILDJ_LAUNCH_MODE": "limited_rollout",
    "USE_PROVIDER_STUB": "0",
    "EMAILDJ_QUICK_GENERATE_MODE": "real",
    "EMAILDJ_REAL_PROVIDER": "openai",
    "REDIS_FORCE_INMEMORY": "0",
    "VECTOR_STORE_BACKEND": "pgvector",
    "EMAILDJ_PRESET_PREVIEW_PIPELINE": "off",
    "EMAILDJ_WEB_RATE_LIMIT_PER_MIN": "300",
}

MANUAL_VALUES = {
    "WEB_APP_ORIGIN",
    "CHROME_EXTENSION_ORIGIN",
    "EMAILDJ_WEB_BETA_KEYS",
    "OPENAI_API_KEY",
    "SLACK_WEBHOOK_URL",
    "PROVIDER_FAILURE_METRICS_WEBHOOK_URL",
    "SALESFORCE_INSTANCE_URL",
    "SALESFORCE_ACCESS_TOKEN",
    "BOMBORA_API_KEY",
}


@dataclass(frozen=True)
class BlueprintSections:
    env_var_groups: str
    services: str
    databases: str


def _normalize_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _top_level_section(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s*$", text, re.MULTILINE)
    if not match:
        raise AssertionError(f"Missing top-level `{name}` section")
    start = match.end()
    next_match = re.search(r"^[A-Za-z_][A-Za-z0-9_-]*:\s*$", text[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end]


def _top_level_item_blocks(section: str) -> list[str]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in section.splitlines():
        if line.startswith("  - "):
            if current:
                blocks.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        blocks.append(current)
    return ["\n".join(block) for block in blocks]


def _named_block(section: str, name: str) -> str:
    for block in _top_level_item_blocks(section):
        if re.search(rf"^\s+(?:-\s+)?name:\s*{re.escape(name)}\s*$", block, re.MULTILINE):
            return block
    raise AssertionError(f"Missing block named `{name}`")


def _env_var_body(block: str, key: str) -> str:
    lines = block.splitlines()
    capture = False
    captured: list[str] = []
    for line in lines:
        if re.match(rf"^\s+- key:\s*{re.escape(key)}\s*$", line):
            capture = True
            captured = [line]
            continue
        if capture and re.match(r"^\s+- (key|fromGroup):", line):
            break
        if capture:
            captured.append(line)
    if not captured:
        raise AssertionError(f"Missing env var `{key}`")
    return "\n".join(captured)


def _env_value(block: str, key: str) -> str:
    body = _env_var_body(block, key)
    match = re.search(r"^\s+value:\s*(?P<value>.+?)\s*$", body, re.MULTILINE)
    if not match:
        raise AssertionError(f"Env var `{key}` must have an explicit value")
    return _normalize_scalar(match.group("value"))


def _require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def _validate_service(service: str, failures: list[str]) -> None:
    required_snippets = [
        "type: web",
        "runtime: python",
        "plan: free",
        "autoDeploy: true",
        "buildCommand: cd hub-api && pip install -r requirements.txt",
        "startCommand: cd hub-api && uvicorn main:app --host 0.0.0.0 --port $PORT",
        "healthCheckPath: /",
        "fromGroup: emaildj-hub-api-launch-defaults",
        "hub-api/**",
        "render.yaml",
    ]
    for snippet in required_snippets:
        _require(snippet in service, f"Hub API service is missing `{snippet}`", failures)

    for key, database_name in {
        "DATABASE_URL": "emaildj-postgres",
        "REDIS_URL": "emaildj-redis",
    }.items():
        try:
            body = _env_var_body(service, key)
        except AssertionError as exc:
            failures.append(str(exc))
            continue
        _require("fromDatabase:" in body, f"`{key}` must come from a managed Render database reference", failures)
        _require(f"name: {database_name}" in body, f"`{key}` must reference `{database_name}`", failures)
        _require("property: connectionString" in body, f"`{key}` must use the connection string property", failures)

    for key in sorted(MANUAL_VALUES):
        try:
            body = _env_var_body(service, key)
        except AssertionError as exc:
            failures.append(str(exc))
            continue
        _require("sync: false" in body, f"`{key}` must be Dashboard-filled with `sync: false`", failures)
        _require("value:" not in body, f"`{key}` must not hardcode a value in render.yaml", failures)
        _require("generateValue:" not in body, f"`{key}` must not be generated by Render", failures)


def _validate_defaults(defaults_group: str, failures: list[str]) -> None:
    for key, expected in LAUNCH_DEFAULTS.items():
        try:
            actual = _env_value(defaults_group, key)
        except AssertionError as exc:
            failures.append(str(exc))
            continue
        _require(actual == expected, f"`{key}` must be `{expected}`, found `{actual}`", failures)


def _validate_databases(databases: str, failures: list[str]) -> None:
    try:
        postgres = _named_block(databases, "emaildj-postgres")
    except AssertionError as exc:
        failures.append(str(exc))
    else:
        for snippet in [
            "databaseName: emaildj",
            "user: emaildj",
            "plan: free",
            'postgresMajorVersion: "15"',
            "ipAllowList: []",
        ]:
            _require(snippet in postgres, f"`emaildj-postgres` is missing `{snippet}`", failures)

    try:
        redis = _named_block(databases, "emaildj-redis")
    except AssertionError as exc:
        failures.append(str(exc))
    else:
        for snippet in ["plan: free", "maxmemoryPolicy: allkeys-lru", "ipAllowList: []"]:
            _require(snippet in redis, f"`emaildj-redis` is missing `{snippet}`", failures)


def _sections(text: str) -> BlueprintSections:
    return BlueprintSections(
        env_var_groups=_top_level_section(text, "envVarGroups"),
        services=_top_level_section(text, "services"),
        databases=_top_level_section(text, "databases"),
    )


def validate_blueprint_text(text: str) -> list[str]:
    failures: list[str] = []
    for value in FORBIDDEN_LOCAL_VALUES:
        if value in text:
            failures.append(f"render.yaml must not contain local/dev value `{value}`")

    try:
        sections = _sections(text)
        defaults_group = _named_block(sections.env_var_groups, "emaildj-hub-api-launch-defaults")
        service = _named_block(sections.services, "emaildj-hub-api")
    except AssertionError as exc:
        return failures + [str(exc)]

    _validate_defaults(defaults_group, failures)
    _validate_service(service, failures)
    _validate_databases(sections.databases, failures)
    return failures


def validate_blueprint_path(path: Path = DEFAULT_BLUEPRINT) -> list[str]:
    if not path.exists():
        return [f"Missing Render Blueprint: {path}"]
    return validate_blueprint_text(path.read_text(encoding="utf-8"))


def main() -> int:
    failures = validate_blueprint_path()
    if failures:
        print("Render Blueprint check FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Render Blueprint check passed.")
    print("Hub API service uses managed Redis/Postgres and Dashboard-filled launch secrets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
