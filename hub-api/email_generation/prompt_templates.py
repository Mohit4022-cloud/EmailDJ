"""Prompt builders for email generation and extraction."""

from __future__ import annotations


def get_quick_generate_prompt(payload: dict, account_context, slider_value: int) -> list[dict[str, str]]:
    tone = "concise and outcome-first" if slider_value <= 2 else "balanced personalization" if slider_value <= 7 else "highly personalized"
    context_json = account_context.model_dump_json() if account_context is not None else "No prior context available"
    return [
        {"role": "system", "content": "You are an expert B2B SDR. Avoid cliches and lead with value."},
        {
            "role": "user",
            "content": (
                f"Write a cold email in a {tone} style.\n"
                f"Payload: {payload}\n"
                f"Context: {context_json}\n"
                "Output with a subject line followed by body."
            ),
        },
    ]


def get_extraction_prompt(raw_notes: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "Extract structured account intelligence from CRM notes. Do not infer."},
        {"role": "user", "content": raw_notes},
    ]


def get_master_brief_prompt(account_context) -> list[dict[str, str]]:
    return [{"role": "user", "content": f"Create a concise master brief: {account_context}"}]


def get_persona_angle_prompt(brief: str, persona: str, other_personas: list) -> list[dict[str, str]]:
    return [{"role": "user", "content": f"Brief: {brief}\nPersona: {persona}\nOther: {other_personas}"}]


def get_sequence_email_prompt(angle: dict, cross_thread_context: str, email_number: int) -> list[dict[str, str]]:
    return [
        {
            "role": "user",
            "content": (
                f"Angle: {angle}\nCross-thread rule: {cross_thread_context}\n"
                f"Draft email #{email_number}. No cross-thread leakage."
            ),
        }
    ]


def get_web_mvp_prompt(
    prospect: dict,
    factual_brief: str,
    anchors: dict,
    style_profile: dict,
    prior_draft: str | None = None,
) -> list[dict[str, str]]:
    mode = "initial generation" if not prior_draft else "remix"
    return [
        {
            "role": "system",
            "content": (
                "You write high-performing outbound SDR emails. "
                "Preserve factual accuracy and never invent company facts."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Task mode: {mode}\n"
                f"Prospect: {prospect}\n"
                f"Factual brief (immutable): {factual_brief}\n"
                f"CTA/intent anchors (preserve): {anchors}\n"
                f"Style controls (continuous -1 to 1): {style_profile}\n"
                f"Prior draft for remix: {prior_draft or 'N/A'}\n"
                "Return only: Subject line, blank line, email body."
            ),
        },
    ]
