from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.openai_client import OpenAIClient

from .realize import word_band_for_brevity
from .types import EmailDraft, MessagePlan, NormalizedContext


@dataclass(slots=True)
class LLMRealizerResult:
    draft: EmailDraft | None
    attempt_count: int
    messages: list[dict[str, str]]
    error: str | None = None
    raw_word_count: int | None = None


def email_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["subject", "body"],
    }


def _clean_text(value: str | None) -> str:
    return str(value or "").strip()


def _clamped_slider(raw: Any, default: int = 50) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(0, min(100, value))


def _orientation_label(ctx: NormalizedContext) -> tuple[str, str]:
    axis = float(ctx.style_profile.get("orientation", 0.0))
    if axis <= -0.2:
        return ("problem-led", "Lead with concrete pain/friction before outcomes.")
    if axis >= 0.2:
        return ("outcome-led", "Lead with business outcomes and measurable impact.")
    return ("balanced", "Balance current pain with a practical outcome focus.")


def _assertiveness_label(ctx: NormalizedContext) -> tuple[str, str]:
    axis = float(ctx.style_profile.get("assertiveness", 0.0))
    if axis <= -0.2:
        return ("bold", "Use crisp, confident language without sounding aggressive.")
    if axis >= 0.2:
        return ("diplomatic", "Use polite and measured language while staying specific.")
    return ("balanced", "Be direct and tactful in equal measure.")


def _formality_label(ctx: NormalizedContext) -> tuple[str, str]:
    formality = _clamped_slider(ctx.sliders.get("formality", 50))
    if formality >= 67:
        return ("formal", "Use professional phrasing and avoid slang.")
    if formality <= 33:
        return ("casual", "Use approachable language but remain business-appropriate.")
    return ("balanced", "Use concise professional language with light warmth.")


def _length_label(ctx: NormalizedContext) -> tuple[str, str]:
    brevity = _clamped_slider(ctx.sliders.get("brevity", 50))
    if brevity >= 67:
        return ("short", "Target roughly 3-5 short paragraphs. No filler.")
    if brevity <= 33:
        return ("long", "Allow fuller context, but keep only useful detail.")
    return ("medium", "Use moderate length with clear progression and no filler.")


def _length_budget(ctx: NormalizedContext) -> tuple[int, int, int]:
    brevity = _clamped_slider(ctx.sliders.get("brevity", 50))
    min_words, max_words = word_band_for_brevity(brevity)
    return brevity, min_words, max_words


def _sentence_target(max_words: int) -> str:
    if max_words <= 80:
        return "3-4"
    if max_words <= 130:
        return "4-6"
    if max_words <= 180:
        return "5-8"
    return "6-9"


def _preset_style_note(preset_id: str) -> str:
    key = _clean_text(preset_id).lower()
    if key in {"straight_shooter", "straight-shooter"}:
        return "Straight Shooter: crisp, direct, 3-5 concise paragraphs."
    if key in {"challenger", "headliner"}:
        return "Challenger: direct point of view, specific tension, practical recommendation."
    if key in {"warm_intro", "warm-intro"}:
        return "Warm Intro: respectful, warm tone while staying concise and concrete."
    return ""


def _research_facts(research_text: str) -> list[str]:
    text = _clean_text(research_text)
    if not text:
        return []
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]
    return sentences[:3]


def build_system_prompt(ctx: NormalizedContext, plan: MessagePlan) -> str:
    formality_label, formality_instruction = _formality_label(ctx)
    orientation_label, orientation_instruction = _orientation_label(ctx)
    assertiveness_label, assertiveness_instruction = _assertiveness_label(ctx)
    length_label, length_instruction = _length_label(ctx)
    _, _, max_words = _length_budget(ctx)
    sentence_target = _sentence_target(max_words)
    seller_name = _clean_text(ctx.sender_company_name)
    cta = _clean_text(plan.cta_line_locked or ctx.cta_lock)
    seller_rule = (
        f"- Mention seller company name \"{seller_name}\" at least once."
        if seller_name
        else "- Mention the seller explicitly using the provided offer/product context."
    )

    return "\n".join(
        [
            "You are an elite B2B cold email copywriter.",
            "Write one outbound email subject and body as STRICT JSON only.",
            "Rules:",
            "- First line must reference something specific from research_text OR a hedged role hypothesis if research_text is empty.",
            "- Never use generic openers: \"hope this finds you\", \"wanted to reach out\", \"synergy\", \"circle back\", \"touch base\".",
            seller_rule,
            "- No invented facts. Use only facts from research_text, company_notes, proof_points, seller_offerings.",
            "- Never mention internal_modules.",
            f"- Body must be <= {max_words} words total.",
            f"- Target {sentence_target} narrative sentences before the CTA line.",
            "- If over word budget, shorten by removing filler and combining sentences.",
            f"- CTA must appear exactly once as the final line and match exactly: {cta}",
            "- Do not add any text after the CTA line.",
            "- Output ONLY valid JSON matching the schema. No prose, no markdown, no extra keys.",
            "Style controls:",
            f"- formality={formality_label}: {formality_instruction}",
            f"- orientation={orientation_label}: {orientation_instruction}",
            f"- assertiveness={assertiveness_label}: {assertiveness_instruction}",
            f"- length={length_label}: {length_instruction}",
        ]
    )


def build_user_payload(ctx: NormalizedContext, plan: MessagePlan) -> dict[str, Any]:
    brevity, min_words, max_words = _length_budget(ctx)
    payload: dict[str, Any] = {
        "seller": {
            "company_name": _clean_text(ctx.sender_company_name),
            "company_url": _clean_text(ctx.sender_company_url),
            "current_product": _clean_text(ctx.current_product),
            "offer_lock": _clean_text(ctx.offer_lock),
        },
        "seller_offerings": [item for item in ctx.seller_offerings if _clean_text(item)],
        "proof_points": [item for item in ctx.proof_points if _clean_text(item)],
        "prospect": {
            "name": _clean_text(ctx.prospect_name),
            "title": _clean_text(ctx.prospect_title),
            "company": _clean_text(ctx.prospect_company),
        },
        "research_text": _clean_text(ctx.research_text),
        "plan": {
            "hook_type": plan.hook_type,
            "hook_sentence": _clean_text(plan.hook_sentence),
            "hook_facts": _research_facts(ctx.research_text),
            "pains_kpis": [item for item in plan.persona_pains_kpis if _clean_text(item)],
            "kpi": _clean_text(plan.persona_pains_kpis[0] if plan.persona_pains_kpis else ""),
            "value_prop": _clean_text(plan.value_prop),
            "proof_point": _clean_text(plan.proof_point),
            "selected_beat_ids": list(plan.selected_beat_ids),
        },
        "cta_offer_lock": _clean_text(plan.cta_line_locked or ctx.cta_lock),
        "length_budget": {
            "brevity_slider": brevity,
            "min_words": min_words,
            "max_words": max_words,
            "target_sentence_count": _sentence_target(max_words),
        },
    }
    style_note = _preset_style_note(ctx.preset_id)
    if style_note:
        payload["preset_style_note"] = style_note
    return payload


def assemble_llm_prompt_messages(ctx: NormalizedContext, plan: MessagePlan) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": build_system_prompt(ctx, plan)},
        {
            "role": "user",
            "content": (
                "Use the following seller-safe context. Return only JSON.\n"
                f"{json.dumps(build_user_payload(ctx, plan), ensure_ascii=True)}"
            ),
        },
    ]


def _normalize_body(text: str) -> str:
    body = _clean_text(text).replace("\r\n", "\n")
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def _payload_to_draft(payload: dict[str, Any], *, plan: MessagePlan) -> EmailDraft | None:
    if not isinstance(payload, dict):
        return None
    subject = _clean_text(payload.get("subject"))
    body = _clean_text(payload.get("body"))
    if not subject or not body:
        return None

    body = _normalize_body(body)
    if not body or not subject:
        return None

    return EmailDraft(
        subject=subject,
        body=body,
        subject_source="llm_realizer",
        body_sources=["llm_realizer"],
        selected_beat_ids=list(plan.selected_beat_ids),
    )


async def _call_structured_email(
    *,
    openai: OpenAIClient,
    settings: Settings,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    return await openai.chat_json(
        messages=messages,
        reasoning_effort=settings.openai_reasoning_low,
        schema_name="email_draft_v1",
        schema=email_schema(),
        max_completion_tokens=900,
    )


def _json_only_repair_messages(ctx: NormalizedContext, plan: MessagePlan) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Return ONLY valid JSON that matches the schema exactly. "
                "No commentary, no markdown, no extra keys."
            ),
        },
        {
            "role": "user",
            "content": (
                "The previous output could not be parsed or was missing required fields.\n"
                "Regenerate from the same context with strict JSON only.\n"
                f"{json.dumps(build_user_payload(ctx, plan), ensure_ascii=True)}"
            ),
        },
    ]


def _validator_repair_messages(
    *,
    ctx: NormalizedContext,
    plan: MessagePlan,
    draft: EmailDraft,
    violations: list[str],
) -> list[dict[str, str]]:
    _, _, max_words = _length_budget(ctx)
    payload = {
        "violations": list(violations),
        "current_draft": {"subject": draft.subject, "body": draft.body},
        "context": build_user_payload(ctx, plan),
    }
    return [
        {
            "role": "system",
            "content": (
                "Repair the draft using only provided facts. "
                "Return ONLY valid JSON matching schema with keys subject/body. "
                f"Body must be <= {max_words} words. CTA must remain exact and final."
            ),
        },
        {
            "role": "user",
            "content": (
                "Fix the violations, keep the CTA exact as final line, and stay within the word budget.\n"
                f"{json.dumps(payload, ensure_ascii=True)}"
            ),
        },
    ]


async def llm_realize(
    *,
    plan: MessagePlan,
    ctx: NormalizedContext,
    openai: OpenAIClient,
    settings: Settings,
) -> LLMRealizerResult:
    messages = assemble_llm_prompt_messages(ctx, plan)
    attempts = 0

    try:
        attempts += 1
        payload = await _call_structured_email(openai=openai, settings=settings, messages=messages)
    except Exception as exc:  # noqa: BLE001
        return LLMRealizerResult(draft=None, attempt_count=attempts, messages=messages, error=str(exc))

    draft = _payload_to_draft(payload, plan=plan)
    if draft is not None:
        return LLMRealizerResult(
            draft=draft,
            attempt_count=attempts,
            messages=messages,
            raw_word_count=_word_count(draft.body),
        )

    try:
        attempts += 1
        repair_messages = _json_only_repair_messages(ctx, plan)
        repaired_payload = await _call_structured_email(openai=openai, settings=settings, messages=repair_messages)
    except Exception as exc:  # noqa: BLE001
        return LLMRealizerResult(draft=None, attempt_count=attempts, messages=messages, error=str(exc))

    repaired_draft = _payload_to_draft(repaired_payload, plan=plan)
    if repaired_draft is None:
        return LLMRealizerResult(draft=None, attempt_count=attempts, messages=messages, error="llm_json_parse_failed")
    return LLMRealizerResult(
        draft=repaired_draft,
        attempt_count=attempts,
        messages=messages,
        raw_word_count=_word_count(repaired_draft.body),
    )


async def llm_repair(
    *,
    plan: MessagePlan,
    ctx: NormalizedContext,
    draft: EmailDraft,
    violations: list[str],
    openai: OpenAIClient,
    settings: Settings,
) -> LLMRealizerResult:
    messages = _validator_repair_messages(ctx=ctx, plan=plan, draft=draft, violations=violations)

    try:
        payload = await _call_structured_email(openai=openai, settings=settings, messages=messages)
    except Exception as exc:  # noqa: BLE001
        return LLMRealizerResult(draft=None, attempt_count=1, messages=messages, error=str(exc))

    repaired = _payload_to_draft(payload, plan=plan)
    if repaired is None:
        return LLMRealizerResult(draft=None, attempt_count=1, messages=messages, error="llm_repair_parse_failed")
    return LLMRealizerResult(
        draft=repaired,
        attempt_count=1,
        messages=messages,
        raw_word_count=_word_count(repaired.body),
    )
