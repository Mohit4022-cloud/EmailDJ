from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from email_generation.model_defaults import default_openai_model
from evals.checks import evaluate_case
from evals.judge.actions import derive_repair_actions
from evals.judge.cache import JudgeCache
from evals.judge.client import JudgeClient, JudgeRuntime
from evals.models import EvalCase, EvalExpected


def _parse_args() -> argparse.Namespace:
    default_model = default_openai_model()
    parser = argparse.ArgumentParser(description="Run judge sanity sentinel suite.")
    parser.add_argument("--sentinel", default="evals/judge/sentinel_cases.v1.json")
    parser.add_argument("--report-dir", default="reports/judge/sanity")
    parser.add_argument("--judge-mode", choices=("mock", "real"), default=os.environ.get("EMAILDJ_JUDGE_MODE", "mock"))
    parser.add_argument("--judge-model", default=os.environ.get("EMAILDJ_JUDGE_MODEL", default_model))
    parser.add_argument(
        "--judge-model-version",
        default=(
            os.environ.get("EMAILDJ_JUDGE_MODEL_VERSION", "").strip()
            or os.environ.get("EMAILDJ_JUDGE_MODEL", default_model).strip()
            or default_model
        ),
    )
    parser.add_argument("--judge-sample-count", type=int, default=int(os.environ.get("EMAILDJ_JUDGE_SAMPLE_COUNT", "1")))
    parser.add_argument("--judge-cache-dir", default="reports/judge/cache")
    parser.add_argument("--allow-failures", action="store_true")
    return parser.parse_args()


def _to_eval_case(row: dict[str, Any]) -> EvalCase:
    offer_lock = str(row.get("offer_lock", "")).strip()
    cta_lock = str(row.get("cta_lock", "")).strip()
    prospect_role = str(row.get("prospect_role", "")).strip() or "VP Sales"
    prospect_company = str(row.get("prospect_company", "")).strip() or "Acme"
    other_products = [str(item).strip() for item in row.get("other_products", []) if str(item).strip()]
    body = str(row.get("body", ""))
    first_name = _expected_first_name_from_body(body) or "Alex"
    expected = EvalExpected(
        must_include=[offer_lock, cta_lock] if offer_lock and cta_lock else [offer_lock] if offer_lock else [],
        must_not_include=other_products,
        greeting_first_name=first_name,
    )
    return EvalCase(
        id=str(row.get("id", "")).strip(),
        tags=[str(row.get("bucket", "sentinel")).strip() or "sentinel"],
        prospect={"full_name": "Alex Doe", "title": prospect_role, "company": prospect_company},
        seller={"company_name": "EmailDJ", "company_url": "https://emaildj.ai", "company_notes": ""},
        offer_lock=offer_lock,
        cta_lock=cta_lock,
        cta_type="time_ask",
        style_profile={"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0},
        research_text=str(row.get("allowed_facts_summary", "")),
        other_products=other_products,
        expected=expected,
        approved_proof_points=[],
    )


def _expected_first_name_from_body(body: str) -> str:
    first_line = next((line.strip() for line in (body or "").splitlines() if line.strip()), "")
    match = re.match(r"^(Hi|Hello|Hey)\s+([^,\n]+),", first_line, flags=re.IGNORECASE)
    if not match:
        return ""
    candidate = str(match.group(2)).strip()
    if " " in candidate:
        return candidate.split(" ", 1)[0]
    return candidate


def _draft(row: dict[str, Any]) -> str:
    subject = str(row.get("subject", "")).strip()
    body = str(row.get("body", "")).strip()
    return f"Subject: {subject}\nBody:\n{body}".strip()


def _context(row: dict[str, Any]) -> dict[str, str]:
    return {
        "prospect_role": str(row.get("prospect_role", "")),
        "prospect_company": str(row.get("prospect_company", "")),
        "offer_lock": str(row.get("offer_lock", "")),
        "cta_lock": str(row.get("cta_lock", "")),
        "allowed_facts_summary": str(row.get("allowed_facts_summary", "")),
        "tone_target": str(row.get("tone_target", "professional, balanced")),
    }


def main() -> int:
    args = _parse_args()
    data = json.loads(Path(args.sentinel).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Sentinel file must be a list.")
    sentinels = [row for row in data if isinstance(row, dict)]

    cache = JudgeCache(Path(args.judge_cache_dir))
    client = JudgeClient(
        cache=cache,
        runtime=JudgeRuntime(
            mode=(args.judge_mode.strip().lower() or "mock"),
            model=(args.judge_model.strip() or default_openai_model()),
            timeout_seconds=float(os.environ.get("EMAILDJ_JUDGE_TIMEOUT_SEC", "30")),
            sample_count=max(1, int(args.judge_sample_count)),
            model_version=(args.judge_model_version.strip() or args.judge_model.strip() or default_openai_model()),
            secondary_model=(os.environ.get("EMAILDJ_JUDGE_SECONDARY_MODEL", "").strip() or None),
        ),
    )

    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for row in sentinels:
        sid = str(row.get("id", "")).strip()
        case = _to_eval_case(row)
        subject, body, violations = evaluate_case(case=case, draft=_draft(row))
        lock_pass = len(violations) == 0
        expected_lock_pass = bool(row.get("expected_lock_pass", True))

        record: dict[str, Any] = {
            "id": sid,
            "bucket": str(row.get("bucket", "")),
            "expected_lock_pass": expected_lock_pass,
            "actual_lock_pass": lock_pass,
            "lock_violations": [v.code for v in violations],
            "assertions_passed": True,
            "messages": [],
        }

        if lock_pass != expected_lock_pass:
            record["assertions_passed"] = False
            message = f"Lock pass mismatch (expected {expected_lock_pass}, got {lock_pass})"
            record["messages"].append(message)
            failures.append(f"{sid}: {message}")

        if lock_pass:
            judged = client.evaluate_ad_hoc(
                case_id=sid,
                context=_context(row),
                subject=subject,
                body=body,
                candidate_id="sentinel",
                eval_mode="sanity",
            )
            judged["repair_actions"] = derive_repair_actions(judged)
            record["judge"] = judged

            expected_pf = str(row.get("expected_pass_fail", "")).strip().lower()
            if expected_pf in {"pass", "fail"} and judged.get("pass_fail") != expected_pf:
                record["assertions_passed"] = False
                message = f"Pass/fail mismatch (expected {expected_pf}, got {judged.get('pass_fail')})"
                record["messages"].append(message)
                failures.append(f"{sid}: {message}")

            required_flags = [str(item).strip() for item in row.get("required_flags", []) if str(item).strip()]
            missing_flags = [flag for flag in required_flags if flag not in set(judged.get("flags", []))]
            if missing_flags:
                record["assertions_passed"] = False
                message = f"Missing required flags: {', '.join(missing_flags)}"
                record["messages"].append(message)
                failures.append(f"{sid}: {message}")

            overall = float(judged.get("overall", 0.0))
            min_overall = row.get("expected_overall_min")
            max_overall = row.get("expected_overall_max")
            if isinstance(min_overall, (int, float)) and overall < float(min_overall):
                record["assertions_passed"] = False
                message = f"Overall score below min ({overall:.2f} < {float(min_overall):.2f})"
                record["messages"].append(message)
                failures.append(f"{sid}: {message}")
            if isinstance(max_overall, (int, float)) and overall > float(max_overall):
                record["assertions_passed"] = False
                message = f"Overall score above max ({overall:.2f} > {float(max_overall):.2f})"
                record["messages"].append(message)
                failures.append(f"{sid}: {message}")
        else:
            record["judge"] = {
                "status": "skipped_hard_fail",
                "reason": "Lock checks failed; judge intentionally skipped.",
            }

        rows.append(record)

    passed = sum(1 for row in rows if row.get("assertions_passed"))
    total = len(rows)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "judge_model": args.judge_model,
        "judge_model_version": args.judge_model_version,
        "judge_mode": args.judge_mode,
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "results": rows,
        "failures": failures,
    }
    out_dir = Path(args.report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    latest = out_dir / "latest.json"
    latest.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Judge Sanity Suite")
    print(f"- Cases: {total}")
    print(f"- Passed: {passed}")
    print(f"- Failed: {total - passed}")
    print(f"- Report: {latest}")
    if failures:
        print("- Failures:")
        for item in failures[:10]:
            print(f"  - {item}")

    if args.allow_failures:
        return 0
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
