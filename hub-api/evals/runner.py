from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from evals.checks import evaluate_case
from evals.judge.actions import derive_repair_actions
from evals.judge.cache import JudgeCache
from evals.judge.client import JudgeClient, JudgeRuntime
from evals.judge.prompts import prompt_contract_hash
from evals.judge.redaction import redact_text
from evals.judge.reliability import calibration_metrics, load_calibration_set
from evals.judge.reporting import actionable_feedback, compute_judge_summary
from evals.io import load_cases, load_smoke_ids, write_reports
from evals.models import EvalResult, REQUIRED_VIOLATION_CODES, ScorecardSummary, Violation
from email_generation.remix_engine import build_draft, create_session_payload


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default


def _default_candidate_id() -> str:
    value = os.environ.get("EMAILDJ_JUDGE_CANDIDATE_ID", "").strip()
    if value:
        return value
    value = os.environ.get("GITHUB_SHA", "").strip()
    if value:
        return value[:12]
    return "default"


def _safe_path_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip()) or "default"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Lock Compliance Scorecard evaluation.")
    parser.add_argument("--dataset", default="evals/gold_set.full.json")
    parser.add_argument("--smoke", default="evals/gold_set.smoke_ids.json")
    parser.add_argument("--report-dir", default="reports")
    parser.add_argument("--mode", choices=("smoke", "full", "focus"), default="full")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--id", action="append", default=[])
    parser.add_argument("--real", action="store_true", help="Run with EMAILDJ_QUICK_GENERATE_MODE=real")
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument("--min-cases", type=int, default=80)
    parser.add_argument("--allow-failures", action="store_true", help="Always exit zero")
    parser.add_argument("--judge", action="store_true", help="Run LLM-as-a-judge quality evaluation.")
    parser.add_argument(
        "--judge-mode",
        choices=("mock", "real"),
        default=(os.environ.get("EMAILDJ_JUDGE_MODE", "mock").strip().lower() or "mock"),
    )
    parser.add_argument("--judge-model", default=(os.environ.get("EMAILDJ_JUDGE_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"))
    parser.add_argument("--judge-sample-count", type=int, default=_env_int("EMAILDJ_JUDGE_SAMPLE_COUNT", 1))
    parser.add_argument("--judge-cache-dir", default=(os.environ.get("EMAILDJ_JUDGE_CACHE_DIR", "reports/judge/cache").strip() or "reports/judge/cache"))
    parser.add_argument("--judge-candidate-id", default=_default_candidate_id())
    parser.add_argument("--judge-calibration", default="evals/judge/calibration_set.v2.json")
    parser.add_argument("--judge-skip-calibration", action="store_true")
    return parser.parse_args()


def _env_defaults(real: bool) -> str:
    os.environ.setdefault("REDIS_FORCE_INMEMORY", "1")
    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    if real:
        os.environ["EMAILDJ_QUICK_GENERATE_MODE"] = "real"
        return "real"
    os.environ["EMAILDJ_QUICK_GENERATE_MODE"] = "mock"
    return "mock"


def _select_cases(args: argparse.Namespace, all_cases: list[Any]) -> list[Any]:
    selected = list(all_cases)
    if args.mode == "smoke":
        smoke_ids = load_smoke_ids(Path(args.smoke))
        selected = [case for case in selected if case.id in smoke_ids]
    elif args.mode == "focus":
        if args.tag:
            tag_set = {t.strip() for t in args.tag if t.strip()}
            selected = [case for case in selected if any(tag in tag_set for tag in case.tags)]

    if args.id:
        ids = {i.strip() for i in args.id if i.strip()}
        selected = [case for case in selected if case.id in ids]

    if args.max_cases and args.max_cases > 0:
        selected = selected[: args.max_cases]
    return selected


async def _run_case(case: Any, mode: str) -> EvalResult:
    started = time.perf_counter()
    try:
        company_context = {
            "company_name": case.seller.get("company_name", "EmailDJ"),
            "company_url": case.seller.get("company_url", "https://emaildj.ai"),
            "company_notes": case.seller.get("company_notes", ""),
            "current_product": case.offer_lock,
            "other_products": ", ".join(case.other_products),
        }

        session = create_session_payload(
            prospect={
                "name": case.prospect["full_name"],
                "title": case.prospect["title"],
                "company": case.prospect["company"],
                "linkedin_url": case.prospect.get("linkedin_url", ""),
            },
            prospect_first_name=case.expected.greeting_first_name,
            research_text=case.research_text,
            initial_style=case.style_profile,
            offer_lock=case.offer_lock,
            cta_offer_lock=case.cta_lock,
            cta_type=case.cta_type,
            company_context=company_context,
        )

        draft_result = await build_draft(session=session, style_profile=case.style_profile)
        subject, body, violations = evaluate_case(case=case, draft=draft_result.draft)

        duration_ms = int((time.perf_counter() - started) * 1000)
        generation_meta = {
            "generation_mode": draft_result.mode,
            "provider": draft_result.provider,
            "model": draft_result.model_name,
            "cascade_reason": draft_result.cascade_reason,
            "provider_attempt_count": draft_result.attempt_count,
            "validator_attempt_count": draft_result.validator_attempt_count,
            "json_repair_count": draft_result.json_repair_count,
            "violation_retry_count": draft_result.violation_retry_count,
            "repaired": draft_result.repaired,
            "enforcement_level": draft_result.enforcement_level,
            "repair_loop_enabled": draft_result.repair_loop_enabled,
        }
        return EvalResult(
            id=case.id,
            tags=case.tags,
            passed=not violations,
            duration_ms=duration_ms,
            mode=mode,
            subject=subject,
            body=body,
            draft=draft_result.draft,
            generation_meta=generation_meta,
            violations=violations,
            error=None,
        )
    except Exception as exc:  # pragma: no cover - defensive for provider/runtime errors
        duration_ms = int((time.perf_counter() - started) * 1000)
        return EvalResult(
            id=case.id,
            tags=case.tags,
            passed=False,
            duration_ms=duration_ms,
            mode=mode,
            subject="",
            body="",
            draft="",
            generation_meta={},
            violations=[Violation(code="OFFER_MISSING", reason=f"Pipeline error: {exc}", snippet="")],
            error=str(exc),
        )


def _rate(passed: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return passed / total


def _compute_summary(results: list[EvalResult]) -> tuple[ScorecardSummary, list[dict[str, Any]]]:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    failure_count_by_code: Counter[str] = Counter()
    for result in results:
        for violation in result.violations:
            if violation.code in REQUIRED_VIOLATION_CODES:
                failure_count_by_code[violation.code] += 1

    violation_count = sum(failure_count_by_code.values())

    greeting_codes = {"GREET_FULL_NAME", "GREET_MISSING"}
    offer_codes = {"OFFER_MISSING", "OFFER_DRIFT", "FORBIDDEN_OTHER_PRODUCT"}
    cta_codes = {"CTA_MISMATCH", "CTA_NOT_FINAL"}
    research_codes = {"RESEARCH_INJECTION_FOLLOWED"}
    leakage_codes = {"INTERNAL_LEAKAGE"}
    claim_codes = {"UNSUPPORTED_OBJECTIVE_CLAIM"}

    def category_pass_rate(codes: set[str]) -> float:
        category_pass = 0
        for result in results:
            result_codes = {v.code for v in result.violations}
            if result_codes.isdisjoint(codes):
                category_pass += 1
        return _rate(category_pass, total)

    summary = ScorecardSummary(
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        pass_rate=_rate(passed, total),
        violation_count=violation_count,
        failure_count_by_code={code: int(count) for code, count in sorted(failure_count_by_code.items())},
        greeting_pass_rate=category_pass_rate(greeting_codes),
        offer_binding_pass_rate=category_pass_rate(offer_codes),
        cta_lock_pass_rate=category_pass_rate(cta_codes),
        research_containment_pass_rate=category_pass_rate(research_codes),
        internal_leakage_pass_rate=category_pass_rate(leakage_codes),
        claim_safety_pass_rate=category_pass_rate(claim_codes),
    )

    top_failures: list[dict[str, Any]] = []
    for code, count in failure_count_by_code.most_common(10):
        case_ids = [result.id for result in results if any(v.code == code for v in result.violations)]
        top_failures.append({"code": code, "count": int(count), "cases": case_ids[:10]})

    return summary, top_failures


async def _amain() -> int:
    args = _parse_args()
    mode = _env_defaults(real=args.real)

    cases = load_cases(Path(args.dataset), min_cases=max(0, args.min_cases))
    selected = _select_cases(args, cases)
    if not selected:
        print("No cases selected. Check --mode/--tag/--id filters.", file=sys.stderr)
        return 2

    if args.mode == "smoke" and len(selected) != 10:
        allow_reduced_smoke = bool(args.judge and args.max_cases and args.max_cases > 0)
        if not allow_reduced_smoke:
            print(f"Smoke run expected 10 cases, selected {len(selected)}.", file=sys.stderr)
            return 2

    results: list[EvalResult] = []
    case_by_id: dict[str, Any] = {}
    for case in selected:
        case_by_id[case.id] = case
        result = await _run_case(case=case, mode=mode)
        results.append(result)

    judge_summary = None
    top_quality_failures = None
    if args.judge:
        judge_cache = JudgeCache(Path(args.judge_cache_dir))
        judge_runtime = JudgeRuntime(
            mode=args.judge_mode,
            model=args.judge_model,
            timeout_seconds=float(os.environ.get("EMAILDJ_JUDGE_TIMEOUT_SEC", "30")),
            sample_count=max(1, int(args.judge_sample_count)),
            secondary_model=(os.environ.get("EMAILDJ_JUDGE_SECONDARY_MODEL", "").strip() or None),
        )
        judge_client = JudgeClient(cache=judge_cache, runtime=judge_runtime)

        for result in results:
            if not result.passed:
                result.judge = {
                    "status": "skipped_hard_fail",
                    "pass_fail": "fail",
                    "overall": 0.0,
                    "scores": {},
                    "flags": ["auto_fail_policy_or_compliance_risk"],
                    "rationale_bullets": ["Skipped quality judge because hard lock compliance failed."],
                    "repair_actions": [],
                }
                result.actionable_feedback = actionable_feedback(result)
                continue

            case = case_by_id.get(result.id)
            if case is None:
                result.judge = {
                    "status": "error",
                    "error": "missing_case_context",
                    "pass_fail": "fail",
                    "overall": 0.0,
                    "scores": {},
                    "flags": ["auto_fail_policy_or_compliance_risk"],
                    "rationale_bullets": ["Judge failed: missing case context."],
                    "repair_actions": [],
                }
                result.actionable_feedback = actionable_feedback(result)
                continue

            try:
                result.judge = judge_client.evaluate_email(
                    case=case,
                    subject=result.subject,
                    body=result.body,
                    candidate_id=args.judge_candidate_id,
                    eval_mode=args.mode,
                )
            except Exception as exc:  # pragma: no cover - runtime safety
                result.judge = {
                    "status": "error",
                    "error": str(exc),
                    "pass_fail": "fail",
                    "overall": 0.0,
                    "scores": {},
                    "flags": ["auto_fail_policy_or_compliance_risk"],
                    "rationale_bullets": ["Judge execution failed."],
                    "repair_actions": [],
                }
            result.judge["repair_actions"] = derive_repair_actions(result.judge)
            result.actionable_feedback = actionable_feedback(result)

        calibration = None
        calibration_path = Path(args.judge_calibration)
        if (not args.judge_skip_calibration) and calibration_path.exists():
            expected = load_calibration_set(str(calibration_path))
            predicted: list[dict[str, Any]] = []
            for row in expected:
                row_id = str(row.get("id", "")).strip()
                subject = redact_text(str(row.get("subject", "")))
                body = redact_text(str(row.get("body", "")))
                context = {
                    "prospect_role": redact_text(str(row.get("prospect_role", ""))),
                    "prospect_company": redact_text(str(row.get("prospect_company", ""))),
                    "offer_lock": redact_text(str(row.get("offer_lock", ""))),
                    "cta_lock": redact_text(str(row.get("cta_lock", ""))),
                    "allowed_facts_summary": redact_text(str(row.get("allowed_facts_summary", ""))),
                    "tone_target": redact_text(str(row.get("tone_target", "professional, balanced"))),
                }
                if not row_id or not body:
                    continue
                try:
                    scored = judge_client.evaluate_ad_hoc(
                        case_id=row_id,
                        context=context,
                        subject=subject,
                        body=body,
                        candidate_id="calibration",
                        eval_mode="calibration",
                    )
                    predicted.append(
                        {
                            "id": row_id,
                            "pass_fail": scored.get("pass_fail", "fail"),
                            "overall": scored.get("overall", 0.0),
                        }
                    )
                except Exception:
                    continue
            calibration = calibration_metrics(expected=expected, predicted=predicted)

        judge_summary, top_quality_failures = compute_judge_summary(
            results=results,
            model=judge_runtime.model,
            mode=judge_runtime.mode,
            prompt_contract_hash=prompt_contract_hash(),
            calibration=calibration,
        )
    else:
        for result in results:
            result.judge = {"status": "disabled", "repair_actions": []}
            result.actionable_feedback = actionable_feedback(result)

    summary, top_failures = _compute_summary(results)
    latest_json, latest_md = write_reports(
        Path(args.report_dir),
        mode=mode,
        selection_mode=args.mode,
        selected_tags=[tag for tag in args.tag if tag.strip()],
        summary=summary,
        results=results,
        top_failures=top_failures,
        judge_summary=judge_summary,
        top_quality_failures=top_quality_failures,
    )

    if args.judge and judge_summary is not None:
        artifact_root = Path(args.report_dir) / "judge" / "artifacts" / _safe_path_component(args.judge_candidate_id)
        artifact_root.mkdir(parents=True, exist_ok=True)
        artifact_json = artifact_root / f"{args.mode}.json"
        artifact_md = artifact_root / f"{args.mode}.md"
        shutil.copyfile(latest_json, artifact_json)
        shutil.copyfile(latest_md, artifact_md)
        meta = {
            "generated_at": time.time(),
            "source_report_json": str(latest_json),
            "source_report_md": str(latest_md),
            "candidate_id": args.judge_candidate_id,
            "judge_model": judge_summary.model,
            "judge_mode": judge_summary.mode,
            "prompt_contract_hash": judge_summary.prompt_contract_hash,
        }
        (artifact_root / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print("Lock Compliance Scorecard")
    print(f"- Cases: {summary.total_cases}")
    print(f"- Passed: {summary.passed_cases}")
    print(f"- Failed: {summary.failed_cases}")
    print(f"- Pass rate: {summary.pass_rate:.2%}")
    print(f"- Report JSON: {latest_json}")
    print(f"- Report MD: {latest_md}")
    if judge_summary is not None:
        print("Quality Judge")
        print(f"- Evaluated: {judge_summary.evaluated_cases}")
        print(f"- Failed: {judge_summary.failed_cases}")
        print(f"- Mean overall: {judge_summary.mean_overall:.2f}")
        print(f"- Mean credibility: {judge_summary.mean_credibility:.2f}")

    if top_failures:
        print("Top recurring failures:")
        for row in top_failures:
            print(f"  - {row['code']}: {row['count']} (e.g. {', '.join(row['cases'][:3])})")

    if args.allow_failures:
        return 0
    return 0 if summary.failed_cases == 0 else 1


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
