#!/usr/bin/env python3
"""Build an A-to-Z launch completion audit from existing launch artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _has_blocker(report: dict[str, Any], prefix: str) -> bool:
    return any(str(item).startswith(prefix) for item in report.get("config_blockers") or [])


def _has_warning(report: dict[str, Any], value: str) -> bool:
    return value in set(report.get("config_warnings") or [])


def _artifact_missing(report: dict[str, Any], key: str) -> bool:
    provenance = dict(report.get("artifact_provenance") or {})
    entry = dict(provenance.get(key) or {})
    return bool(entry.get("missing", True))


def _item(
    *,
    item_id: str,
    requirement: str,
    passed: bool,
    evidence: list[str],
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    blockers = [item for item in (blockers or []) if item]
    return {
        "id": item_id,
        "requirement": requirement,
        "status": "pass" if passed else "blocked",
        "evidence": evidence,
        "blockers": [] if passed else blockers,
    }


def _surface_manifest_item(manifest: dict[str, Any]) -> dict[str, Any]:
    launch_owned = {item.get("path") for item in manifest.get("launch_owned") or []}
    legacy = {item.get("path"): item for item in manifest.get("legacy_explicit_only") or []}
    expected_launch = {"hub-api/", "web-app/", "chrome-extension/"}
    expected_legacy = {"backend/", "frontend/"}
    legacy_safe = (
        set(legacy) == expected_legacy
        and all(item.get("launch_readiness_evidence") is False for item in legacy.values())
    )
    passed = launch_owned == expected_launch and legacy_safe
    return _item(
        item_id="parallel_stack_story",
        requirement="Decide and enforce which surfaces count as launch evidence.",
        passed=passed,
        evidence=[
            f"launch_owned={sorted(launch_owned)}",
            f"legacy_explicit_only={sorted(legacy)}",
            "source=docs/ops/launch_surfaces.json",
        ],
        blockers=[] if passed else ["surface_manifest_mismatch"],
    )


def _ux_item() -> dict[str, Any]:
    layout_test = REPO_ROOT / "web-app" / "tests" / "layout-contract.test.js"
    editor = REPO_ROOT / "web-app" / "src" / "components" / "EmailEditor.js"
    layout_text = layout_test.read_text(encoding="utf-8") if layout_test.exists() else ""
    editor_text = editor.read_text(encoding="utf-8") if editor.exists() else ""
    passed = (
        "draft editor owns the primary canvas chrome and empty state" in layout_text
        and "mobile workspace controls stay within the viewport grid" in layout_text
        and 'id="editorFrame"' in editor_text
        and 'id="draftCanvasTitle"' in editor_text
    )
    return _item(
        item_id="draft_workspace_ux",
        requirement="Final UX pass makes the draft workspace primary and guarded on mobile.",
        passed=passed,
        evidence=[
            "web-app/tests/layout-contract.test.js",
            "web-app/src/components/EmailEditor.js",
        ],
        blockers=[] if passed else ["draft_workspace_layout_contract_missing"],
    )


def build_launch_audit() -> dict[str, Any]:
    report = _read_json(ROOT / "reports" / "launch" / "latest.json")
    preflight = _read_json(ROOT / "reports" / "launch" / "preflight.json")
    backend_suite = _read_json(ROOT / "reports" / "launch" / "backend_suite.json")
    provider_stub = _read_json(ROOT / "reports" / "provider_stub" / "latest.json")
    external_provider = _read_json(ROOT / "reports" / "external_provider" / "latest.json")
    manifest = _read_json(REPO_ROOT / "docs" / "ops" / "launch_surfaces.json")

    provider_summary = dict(external_provider.get("summary") or {})
    stub_summary = dict(provider_stub.get("summary") or {})
    preflight_presence = dict(preflight.get("required_inputs_present") or {})

    origin_blockers = [
        blocker
        for blocker in report.get("config_blockers") or []
        if str(blocker).startswith(("web_app_origin_not_pinned", "chrome_extension_origin_not_pinned", "beta_keys_not_safe"))
    ]
    durable_blockers = [
        blocker
        for blocker in report.get("config_blockers") or []
        if str(blocker).startswith(
            (
                "redis_not_durable_for_launch_mode",
                "database_not_durable_for_launch_mode",
                "vector_store_not_durable_for_launch_mode",
            )
        )
    ]
    http_smoke_blockers = [
        blocker for blocker in report.get("config_blockers") or [] if str(blocker).startswith("http_smoke_")
    ]

    items = [
        _item(
            item_id="hub_api_full_suite",
            requirement="Fix and keep the Hub API full quality gate green.",
            passed=report.get("backend_green") == "green" and backend_suite.get("ok") is True,
            evidence=[
                f"backend_green={report.get('backend_green')}",
                f"backend_suite_summary={backend_suite.get('summary') or 'unset'}",
            ],
            blockers=["backend_suite_not_green"],
        ),
        _item(
            item_id="live_provider_harness",
            requirement="Get a fresh live-provider run green, not only provider-stub evidence.",
            passed=(
                report.get("provider_green") == "green"
                and report.get("provider_source") == "external_provider"
                and provider_summary.get("provider_source") == "external_provider"
                and int(provider_summary.get("failed_cases") or 0) == 0
            ),
            evidence=[
                f"provider_green={report.get('provider_green')}",
                f"provider_source={report.get('provider_source')}",
                f"external_provider_cases={provider_summary.get('passed_cases')}/{provider_summary.get('total_cases')}",
            ],
            blockers=["external_provider_harness_not_green"],
        ),
        _item(
            item_id="lock_and_launch_artifacts",
            requirement="Refresh lock compliance, parity/adversarial/full eval evidence, and launch check artifacts.",
            passed=(
                report.get("harness_green") == "green"
                and report.get("render_blueprint_green") == "green"
                and int(stub_summary.get("failed_cases") or 0) == 0
                and float(stub_summary.get("pass_rate") or 0.0) >= 1.0
            ),
            evidence=[
                f"harness_green={report.get('harness_green')}",
                f"render_blueprint_green={report.get('render_blueprint_green')}",
                f"provider_stub_cases={stub_summary.get('passed_cases')}/{stub_summary.get('total_cases')}",
                f"launch_report_generated_at={report.get('generated_at') or 'unset'}",
            ],
            blockers=["local_lock_or_launch_artifacts_not_green"],
        ),
        _item(
            item_id="deployed_preflight_inputs",
            requirement="Operator exports staging/prod Hub API roots and one explicit deployed beta key.",
            passed=preflight.get("ready") is True,
            evidence=[
                f"preflight_ready={preflight.get('ready')}",
                f"required_inputs_present={preflight_presence}",
                f"failure_bucket={preflight.get('failure_bucket') or 'none'}",
            ],
            blockers=list(preflight.get("missing_inputs") or preflight.get("operator_input_errors") or []),
        ),
        _item(
            item_id="runtime_snapshots",
            requirement="Capture staging and production runtime snapshots.",
            passed=not _artifact_missing(report, "staging_runtime_snapshot")
            and not _artifact_missing(report, "production_runtime_snapshot"),
            evidence=[
                f"staging_snapshot_missing={_artifact_missing(report, 'staging_runtime_snapshot')}",
                f"production_snapshot_missing={_artifact_missing(report, 'production_runtime_snapshot')}",
            ],
            blockers=[
                "staging_runtime_snapshot_missing" if _artifact_missing(report, "staging_runtime_snapshot") else "",
                "production_runtime_snapshot_missing" if _artifact_missing(report, "production_runtime_snapshot") else "",
            ],
        ),
        _item(
            item_id="pinned_origins_beta_provider",
            requirement="Pin deployed web/extension origins, non-dev beta keys, and real provider mode.",
            passed=not origin_blockers
            and report.get("provider_stub_enabled") is False
            and report.get("effective_provider_source") == "external_provider",
            evidence=[
                f"web_app_origin_state={report.get('web_app_origin_state')}",
                f"chrome_extension_origin_state={report.get('chrome_extension_origin_state')}",
                f"beta_keys_state={report.get('beta_keys_state')}",
                f"effective_provider_source={report.get('effective_provider_source')}",
            ],
            blockers=origin_blockers,
        ),
        _item(
            item_id="durable_infra",
            requirement="Use durable Redis/Postgres/pgvector instead of local or in-memory state.",
            passed=not durable_blockers,
            evidence=[
                f"redis_config_state={report.get('redis_config_state')}",
                f"database_config_state={report.get('database_config_state')}",
                f"vector_store_config_state={report.get('vector_store_config_state')}",
            ],
            blockers=durable_blockers,
        ),
        _item(
            item_id="deployed_http_smoke",
            requirement="Prove deployed web generate/remix coverage against staging; require preview smoke only when preview is enabled.",
            passed=not http_smoke_blockers,
            evidence=[
                f"required_http_smoke_routes={report.get('required_http_smoke_routes')}",
                f"route_gates={report.get('route_gates')}",
                f"localhost_smoke_provider_source_counts={(report.get('localhost_smoke') or {}).get('provider_source_counts')}",
            ],
            blockers=http_smoke_blockers,
        ),
        _item(
            item_id="release_fingerprint_parity",
            requirement="Capture comparable staging/prod release fingerprints.",
            passed=not _has_warning(report, "release_fingerprint_unavailable")
            and not _has_blocker(report, "release_fingerprint_mismatch:"),
            evidence=[
                f"release_fingerprint_available={report.get('release_fingerprint_available')}",
                f"release_fingerprint={report.get('release_fingerprint') or 'unset'}",
                f"runtime_source_used={(report.get('release_fingerprint_parity') or {}).get('runtime_source_used')}",
            ],
            blockers=[
                "release_fingerprint_unavailable" if _has_warning(report, "release_fingerprint_unavailable") else "",
                *[
                    blocker
                    for blocker in report.get("config_blockers") or []
                    if str(blocker).startswith("release_fingerprint_mismatch:")
                ],
            ],
        ),
        _item(
            item_id="chrome_extension_real_target",
            requirement="Prove the Chrome extension flow against the real shipped extension origin.",
            passed=not _has_blocker(report, "chrome_extension_origin_not_pinned:"),
            evidence=[
                f"chrome_extension_origin={report.get('chrome_extension_origin')}",
                f"chrome_extension_origin_state={report.get('chrome_extension_origin_state')}",
            ],
            blockers=[
                blocker
                for blocker in report.get("config_blockers") or []
                if str(blocker).startswith("chrome_extension_origin_not_pinned:")
            ],
        ),
        _surface_manifest_item(manifest),
        _ux_item(),
        _item(
            item_id="launch_report_recommendation",
            requirement="Launch-check itself must no longer report Not yet launch-ready.",
            passed=report.get("final_recommendation") != "Not yet launch-ready"
            and not report.get("config_blockers")
            and not report.get("errors"),
            evidence=[
                f"final_recommendation={report.get('final_recommendation') or 'unset'}",
                f"config_blocker_count={len(report.get('config_blockers') or [])}",
                f"error_count={len(report.get('errors') or [])}",
            ],
            blockers=[
                "launch_check_not_ready"
                if report.get("final_recommendation") == "Not yet launch-ready"
                else "",
                *list(report.get("errors") or []),
            ],
        ),
    ]

    incomplete = [item for item in items if item["status"] != "pass"]
    return {
        "generated_at": _utc_now_text(),
        "final_status": "complete" if not incomplete else "not_complete",
        "launch_report_recommendation": report.get("final_recommendation"),
        "source_artifacts": {
            "launch_report": str(ROOT / "reports" / "launch" / "latest.json"),
            "preflight": str(ROOT / "reports" / "launch" / "preflight.json"),
            "surface_manifest": str(REPO_ROOT / "docs" / "ops" / "launch_surfaces.json"),
        },
        "items": items,
        "open_blocker_count": len(incomplete),
        "open_blockers": [
            {"id": item["id"], "blockers": item["blockers"]}
            for item in incomplete
        ],
    }


def _write_markdown(path: Path, audit: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Launch Completion Audit",
        "",
        f"- Generated at: `{audit['generated_at']}`",
        f"- Final status: `{audit['final_status']}`",
        f"- Launch report recommendation: `{audit.get('launch_report_recommendation') or 'unset'}`",
        f"- Open blocker count: `{audit['open_blocker_count']}`",
        "",
        "| Requirement | Status | Evidence | Blockers |",
        "|---|---|---|---|",
    ]
    for item in audit["items"]:
        evidence = "<br>".join(f"`{entry}`" for entry in item["evidence"])
        blockers = "<br>".join(f"`{entry}`" for entry in item["blockers"]) or "`none`"
        lines.append(f"| `{item['id']}` | `{item['status']}` | {evidence} | {blockers} |")
    lines.append("")
    lines.append("## Source Artifacts")
    lines.append("")
    for key, value in audit["source_artifacts"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_launch_audit() -> tuple[Path, Path, dict[str, Any]]:
    audit = build_launch_audit()
    report_dir = ROOT / "reports" / "launch"
    json_path = report_dir / "completion_audit.json"
    md_path = report_dir / "completion_audit.md"
    _write_json(json_path, audit)
    _write_markdown(md_path, audit)
    return json_path, md_path, audit


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an artifact-backed EmailDJ launch completion audit.")
    parser.add_argument("--fail-if-incomplete", action="store_true", help="Exit nonzero when open blockers remain.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    json_path, md_path, audit = write_launch_audit()
    print(
        json.dumps(
            {
                "completion_audit_json": str(json_path),
                "completion_audit_md": str(md_path),
                "final_status": audit["final_status"],
                "open_blocker_count": audit["open_blocker_count"],
            },
            indent=2,
        )
    )
    if args.fail_if_incomplete and audit["final_status"] != "complete":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
