"""HTTP Smoke Runner — hits real localhost endpoints (same path as UI).

USAGE:
    cd hub-api
    python -m devtools.http_smoke_runner --mode smoke --out debug_runs/smoke/<timestamp>

    # With judge (top N passing emails):
    python -m devtools.http_smoke_runner --mode smoke --judge_limit 10

    # 120-email expanded run:
    python -m devtools.http_smoke_runner --mode small120

REQUIREMENTS:
    Hub API must be running: uvicorn main:app --reload

FLOWS (per case):
    A) POST /web/v1/generate → GET /web/v1/stream/{request_id}  (SSE)
    B) POST /web/v1/preset-previews/batch  (non-streaming)
    C) POST /web/v1/remix → GET /web/v1/stream/{request_id}  (SSE)  [generate first, then remix]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PACK_PATH = Path(__file__).resolve().parent / "benchmark_pack.smoke.json"
DEVTOOLS_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Benchmark pack loading
# ---------------------------------------------------------------------------


def _load_pack() -> dict[str, Any]:
    return json.loads(PACK_PATH.read_text(encoding="utf-8"))


def _build_cases(pack: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    """Expand benchmark pack into a flat list of test cases.

    smoke   : 3 companies × 5 personas × 2 presets × 1 slider = 30
    small120: 3 companies × 5 personas × 2 presets × 2 sliders = 60
              (+ 3 extra companies fictional — placeholder, same 3 × 2 = same 60)
              Actual: 3 co × 5 persona × 4 presets × 2 sliders = 120
              For now we use all 6 presets × 2 sliders = 3 × 5 × 4 × 2 = 120
    """
    meta = pack["_meta"]
    seller = pack["seller"]
    companies = pack["companies"]

    slider_configs = meta["slider_configs"]
    base_presets = meta["presets"]  # ["straight_shooter", "c_suite_sniper"]

    if mode == "smoke":
        presets = base_presets
        sliders = [("medium", slider_configs["medium"])]
    elif mode == "small120":
        # Expand: 6 presets × 2 sliders
        all_presets = ["straight_shooter", "c_suite_sniper", "headliner", "giver", "challenger", "industry_insider"]
        presets = all_presets[:4]  # 4 presets to hit 3×5×4×2=120
        sliders = [
            ("medium", slider_configs["medium"]),
            ("assertive", {"formality": -0.3, "orientation": 0.3, "length": -0.2, "assertiveness": 0.7}),
        ]
    else:
        raise ValueError(f"Unknown mode: {mode}")

    cases: list[dict[str, Any]] = []
    for company in companies:
        for persona in company["personas"]:
            for preset in presets:
                for slider_name, slider_vals in sliders:
                    case_id = f"{company['id']}__{persona['id']}__{preset}__{slider_name}"
                    cases.append(
                        {
                            "case_id": case_id,
                            "company": company,
                            "persona": persona,
                            "preset_id": preset,
                            "slider_name": slider_name,
                            "slider_config": slider_vals,
                            "seller": seller,
                        }
                    )
    return cases


# ---------------------------------------------------------------------------
# Request payload builders
# ---------------------------------------------------------------------------


def _build_generate_payload(case: dict[str, Any]) -> dict[str, Any]:
    seller = case["seller"]
    company = case["company"]
    persona = case["persona"]
    slider = case["slider_config"]

    return {
        "prospect": {
            "name": persona["name"],
            "title": persona["title"],
            "company": company["name"],
            "linkedin_url": None,
        },
        "prospect_first_name": persona["name"].split()[0],
        "research_text": persona.get("research_text", "No research available."),
        "offer_lock": seller["offer_lock"],
        "cta_offer_lock": seller["cta_offer_lock"],
        "cta_type": seller["cta_type"],
        "preset_id": case["preset_id"],
        "response_contract": "legacy_text",
        "pipeline_meta": {"mode": "generate", "model_hint": "gpt-4.1-nano"},
        "style_profile": slider,
        "company_context": {
            "company_name": seller["company_name"],
            "company_url": seller["company_url"],
            "current_product": seller["offer_lock"],
            "other_products": seller.get("other_products", ""),
            "company_notes": seller.get("company_notes", ""),
            "cta_offer_lock": seller["cta_offer_lock"],
            "cta_type": seller["cta_type"],
        },
    }


def _build_preview_payload(case: dict[str, Any]) -> dict[str, Any]:
    seller = case["seller"]
    company = case["company"]
    persona = case["persona"]
    slider = case["slider_config"]

    # Convert -1.0→+1.0 style_profile to 0-100 global_sliders for preview endpoint
    def _to_100(v: float) -> int:
        return max(0, min(100, int((v + 1.0) / 2.0 * 100)))

    global_sliders = {
        "formality": _to_100(slider.get("formality", 0.0)),
        "brevity": _to_100(-slider.get("length", 0.0)),  # brevity is inverse of length
        "directness": _to_100(slider.get("assertiveness", 0.0)),
        "personalization": _to_100(slider.get("orientation", 0.0)),
    }

    presets_list = [
        {"preset_id": case["preset_id"], "label": case["preset_id"].replace("_", " ").title(), "slider_overrides": {}}
    ]

    return {
        "prospect": {
            "name": persona["name"],
            "title": persona["title"],
            "company": company["name"],
            "company_url": company.get("company_url"),
            "linkedin_url": None,
        },
        "prospect_first_name": persona["name"].split()[0],
        "product_context": {
            "product_name": seller["offer_lock"],
            "one_line_value": seller.get("company_notes", "")[:80],
            "proof_points": (seller.get("other_products") or "").splitlines(),
            "target_outcome": "15-minute meeting",
        },
        "raw_research": {
            "deep_research_paste": persona.get("research_text", ""),
            "company_notes": company.get("company_notes", ""),
            "extra_constraints": None,
        },
        "global_sliders": global_sliders,
        "presets": presets_list,
        "offer_lock": seller["offer_lock"],
        "cta_lock": seller["cta_offer_lock"],
        "cta_lock_text": seller["cta_offer_lock"],
        "cta_type": seller["cta_type"],
    }


def _build_remix_payload(session_id: str, preset_id: str, slider: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "preset_id": preset_id,
        "style_profile": slider,
    }


# ---------------------------------------------------------------------------
# SSE parsing (ported from scripts/debug_run_harness.py)
# ---------------------------------------------------------------------------


def _extract_stream(stream_text: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    token_parts: list[str] = []
    done_payload: dict[str, Any] = {}
    error_payload: dict[str, Any] = {}
    event_name = ""
    for line in stream_text.splitlines():
        if line.startswith("event: "):
            event_name = line[7:].strip()
            continue
        if not line.startswith("data: "):
            continue
        try:
            payload = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        if event_name == "token":
            token = payload.get("token")
            if token is not None:
                token_parts.append(str(token))
        elif event_name == "done":
            done_payload = payload
        elif event_name == "error":
            error_payload = payload
    return "".join(token_parts), done_payload, error_payload


# ---------------------------------------------------------------------------
# Artifact writer
# ---------------------------------------------------------------------------


def _write_case_artifacts(
    out_dir: Path,
    case_id: str,
    request_payload: dict,
    response_json: dict | None,
    done_payload: dict,
    email_text: str,
    scorecard: dict,
    debug_meta: dict,
) -> None:
    case_dir = out_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    (case_dir / "request.json").write_text(json.dumps(request_payload, indent=2), encoding="utf-8")
    (case_dir / "response.json").write_text(json.dumps(response_json or {}, indent=2), encoding="utf-8")
    (case_dir / "email.txt").write_text(email_text or "", encoding="utf-8")
    (case_dir / "scorecard.json").write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    (case_dir / "debug_meta.json").write_text(json.dumps(debug_meta, indent=2), encoding="utf-8")
    # Combined done payload for quick inspection
    (case_dir / "done_payload.json").write_text(json.dumps(done_payload, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Core runner — single case, Flow A (generate + stream)
# ---------------------------------------------------------------------------


async def _run_generate_case(
    client: Any,
    case: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
    sem: asyncio.Semaphore,
) -> dict[str, Any]:
    """Run Flow A: POST /web/v1/generate → GET /web/v1/stream/{request_id}."""
    httpx = __import__("httpx")

    async with sem:
        t0 = time.perf_counter()
        payload = _build_generate_payload(case)
        error: str | None = None
        email_text = ""
        done_payload: dict = {}
        stream_error_payload: dict = {}
        response_json: dict = {}
        latency_ms = 0

        try:
            # Step 1: POST generate
            gen_resp = await client.post(
                "/web/v1/generate",
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            gen_resp.raise_for_status()
            accepted = gen_resp.json()
            response_json = accepted

            # Step 2: GET stream (reads full SSE response)
            stream_resp = await client.get(
                f"/web/v1/stream/{accepted['request_id']}",
                headers=headers,
                timeout=timeout + 30,  # generation takes longer
            )
            stream_resp.raise_for_status()
            email_text, done_payload, stream_error_payload = _extract_stream(stream_resp.text)
            if stream_error_payload:
                stream_error = str(stream_error_payload.get("error") or "unknown_stream_error")
                error = f"SSE error: {stream_error}"
            latency_ms = int((time.perf_counter() - t0) * 1000)

        except httpx.HTTPStatusError as exc:
            error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            latency_ms = int((time.perf_counter() - t0) * 1000)
        except Exception as exc:
            error = str(exc)
            latency_ms = int((time.perf_counter() - t0) * 1000)

        return {
            "case": case,
            "flow": "generate",
            "request_payload": payload,
            "response_json": response_json,
            "done_payload": done_payload,
            "email_text": email_text,
            "latency_ms": latency_ms,
            "error": error,
            "stream_error": stream_error_payload,
            "stream_error_event_seen": bool(stream_error_payload),
        }


# ---------------------------------------------------------------------------
# Core runner — Flow B (preset preview batch)
# ---------------------------------------------------------------------------


async def _run_preview_case(
    client: Any,
    case: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
    sem: asyncio.Semaphore,
) -> dict[str, Any]:
    """Run Flow B: POST /web/v1/preset-previews/batch."""
    httpx = __import__("httpx")

    async with sem:
        t0 = time.perf_counter()
        payload = _build_preview_payload(case)
        error: str | None = None
        email_text = ""
        response_json: dict = {}
        latency_ms = 0

        try:
            resp = await client.post(
                "/web/v1/preset-previews/batch",
                json=payload,
                headers=headers,
                timeout=timeout + 30,
            )
            resp.raise_for_status()
            response_json = resp.json()
            previews = response_json.get("previews") or []
            if previews:
                # Take the first matching preset preview
                first = previews[0]
                email_text = f"Subject: {first.get('subject', '')}\n\n{first.get('body', '')}"
            latency_ms = int((time.perf_counter() - t0) * 1000)

        except httpx.HTTPStatusError as exc:
            error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            latency_ms = int((time.perf_counter() - t0) * 1000)
        except Exception as exc:
            error = str(exc)
            latency_ms = int((time.perf_counter() - t0) * 1000)

        return {
            "case": case,
            "flow": "preview",
            "request_payload": payload,
            "response_json": response_json,
            "done_payload": {},  # no SSE done for preview
            "email_text": email_text,
            "latency_ms": latency_ms,
            "error": error,
        }


# ---------------------------------------------------------------------------
# Scorecard builder
# ---------------------------------------------------------------------------


def _build_scorecard(result: dict[str, Any]) -> dict[str, Any]:
    from devtools.fail_detectors import scorecard as compute_scorecard

    case = result["case"]
    persona = case["persona"]
    company = case["company"]
    seller = case["seller"]
    email_text = result.get("email_text") or ""

    # Extract body (strip "Subject: ..." line if present)
    lines = email_text.splitlines()
    body_lines: list[str] = []
    skip_header = True
    for line in lines:
        if skip_header and line.startswith("Subject:"):
            continue
        if skip_header and line.strip() == "":
            skip_header = False
            continue
        body_lines.append(line)
    body = "\n".join(body_lines).strip()

    meta = {
        "prospect_name": persona["name"],
        "prospect_company": company["name"],
        "prospect_title": persona["title"],
        "offer_lock": seller["offer_lock"],
        "preset_id": case["preset_id"],
        "cta_offer_lock": seller["cta_offer_lock"],
    }

    if result.get("error"):
        return {
            "case_id": result["case"]["case_id"],
            "pass": False,
            "fail_tags": ["ERROR"],
            "word_count": 0,
            "has_required_fields": {},
            "notes": [f"Runner error: {result['error']}"],
        }

    if not body:
        return {
            "case_id": result["case"]["case_id"],
            "pass": False,
            "fail_tags": ["EMPTY_EMAIL"],
            "word_count": 0,
            "has_required_fields": {},
            "notes": ["Email body is empty — generation may have failed"],
        }

    return compute_scorecard(case_id=case["case_id"], body=body, meta=meta)


# ---------------------------------------------------------------------------
# Debug meta builder
# ---------------------------------------------------------------------------


def _build_debug_meta(result: dict[str, Any], run_id: str) -> dict[str, Any]:
    case = result["case"]
    done = result.get("done_payload") or {}
    return {
        "run_id": run_id,
        "case_id": case["case_id"],
        "flow": result.get("flow"),
        "latency_ms": result.get("latency_ms"),
        "error": result.get("error"),
        "stream_error": (result.get("stream_error") or {}).get("error"),
        "stream_error_event_seen": bool(result.get("stream_error_event_seen")),
        # Provenance fields from done payload (Phase 0 additions)
        "endpoint_name": done.get("endpoint_name"),
        "preset_name": done.get("preset_name"),
        "slider_config": done.get("slider_config") or case["slider_config"],
        "prompt_template_hash": done.get("prompt_template_hash"),
        "flags_effective": done.get("flags_effective"),
        # Provider/model
        "provider": done.get("provider"),
        "model": done.get("model"),
        "mode": done.get("mode"),
        "cascade_reason": done.get("cascade_reason"),
        # Quality signals
        "violation_codes": done.get("violation_codes"),
        "violation_count": done.get("violation_count"),
        "repaired": done.get("repaired"),
        "enforcement_level": done.get("enforcement_level"),
        "generation_status": done.get("generation_status"),
        "fallback_reason": done.get("fallback_reason"),
        # Stream integrity
        "stream_checksum": done.get("stream_checksum"),
        "stream_missing_chunks": done.get("stream_missing_chunks"),
        # Case config
        "company_id": case["company"]["id"],
        "persona_id": case["persona"]["id"],
        "persona_type": case["persona"].get("persona_type"),
        "preset_id": case["preset_id"],
        "slider_name": case["slider_name"],
    }


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------


def _build_summary(
    run_id: str,
    mode: str,
    results: list[dict[str, Any]],
    scorecards: list[dict[str, Any]],
    elapsed_s: float,
) -> dict[str, Any]:
    total = len(scorecards)
    passed = sum(1 for sc in scorecards if sc.get("pass"))
    failed = total - passed
    errors = sum(1 for r in results if r.get("error"))

    fail_tag_counts: Counter = Counter()
    for sc in scorecards:
        for tag in sc.get("fail_tags") or []:
            fail_tag_counts[tag] += 1

    # Top 10 worst cases (most fail tags)
    paired = list(zip(scorecards, results))
    paired_sorted = sorted(paired, key=lambda x: len(x[0].get("fail_tags") or []), reverse=True)
    top_worst = []
    for sc, res in paired_sorted[:10]:
        if not sc.get("fail_tags"):
            break
        top_worst.append(
            {
                "case_id": sc["case_id"],
                "fail_tags": sc.get("fail_tags"),
                "word_count": sc.get("word_count"),
                "notes": (sc.get("notes") or [])[:3],
                "latency_ms": res.get("latency_ms"),
                "provider": (res.get("done_payload") or {}).get("provider"),
            }
        )

    # Breakdown by persona type
    by_persona_type: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "pass": 0})
    for sc, res in zip(scorecards, results):
        pt = res["case"]["persona"].get("persona_type", "unknown")
        by_persona_type[pt]["total"] += 1
        if sc.get("pass"):
            by_persona_type[pt]["pass"] += 1

    # Breakdown by preset
    by_preset: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "pass": 0})
    for sc, res in zip(scorecards, results):
        pr = res["case"]["preset_id"]
        by_preset[pr]["total"] += 1
        if sc.get("pass"):
            by_preset[pr]["pass"] += 1

    return {
        "run_id": run_id,
        "mode": mode,
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "elapsed_seconds": round(elapsed_s, 1),
        "total": total,
        "pass": passed,
        "fail": failed,
        "errors": errors,
        "pass_rate_pct": round(passed / total * 100, 1) if total else 0.0,
        "fail_tag_counts": dict(fail_tag_counts.most_common()),
        "top_10_worst": top_worst,
        "breakdown_by_persona_type": dict(by_persona_type),
        "breakdown_by_preset": dict(by_preset),
    }


# ---------------------------------------------------------------------------
# Optional LLM judge (budget-safe)
# ---------------------------------------------------------------------------


async def _maybe_judge(
    results: list[dict[str, Any]],
    scorecards: list[dict[str, Any]],
    judge_limit: int,
) -> None:
    """Invoke the existing JudgeClient for emails that pass deterministic checks."""
    if judge_limit <= 0:
        return

    try:
        from evals.judge.client import JudgeClient  # noqa: PLC0415
    except ImportError:
        print("  [judge] evals/judge/client.py not importable — skipping judge", flush=True)
        return

    judged = 0
    client = JudgeClient()
    for sc, res in zip(scorecards, results):
        if judged >= judge_limit:
            break
        if not sc.get("pass"):
            continue  # only judge passing emails (borderline = no hard fails)
        try:
            judge_result = await client.evaluate_email(
                email_body=res.get("email_text") or "",
                metadata={
                    "prospect_title": res["case"]["persona"]["title"],
                    "offer_lock": res["case"]["seller"]["offer_lock"],
                    "preset_id": res["case"]["preset_id"],
                },
            )
            sc["judge"] = judge_result
            judged += 1
            print(f"  [judge] {sc['case_id']}: persona_fit={judge_result.get('persona_fit')} specificity={judge_result.get('specificity')}", flush=True)
        except Exception as exc:
            print(f"  [judge] {sc['case_id']}: error — {exc}", flush=True)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


async def _run_all(
    mode: str,
    base_url: str,
    beta_key: str,
    out_dir: Path,
    flow: str,
    judge_limit: int,
    concurrency: int,
    timeout: float,
) -> dict[str, Any]:
    httpx = __import__("httpx")

    pack = _load_pack()
    cases = _build_cases(pack, mode)
    run_id = f"{mode}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    headers = {
        "Content-Type": "application/json",
        "X-EmailDJ-Beta-Key": beta_key,
    }
    sem = asyncio.Semaphore(concurrency)

    print(f"\n{'='*60}", flush=True)
    print(f"  EmailDJ Smoke Runner — mode={mode}  flow={flow}", flush=True)
    print(f"  base_url={base_url}  cases={len(cases)}  concurrency={concurrency}", flush=True)
    print(f"  out={out_dir}", flush=True)
    print(f"{'='*60}\n", flush=True)

    t_start = time.perf_counter()

    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        if flow in ("generate", "all"):
            runner = _run_generate_case
        elif flow == "preview":
            runner = _run_preview_case
        else:
            runner = _run_generate_case

        tasks = [
            runner(client=client, case=case, headers=headers, timeout=timeout, sem=sem)
            for case in cases
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    elapsed = time.perf_counter() - t_start
    results_list = list(results)

    # Build scorecards
    scorecards = [_build_scorecard(r) for r in results_list]

    # Optional LLM judge
    if judge_limit > 0:
        print(f"\n  Running LLM judge on up to {judge_limit} passing emails...", flush=True)
        await _maybe_judge(results_list, scorecards, judge_limit)

    # Write per-case artifacts
    for result, sc in zip(results_list, scorecards):
        case = result["case"]
        debug_meta = _build_debug_meta(result, run_id)
        _write_case_artifacts(
            out_dir=out_dir,
            case_id=case["case_id"],
            request_payload=result["request_payload"],
            response_json=result.get("response_json"),
            done_payload=result.get("done_payload") or {},
            email_text=result.get("email_text") or "",
            scorecard=sc,
            debug_meta=debug_meta,
        )

    # Build and write summary
    summary = _build_summary(run_id, mode, results_list, scorecards, elapsed)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return summary


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------


def _print_summary(summary: dict[str, Any]) -> None:
    total = summary["total"]
    passed = summary["pass"]
    failed = summary["fail"]
    errors = summary["errors"]
    pass_rate = summary["pass_rate_pct"]

    print(f"\n{'='*60}", flush=True)
    print(f"  SMOKE RUN COMPLETE — {summary['run_id']}", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  Total:     {total}", flush=True)
    print(f"  Pass:      {passed}  ({pass_rate}%)", flush=True)
    print(f"  Fail:      {failed}", flush=True)
    print(f"  Errors:    {errors}", flush=True)
    print(f"  Elapsed:   {summary['elapsed_seconds']}s", flush=True)

    if summary["fail_tag_counts"]:
        print(f"\n  FAIL TAG FREQUENCY:", flush=True)
        for tag, count in summary["fail_tag_counts"].items():
            bar = "█" * min(count, 30)
            print(f"    {tag:<35} {count:>3}  {bar}", flush=True)

    if summary["breakdown_by_persona_type"]:
        print(f"\n  PASS RATE BY PERSONA TYPE:", flush=True)
        for pt, counts in summary["breakdown_by_persona_type"].items():
            t = counts["total"]
            p = counts["pass"]
            pct = round(p / t * 100, 0) if t else 0
            print(f"    {pt:<20} {p}/{t} ({pct}%)", flush=True)

    if summary["breakdown_by_preset"]:
        print(f"\n  PASS RATE BY PRESET:", flush=True)
        for preset, counts in summary["breakdown_by_preset"].items():
            t = counts["total"]
            p = counts["pass"]
            pct = round(p / t * 100, 0) if t else 0
            print(f"    {preset:<30} {p}/{t} ({pct}%)", flush=True)

    if summary["top_10_worst"]:
        print(f"\n  TOP WORST CASES:", flush=True)
        for item in summary["top_10_worst"]:
            tags = ", ".join(item["fail_tags"])
            print(f"    [{item['case_id']}]  tags={tags}", flush=True)
            for note in item.get("notes") or []:
                print(f"      → {note}", flush=True)

    print(f"\n{'='*60}\n", flush=True)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="EmailDJ HTTP Smoke Runner — hits real localhost endpoints.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start the server first:
  cd hub-api && uvicorn main:app --reload

  # Run 30-email smoke:
  python -m devtools.http_smoke_runner --mode smoke

  # Custom output dir:
  python -m devtools.http_smoke_runner --mode smoke --out debug_runs/smoke/$(date -u +%Y%m%dT%H%M%SZ)

  # Run 120-email expanded:
  python -m devtools.http_smoke_runner --mode small120

  # With LLM judge on top 10 passers:
  python -m devtools.http_smoke_runner --mode smoke --judge_limit 10

  # Preview flow (preset-previews/batch):
  python -m devtools.http_smoke_runner --mode smoke --flow preview
""",
    )
    parser.add_argument(
        "--mode",
        choices=("smoke", "small120"),
        default="smoke",
        help="smoke=30 emails (default), small120=120 emails",
    )
    parser.add_argument(
        "--flow",
        choices=("generate", "preview"),
        default="generate",
        help="generate=generate+stream flow (default), preview=preset-previews/batch flow",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Hub API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--beta-key",
        default="dev-beta-key",
        help="Beta key for authentication (default: dev-beta-key)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output directory (default: debug_runs/smoke/<timestamp>)",
    )
    parser.add_argument(
        "--judge_limit",
        type=int,
        default=0,
        help="Max emails to send to LLM judge (0=off, default). Only passing emails are judged.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Max concurrent cases (default: 3 — be gentle with the local server)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds per request (default: 60)",
    )

    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.out:
        out_dir = Path(args.out)
    else:
        out_dir = ROOT / "debug_runs" / "smoke" / timestamp

    summary = asyncio.run(
        _run_all(
            mode=args.mode,
            base_url=args.base_url,
            beta_key=args.beta_key,
            out_dir=out_dir,
            flow=args.flow,
            judge_limit=args.judge_limit,
            concurrency=args.concurrency,
            timeout=args.timeout,
        )
    )

    _print_summary(summary)
    print(f"Artifacts: {out_dir}", flush=True)
    print(f"Summary:   {out_dir / 'summary.json'}\n", flush=True)

    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
