from __future__ import annotations

import json
import re
from typing import Any

from app.config import Settings
from app.openai_client import OpenAIClient
from app.prompts import render_email_prompt
from app.schemas import EmailBlueprint, WebStyleProfile


PRESET_TACTICS: dict[str, dict[str, str]] = {
    "straight_shooter": {"angle_shift": "direct", "hook": "concise"},
    "headliner": {"angle_shift": "bold", "hook": "news"},
    "c_suite_sniper": {"angle_shift": "executive", "hook": "risk"},
    "industry_insider": {"angle_shift": "domain", "hook": "trend"},
}


def style_params(style: WebStyleProfile) -> dict[str, float]:
    return {
        "formality": max(0.0, min(1.0, (style.formality + 1.0) / 2.0)),
        "outcome_bias": max(0.0, min(1.0, (style.orientation + 1.0) / 2.0)),
        "length": max(0.0, min(1.0, (style.length + 1.0) / 2.0)),
        "diplomacy": max(0.0, min(1.0, (style.assertiveness + 1.0) / 2.0)),
    }


def _word_band(blueprint: EmailBlueprint, length_norm: float) -> tuple[int, int]:
    ranges = blueprint.constraints.target_word_count_range_by_length_slider
    if length_norm < 0.33:
        return tuple(ranges.get("short", [55, 75]))  # type: ignore[return-value]
    if length_norm < 0.66:
        return tuple(ranges.get("medium", [75, 110]))  # type: ignore[return-value]
    return tuple(ranges.get("long", [110, 160]))  # type: ignore[return-value]


def _fallback_render(blueprint: EmailBlueprint, style: WebStyleProfile, preset_id: str | None) -> dict[str, str]:
    params = style_params(style)
    min_words, max_words = _word_band(blueprint, params["length"])
    tactic = PRESET_TACTICS.get((preset_id or "").strip(), {})
    hook = blueprint.structure.opener_hook
    if tactic.get("hook") == "news":
        hook = f"{hook} Timing looked worth a quick note."
    elif tactic.get("hook") == "risk":
        hook = f"{hook} The risk of delay seems higher right now."

    if params["outcome_bias"] >= 0.5:
        framing = "If helpful, this is about faster outcomes with lower outreach friction."
    else:
        framing = "If helpful, this is about reducing execution drag before it compounds."

    value_points = blueprint.structure.value_points[:3]
    lines = [
        f"Hi {blueprint.identity.prospect_name.split()[0]},",
        hook,
        blueprint.structure.why_you_why_now,
        framing,
    ]
    for point in value_points:
        lines.append(f"- {point}")
    if blueprint.structure.proof_line:
        lines.append(blueprint.structure.proof_line)
    lines.append(blueprint.structure.cta_line_locked)

    body = "\n".join([line.strip() for line in lines if line.strip()])
    words = re.findall(r"\b\w+\b", body)
    if len(words) > max_words:
        trimmed = " ".join(words[:max_words])
        if not trimmed.endswith((".", "!", "?")):
            trimmed = trimmed.rstrip(",;:") + "."
        body = trimmed + "\n" + blueprint.structure.cta_line_locked
    subject_seed = blueprint.angle[:60].strip() or "Quick idea"
    subject = f"{subject_seed} for {blueprint.identity.prospect_company}"[:78]
    return {"subject": subject, "body": body}


def _email_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["subject", "body"],
    }


async def render_email(
    *,
    blueprint: EmailBlueprint,
    style: WebStyleProfile,
    preset_id: str | None,
    openai: OpenAIClient,
    settings: Settings,
) -> dict[str, str]:
    if openai.enabled():
        try:
            payload = await openai.chat_json(
                messages=render_email_prompt(blueprint.model_dump(), style_params(style), preset_id=preset_id),
                reasoning_effort=settings.openai_reasoning_low,
                schema_name="rendered_email",
                schema=_email_schema(),
                max_completion_tokens=900,
            )
            if payload and payload.get("subject") and payload.get("body"):
                return {"subject": str(payload.get("subject", "")).strip(), "body": str(payload.get("body", "")).strip()}
        except Exception:
            pass

    return _fallback_render(blueprint, style, preset_id)


def render_to_text(subject: str, body: str) -> str:
    return f"Subject: {subject.strip()}\nBody:\n{body.strip()}"

