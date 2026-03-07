"""Golden repro harness for end-to-end web_mvp generation path."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
os.environ.setdefault("WEB_APP_ORIGIN", "http://localhost:5174")
os.environ.setdefault("REDIS_FORCE_INMEMORY", "1")
os.environ.setdefault("EMAILDJ_WEB_BETA_KEYS", "dev-beta-key")
os.environ.setdefault("EMAILDJ_WEB_RATE_LIMIT_PER_MIN", "300")
os.environ.setdefault("EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL", "repair")
os.environ.setdefault("EMAILDJ_REPAIR_LOOP_ENABLED", "1")


def _payload() -> dict[str, Any]:
    oversized_notes = (
        "Corsearch supports enterprise outbound quality control. "
        "This note intentionally exceeds truncation thresholds to test sentence-safe boundaries. "
        "We provide deterministic controls for SDR messaging and enforce strict product locks. "
    ) * 30
    oversized_research = (
        "Acme launched a new enterprise outbound initiative in January 2026 and expanded SDR hiring by 12 roles in Q1. "
        "Leadership is focused on response quality and repeatable message governance under higher send volume. "
        "The team recently consolidated enablement playbooks and is measuring quality drift weekly. "
    ) * 30
    return {
        "prospect": {
            "name": "Alex Doe",
            "title": "SDR Manager",
            "company": "Acme",
            "linkedin_url": "https://linkedin.com/in/alex-doe",
        },
        "prospect_first_name": "Alex",
        "research_text": oversized_research,
        "offer_lock": "Remix Studio",
        "cta_offer_lock": "",
        "cta_type": "question",
        "preset_id": "straight_shooter",
        "response_contract": "legacy_text",
        "pipeline_meta": {"mode": "generate", "model_hint": "gpt-5-nano"},
        "style_profile": {
            "formality": 0.0,
            "orientation": 0.0,
            "length": 1.0,  # long mode fixture
            "assertiveness": 0.0,
        },
        "company_context": {
            "company_name": "Corsearch",
            "company_url": "https://corsearch.com",
            "current_product": "Remix Studio",
            "other_products": "Prospect Enrichment\nSequence QA",
            "company_notes": oversized_notes,
        },
    }


def _extract_stream(stream_text: str) -> tuple[str, dict[str, Any]]:
    token_parts: list[str] = []
    done_payload: dict[str, Any] = {}
    event_name = ""
    for line in stream_text.splitlines():
        if line.startswith("event: "):
            event_name = line[7:].strip()
            continue
        if not line.startswith("data: "):
            continue
        payload = json.loads(line[6:])
        if event_name == "token":
            token = payload.get("token")
            if token is not None:
                token_parts.append(str(token))
        elif event_name == "done":
            done_payload = payload
    return "".join(token_parts), done_payload


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _quality_metrics(session_trace: dict[str, Any], truncation_meta: dict[str, Any] | None, done_payload: dict[str, Any]) -> dict[str, Any]:
    attempts = session_trace.get("attempts") or []
    parse_attempt_count = len(attempts)
    parse_invalid_json_count = sum(1 for attempt in attempts if attempt.get("parse_error"))
    finish_reason_length_count = sum(
        1 for attempt in attempts if str(attempt.get("finish_reason") or "").strip().lower() in {"length", "max_tokens"}
    )
    fluency_violation_count = 0
    for attempt in attempts:
        for violation in attempt.get("violations") or []:
            if str(violation).startswith("fluency_") or str(violation).startswith("missing_required_field:"):
                fluency_violation_count += 1

    company_cut = bool(((truncation_meta or {}).get("company_notes") or {}).get("cut_mid_sentence"))
    research_cut = bool(((truncation_meta or {}).get("research_excerpt") or {}).get("cut_mid_sentence"))
    truncation_mid_sentence_count = 1 if (company_cut or research_cut) else 0
    stream_integrity_fail_count = 1 if int(done_payload.get("stream_missing_chunks", 0) or 0) > 0 else 0

    return {
        "truncation_mid_sentence_count": truncation_mid_sentence_count,
        "parse_invalid_json_count": parse_invalid_json_count,
        "parse_attempt_count": parse_attempt_count,
        "parse_invalid_json_rate": _rate(parse_invalid_json_count, parse_attempt_count),
        "finish_reason_length_count": finish_reason_length_count,
        "provider_response_count": parse_attempt_count,
        "finish_reason_length_rate": _rate(finish_reason_length_count, parse_attempt_count),
        "stream_integrity_fail_count": stream_integrity_fail_count,
        "stream_count": 1,
        "stream_integrity_fail_rate": _rate(stream_integrity_fail_count, 1),
        "fluency_violation_count": fluency_violation_count,
        "draft_count": 1,
        "fluency_violation_rate": _rate(fluency_violation_count, 1),
    }


async def _run(mode: str, simulate_fallback: bool) -> dict[str, Any]:
    httpx = __import__("httpx")
    from email_generation import remix_engine
    from email_generation import quick_generate as qg
    from main import app

    os.environ["USE_PROVIDER_STUB"] = "1" if mode == "mock" else "0"
    if mode == "real":
        os.environ.setdefault("OPENAI_API_KEY", "test-key")
        os.environ.setdefault("EMAILDJ_REAL_PROVIDER", "openai")

    restore_openai = qg._openai_chat_completion
    restore_anthropic = qg._anthropic_messages

    if simulate_fallback:
        attempts = {"openai": 0}

        async def fake_openai(prompt, model_name, timeout=30.0, max_output_tokens=None, strict_json=False):  # noqa: ARG001
            attempts["openai"] += 1
            raise RuntimeError("simulated_openai_failure")

        async def fake_anthropic(prompt, model_name, timeout=35.0, max_output_tokens=None):  # noqa: ARG001
            return (
                json.dumps(
                    {
                        "subject": "Remix Studio for Acme",
                        "body": (
                            "Hi Alex, Acme is scaling outbound quality controls and your SDR team is balancing throughput with consistency. "
                            "Remix Studio helps keep messaging specific and enforceable without adding workflow overhead.\n\n"
                            "Open to a quick chat to see if this is relevant?"
                        ),
                    }
                ),
                "stop",
            )

        qg._openai_chat_completion = fake_openai  # type: ignore[assignment]
        qg._anthropic_messages = fake_anthropic  # type: ignore[assignment]

    payload = _payload()
    headers = {"x-emaildj-beta-key": "dev-beta-key"}
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            start = await client.post("/web/v1/generate", json=payload, headers=headers)
            start.raise_for_status()
            accepted = start.json()

            stream = await client.get(f"/web/v1/stream/{accepted['request_id']}", headers=headers)
            stream.raise_for_status()
            stream_text = stream.text

            rendered_text, done_payload = _extract_stream(stream_text)
            session = await remix_engine.load_session(accepted["session_id"])
            trace = (session or {}).get("last_generation_trace") or {}
            truncation_meta = (session or {}).get("truncation_metadata")
            metrics = _quality_metrics(trace, truncation_meta, done_payload)

            return {
                "accepted": accepted,
                "done_payload": done_payload,
                "stream_text_length": len(stream_text),
                "rendered_text": rendered_text,
                "rendered_text_length": len(rendered_text),
                "session_trace": trace,
                "session_truncation_metadata": truncation_meta,
                "session_allowed_facts_count": len((session or {}).get("allowed_facts") or []),
                "quality_metrics": metrics,
            }
    finally:
        if simulate_fallback:
            qg._openai_chat_completion = restore_openai  # type: ignore[assignment]
            qg._anthropic_messages = restore_anthropic  # type: ignore[assignment]


def _write_artifacts(output_dir: Path, result: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (output_dir / "rendered_email.txt").write_text(result.get("rendered_text", ""), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic web_mvp golden repro harness.")
    parser.add_argument("--mode", choices=("mock", "real"), default="mock")
    parser.add_argument("--simulate-fallback", action="store_true")
    parser.add_argument("--output-dir", default="debug_runs")
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = (ROOT / args.output_dir / timestamp).resolve()

    result = asyncio.run(_run(mode=args.mode, simulate_fallback=args.simulate_fallback))
    result["harness_meta"] = {
        "timestamp_utc": timestamp,
        "mode": args.mode,
        "simulate_fallback": args.simulate_fallback,
        "output_dir": str(output_dir),
    }
    _write_artifacts(output_dir, result)

    print(json.dumps({"ok": True, "output_dir": str(output_dir), "done_payload": result.get("done_payload", {})}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
