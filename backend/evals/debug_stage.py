from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.config import load_settings
from app.engine.ai_orchestrator import AIOrchestrator
from app.engine.normalize import normalize_generate_request
from app.engine.prompts import stage_a
from app.engine.schemas import RF_MESSAGING_BRIEF
from app.engine.validators import ValidationIssue, validate_messaging_brief
from app.openai_client import ENFORCED_OPENAI_MODEL, OpenAIClient
from app.schemas import WebGenerateRequest

from .eval_payloads import get_payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay a single stage for one eval payload with validator diagnostics.")
    parser.add_argument("--stage", default="a", choices=["a"], help="Stage key to debug (currently supports: a)")
    parser.add_argument("--payload", required=True, help="Payload ID from eval_payloads.py")
    parser.add_argument("--raw", action="store_true", help="Print raw prompt/input and model response")
    return parser.parse_args()


def _extract_message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "".join(parts).strip()
    return str(content or "").strip()


async def _run_stage_a(*, payload_id: str, raw: bool) -> int:
    payload = get_payload(payload_id)
    if payload is None:
        print(f"ERROR: unknown payload '{payload_id}'")
        return 2

    request = WebGenerateRequest(**dict(payload.get("request") or {}))
    settings = load_settings()
    openai = OpenAIClient(settings)
    if not openai.enabled():
        print("ERROR: OpenAI provider unavailable. Set OPENAI_API_KEY and disable USE_PROVIDER_STUB.")
        return 2

    orchestrator = AIOrchestrator(openai=openai, settings=settings)
    ctx = normalize_generate_request(request, preset_id=request.preset_id)
    cta_line = orchestrator._cta_lock(request, ctx)
    stage_a_input = orchestrator._stage_a_input(request=request, ctx=ctx, cta_line=cta_line)
    messages = stage_a.build_messages(stage_a_input)

    response = await openai.chat_completion(
        model=ENFORCED_OPENAI_MODEL,
        messages=messages,
        reasoning_effort=settings.openai_reasoning_low,
        max_completion_tokens=1800,
        response_format=RF_MESSAGING_BRIEF,
        timeout_seconds=60.0,
    )

    raw_text = _extract_message_text(dict(response.get("message") or {}))
    try:
        brief = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        print("VALIDATION=FAIL")
        print("CODES=['json_decode_failed']")
        print(f"DETAILS=[{{'error': '{exc}'}}]")
        if raw:
            print("RAW_RESPONSE_START")
            print(raw_text)
            print("RAW_RESPONSE_END")
        return 3

    if raw:
        print("STAGE_INPUT_START")
        print(json.dumps(stage_a_input, indent=2, ensure_ascii=True))
        print("STAGE_INPUT_END")
        print("RAW_RESPONSE_START")
        print(raw_text)
        print("RAW_RESPONSE_END")

    print(f"payload_id={payload_id}")
    print(f"facts={len(list(brief.get('facts_from_input') or []))}")
    print(f"hooks={len(list(brief.get('hooks') or []))}")

    try:
        validate_messaging_brief(brief, source_text=ctx.research_text, source_payload=stage_a_input)
        print("VALIDATION=PASS")
        return 0
    except ValidationIssue as exc:
        print("VALIDATION=FAIL")
        print(f"CODES={exc.codes}")
        print("DETAILS_START")
        print(json.dumps(exc.details, indent=2, ensure_ascii=True))
        print("DETAILS_END")
        return 3


async def _run() -> int:
    args = _parse_args()
    if args.stage == "a":
        return await _run_stage_a(payload_id=str(args.payload), raw=bool(args.raw))
    print(f"ERROR: unsupported stage '{args.stage}'")
    return 2


def main() -> None:
    try:
        code = asyncio.run(_run())
    except KeyboardInterrupt:
        code = 130
    raise SystemExit(code)


if __name__ == "__main__":
    main()
