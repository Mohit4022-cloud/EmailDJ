from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.config import load_settings
from app.engine.ai_orchestrator import AIOrchestrator
from app.engine.tracer import Trace
from app.openai_client import OpenAIClient
from app.schemas import WebGenerateRequest

from .eval_payloads import get_all_payloads, get_payload, get_payloads_by_type
from .eval_report import build_report, render_stdout_summary, write_report_json
from .stage_judge import (
    STAGE_NAME_MAP,
    judge_angle_set,
    judge_email_draft,
    judge_fit_map,
    judge_message_atoms,
    judge_messaging_brief,
    judge_qa_report,
    judge_rewritten_draft,
)


STAGE_ORDER = [
    "CONTEXT_SYNTHESIS",
    "FIT_REASONING",
    "ANGLE_PICKER",
    "ONE_LINER_COMPRESSOR",
    "EMAIL_GENERATION",
    "EMAIL_QA",
    "EMAIL_REWRITE",
]

ARTIFACT_KEY_BY_STAGE = {
    "CONTEXT_SYNTHESIS": "messaging_brief",
    "FIT_REASONING": "fit_map",
    "ANGLE_PICKER": "angle_set",
    "ONE_LINER_COMPRESSOR": "message_atoms",
    "EMAIL_GENERATION": "email_draft",
    "EMAIL_QA": "qa_report",
    "EMAIL_REWRITE": "rewritten_draft",
}

PAYLOAD_TYPE_ALIASES = {
    "high_signal": "high_signal",
    "medium_signal": "medium_signal",
    "thin_input": "thin_input",
    "thin": "thin_input",
    "edge_case": "edge_case",
    "edge": "edge_case",
    "diverse_persona": "diverse_persona",
    "diverse": "diverse_persona",
    "emaildj": "emaildj",
    "seller_proof_rich": "seller_proof_rich",
    "seller_proof": "seller_proof_rich",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run EmailDJ eval harness and stage judges.")
    parser.add_argument("--payloads", default="all", help="all | high_signal | thin | edge | emaildj | <payload_id>")
    parser.add_argument("--stages", default="all", help="all | a | b | b0 | c0 | c | d | e (or comma-separated)")
    parser.add_argument("--golden", action="store_true", help="Compare against golden set if present")
    parser.add_argument("--raw", action="store_true", help="Enable DEBUG_TRACE_RAW for this run")
    parser.add_argument("--report", default="", help="Report output path")
    parser.add_argument("--fail-fast", action="store_true", help="Stop after first payload overall failure")
    parser.add_argument("--lock-golden", action="store_true", help="Write passing payload results into golden set")
    return parser.parse_args()


def _resolve_payloads(selector: str) -> list[dict[str, Any]]:
    needle = str(selector or "all").strip().lower()
    if needle == "all":
        return get_all_payloads()
    payload_type = PAYLOAD_TYPE_ALIASES.get(needle)
    if payload_type:
        return get_payloads_by_type(payload_type)
    payload = get_payload(needle)
    if payload:
        return [payload]
    raise ValueError(f"unknown_payload_selector:{selector}")


def _resolve_stages(selector: str) -> list[str]:
    needle = str(selector or "all").strip().lower()
    if needle == "all":
        return list(STAGE_ORDER)

    selected: list[str] = []
    tokens = [part.strip().lower() for part in needle.split(",") if part.strip()]
    for token in tokens:
        if token in STAGE_NAME_MAP:
            stage_name = STAGE_NAME_MAP[token]
        elif token in STAGE_ORDER:
            stage_name = token
        else:
            raise ValueError(f"unknown_stage_selector:{token}")
        if stage_name not in selected:
            selected.append(stage_name)

    if not selected:
        raise ValueError("empty_stage_selection")
    return selected


def _find_raw_trace_path(trace_id: str) -> Path | None:
    debug_root = _BACKEND_ROOT / "debug_traces"
    candidates = list(debug_root.glob(f"*/_raw/{trace_id}.json"))
    if not candidates:
        return None
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0]


def _load_raw_trace(trace_id: str) -> dict[str, Any] | None:
    path = _find_raw_trace_path(trace_id)
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _extract_stage_artifacts(raw_trace: dict[str, Any] | None) -> dict[str, Any]:
    artifacts = {
        key: {
            "artifact": None,
            "status": "artifact_missing",
            "error_code": None,
            "raw_output": None,
            "raw_output_artifact": None,
            "artifact_views": {},
        }
        for key in ARTIFACT_KEY_BY_STAGE.values()
    }
    if not isinstance(raw_trace, dict):
        return artifacts

    stage_payloads = raw_trace.get("stage_payloads") if isinstance(raw_trace.get("stage_payloads"), list) else []
    for item in stage_payloads:
        if not isinstance(item, dict):
            continue
        stage = str(item.get("stage") or "")
        artifact_key = ARTIFACT_KEY_BY_STAGE.get(stage)
        if not artifact_key:
            continue
        status = str(item.get("status") or "")
        output = item.get("output")
        raw_output = item.get("raw_output")
        raw_output_artifact = item.get("raw_output_artifact")
        artifact_views = item.get("artifact_views") if isinstance(item.get("artifact_views"), dict) else {}
        slot = artifacts[artifact_key]
        stage_a_artifact = None
        if artifact_key == "messaging_brief":
            stage_a_artifact = artifact_views.get("sanitized_stage_a_artifact") or artifact_views.get("raw_stage_a_artifact")

        if status == "complete":
            completed_artifact = output if isinstance(output, dict) else None
            if completed_artifact is None and isinstance(raw_output_artifact, dict):
                completed_artifact = raw_output_artifact
            if completed_artifact is None and isinstance(stage_a_artifact, dict):
                completed_artifact = stage_a_artifact
            if completed_artifact is None:
                continue
            slot["artifact"] = completed_artifact
            slot["status"] = "complete_artifact"
            slot["error_code"] = None
            slot["raw_output"] = raw_output
            slot["raw_output_artifact"] = raw_output_artifact if isinstance(raw_output_artifact, dict) else None
            slot["artifact_views"] = artifact_views
            continue

        if status != "failed" or slot["status"] == "complete_artifact":
            continue

        artifact_status = str(item.get("artifact_status") or "").strip() or "artifact_missing"
        failed_output = output if isinstance(output, dict) else None
        if failed_output is None and isinstance(raw_output_artifact, dict):
            failed_output = raw_output_artifact
        if failed_output is None and isinstance(stage_a_artifact, dict):
            failed_output = stage_a_artifact
        if failed_output is None and isinstance(raw_output, str):
            try:
                parsed_raw = json.loads(raw_output)
            except json.JSONDecodeError:
                parsed_raw = None
            if isinstance(parsed_raw, dict):
                failed_output = parsed_raw
        slot["status"] = artifact_status
        slot["error_code"] = str(item.get("error_code") or "").strip() or None
        slot["raw_output"] = raw_output if isinstance(raw_output, str) else None
        slot["raw_output_artifact"] = raw_output_artifact if isinstance(raw_output_artifact, dict) else None
        slot["artifact_views"] = artifact_views
        if failed_output is not None:
            slot["artifact"] = failed_output

    return artifacts


def _selected_angle(angle_set: dict[str, Any] | None, atoms: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(angle_set, dict):
        return None
    angles = [item for item in angle_set.get("angles") or [] if isinstance(item, dict)]
    if not angles:
        return None
    selected_id = str((atoms or {}).get("selected_angle_id") or "").strip()
    if selected_id:
        for angle in angles:
            if str(angle.get("angle_id") or "") == selected_id:
                return angle
    return angles[0]


def _proof_gap_from_atoms(atoms: dict[str, Any] | None) -> bool:
    if not isinstance(atoms, dict):
        return True
    return str(atoms.get("proof_atom") or atoms.get("proof_line") or "").strip() == ""


def _cta_lock_from_request(request: WebGenerateRequest) -> str:
    return str(request.cta_offer_lock or request.company_context.cta_offer_lock or "Open to a quick chat to see if this is relevant?").strip()


def _empty_judge_results() -> dict[str, Any]:
    return {
        "CONTEXT_SYNTHESIS": None,
        "FIT_REASONING": None,
        "ANGLE_PICKER": None,
        "ONE_LINER_COMPRESSOR": None,
        "EMAIL_GENERATION": None,
        "EMAIL_QA": None,
        "EMAIL_REWRITE": None,
    }


def _hard_fail_union(judge_results: dict[str, Any]) -> tuple[bool, list[str]]:
    criteria: list[str] = []
    triggered = False
    for result in judge_results.values():
        if not isinstance(result, dict):
            continue
        if bool(result.get("hard_fail_triggered")):
            triggered = True
        for criterion in result.get("hard_fail_criteria") or []:
            criterion_text = str(criterion or "").strip()
            if criterion_text and criterion_text not in criteria:
                criteria.append(criterion_text)
    return triggered, criteria


def _all_selected_pass(judge_results: dict[str, Any], selected_stages: list[str]) -> bool:
    for stage in selected_stages:
        result = judge_results.get(stage)
        if not isinstance(result, dict):
            return False
        if not bool(result.get("pass")):
            return False
    return True


def _golden_dir() -> Path:
    return _BACKEND_ROOT / "evals" / "golden"


def _load_golden_result(payload_id: str) -> dict[str, Any] | None:
    path = _golden_dir() / f"{payload_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _compare_payload_against_golden(current: dict[str, Any], golden: dict[str, Any]) -> tuple[bool, bool]:
    improved = False
    regressed = False

    current_judges = current.get("judge_results") if isinstance(current.get("judge_results"), dict) else {}
    golden_judges = golden.get("judge_results") if isinstance(golden.get("judge_results"), dict) else {}

    for stage in STAGE_ORDER:
        current_result = current_judges.get(stage)
        golden_result = golden_judges.get(stage)
        if not isinstance(current_result, dict) or not isinstance(golden_result, dict):
            continue

        current_scores = current_result.get("scores") if isinstance(current_result.get("scores"), dict) else {}
        golden_scores = golden_result.get("scores") if isinstance(golden_result.get("scores"), dict) else {}
        all_criteria = set(current_scores.keys()) | set(golden_scores.keys())

        for criterion in all_criteria:
            c_score = int(current_scores.get(criterion) or 0)
            g_score = int(golden_scores.get(criterion) or 0)
            if g_score == 1 and c_score == 0:
                regressed = True
            elif g_score == 0 and c_score == 1:
                improved = True

    return improved, regressed


def _compute_regression_summary(payload_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    improved_ids: list[str] = []
    regressed_ids: list[str] = []
    unchanged_ids: list[str] = []
    compared = 0

    for result in payload_results:
        payload_id = str(result.get("payload_id") or "")
        golden = _load_golden_result(payload_id)
        if golden is None:
            continue
        compared += 1
        improved, regressed = _compare_payload_against_golden(result, golden)
        if regressed:
            regressed_ids.append(payload_id)
        elif improved:
            improved_ids.append(payload_id)
        else:
            unchanged_ids.append(payload_id)

    if compared == 0:
        return None

    return {
        "improved": improved_ids,
        "regressed": regressed_ids,
        "unchanged": unchanged_ids,
        "net_delta": len(improved_ids) - len(regressed_ids),
    }


def _maybe_lock_golden(payload_results: list[dict[str, Any]]) -> int:
    out_dir = _golden_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for result in payload_results:
        if not bool(result.get("overall_pass")):
            continue
        payload_id = str(result.get("payload_id") or "").strip()
        if not payload_id:
            continue
        path = out_dir / f"{payload_id}.json"
        path.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
        written += 1
    return written


async def _evaluate_payload(
    *,
    payload: dict[str, Any],
    orchestrator: AIOrchestrator,
    openai: OpenAIClient,
    settings: Any,
    selected_stages: list[str],
    run_id: str,
    read_raw: bool,
) -> dict[str, Any]:
    request = WebGenerateRequest(**dict(payload.get("request") or {}))
    sliders = request.sliders.model_dump(mode="json") if request.sliders else None

    trace = Trace(str(uuid4()), settings.app_env, debug_trace_raw=bool(read_raw))
    pipeline = await orchestrator.run_pipeline_single(
        request=request,
        trace=trace,
        preset_id=request.preset_id,
        sliders=sliders,
    )

    raw_trace = _load_raw_trace(pipeline.trace_id) if read_raw else None
    artifacts = _extract_stage_artifacts(raw_trace)

    brief = artifacts["messaging_brief"]["artifact"]
    fit_map = artifacts["fit_map"]["artifact"]
    angle_set = artifacts["angle_set"]["artifact"]
    atoms = artifacts["message_atoms"]["artifact"]
    draft = artifacts["email_draft"]["artifact"]
    qa_report = artifacts["qa_report"]["artifact"]
    rewritten = artifacts["rewritten_draft"]["artifact"]

    locked_cta = _cta_lock_from_request(request)
    angle = _selected_angle(angle_set, atoms)
    proof_gap = _proof_gap_from_atoms(atoms)

    judge_results = _empty_judge_results()

    for stage in selected_stages:
        if stage == "CONTEXT_SYNTHESIS":
            judge_results[stage] = await judge_messaging_brief(
                brief,
                payload.get("request") if isinstance(payload.get("request"), dict) else {},
                artifact_views=artifacts["messaging_brief"].get("artifact_views"),
                openai=openai,
                run_id=run_id,
                payload_id=str(payload.get("payload_id") or ""),
            )
        elif stage == "FIT_REASONING":
            judge_results[stage] = await judge_fit_map(
                fit_map,
                brief,
                openai=openai,
                run_id=run_id,
                payload_id=str(payload.get("payload_id") or ""),
            )
        elif stage == "ANGLE_PICKER":
            judge_results[stage] = await judge_angle_set(
                angle_set,
                brief,
                fit_map,
                openai=openai,
                run_id=run_id,
                payload_id=str(payload.get("payload_id") or ""),
            )
        elif stage == "ONE_LINER_COMPRESSOR":
            judge_results[stage] = await judge_message_atoms(
                atoms,
                brief,
                angle,
                locked_cta=locked_cta,
                openai=openai,
                run_id=run_id,
                payload_id=str(payload.get("payload_id") or ""),
            )
        elif stage == "EMAIL_GENERATION":
            judge_results[stage] = await judge_email_draft(
                draft,
                atoms,
                brief,
                cta_final_line=locked_cta,
                proof_gap=proof_gap,
                openai=openai,
                run_id=run_id,
                payload_id=str(payload.get("payload_id") or ""),
            )
        elif stage == "EMAIL_QA":
            judge_results[stage] = await judge_qa_report(
                qa_report,
                draft,
                openai=openai,
                run_id=run_id,
                payload_id=str(payload.get("payload_id") or ""),
            )
        elif stage == "EMAIL_REWRITE":
            judge_results[stage] = await judge_rewritten_draft(
                rewritten,
                draft,
                qa_report,
                atoms,
                cta_final_line=locked_cta,
                proof_gap=proof_gap,
                openai=openai,
                run_id=run_id,
                payload_id=str(payload.get("payload_id") or ""),
            )

    hard_fail_triggered, hard_fail_criteria = _hard_fail_union(judge_results)
    overall_pass = bool(pipeline.ok) and _all_selected_pass(judge_results, selected_stages) and not hard_fail_triggered

    pipeline_error = None
    if not pipeline.ok:
        error = pipeline.error if isinstance(pipeline.error, dict) else {}
        pipeline_error = {
            "code": str(error.get("code") or "UNKNOWN"),
            "stage": str(error.get("stage") or "UNKNOWN"),
            "message": str(error.get("message") or "pipeline_failed"),
        }

    return {
        "payload_id": str(payload.get("payload_id") or ""),
        "payload_type": str(payload.get("payload_type") or ""),
        "pipeline_ok": bool(pipeline.ok),
        "pipeline_error": pipeline_error,
        "trace_id": pipeline.trace_id,
        "final_subject": str(pipeline.subject or ""),
        "final_body": str(pipeline.body or ""),
        "artifact_statuses": {
            stage: str(artifacts[key].get("status") or "artifact_missing")
            for stage, key in ARTIFACT_KEY_BY_STAGE.items()
        },
        "judge_results": judge_results,
        "overall_pass": overall_pass,
        "hard_fail_triggered": hard_fail_triggered,
        "hard_fail_criteria": hard_fail_criteria,
    }


async def _run() -> int:
    args = _parse_args()

    if args.raw:
        os.environ["DEBUG_TRACE_RAW"] = "1"

    payloads = _resolve_payloads(args.payloads)
    selected_stages = _resolve_stages(args.stages)

    settings = load_settings()
    openai = OpenAIClient(settings)
    if not openai.enabled():
        print("ERROR: OpenAI provider is unavailable. Set OPENAI_API_KEY and disable USE_PROVIDER_STUB.")
        return 2

    orchestrator = AIOrchestrator(openai=openai, settings=settings)

    run_timestamp = datetime.now(timezone.utc)
    run_id = run_timestamp.strftime("%Y%m%d_%H%M%S")

    payload_results: list[dict[str, Any]] = []
    for payload in payloads:
        result = await _evaluate_payload(
            payload=payload,
            orchestrator=orchestrator,
            openai=openai,
            settings=settings,
            selected_stages=selected_stages,
            run_id=run_id,
            read_raw=bool(args.raw),
        )
        payload_results.append(result)
        print(f"[payload] {result['payload_id']} overall_pass={result['overall_pass']} pipeline_ok={result['pipeline_ok']}")

        if args.fail_fast and not bool(result.get("overall_pass")):
            print("Fail-fast triggered.")
            break

    if args.lock_golden:
        written = _maybe_lock_golden(payload_results)
        print(f"[golden] wrote {written} payload result(s)")

    regression_vs_golden = _compute_regression_summary(payload_results) if args.golden else None

    report = build_report(
        run_id=run_id,
        run_timestamp=run_timestamp.isoformat(),
        payload_results=payload_results,
        selected_stage_names=selected_stages,
        regression_vs_golden=regression_vs_golden,
    )

    report_path = Path(args.report).expanduser() if args.report else (_BACKEND_ROOT / "evals" / "reports" / f"{run_id}.json")
    write_report_json(report, report_path)

    print(render_stdout_summary(report))
    print(f"Report JSON: {report_path}")

    return 0


def main() -> None:
    try:
        code = asyncio.run(_run())
    except KeyboardInterrupt:
        code = 130
    raise SystemExit(code)


if __name__ == "__main__":
    main()
