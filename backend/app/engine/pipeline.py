from __future__ import annotations

import time
from typing import Any

from .planning import build_message_plan
from .realize import realize_email
from .repair import repair_draft
from .types import EmailDraft, EngineResult, MessagePlan, NormalizedContext, ValidationDebug
from .validate import validate_draft


def assembled_prompt_messages(ctx: NormalizedContext, plan: MessagePlan) -> list[dict[str, Any]]:
    # Deterministic prompt assembly trace for debugging and tests.
    return [
        {
            "role": "system",
            "content": "Write one concise business email using only provided seller and prospect context.",
        },
        {
            "role": "developer",
            "content": "Never include internal module names. Use seller-facing offerings only. Keep CTA exact and final.",
        },
        {
            "role": "user",
            "content": {
                "prospect": {
                    "name": ctx.prospect_name,
                    "title": ctx.prospect_title,
                    "company": ctx.prospect_company,
                },
                "seller": {
                    "offer_lock": ctx.offer_lock,
                    "current_product": ctx.current_product,
                    "seller_offerings": list(ctx.seller_offerings),
                },
                "plan": {
                    "hook": plan.hook_sentence,
                    "value_prop": plan.value_prop,
                    "kpis": list(plan.persona_pains_kpis),
                    "proof_point": plan.proof_point,
                    "cta_line_locked": plan.cta_line_locked,
                    "selected_beat_ids": list(plan.selected_beat_ids),
                },
                "style": {
                    "sliders": dict(ctx.sliders),
                    "preset_id": ctx.preset_id,
                    "product_category": ctx.product_category,
                },
            },
        },
    ]


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


def run_engine(ctx: NormalizedContext, *, max_repairs: int = 2) -> EngineResult:
    debug = ValidationDebug()

    t0 = time.perf_counter()
    plan = build_message_plan(ctx)
    debug.stage_latency_ms["message_plan"] = int(round((time.perf_counter() - t0) * 1000))

    t1 = time.perf_counter()
    draft = realize_email(plan, ctx)
    debug.stage_latency_ms["realize"] = int(round((time.perf_counter() - t1) * 1000))

    t2 = time.perf_counter()
    violations = validate_draft(draft, plan, ctx)
    debug.stage_latency_ms["validate"] = int(round((time.perf_counter() - t2) * 1000))

    attempts = 0
    repaired = False
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
        violations = validate_draft(draft, plan, ctx)

    debug.violations = violations
    debug.repair_attempt_count = attempts
    debug.validator_attempt_count = 1 + attempts
    debug.repaired = repaired

    return EngineResult(draft=draft, debug=debug, plan=plan)
