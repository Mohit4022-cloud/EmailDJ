from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify judge determinism and cache correctness.")
    parser.add_argument("--report-dir", default="reports")
    parser.add_argument("--out-dir", default="reports/judge/stability")
    parser.add_argument("--judge-mode", choices=("mock", "real"), default="mock")
    parser.add_argument("--judge-model", default="gpt-4.1-nano")
    parser.add_argument("--judge-sample-count", type=int, default=1)
    parser.add_argument("--pairwise-model", default="gpt-4.1-nano")
    return parser.parse_args()


def _run_smoke(root: Path, env: dict[str, str]) -> dict[str, Any]:
    cmd = [str(root / "scripts" / "eval:judge:smoke")]
    subprocess.run(cmd, cwd=str(root), env=env, check=True)
    return json.loads((root / "reports" / "latest.json").read_text(encoding="utf-8"))


def _run_pairwise(root: Path, *, report_a: Path, report_b: Path, env: dict[str, str]) -> dict[str, Any]:
    cmd = [
        str(root / "scripts" / "eval:judge:pairwise"),
        "--a-report",
        str(report_a),
        "--b-report",
        str(report_b),
        "--label-a",
        "A",
        "--label-b",
        "B",
        "--judge-mode",
        env.get("EMAILDJ_JUDGE_MODE", "mock"),
        "--judge-model",
        env.get("EMAILDJ_JUDGE_MODEL", "gpt-4.1-nano"),
    ]
    subprocess.run(cmd, cwd=str(root), env=env, check=True)
    return json.loads((root / "reports" / "judge" / "pairwise_latest.json").read_text(encoding="utf-8"))


def _aggregate_signature(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("judge", {}).get("summary", {})
    return {
        "evaluated_cases": summary.get("evaluated_cases"),
        "failed_cases": summary.get("failed_cases"),
        "pass_rate": summary.get("pass_rate"),
        "mean_overall": summary.get("mean_overall"),
        "mean_credibility": summary.get("mean_credibility"),
    }


def _case_signatures(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in report.get("results", []):
        cid = str(row.get("id", "")).strip()
        if not cid:
            continue
        judge = row.get("judge", {})
        out[cid] = {
            "status": judge.get("status"),
            "overall": judge.get("overall"),
            "pass_fail": judge.get("pass_fail"),
            "scores": judge.get("scores"),
            "flags": sorted(judge.get("flags", [])),
        }
    return out


def _cache_rate(report: dict[str, Any]) -> float:
    summary = report.get("judge", {}).get("summary", {})
    lookups = int(summary.get("cache_lookups", 0) or 0)
    hits = int(summary.get("cache_hits", 0) or 0)
    return (hits / lookups) if lookups else 0.0


def _pairwise_order_map(report: dict[str, Any]) -> dict[str, bool]:
    return {str(row.get("id")): bool(row.get("order_swapped", False)) for row in report.get("results", []) if row.get("id")}


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parents[2]
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = root / args.report_dir / "judge" / "stability_cache"
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    base_env = os.environ.copy()
    base_env.update(
        {
            "EMAILDJ_JUDGE_MODE": args.judge_mode,
            "EMAILDJ_JUDGE_MODEL": args.judge_model,
            "EMAILDJ_JUDGE_SAMPLE_COUNT": str(args.judge_sample_count),
            "EMAILDJ_JUDGE_CACHE_DIR": str(cache_dir),
            "EMAILDJ_JUDGE_CANDIDATE_ID": "stability-check",
            "EMAILDJ_JUDGE_RUBRIC_VERSION": "enterprise_outbound_v1",
            "EMAILDJ_JUDGE_PAIRWISE_SEED": "seed-123",
        }
    )

    run1 = _run_smoke(root, base_env)
    (out_dir / "run1.json").write_text(json.dumps(run1, indent=2), encoding="utf-8")
    run2 = _run_smoke(root, base_env)
    (out_dir / "run2.json").write_text(json.dumps(run2, indent=2), encoding="utf-8")

    aggregate_identical = _aggregate_signature(run1) == _aggregate_signature(run2)
    case_identical = _case_signatures(run1) == _case_signatures(run2)
    run2_cache_rate = _cache_rate(run2)

    rubric_env = dict(base_env)
    rubric_env["EMAILDJ_JUDGE_RUBRIC_VERSION"] = "enterprise_outbound_v1_rubric_bump"
    rubric_run = _run_smoke(root, rubric_env)
    (out_dir / "run_rubric_bump.json").write_text(json.dumps(rubric_run, indent=2), encoding="utf-8")
    rubric_cache_rate = _cache_rate(rubric_run)

    model_env = dict(base_env)
    model_env["EMAILDJ_JUDGE_MODEL"] = "gpt-4.1-mini"
    model_run = _run_smoke(root, model_env)
    (out_dir / "run_model_bump.json").write_text(json.dumps(model_run, indent=2), encoding="utf-8")
    model_cache_rate = _cache_rate(model_run)

    baseline_path = out_dir / "run2.json"
    pair_seed_1 = _run_pairwise(root, report_a=baseline_path, report_b=baseline_path, env=base_env)
    (out_dir / "pair_seed_1_a.json").write_text(json.dumps(pair_seed_1, indent=2), encoding="utf-8")
    pair_seed_1_repeat = _run_pairwise(root, report_a=baseline_path, report_b=baseline_path, env=base_env)
    (out_dir / "pair_seed_1_b.json").write_text(json.dumps(pair_seed_1_repeat, indent=2), encoding="utf-8")
    pair_seed_1_deterministic = _pairwise_order_map(pair_seed_1) == _pairwise_order_map(pair_seed_1_repeat)

    seed2_env = dict(base_env)
    seed2_env["EMAILDJ_JUDGE_PAIRWISE_SEED"] = "seed-456"
    pair_seed_2 = _run_pairwise(root, report_a=baseline_path, report_b=baseline_path, env=seed2_env)
    (out_dir / "pair_seed_2.json").write_text(json.dumps(pair_seed_2, indent=2), encoding="utf-8")
    pair_seed_changed = _pairwise_order_map(pair_seed_1) != _pairwise_order_map(pair_seed_2)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "checks": {
            "same_inputs_same_aggregate_scores": aggregate_identical,
            "same_inputs_same_per_case_scores": case_identical,
            "second_run_cache_hit_rate": round(run2_cache_rate, 4),
            "rubric_version_bump_cache_hit_rate": round(rubric_cache_rate, 4),
            "judge_model_bump_cache_hit_rate": round(model_cache_rate, 4),
            "pairwise_fixed_seed_deterministic": pair_seed_1_deterministic,
            "pairwise_seed_change_changes_order_plan": pair_seed_changed,
        },
        "notes": {
            "expected_cache_behavior": "Run2 should be mostly/all cache hits. Rubric/model bump should force recompute (low cache hit rate).",
            "same_inputs_contract_hash": run2.get("judge", {}).get("summary", {}).get("prompt_contract_hash"),
            "rubric_bump_contract_hash": rubric_run.get("judge", {}).get("summary", {}).get("prompt_contract_hash"),
            "model_bump_contract_hash": model_run.get("judge", {}).get("summary", {}).get("prompt_contract_hash"),
        },
    }

    latest = out_dir / "latest.json"
    latest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("Judge Stability Check")
    print(f"- Same aggregate scores: {aggregate_identical}")
    print(f"- Same per-case scores: {case_identical}")
    print(f"- Run2 cache hit rate: {run2_cache_rate:.2%}")
    print(f"- Rubric bump cache hit rate: {rubric_cache_rate:.2%}")
    print(f"- Model bump cache hit rate: {model_cache_rate:.2%}")
    print(f"- Pairwise fixed seed deterministic: {pair_seed_1_deterministic}")
    print(f"- Pairwise seed change alters order plan: {pair_seed_changed}")
    print(f"- Report: {latest}")

    ok = all(
        [
            aggregate_identical,
            case_identical,
            run2_cache_rate >= 0.8,
            rubric_cache_rate <= 0.2,
            model_cache_rate <= 0.2,
            pair_seed_1_deterministic,
            pair_seed_changed,
        ]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

