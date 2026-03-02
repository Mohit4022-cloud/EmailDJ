from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from evals.checks import evaluate_case
from evals.io import load_cases, load_smoke_ids, write_reports
from evals.models import EvalResult, REQUIRED_VIOLATION_CODES, ScorecardSummary, Violation
from email_generation.remix_engine import build_draft, create_session_payload


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
    parser.add_argument("--allow-failures", action="store_true", help="Always exit zero")
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
        return EvalResult(
            id=case.id,
            tags=case.tags,
            passed=not violations,
            duration_ms=duration_ms,
            mode=mode,
            subject=subject,
            body=body,
            draft=draft_result.draft,
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

    cases = load_cases(Path(args.dataset))
    selected = _select_cases(args, cases)
    if not selected:
        print("No cases selected. Check --mode/--tag/--id filters.", file=sys.stderr)
        return 2

    if args.mode == "smoke" and len(selected) != 10:
        print(f"Smoke run expected 10 cases, selected {len(selected)}.", file=sys.stderr)
        return 2

    results: list[EvalResult] = []
    for case in selected:
        result = await _run_case(case=case, mode=mode)
        results.append(result)

    summary, top_failures = _compute_summary(results)
    latest_json, latest_md = write_reports(
        Path(args.report_dir),
        mode=mode,
        selection_mode=args.mode,
        selected_tags=[tag for tag in args.tag if tag.strip()],
        summary=summary,
        results=results,
        top_failures=top_failures,
    )

    print("Lock Compliance Scorecard")
    print(f"- Cases: {summary.total_cases}")
    print(f"- Passed: {summary.passed_cases}")
    print(f"- Failed: {summary.failed_cases}")
    print(f"- Pass rate: {summary.pass_rate:.2%}")
    print(f"- Report JSON: {latest_json}")
    print(f"- Report MD: {latest_md}")

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
