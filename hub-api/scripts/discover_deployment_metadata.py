#!/usr/bin/env python3
"""Record GitHub/Vercel deployment metadata as launch-handoff evidence."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent

LAUNCH_BLOCKER_NOTE = (
    "Deployment metadata only identifies candidate web origins. It does not clear launch blockers until the Hub API "
    "deployment pins WEB_APP_ORIGIN, CHROME_EXTENSION_ORIGIN, beta keys, provider mode, and fresh runtime snapshots."
)


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _run(args: list[str], *, cwd: Path) -> tuple[int, str, str]:
    completed = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _git_text(args: list[str]) -> str | None:
    code, stdout, _stderr = _run(["git", *args], cwd=REPO_ROOT)
    if code != 0:
        return None
    return stdout or None


def _repo_slug_from_remote(remote_url: str | None) -> str | None:
    if not remote_url:
        return None
    value = remote_url.strip()
    if value.endswith(".git"):
        value = value[:-4]
    if value.startswith("git@github.com:"):
        return value.split(":", 1)[1]
    parsed = urlparse(value)
    if parsed.netloc == "github.com" and parsed.path.strip("/"):
        return parsed.path.strip("/")
    return None


def _origin_from_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_vercel_origin(value: str | None) -> bool:
    origin = _origin_from_url(value)
    return bool(origin and origin.endswith(".vercel.app"))


def _status_urls(status: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in ("environment_url", "target_url", "log_url"):
        value = status.get(key)
        if isinstance(value, str) and value:
            urls.append(value)
    return urls


def _first_successful_vercel_origin(statuses: list[dict[str, Any]]) -> str | None:
    for status in statuses:
        if status.get("state") != "success":
            continue
        for value in _status_urls(status):
            origin = _origin_from_url(value)
            if _is_vercel_origin(origin):
                return origin
    return None


def _summarize_statuses(statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summarized = []
    for status in statuses[:5]:
        summarized.append(
            {
                "state": status.get("state"),
                "environment_url": status.get("environment_url"),
                "target_url": status.get("target_url"),
                "log_url": status.get("log_url"),
                "description": status.get("description"),
                "created_at": status.get("created_at"),
                "updated_at": status.get("updated_at"),
            }
        )
    return summarized


def _deployment_summary(deployment: dict[str, Any], statuses: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": deployment.get("id"),
        "environment": deployment.get("environment"),
        "ref": deployment.get("ref"),
        "sha": deployment.get("sha"),
        "task": deployment.get("task"),
        "created_at": deployment.get("created_at"),
        "updated_at": deployment.get("updated_at"),
        "successful_vercel_origin": _first_successful_vercel_origin(statuses),
        "latest_statuses": _summarize_statuses(statuses),
    }


def build_discovery_payload(
    *,
    repo_slug: str | None,
    current_sha: str | None,
    deployments: list[dict[str, Any]],
    statuses_by_deployment_id: dict[str, list[dict[str, Any]]],
    generated_at: str | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    current_head_deployments: list[dict[str, Any]] = []
    historical_production_candidates: list[dict[str, Any]] = []

    for deployment in deployments:
        deployment_id = str(deployment.get("id") or "")
        statuses = statuses_by_deployment_id.get(deployment_id, [])
        summary = _deployment_summary(deployment, statuses)
        if current_sha and deployment.get("sha") == current_sha:
            current_head_deployments.append(summary)
        if str(deployment.get("environment") or "").lower() == "production":
            origin = summary.get("successful_vercel_origin")
            if origin:
                historical_production_candidates.append(
                    {
                        "deployment_id": deployment.get("id"),
                        "sha": deployment.get("sha"),
                        "ref": deployment.get("ref"),
                        "created_at": deployment.get("created_at"),
                        "environment": deployment.get("environment"),
                        "candidate_web_app_origin": origin,
                        "operator_label": (
                            "current_head_candidate"
                            if current_sha and deployment.get("sha") == current_sha
                            else "historical_candidate_only"
                        ),
                    }
                )

    candidate_web_app_origin = None
    for deployment in current_head_deployments:
        origin = deployment.get("successful_vercel_origin")
        if origin:
            candidate_web_app_origin = origin
            break

    return {
        "generated_at": generated_at or _utc_now_text(),
        "source": "github_deployments_via_gh_api",
        "repo_slug": repo_slug,
        "current_git_sha": current_sha,
        "found": bool(current_head_deployments or historical_production_candidates),
        "current_head_deployments": current_head_deployments,
        "candidate_web_app_origin": candidate_web_app_origin,
        "usable_as_web_app_origin_candidate": bool(candidate_web_app_origin),
        "historical_production_candidates": historical_production_candidates[:5],
        "clears_launch_blockers": False,
        "launch_blocker_note": LAUNCH_BLOCKER_NOTE,
        "errors": errors or [],
    }


def _gh_api_json(path: str) -> tuple[Any | None, str | None]:
    code, stdout, stderr = _run(["gh", "api", path], cwd=REPO_ROOT)
    if code != 0:
        return None, stderr or f"gh api exited {code}"
    try:
        return json.loads(stdout), None
    except json.JSONDecodeError as exc:
        return None, f"gh api returned non-json for {path}: {exc}"


def discover_from_github() -> dict[str, Any]:
    remote_url = _git_text(["remote", "get-url", "origin"])
    repo_slug = _repo_slug_from_remote(remote_url)
    current_sha = _git_text(["rev-parse", "HEAD"])
    errors: list[str] = []

    if not repo_slug:
        errors.append("could_not_resolve_github_repo_slug_from_origin")
    if not current_sha:
        errors.append("could_not_resolve_current_git_sha")

    deployments: list[dict[str, Any]] = []
    statuses_by_deployment_id: dict[str, list[dict[str, Any]]] = {}
    if repo_slug:
        payload, error = _gh_api_json(f"repos/{repo_slug}/deployments?per_page=100")
        if error:
            errors.append(error)
        elif isinstance(payload, list):
            deployments = [item for item in payload if isinstance(item, dict)]
        else:
            errors.append("github_deployments_payload_was_not_a_list")

        for deployment in deployments[:20]:
            deployment_id = deployment.get("id")
            if deployment_id is None:
                continue
            statuses_payload, statuses_error = _gh_api_json(f"repos/{repo_slug}/deployments/{deployment_id}/statuses")
            if statuses_error:
                errors.append(f"deployment_{deployment_id}_statuses_error:{statuses_error}")
                continue
            if isinstance(statuses_payload, list):
                statuses_by_deployment_id[str(deployment_id)] = [
                    item for item in statuses_payload if isinstance(item, dict)
                ]
            else:
                errors.append(f"deployment_{deployment_id}_statuses_payload_was_not_a_list")

    return build_discovery_payload(
        repo_slug=repo_slug,
        current_sha=current_sha,
        deployments=deployments,
        statuses_by_deployment_id=statuses_by_deployment_id,
        errors=errors,
    )


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Deployment Discovery",
        "",
        f"- Generated at: `{payload.get('generated_at')}`",
        f"- Source: `{payload.get('source')}`",
        f"- Repo: `{payload.get('repo_slug')}`",
        f"- Current git sha: `{payload.get('current_git_sha')}`",
        f"- Found deployment metadata: `{payload.get('found')}`",
        f"- Candidate web app origin: `{payload.get('candidate_web_app_origin') or 'none'}`",
        f"- Usable as WEB_APP_ORIGIN candidate: `{payload.get('usable_as_web_app_origin_candidate')}`",
        f"- Clears launch blockers: `{payload.get('clears_launch_blockers')}`",
        f"- Launch blocker note: {payload.get('launch_blocker_note')}",
        "",
        "## Current HEAD Deployments",
        "",
    ]
    current_head_deployments = payload.get("current_head_deployments") or []
    if current_head_deployments:
        for deployment in current_head_deployments:
            lines.append(
                "- "
                f"`{deployment.get('id')}` "
                f"`{deployment.get('environment')}` "
                f"`{deployment.get('created_at')}` "
                f"`{deployment.get('successful_vercel_origin') or 'no-vercel-origin'}`"
            )
    else:
        lines.append("- `none`")

    lines.extend(["", "## Historical Production Candidates", ""])
    historical_candidates = payload.get("historical_production_candidates") or []
    if historical_candidates:
        for candidate in historical_candidates:
            lines.append(
                "- "
                f"`{candidate.get('deployment_id')}` "
                f"`{candidate.get('operator_label')}` "
                f"`{candidate.get('candidate_web_app_origin')}` "
                f"`{candidate.get('created_at')}`"
            )
    else:
        lines.append("- `none`")

    errors = payload.get("errors") or []
    if errors:
        lines.extend(["", "## Errors", ""])
        for error in errors:
            lines.append(f"- `{error}`")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_discovery() -> tuple[Path, Path, dict[str, Any]]:
    payload = discover_from_github()
    report_dir = ROOT / "reports" / "launch"
    json_path = report_dir / "deployment_discovery.json"
    md_path = report_dir / "deployment_discovery.md"
    _write_json(json_path, payload)
    _write_markdown(md_path, payload)
    return json_path, md_path, payload


def main() -> int:
    json_path, md_path, payload = write_discovery()
    print(
        json.dumps(
            {
                "deployment_discovery_json": str(json_path),
                "deployment_discovery_md": str(md_path),
                "found": payload.get("found"),
                "candidate_web_app_origin": payload.get("candidate_web_app_origin"),
                "clears_launch_blockers": payload.get("clears_launch_blockers"),
                "errors": payload.get("errors"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
