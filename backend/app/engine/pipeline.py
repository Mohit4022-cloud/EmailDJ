from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.config import Settings
from app.openai_client import OpenAIClient

from .llm_realizer import assemble_llm_prompt_messages, llm_realize, llm_repair
from .planning import build_message_plan
from .postprocess import (
    deterministic_postprocess_draft,
    has_any_mechanical_violations,
    violation_codes,
    word_count,
)
from .realize import word_band_for_brevity
from .types import EmailDraft, EngineResult, MessagePlan, NormalizedContext, ValidationDebug
from .validate import validate_draft

logger = logging.getLogger(__name__)


def assembled_prompt_messages(ctx: NormalizedContext, plan: MessagePlan) -> list[dict[str, Any]]:
    return assemble_llm_prompt_messages(ctx, plan)


def fallback_draft(ctx: NormalizedContext, plan: MessagePlan | None = None) -> EmailDraft:
    del ctx, plan
    raise RuntimeError("deterministic_fallback_disabled")


async def run_engine_async(
    ctx: NormalizedContext,
    *,
    max_repairs: int = 1,
    openai: OpenAIClient | None = None,
    settings: Settings | None = None,
) -> EngineResult:
    debug = ValidationDebug()

    t0 = time.perf_counter()
    plan = build_message_plan(ctx)
    debug.stage_latency_ms["message_plan"] = int(round((time.perf_counter() - t0) * 1000))
    debug.length_input_raw = float(ctx.style_profile.get("length", 0.0))
    debug.length_normalized = int(ctx.sliders.get("brevity", 50))
    debug.word_band_min, debug.word_band_max = word_band_for_brevity(debug.length_normalized)

    provider_configured = bool(openai and openai.enabled())
    llm_drafting_enabled = bool(settings and settings.llm_drafting_enabled)
    llm_ready = bool(provider_configured and llm_drafting_enabled and openai and settings)
    if not llm_ready:
        raise RuntimeError("ai_only_pipeline_requires_openai")

    t1 = time.perf_counter()
    llm_attempt_count = 0
    if not (openai and settings):
        raise RuntimeError("ai_only_pipeline_requires_openai")
    llm_result = await llm_realize(plan=plan, ctx=ctx, openai=openai, settings=settings)
    llm_attempt_count += llm_result.attempt_count
    debug.word_count_llm_raw = llm_result.raw_word_count
    if llm_result.draft is None:
        raise RuntimeError(f"llm_realize_failed:{llm_result.error or 'unknown'}")
    draft = llm_result.draft
    draft_source = "llm"

    logger.info(
        "engine_draft_selected draft_source=%s llm_drafting_enabled=%s provider_configured=%s",
        draft_source,
        llm_drafting_enabled,
        provider_configured,
    )
    debug.stage_latency_ms["realize"] = int(round((time.perf_counter() - t1) * 1000))

    validation_runs = 0

    def _validate(label: str = "validate") -> list[str]:
        nonlocal validation_runs
        started = time.perf_counter()
        current = validate_draft(draft, plan, ctx)
        validation_runs += 1
        suffix = "" if validation_runs == 1 else f"_{validation_runs}"
        debug.stage_latency_ms[f"{label}{suffix}"] = int(round((time.perf_counter() - started) * 1000))
        return current

    def _apply_mechanical_postprocess(current_violations: list[str]) -> tuple[list[str], list[str]]:
        nonlocal draft
        if not current_violations or not has_any_mechanical_violations(current_violations):
            return current_violations, []
        before_subject = draft.subject
        before_body = draft.body
        outcome = deterministic_postprocess_draft(
            draft,
            max_words=debug.word_band_max,
            cta_line=plan.cta_line_locked or ctx.cta_lock,
            subject_limit=70,
        )
        applied = outcome.applied
        draft = outcome.draft
        changed = draft.subject != before_subject or draft.body != before_body
        if not applied and not changed:
            return current_violations, []
        if changed and not applied:
            applied = ["mechanical_postprocess"]
        return _validate(label="validate"), applied

    violations = _validate(label="validate")
    debug.validation_error_codes_raw = violation_codes(violations)

    attempts = 0
    repaired = False
    postprocess_applied: list[str] = []
    if violations:
        violations, applied = _apply_mechanical_postprocess(violations)
        if applied:
            postprocess_applied.extend(applied)
            if not violations:
                draft_source = "llm_postprocessed"

        can_retry_llm = bool(openai and settings)
        needs_llm_repair = bool(violations)
        if needs_llm_repair and attempts < max_repairs and can_retry_llm and openai and settings:
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
                violations = _validate(label="validate")
                violations, repair_applied = _apply_mechanical_postprocess(violations)
                if repair_applied:
                    postprocess_applied.extend(repair_applied)
                    if not violations:
                        draft_source = "llm_postprocessed"
            debug.stage_latency_ms[f"repair_{attempts}"] = int(round((time.perf_counter() - t_repair) * 1000))

    if violations:
        raise RuntimeError(f"final_validation_failed:{','.join(violations)}")

    debug.violations = violations
    debug.repair_attempt_count = attempts
    debug.validator_attempt_count = validation_runs
    debug.repaired = repaired or bool(postprocess_applied)
    debug.draft_source = draft_source
    debug.llm_attempt_count = llm_attempt_count
    debug.llm_used = llm_attempt_count > 0
    debug.postprocess_applied = list(dict.fromkeys(postprocess_applied))
    debug.word_count_final = word_count(draft.body)
    debug.validation_error_codes_final = violation_codes(violations)

    logger.info(
        "engine_length_observability length_input_raw=%s length_normalized=%s "
        "word_band_min=%s word_band_max=%s word_count_llm_raw=%s word_count_final=%s "
        "postprocess_applied=%s validation_error_codes_raw=%s validation_error_codes_final=%s draft_source=%s",
        debug.length_input_raw,
        debug.length_normalized,
        debug.word_band_min,
        debug.word_band_max,
        debug.word_count_llm_raw,
        debug.word_count_final,
        debug.postprocess_applied,
        debug.validation_error_codes_raw,
        debug.validation_error_codes_final,
        debug.draft_source,
    )

    return EngineResult(draft=draft, debug=debug, plan=plan)


def run_engine(
    ctx: NormalizedContext,
    *,
    max_repairs: int = 1,
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
