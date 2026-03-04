from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.config import Settings
from app.openai_client import OpenAIClient

from .llm_realizer import assemble_llm_prompt_messages, llm_realize, llm_repair
from .planning import build_message_plan
from .realize import realize_email
from .repair import repair_draft
from .types import EmailDraft, EngineResult, MessagePlan, NormalizedContext, ValidationDebug
from .validate import validate_draft

logger = logging.getLogger(__name__)


def assembled_prompt_messages(ctx: NormalizedContext, plan: MessagePlan) -> list[dict[str, Any]]:
    return assemble_llm_prompt_messages(ctx, plan)


def fallback_draft(ctx: NormalizedContext, plan: MessagePlan | None = None) -> EmailDraft:
    cta = (plan.cta_line_locked if plan else ctx.cta_lock) or "Open to a quick chat to see if this is relevant?"
    offer = ctx.offer_lock or ctx.current_product or "our platform"
    subject = f"Quick idea for {ctx.prospect_company or 'your team'}"[:78]
    body = "\n\n".join(
        [
            f"Hi {ctx.prospect_first_name or 'there'},",
            f"{offer} helps teams improve workflow consistency with clearer execution.",
            cta,
        ]
    )
    return EmailDraft(
        subject=subject,
        body=body,
        subject_source="fallback",
        body_sources=["fallback", "cta"],
        selected_beat_ids=["fallback", "cta"],
    )


async def run_engine_async(
    ctx: NormalizedContext,
    *,
    max_repairs: int = 2,
    openai: OpenAIClient | None = None,
    settings: Settings | None = None,
) -> EngineResult:
    debug = ValidationDebug()

    t0 = time.perf_counter()
    plan = build_message_plan(ctx)
    debug.stage_latency_ms["message_plan"] = int(round((time.perf_counter() - t0) * 1000))

    provider_configured = bool(openai and openai.enabled())
    llm_drafting_enabled = bool(settings and settings.llm_drafting_enabled)
    llm_ready = bool(provider_configured and llm_drafting_enabled and openai and settings)

    t1 = time.perf_counter()
    llm_attempt_count = 0
    draft_source = "deterministic"
    draft = realize_email(plan, ctx)
    if llm_ready and openai and settings:
        llm_result = await llm_realize(plan=plan, ctx=ctx, openai=openai, settings=settings)
        llm_attempt_count += llm_result.attempt_count
        if llm_result.draft is not None:
            draft = llm_result.draft
            draft_source = "llm"
        else:
            # LLM schema/JSON failures move to neutral safe fallback; transport errors can use deterministic continuity.
            if llm_result.error == "llm_json_parse_failed":
                draft = fallback_draft(ctx, plan)
                draft_source = "fallback"
            else:
                draft = realize_email(plan, ctx)
                draft_source = "deterministic"
            debug.degraded = True

    logger.info(
        "engine_draft_selected draft_source=%s llm_drafting_enabled=%s provider_configured=%s",
        draft_source,
        llm_drafting_enabled,
        provider_configured,
    )
    debug.stage_latency_ms["realize"] = int(round((time.perf_counter() - t1) * 1000))

    t2 = time.perf_counter()
    violations = validate_draft(draft, plan, ctx)
    debug.stage_latency_ms["validate"] = int(round((time.perf_counter() - t2) * 1000))

    attempts = 0
    repaired = False
    if violations and draft_source == "llm":
        can_retry_llm = llm_attempt_count < 2 and bool(openai and settings)
        if can_retry_llm and openai and settings:
            attempts += 1
            repaired = True
            t_repair = time.perf_counter()
            llm_fix = await llm_repair(
                plan=plan,
                ctx=ctx,
                draft=draft,
                violations=violations,
                openai=openai,
                settings=settings,
            )
            llm_attempt_count += llm_fix.attempt_count
            if llm_fix.draft is not None:
                draft = llm_fix.draft
                violations = validate_draft(draft, plan, ctx)
            debug.stage_latency_ms[f"repair_{attempts}"] = int(round((time.perf_counter() - t_repair) * 1000))
    else:
        while violations and attempts < max_repairs:
            attempts += 1
            repaired = True
            t_repair = time.perf_counter()
            draft = repair_draft(draft, plan, ctx, violations)
            debug.stage_latency_ms[f"repair_{attempts}"] = int(round((time.perf_counter() - t_repair) * 1000))
            violations = validate_draft(draft, plan, ctx)

    if violations:
        draft = fallback_draft(ctx, plan)
        debug.degraded = True
        draft_source = "fallback"
        violations = validate_draft(draft, plan, ctx)

    debug.violations = violations
    debug.repair_attempt_count = attempts
    debug.validator_attempt_count = 1 + attempts
    debug.repaired = repaired
    debug.draft_source = draft_source
    debug.llm_attempt_count = llm_attempt_count
    debug.llm_used = llm_attempt_count > 0

    return EngineResult(draft=draft, debug=debug, plan=plan)


def run_engine(
    ctx: NormalizedContext,
    *,
    max_repairs: int = 2,
    openai: OpenAIClient | None = None,
    settings: Settings | None = None,
) -> EngineResult:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        raise RuntimeError("run_engine cannot be called inside an active event loop; use run_engine_async")
    return asyncio.run(
        run_engine_async(
            ctx,
            max_repairs=max_repairs,
            openai=openai,
            settings=settings,
        )
    )
