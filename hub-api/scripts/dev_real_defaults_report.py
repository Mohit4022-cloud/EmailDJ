#!/usr/bin/env python3
"""Verify dev defaults: real mode + P0 flags on without manual feature toggles."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Minimal runtime requirements.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
os.environ.setdefault("WEB_APP_ORIGIN", "http://localhost:5174")
os.environ.setdefault("REDIS_FORCE_INMEMORY", "1")
os.environ.setdefault("EMAILDJ_WEB_BETA_KEYS", "dev-beta-key")
os.environ.setdefault("EMAILDJ_WEB_RATE_LIMIT_PER_MIN", "300")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

# Dev defaults should resolve behavior when mode/feature flags are absent.
for key in list(os.environ.keys()):
    if key == "USE_PROVIDER_STUB":
        os.environ.pop(key, None)
    if key == "EMAILDJ_QUICK_GENERATE_MODE":
        os.environ.pop(key, None)
    if key == "EMAILDJ_PRESET_PREVIEW_PIPELINE":
        os.environ.pop(key, None)
    if key.startswith("FEATURE_"):
        os.environ.pop(key, None)

import httpx

from email_generation import preset_preview_pipeline as preview_pipeline
from email_generation import remix_engine
from email_generation.prompt_templates import web_mvp_prompt_template_hash
from email_generation.preset_preview_pipeline import preview_prompt_template_hashes
from email_generation.quick_generate import GenerateResult
from main import app

_P0_FEATURES = [
    "FEATURE_PERSONA_ROUTER",
    "FEATURE_NO_PROSPECT_OWNS_GUARDRAIL",
    "FEATURE_PRESET_TRUE_REWRITE",
    "FEATURE_STRUCTURED_OUTPUT",
    "FEATURE_SENTENCE_SAFE_TRUNCATION",
    "FEATURE_LOSSLESS_STREAMING",
    "FEATURE_FLUENCY_REPAIR",
]


def _headers() -> dict[str, str]:
    return {"x-emaildj-beta-key": "dev-beta-key"}


def _parse_done_payload(stream_text: str) -> dict[str, Any]:
    event_name = ""
    done_payload: dict[str, Any] = {}
    for line in stream_text.splitlines():
        if line.startswith("event: "):
            event_name = line[7:].strip()
            continue
        if line.startswith("data: ") and event_name == "done":
            done_payload = json.loads(line[6:])
    return done_payload


def _generate_payload() -> dict[str, Any]:
    return {
        "prospect": {
            "name": "Alex Doe",
            "title": "SDR Manager",
            "company": "Acme",
            "linkedin_url": "https://linkedin.com/in/alex-doe",
        },
        "prospect_first_name": "Alex",
        "research_text": (
            "Acme launched an outbound quality initiative in January and expanded SDR hiring in Q1. "
            "Leadership is focused on consistency and message quality for enterprise accounts."
        ),
        "offer_lock": "Remix Studio",
        "cta_offer_lock": "Open to a quick chat to see if this is relevant?",
        "cta_type": "question",
        "preset_id": "straight_shooter",
        "response_contract": "legacy_text",
        "pipeline_meta": {"mode": "generate", "model_hint": "gpt-4.1-nano"},
        "style_profile": {"formality": 0.1, "orientation": 0.2, "length": -0.2, "assertiveness": 0.1},
        "company_context": {
            "company_name": "Corsearch",
            "company_url": "https://corsearch.com",
            "current_product": "Remix Studio",
            "other_products": "Prospect Enrichment\nSequence QA",
            "company_notes": "Teams use Remix Studio to keep first-touch copy consistent across reps.",
        },
    }


def _preview_payload() -> dict[str, Any]:
    return {
        "prospect": {
            "name": "Alex Doe",
            "title": "SDR Manager",
            "company": "Acme",
            "company_url": "https://acme.example",
            "linkedin_url": "https://linkedin.com/in/alex-doe",
        },
        "prospect_first_name": "Alex",
        "product_context": {
            "product_name": "Remix Studio",
            "one_line_value": "improve SDR reply quality with deterministic controls",
            "proof_points": ["Deterministic quality controls", "Offer-lock guardrails"],
            "target_outcome": "higher quality replies",
        },
        "raw_research": {
            "deep_research_paste": (
                "Acme is scaling outbound quality reviews and tightened enterprise qualification standards."
            ),
            "company_notes": "Remix Studio keeps messaging specific while preserving rep speed.",
            "extra_constraints": "",
        },
        "global_sliders": {"formality": 40, "brevity": 65, "directness": 70, "personalization": 75},
        "presets": [{"preset_id": "challenger", "label": "The Challenger", "slider_overrides": {"directness": 80}}],
        "offer_lock": "Remix Studio",
        "cta_lock": "Open to a quick chat to see if this is relevant?",
        "cta_type": "question",
    }


def _fake_real_output() -> str:
    body = (
        "Hi Alex, Acme is scaling outbound quality controls and your SDR team is balancing speed with consistency "
        "for enterprise accounts. Remix Studio keeps first-touch messaging specific and controlled without adding "
        "manager overhead, so reps can execute with a predictable quality bar across high-volume sequences.\n\n"
        "Open to a quick chat to see if this is relevant?"
    )
    return json.dumps({"subject": "Remix Studio for Acme", "body": body}, separators=(",", ":"), ensure_ascii=True)


async def _fake_real_generate(
    prompt: list[dict[str, str]],  # noqa: ARG001
    task: str = "web_mvp",  # noqa: ARG001
    throttled: bool = False,  # noqa: ARG001
    output_token_budget: int | None = None,  # noqa: ARG001
) -> GenerateResult:
    return GenerateResult(
        text=_fake_real_output(),
        provider="openai",
        model_name="gpt-4.1-nano",
        cascade_reason="primary",
        attempt_count=1,
        finish_reason="stop",
    )


async def _fake_preview_openai(*, messages, schema, schema_name, model_name):  # noqa: ARG001
    if schema_name == "preset_preview_combined":
        return (
            {
                "summary_pack": {
                    "facts": [
                        "Acme is scaling outbound quality reviews in enterprise accounts.",
                        "Leadership tightened qualification and messaging consistency standards.",
                        "SDR teams are balancing higher send volume with response quality.",
                        "Managers need predictable first-touch quality without extra process overhead.",
                    ],
                    "hooks": [
                        "Outbound quality controls are now a leadership priority.",
                        "Enterprise qualification standards tightened this quarter.",
                        "Teams are reducing drift across first-touch sequences.",
                    ],
                    "likely_priorities": [
                        "(likely) improving reply quality from first-touch messaging",
                        "(likely) reducing quality drift across reps",
                        "(likely) keeping throughput high while maintaining message control",
                    ],
                    "keywords": ["outbound", "quality", "enterprise", "consistency", "sdr", "qualification"],
                },
                "previews": [
                    {
                        "preset_id": "challenger",
                        "label": "The Challenger",
                        "effective_sliders": {
                            "formality": 40,
                            "brevity": 65,
                            "directness": 80,
                            "personalization": 75,
                        },
                        "vibeLabel": "Risk-led direct",
                        "vibeTags": ["Direct", "Specific"],
                        "whyItWorks": [
                            "Anchors one account risk",
                            "Uses grounded proof only",
                            "Ends with one clear ask",
                        ],
                        "subject": "Remix Studio for Acme",
                        "body": (
                            "Hi Alex, Acme is tightening outbound quality controls while keeping SDR execution speed high. "
                            "Remix Studio keeps first-touch messaging specific and easier to review across reps, so quality "
                            "stays predictable under higher enterprise volume.\n\n"
                            "Open to a quick chat to see if this is relevant?"
                        ),
                    }
                ],
            },
            model_name,
        )
    return (
        {
            "previews": [
                {
                    "preset_id": "challenger",
                    "label": "The Challenger",
                    "effective_sliders": {"formality": 40, "brevity": 65, "directness": 80, "personalization": 75},
                    "vibeLabel": "Risk-led direct",
                    "vibeTags": ["Direct", "Specific"],
                    "whyItWorks": [
                        "Anchors one account risk",
                        "Uses grounded proof only",
                        "Ends with one clear ask",
                    ],
                    "subject": "Remix Studio for Acme",
                    "body": (
                        "Hi Alex, Acme is tightening outbound quality controls while keeping SDR execution speed high. "
                        "Remix Studio keeps first-touch messaging specific and easier to review across reps, so quality "
                        "stays predictable under higher enterprise volume.\n\n"
                        "Open to a quick chat to see if this is relevant?"
                    ),
                }
            ]
        },
        model_name,
    )


async def run() -> None:
    expected_web_hash = web_mvp_prompt_template_hash()
    expected_preview_hashes = preview_prompt_template_hashes()

    restore_real_generate = remix_engine._real_generate
    restore_preview_openai = preview_pipeline._openai_structured_json_with_fallback
    remix_engine._real_generate = _fake_real_generate  # type: ignore[assignment]
    preview_pipeline._openai_structured_json_with_fallback = _fake_preview_openai  # type: ignore[assignment]

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            debug = await client.get("/web/v1/debug/config?endpoint=generate&bucket_key=dev-defaults", headers=_headers())
            debug.raise_for_status()
            debug_json = debug.json()

            if debug_json.get("runtime_mode") != "real":
                raise AssertionError(f"expected runtime_mode=real, got {debug_json.get('runtime_mode')}")
            if debug_json.get("provider_stub_enabled") is True:
                raise AssertionError("expected provider_stub_enabled=false")
            effective_flags = dict(debug_json.get("effective_flags") or {})
            for feature_name in _P0_FEATURES:
                if not effective_flags.get(feature_name):
                    raise AssertionError(f"expected {feature_name}=true in dev defaults")
            prompt_versions = debug_json.get("prompt_template_versions") or {}
            if prompt_versions.get("web_mvp_prompt_hash") != expected_web_hash:
                raise AssertionError("web_mvp prompt hash mismatch")
            if prompt_versions.get("preview_prompt_hashes") != expected_preview_hashes:
                raise AssertionError("preview prompt hash mismatch")

            generate = await client.post("/web/v1/generate", json=_generate_payload(), headers=_headers())
            generate.raise_for_status()
            generate_json = generate.json()
            stream_generate = await client.get(f"/web/v1/stream/{generate_json['request_id']}", headers=_headers())
            stream_generate.raise_for_status()
            generate_done = _parse_done_payload(stream_generate.text)
            if generate_done.get("mode") != "real":
                raise AssertionError("generate mode should be real")
            if str(generate_done.get("provider") or "").lower() == "mock":
                raise AssertionError("generate provider must be real")
            if generate_done.get("prompt_template_hash") != expected_web_hash:
                raise AssertionError("generate prompt hash mismatch")

            remix = await client.post(
                "/web/v1/remix",
                json={
                    "session_id": generate_json["session_id"],
                    "preset_id": "challenger",
                    "style_profile": {"formality": 0.2, "orientation": 0.6, "length": -0.2, "assertiveness": 0.4},
                },
                headers=_headers(),
            )
            remix.raise_for_status()
            remix_json = remix.json()
            stream_remix = await client.get(f"/web/v1/stream/{remix_json['request_id']}", headers=_headers())
            stream_remix.raise_for_status()
            remix_done = _parse_done_payload(stream_remix.text)
            if remix_done.get("mode") != "real":
                raise AssertionError("remix mode should be real")
            if str(remix_done.get("provider") or "").lower() == "mock":
                raise AssertionError("remix provider must be real")
            if remix_done.get("prompt_template_hash") != expected_web_hash:
                raise AssertionError("remix prompt hash mismatch")

            preview = await client.post("/web/v1/preset-previews/batch", json=_preview_payload(), headers=_headers())
            preview.raise_for_status()
            preview_json = preview.json()
            preview_meta = preview_json.get("meta") or {}
            if preview_meta.get("generation_mode") != "real":
                raise AssertionError("preview generation_mode should be real")
            if str(preview_meta.get("provider") or "").lower() == "mock":
                raise AssertionError("preview provider must be real")
            preview_flags = dict(preview_meta.get("flags_effective") or {})
            for feature_name in _P0_FEATURES:
                if not preview_flags.get(feature_name):
                    raise AssertionError(f"expected preview flag {feature_name}=true")
            preview_prompt_versions = preview_meta.get("prompt_template_versions") or {}
            if preview_prompt_versions.get("web_mvp_prompt_hash") != expected_web_hash:
                raise AssertionError("preview meta prompt hash mismatch")

            report = {
                "runtime_mode": debug_json.get("runtime_mode"),
                "provider_stub_enabled": debug_json.get("provider_stub_enabled"),
                "p0_flags_true": {name: bool(effective_flags.get(name, False)) for name in _P0_FEATURES},
                "generate": {
                    "mode": generate_done.get("mode"),
                    "provider": generate_done.get("provider"),
                    "model": generate_done.get("model"),
                },
                "remix": {
                    "mode": remix_done.get("mode"),
                    "provider": remix_done.get("provider"),
                    "model": remix_done.get("model"),
                },
                "preview_batch": {
                    "generation_mode": preview_meta.get("generation_mode"),
                    "provider": preview_meta.get("provider"),
                    "model": preview_meta.get("model"),
                },
                "prompt_hash": expected_web_hash,
            }
            print(json.dumps(report, indent=2))
    finally:
        remix_engine._real_generate = restore_real_generate  # type: ignore[assignment]
        preview_pipeline._openai_structured_json_with_fallback = restore_preview_openai  # type: ignore[assignment]


if __name__ == "__main__":
    asyncio.run(run())
