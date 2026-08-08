#!/usr/bin/env python3
"""Write the compact operator-input readout needed to unblock launch gates."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import launch_handoff


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _required(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in items if item.get("required_when")]


def _shell_export_lines(items: list[dict[str, Any]]) -> list[str]:
    return [f'export {item["name"]}="{item["value"]}"' for item in items]


def build_launch_unblock_inputs() -> dict[str, Any]:
    handoff = launch_handoff.build_launch_handoff()
    required_exports = _required(handoff.get("required_exports") or [])
    required_dashboard_inputs = _required(handoff.get("dashboard_inputs") or [])
    return {
        "generated_at": handoff.get("generated_at"),
        "current_status": handoff.get("current_status"),
        "launch_recommendation": handoff.get("launch_recommendation"),
        "preflight_ready": handoff.get("preflight_ready"),
        "provider": handoff.get("provider"),
        "provider_env": handoff.get("provider_env"),
        "operator_contract": (
            "This readout is paste-safe and placeholder-only. It lists the operator inputs required by the current "
            "launch artifacts; rerun make launch-preflight and make launch-verify-deployed after setting real values."
        ),
        "required_shell_exports": required_exports,
        "required_dashboard_inputs": required_dashboard_inputs,
        "shell_export_template": _shell_export_lines(required_exports),
        "command_defaults": list(handoff.get("operator_command_defaults") or []),
        "next_commands": list(handoff.get("commands") or []),
        "blocked_evidence_refresh_commands": list(handoff.get("blocked_evidence_refresh_commands") or []),
        "open_blockers": list(handoff.get("open_blockers") or []),
        "blocker_clearance_plan": list(handoff.get("blocker_clearance_plan") or []),
        "source_artifacts": dict(handoff.get("source_artifacts") or {}),
    }


def _md_cell(value: Any) -> str:
    return str(value).replace("|", "\\|")


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Launch Unblock Inputs",
        "",
        f"- Generated at: `{payload.get('generated_at')}`",
        f"- Current completion status: `{payload.get('current_status')}`",
        f"- Launch recommendation: `{payload.get('launch_recommendation')}`",
        f"- Preflight ready: `{payload.get('preflight_ready')}`",
        f"- Provider: `{payload.get('provider')}`",
        f"- Provider env: `{payload.get('provider_env')}`",
        f"- Contract: {payload.get('operator_contract')}",
        "",
        "## Paste-Safe Shell Exports",
        "",
        "```bash",
        *payload.get("shell_export_template", []),
        "```",
        "",
        "## Required Dashboard Inputs",
        "",
        "| Name | Value | Candidate | Note |",
        "|---|---|---|---|",
    ]
    for item in payload.get("required_dashboard_inputs") or []:
        lines.append(
            f"| `{_md_cell(item.get('name'))}` | `{_md_cell(item.get('value'))}` | "
            f"`{_md_cell(item.get('candidate_value') or 'none')}` | {_md_cell(item.get('note') or '')} |"
        )

    command_defaults = payload.get("command_defaults") or []
    if command_defaults:
        lines.extend(["", "## Command Defaults", "", "```bash"])
        for item in command_defaults:
            lines.append(f'export {item.get("name")}="{item.get("value")}"')
        lines.extend(["```"])

    blocked_refresh = payload.get("blocked_evidence_refresh_commands") or []
    if blocked_refresh:
        lines.extend(["", "## Blocked Evidence Refresh", ""])
        for item in blocked_refresh:
            lines.extend(
                [
                    f"### `{item.get('id')}`",
                    "",
                    f"- When: {item.get('when')}",
                    f"- Evidence: {item.get('evidence')}",
                    "",
                    "```bash",
                    *list(item.get("commands") or []),
                    "```",
                    "",
                ]
            )

    lines.extend(["", "## Next Commands", "", "```bash", *payload.get("next_commands", []), "```"])
    lines.extend(["", "## Open Blockers", ""])
    blockers = payload.get("open_blockers") or []
    if blockers:
        for blocker in blockers:
            values = ", ".join(f"`{value}`" for value in blocker.get("blockers") or []) or "`none`"
            lines.append(f"- `{blocker.get('id')}`: {values}")
    else:
        lines.append("- `none`")

    lines.extend(["", "## Blocker Clearance Plan", "", "| Blocker | Operator action | Evidence to expect |", "|---|---|---|"])
    for item in payload.get("blocker_clearance_plan") or []:
        lines.append(
            f"| `{_md_cell(item.get('id'))}` | {_md_cell(item.get('action'))} | "
            f"{_md_cell(item.get('evidence'))} |"
        )

    lines.extend(["", "## Source Artifacts", ""])
    for key, value in (payload.get("source_artifacts") or {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_launch_unblock_inputs() -> tuple[Path, Path, dict[str, Any]]:
    payload = build_launch_unblock_inputs()
    report_dir = ROOT / "reports" / "launch"
    json_path = report_dir / "unblock_inputs.json"
    md_path = report_dir / "unblock_inputs.md"
    _write_json(json_path, payload)
    _write_markdown(md_path, payload)
    return json_path, md_path, payload


def main() -> int:
    json_path, md_path, payload = write_launch_unblock_inputs()
    print(
        json.dumps(
            {
                "unblock_inputs_json": str(json_path),
                "unblock_inputs_md": str(md_path),
                "required_shell_exports": [
                    item.get("name") for item in payload.get("required_shell_exports", [])
                ],
                "required_dashboard_inputs": [
                    item.get("name") for item in payload.get("required_dashboard_inputs", [])
                ],
                "open_blocker_count": len(payload.get("open_blockers") or []),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
