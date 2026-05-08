#!/usr/bin/env python3
"""Capture reproducible UI-session request artifacts for generate/remix/preview flows."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from contextlib import contextmanager, nullcontext
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
os.environ.setdefault("EMAILDJ_LAUNCH_MODE", "dev")
os.environ.setdefault("EMAILDJ_PRESET_PREVIEW_PIPELINE", "on")
os.environ.setdefault("EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL", "warn")

from email_generation import remix_engine
from email_generation.quick_generate import GenerateResult
from main import app

import httpx

_ALLOWED_PRESETS = [
    "straight_shooter",
    "headliner",
    "giver",
    "challenger",
    "industry_insider",
    "c_suite_sniper",
]


def _required_external_provider_env() -> tuple[str, str]:
    provider = (os.environ.get("EMAILDJ_REAL_PROVIDER", "openai").strip().lower() or "openai")
    required_key = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "groq": "GROQ_API_KEY",
    }.get(provider, "OPENAI_API_KEY")
    return provider, required_key


def _capture_beta_key() -> str:
    raw = (os.environ.get("EMAILDJ_WEB_BETA_KEYS") or "").strip()
    keys = [part.strip() for part in raw.split(",") if part.strip()]
    return keys[0] if keys else "dev-beta-key"


def _capture_headers() -> dict[str, str]:
    return {"x-emaildj-beta-key": _capture_beta_key()}


def _json_or_raise(response: httpx.Response, *, endpoint: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        payload = {"raw_response": response.text[:500]}
    if response.status_code >= 400:
        raise RuntimeError(f"capture_ui_session_request_failed:{endpoint}:{response.status_code}:{payload}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"capture_ui_session_request_failed:{endpoint}:non_object_json")
    return payload


def _text_or_raise(response: httpx.Response, *, endpoint: str) -> str:
    if response.status_code >= 400:
        raise RuntimeError(f"capture_ui_session_request_failed:{endpoint}:{response.status_code}:{response.text[:500]}")
    return response.text


def _ui_generate_payload(*, title: str = "CEO", preset_id: str = "straight_shooter", length: float = -0.2) -> dict[str, Any]:
    return {
        "prospect": {
            "name": "Alex Doe",
            "title": title,
            "company": "SignalForge",
            "linkedin_url": "https://linkedin.com/in/alex-doe",
        },
        "prospect_first_name": "Alex",
        "research_text": (
            "SignalForge announced a 2026 outbound quality initiative and opened 12 SDR roles in Q1. "
            "The latest earnings call tied pipeline review goals to reply quality and qualification discipline."
        ),
        "offer_lock": "Remix Studio",
        "cta_offer_lock": None,
        "cta_type": None,
        "preset_id": preset_id,
        "response_contract": "legacy_text",
        "pipeline_meta": {"mode": "generate", "model_hint": "gpt-5-nano"},
        "style_profile": {
            "formality": 0.1,
            "orientation": 0.2,
            "length": length,
            "assertiveness": 0.2,
        },
        "company_context": {
            "company_name": "Corsearch",
            "company_url": "https://corsearch.com",
            "current_product": "Remix Studio",
            "other_products": "Search\nEnrich\nSequence QA",
            "company_notes": (
                "Customers use structured guardrails to reduce message drift while preserving rep autonomy. "
                "Teams prioritize response quality in enterprise accounts."
            ),
        },
    }


def _preview_payload() -> dict[str, Any]:
    return {
        "prospect": {
            "name": "Alex Doe",
            "title": "CEO",
            "company": "SignalForge",
            "linkedin_url": "https://linkedin.com/in/alex-doe",
        },
        "prospect_first_name": "Alex",
        "product_context": {
            "product_name": "Remix Studio",
            "one_line_value": "Improve first-touch outbound quality with deterministic controls.",
            "proof_points": [
                "Teams use structured guardrails to reduce drift across reps.",
                "Managers get faster visibility into risky messaging patterns.",
            ],
            "target_outcome": "Higher-quality replies from enterprise accounts",
        },
        "raw_research": {
            "deep_research_paste": (
                "SignalForge announced a 2026 outbound quality initiative and opened 12 SDR roles in Q1. "
                "Leadership tied pipeline quality to quarterly targets."
            ),
            "company_notes": "Corsearch notes: consistent SDR messaging quality is a board-level focus.",
            "extra_constraints": "",
        },
        "global_sliders": {"formality": 45, "brevity": 60, "directness": 55, "personalization": 65},
        "presets": [{"preset_id": preset, "label": preset.replace("_", " ").title(), "slider_overrides": {}} for preset in _ALLOWED_PRESETS],
        "offer_lock": "Remix Studio",
        "cta_type": "time_ask",
    }


def _derive_preset(prompt: list[dict[str, str]]) -> str:
    text = "\n".join(str(item.get("content") or "") for item in prompt)
    for preset in _ALLOWED_PRESETS:
        if preset in text:
            return preset
    return "straight_shooter"


def _first_high_conf_fact(prompt: list[dict[str, str]]) -> str:
    text = "\n".join(str(item.get("content") or "") for item in prompt)
    match = re.search(r"ALLOWED_FACTS_HIGH_CONFIDENCE.*?\[(.*?)\]", text, flags=re.DOTALL)
    if not match:
        return "SignalForge announced a 2026 outbound quality initiative and opened 12 SDR roles in Q1."
    compact = " ".join(match.group(1).split())
    compact = compact.strip(" '\"")
    if not compact:
        return "SignalForge announced a 2026 outbound quality initiative and opened 12 SDR roles in Q1."
    return compact[:220]


async def _fake_real_generate(
    prompt: list[dict[str, str]],
    task: str = "web_mvp",  # noqa: ARG001
    throttled: bool = False,  # noqa: ARG001
    output_token_budget: int | None = None,  # noqa: ARG001
) -> GenerateResult:
    preset = _derive_preset(prompt)
    fact = _first_high_conf_fact(prompt)
    wedge = {
        "straight_shooter": "Most teams lose replies when first touches drift from account-specific triggers.",
        "headliner": "Hidden gap: strong outbound volume, inconsistent first-touch message quality.",
        "giver": "We usually start with an async teardown so teams can test improvements immediately.",
        "challenger": "The expensive risk is not volume, it's low-signal conversations entering pipeline.",
        "industry_insider": "Across peer teams, trigger-aware messaging separates quality replies from noise.",
        "c_suite_sniper": "At the exec level, outbound quality drift becomes a pipeline governance risk.",
    }[preset]
    subject = {
        "straight_shooter": "Remix Studio for SignalForge",
        "headliner": "SignalForge outbound risk brief",
        "giver": "Async teardown for SignalForge",
        "challenger": "Hidden outbound quality cost",
        "industry_insider": "Pattern we see in enterprise SDR motion",
        "c_suite_sniper": "Executive outbound quality risk",
    }[preset]
    body = (
        f"Hi Alex, {fact} "
        f"{wedge} "
        "Remix Studio helps keep first-touch quality high while preserving rep speed.\n\n"
        "Would it be useful if I sent a short risk brief on Remix Studio with the first sequence changes we'd test?"
    )
    payload = {"subject": subject, "body": body}
    return GenerateResult(
        text=json.dumps(payload, separators=(",", ":"), ensure_ascii=True),
        provider="openai",
        model_name="gpt-5-nano",
        cascade_reason="primary",
        attempt_count=1,
        finish_reason="stop",
    )


def _extract_stream(stream_text: str) -> tuple[str, dict[str, Any] | None]:
    event_name = ""
    token_parts: list[str] = []
    done_payload: dict[str, Any] | None = None
    for line in stream_text.splitlines():
        if line.startswith("event: "):
            event_name = line[7:].strip()
            continue
        if not line.startswith("data: "):
            continue
        try:
            payload = json.loads(line[6:])
        except Exception:
            continue
        if event_name == "token":
            token = payload.get("token")
            if token is not None:
                token_parts.append(str(token))
        elif event_name == "done":
            done_payload = payload
    return "".join(token_parts), done_payload


def _request_record(
    *,
    index: int,
    endpoint: str,
    payload: dict[str, Any],
    accepted: dict[str, Any] | None = None,
    stream_text: str | None = None,
    stream_done: dict[str, Any] | None = None,
    session: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
    response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attempts = list((trace or {}).get("attempts") or [])
    last_attempt = attempts[-1] if attempts else {}
    ui_text = ""
    if stream_done:
        final = stream_done.get("final") or {}
        if isinstance(final, dict):
            ui_text = str(final.get("body") or "").strip()
    if not ui_text and stream_text:
        ui_text = stream_text.strip()
    return {
        "request_index": index,
        "endpoint": endpoint,
        "request_payload": payload,
        "accepted": accepted,
        "response": response,
        "stream_done": stream_done,
        "ui_text_shown": ui_text,
        "provider_raw_output": (trace or {}).get("last_raw_model_output"),
        "parsed_json_output": last_attempt.get("parsed_json"),
        "post_validation_output": (trace or {}).get("final_candidate"),
        "prompt_redacted": last_attempt.get("prompt_redacted"),
        "session_request_config": (session or {}).get("request_config"),
        "generation_plan": (session or {}).get("generation_plan"),
        "execution_trace": (stream_done or {}).get("execution_trace"),
        "trace_status": (trace or {}).get("status"),
        "provider_source": (stream_done or {}).get("provider_source")
        or ((response or {}).get("meta") or {}).get("provider_source"),
    }


def _remix_record_clean(record: dict[str, Any]) -> bool:
    stream_done = dict(record.get("stream_done") or {})
    trace_status = str(record.get("trace_status") or "").strip()
    generation_status = str(stream_done.get("generation_status") or "").strip()
    fallback_reason = stream_done.get("fallback_reason")
    final = dict(stream_done.get("final") or {})
    final_body = str(final.get("body") or "").strip()
    return trace_status.startswith("ok") and generation_status == "ok" and not fallback_reason and bool(final_body)


@contextmanager
def _temporary_env(name: str, value: str):
    previous = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


async def _run_capture(output_dir: Path, *, provider_path: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    headers = _capture_headers()

    original_real_generate = remix_engine._real_generate
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            index = 1
            records: list[dict[str, Any]] = []

            with _temporary_env("USE_PROVIDER_STUB", "1"):
                preview_payload = _preview_payload()
                preview_response = await client.post("/web/v1/preset-previews/batch", json=preview_payload, headers=headers)
                preview_json = _json_or_raise(preview_response, endpoint="/web/v1/preset-previews/batch")
                preview_record = _request_record(
                    index=index,
                    endpoint="/web/v1/preset-previews/batch",
                    payload=preview_payload,
                    response=preview_json,
                )
                preview_record["ui_text_shown"] = "\n\n".join(
                    [
                        f"Subject: {item.get('subject', '')}\n{item.get('body', '')}"
                        for item in list(preview_json.get("previews") or [])[:2]
                    ]
                ).strip()
                records.append(preview_record)
                (output_dir / f"{index:02d}_preview_batch.json").write_text(json.dumps(preview_record, indent=2), encoding="utf-8")
                index += 1

            if provider_path == "provider_shim":
                remix_engine._real_generate = _fake_real_generate  # type: ignore[assignment]
            else:
                provider, required_key = _required_external_provider_env()
                if not os.environ.get(required_key):
                    raise RuntimeError(
                        f"external_provider_capture_requires provider={provider} env_var={required_key}"
                    )

            with _temporary_env("USE_PROVIDER_STUB", "0"):
                shim_key_ctx = _temporary_env("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", "shim-key")) if provider_path == "provider_shim" else nullcontext()
                with shim_key_ctx:
                    generate_payload = _ui_generate_payload(title="CEO", preset_id="straight_shooter", length=-0.6)
                    accepted = _json_or_raise(
                        await client.post("/web/v1/generate", json=generate_payload, headers=headers),
                        endpoint="/web/v1/generate",
                    )
                    stream_response = await client.get(f"/web/v1/stream/{accepted['request_id']}", headers=headers)
                    stream_text = _text_or_raise(stream_response, endpoint="/web/v1/stream")
                    stream_tokens, stream_done = _extract_stream(stream_text)
                    session = await remix_engine.load_session(accepted["session_id"])
                    trace = (session or {}).get("last_generation_trace") or {}
                    record = _request_record(
                        index=index,
                        endpoint="/web/v1/generate",
                        payload=generate_payload,
                        accepted=accepted,
                        stream_text=stream_tokens,
                        stream_done=stream_done,
                        session=session,
                        trace=trace,
                    )
                    if provider_path == "provider_shim":
                        record["provider_source"] = "provider_shim"
                        if isinstance(record.get("stream_done"), dict):
                            record["stream_done"]["provider_source"] = "provider_shim"
                    records.append(record)
                    (output_dir / f"{index:02d}_generate.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
                    session_id = accepted["session_id"]
                    index += 1

                    remix_variants = [
                        ("headliner", {"formality": 0.2, "orientation": 0.4, "length": -0.2, "assertiveness": 0.3}),
                        ("c_suite_sniper", {"formality": 0.1, "orientation": 0.9, "length": -0.7, "assertiveness": 0.4}),
                        ("industry_insider", {"formality": 0.0, "orientation": 0.6, "length": 0.2, "assertiveness": 0.1}),
                    ]
                    for preset_id, style_profile in remix_variants:
                        remix_payload = {
                            "session_id": session_id,
                            "preset_id": preset_id,
                            "style_profile": style_profile,
                        }
                        accepted = _json_or_raise(
                            await client.post("/web/v1/remix", json=remix_payload, headers=headers),
                            endpoint="/web/v1/remix",
                        )
                        stream_response = await client.get(f"/web/v1/stream/{accepted['request_id']}", headers=headers)
                        stream_text = _text_or_raise(stream_response, endpoint="/web/v1/stream")
                        stream_tokens, stream_done = _extract_stream(stream_text)
                        session = await remix_engine.load_session(session_id)
                        trace = (session or {}).get("last_generation_trace") or {}
                        record = _request_record(
                            index=index,
                            endpoint="/web/v1/remix",
                            payload=remix_payload,
                            accepted=accepted,
                            stream_text=stream_tokens,
                            stream_done=stream_done,
                            session=session,
                            trace=trace,
                        )
                        if provider_path == "provider_shim":
                            record["provider_source"] = "provider_shim"
                            if isinstance(record.get("stream_done"), dict):
                                record["stream_done"]["provider_source"] = "provider_shim"
                        records.append(record)
                        (output_dir / f"{index:02d}_remix_{preset_id}.json").write_text(
                            json.dumps(record, indent=2), encoding="utf-8"
                        )
                        index += 1

            remix_records = [rec for rec in records if rec.get("endpoint") == "/web/v1/remix"]
            remix_clean = bool(remix_records) and all(_remix_record_clean(rec) for rec in remix_records)
            summary = {
                "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                "request_count": len(records),
                "output_dir": str(output_dir),
                "provider_source": provider_path,
                "launch_gates": {
                    "shim_green": "green" if provider_path == "provider_shim" and remix_clean else "red" if provider_path == "provider_shim" else "not_run",
                    "provider_green": "green" if provider_path == "external_provider" and remix_clean else "red" if provider_path == "external_provider" else "not_run",
                    "remix_green": "green" if remix_clean else "red",
                },
                "requests": [
                    {
                        "index": rec["request_index"],
                        "endpoint": rec["endpoint"],
                        "request_id": (rec.get("accepted") or {}).get("request_id"),
                        "session_id": (rec.get("accepted") or {}).get("session_id"),
                        "provider_source": rec.get("provider_source"),
                        "flags_effective": (rec.get("stream_done") or {}).get("flags_effective")
                        or ((rec.get("response") or {}).get("meta") or {}).get("flags_effective"),
                    }
                    for rec in records
                ],
            }
            (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    finally:
        remix_engine._real_generate = original_real_generate  # type: ignore[assignment]


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture five UI-path requests and debug artifacts.")
    parser.add_argument("--output-root", default="debug_runs/ui_sessions", help="Output root relative to hub-api/")
    parser.add_argument("--out", default="", help="Explicit output directory. If omitted, a timestamped directory is created under --output-root.")
    parser.add_argument(
        "--provider-path",
        choices=("provider_shim", "external_provider"),
        default="provider_shim",
        help="provider_shim uses the real code path with a local fake provider; external_provider requires real provider credentials.",
    )
    args = parser.parse_args()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.out).resolve() if args.out.strip() else (ROOT / args.output_root / timestamp).resolve()
    asyncio.run(_run_capture(output_dir, provider_path=args.provider_path))
    print(json.dumps({"ok": True, "output_dir": str(output_dir), "provider_source": args.provider_path}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
