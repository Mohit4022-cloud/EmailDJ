#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare EmailDJ preset behavior across traces or eval reports.")
    parser.add_argument("paths", nargs="+", help="Trace files, report files, or directories containing JSON artifacts")
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected_dict_json:{path}")
    return data


def _iter_json_paths(inputs: list[str]) -> list[Path]:
    paths: list[Path] = []
    for raw in inputs:
        path = Path(raw).resolve()
        if path.is_dir():
            paths.extend(sorted(candidate for candidate in path.rglob("*.json") if candidate.is_file()))
        elif path.is_file():
            paths.append(path)
    return paths


def _find_backend_root(path: Path) -> Path | None:
    for parent in [path, *path.parents]:
        if parent.name == "backend":
            return parent
    return None


def _trace_paths_from_report(path: Path, data: dict[str, Any]) -> list[Path]:
    backend_root = _find_backend_root(path)
    if backend_root is None:
        return []
    debug_root = backend_root / "debug_traces"
    trace_paths: list[Path] = []
    for result in data.get("payload_results") or []:
        if not isinstance(result, dict):
            continue
        trace_id = str(result.get("trace_id") or "").strip()
        if not trace_id:
            continue
        candidate = next(iter(sorted(debug_root.glob(f"**/{trace_id}.json"))), None)
        if candidate is not None and candidate.parent.name != "_raw":
            trace_paths.append(candidate)
    return trace_paths


def _load_summary_and_raw(path: Path) -> tuple[Path | None, dict[str, Any] | None, Path | None, dict[str, Any] | None]:
    data = _load_json(path)
    summary_path: Path | None = None
    summary_data: dict[str, Any] | None = None
    raw_path: Path | None = None
    raw_data: dict[str, Any] | None = None

    if isinstance(data.get("payload_results"), list):
        return None, None, None, None

    if isinstance(data.get("stage_payloads"), list):
        raw_path = path
        raw_data = data
        if path.parent.name == "_raw":
            candidate = path.parent.parent / path.name
            if candidate.exists():
                summary_path = candidate
                summary_data = _load_json(candidate)
    else:
        summary_path = path
        summary_data = data
        candidate = path.parent / "_raw" / path.name
        if candidate.exists():
            raw_path = candidate
            raw_data = _load_json(candidate)

    return summary_path, summary_data, raw_path, raw_data


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _extract_stage_artifacts(raw_data: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for entry in _dict_items((raw_data or {}).get("stage_payloads")):
        stage = str(entry.get("stage") or "").strip()
        if not stage:
            continue
        artifact: dict[str, Any] | None = None
        output = entry.get("output")
        if isinstance(output, dict):
            artifact = output
        if artifact is None:
            raw_output_artifact = entry.get("raw_output_artifact")
            if isinstance(raw_output_artifact, dict):
                artifact = raw_output_artifact
        if artifact is None:
            artifact_views = entry.get("artifact_views")
            if isinstance(artifact_views, dict):
                candidate = artifact_views.get("sanitized_stage_a_artifact") or artifact_views.get("raw_stage_a_artifact")
                if isinstance(candidate, dict):
                    artifact = candidate
        if artifact is not None:
            artifacts[stage] = artifact
    return artifacts


def _normalized_brief_signature(brief: dict[str, Any] | None) -> str | None:
    if not isinstance(brief, dict):
        return None
    facts = []
    for fact in _dict_items(brief.get("facts_from_input")):
        facts.append(
            {
                "source_field": str(fact.get("source_field") or "").strip(),
                "text": str(fact.get("text") or "").strip(),
            }
        )
    hooks = []
    for hook in _dict_items(brief.get("hooks")):
        hooks.append(
            {
                "hook_id": str(hook.get("hook_id") or "").strip(),
                "hook_text": str(hook.get("hook_text") or hook.get("grounded_observation") or "").strip(),
                "supported_by_fact_ids": sorted(
                    str(item).strip()
                    for item in (hook.get("supported_by_fact_ids") or [])
                    if str(item).strip()
                ),
            }
        )
    return json.dumps({"facts": sorted(facts, key=lambda item: (item["source_field"], item["text"])), "hooks": sorted(hooks, key=lambda item: item["hook_id"])}, sort_keys=True, ensure_ascii=True)


def _cta_from_brief(brief: dict[str, Any] | None) -> str | None:
    if not isinstance(brief, dict):
        return None
    for fact in _dict_items(brief.get("facts_from_input")):
        if str(fact.get("source_field") or "").strip() == "cta_final_line":
            text = str(fact.get("text") or "").strip()
            if text:
                return text
    return None


def _last_nonempty_line(text: Any) -> str | None:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    return lines[-1] if lines else None


def _list_signature(items: list[str]) -> str | None:
    cleaned = sorted({str(item).strip() for item in items if str(item).strip()})
    return json.dumps(cleaned, ensure_ascii=True) if cleaned else None


def _build_record(path: Path) -> dict[str, Any] | None:
    summary_path, summary_data, raw_path, raw_data = _load_summary_and_raw(path)
    if summary_data is None and raw_data is None:
        return None

    summary = summary_data or {}
    trace_id = str(summary.get("trace_id") or (raw_data or {}).get("trace_id") or path.stem).strip()
    meta = summary.get("meta") if isinstance(summary.get("meta"), dict) else {}
    hashes = summary.get("hashes") if isinstance(summary.get("hashes"), dict) else {}
    artifacts = _extract_stage_artifacts(raw_data)
    brief = artifacts.get("CONTEXT_SYNTHESIS")
    atoms = artifacts.get("ONE_LINER_COMPRESSOR") or {}
    rewritten_draft = artifacts.get("EMAIL_REWRITE") or {}
    generated_draft = artifacts.get("EMAIL_GENERATION") or {}
    final_draft = rewritten_draft if rewritten_draft else generated_draft

    used_hook_ids = [
        str(item).strip()
        for item in (atoms.get("used_hook_ids") or final_draft.get("used_hook_ids") or [])
        if str(item).strip()
    ]
    selected_angle_id = str(
        atoms.get("selected_angle_id")
        or final_draft.get("selected_angle_id")
        or ""
    ).strip() or None
    required_cta_line = (
        str(atoms.get("required_cta_line") or "").strip()
        or str(atoms.get("cta_atom") or "").strip()
        or str(atoms.get("cta_line") or "").strip()
        or _cta_from_brief(brief)
    )
    required_cta_line = required_cta_line or None
    final_cta_line = _last_nonempty_line(final_draft.get("body")) or required_cta_line
    proof_text = str(atoms.get("proof_atom") or atoms.get("proof_line") or "").strip()

    outcome = summary.get("outcome") if isinstance(summary.get("outcome"), dict) else {}
    return {
        "trace_id": trace_id,
        "summary_path": str(summary_path) if summary_path else None,
        "raw_path": str(raw_path) if raw_path else None,
        "group_key": str(hashes.get("request:normalized") or trace_id),
        "preset_id": str(meta.get("preset_id") or "unknown"),
        "sliders": meta.get("sliders") if isinstance(meta.get("sliders"), dict) else {},
        "brief_signature": _normalized_brief_signature(brief),
        "used_hook_ids": sorted(set(used_hook_ids)),
        "selected_angle_id": selected_angle_id,
        "required_cta_line": required_cta_line,
        "final_cta_line": final_cta_line,
        "proof_present": bool(proof_text),
        "outcome_ok": outcome.get("ok") if isinstance(outcome.get("ok"), bool) else None,
        "artifact_gaps": sorted(stage for stage in ("CONTEXT_SYNTHESIS", "ONE_LINER_COMPRESSOR", "EMAIL_GENERATION") if stage not in artifacts),
    }


def _compare_group(records: list[dict[str, Any]]) -> dict[str, Any]:
    if len(records) < 2:
        single_record = records[0]
        issues = ["single_member_group"]
        if single_record.get("artifact_gaps"):
            issues.append("missing_stage_artifacts")
        return {
            "group_key": single_record["group_key"],
            "trace_count": len(records),
            "presets": sorted({record["preset_id"] for record in records}),
            "verdict": "insufficient_comparison",
            "issues": issues,
            "members": [
                {
                    "trace_id": single_record["trace_id"],
                    "preset_id": single_record["preset_id"],
                    "sliders": single_record["sliders"],
                    "selected_angle_id": single_record["selected_angle_id"],
                    "used_hook_ids": single_record["used_hook_ids"],
                    "required_cta_line": single_record["required_cta_line"],
                    "final_cta_line": single_record["final_cta_line"],
                    "proof_present": single_record["proof_present"],
                    "outcome_ok": single_record["outcome_ok"],
                    "artifact_gaps": single_record["artifact_gaps"],
                }
            ],
        }

    issues: list[str] = []

    brief_signatures = {record["brief_signature"] for record in records if record.get("brief_signature")}
    if len(brief_signatures) > 1:
        issues.append("brief_changed")

    hook_signatures = {
        _list_signature(record.get("used_hook_ids") or [])
        for record in records
        if record.get("used_hook_ids")
    }
    hook_signatures.discard(None)
    if len(hook_signatures) > 1:
        issues.append("hooks_changed")

    cta_locks = {record["required_cta_line"] for record in records if record.get("required_cta_line")}
    if len(cta_locks) > 1:
        issues.append("cta_changed")

    if any(
        record.get("required_cta_line")
        and record.get("final_cta_line")
        and record["required_cta_line"] != record["final_cta_line"]
        for record in records
    ):
        issues.append("cta_not_locked")

    proof_values = {record["proof_present"] for record in records}
    if len(proof_values) > 1:
        issues.append("proof_dropped")

    angle_ids = {record["selected_angle_id"] for record in records if record.get("selected_angle_id")}
    if len(angle_ids) > 1:
        issues.append("angle_changed")

    if any(record.get("artifact_gaps") for record in records):
        issues.append("missing_stage_artifacts")

    outcome_values = {record["outcome_ok"] for record in records if record.get("outcome_ok") is not None}
    if len(outcome_values) > 1:
        issues.append("mixed_pipeline_outcome")

    return {
        "group_key": records[0]["group_key"],
        "trace_count": len(records),
        "presets": sorted({record["preset_id"] for record in records}),
        "verdict": "stable" if not issues else "unexpected_drift",
        "issues": issues,
        "members": [
            {
                "trace_id": record["trace_id"],
                "preset_id": record["preset_id"],
                "sliders": record["sliders"],
                "selected_angle_id": record["selected_angle_id"],
                "used_hook_ids": record["used_hook_ids"],
                "required_cta_line": record["required_cta_line"],
                "final_cta_line": record["final_cta_line"],
                "proof_present": record["proof_present"],
                "outcome_ok": record["outcome_ok"],
                "artifact_gaps": record["artifact_gaps"],
            }
            for record in sorted(records, key=lambda item: (item["preset_id"], item["trace_id"]))
        ],
    }


def main() -> None:
    args = _parse_args()
    direct_paths = _iter_json_paths(args.paths)
    trace_paths: list[Path] = []
    for path in direct_paths:
        data = _load_json(path)
        if isinstance(data.get("payload_results"), list):
            trace_paths.extend(_trace_paths_from_report(path, data))
        else:
            trace_paths.append(path)

    records_by_trace_id: dict[str, dict[str, Any]] = {}
    for path in trace_paths:
        record = _build_record(path)
        if record is None:
            continue
        records_by_trace_id.setdefault(record["trace_id"], record)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records_by_trace_id.values():
        grouped[record["group_key"]].append(record)

    groups = [_compare_group(records) for _, records in sorted(grouped.items())]
    payload = {
        "group_count": len(groups),
        "stable_group_count": sum(group["verdict"] == "stable" for group in groups),
        "unexpected_drift_count": sum(group["verdict"] == "unexpected_drift" for group in groups),
        "insufficient_comparison_count": sum(group["verdict"] == "insufficient_comparison" for group in groups),
        "groups": groups,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
