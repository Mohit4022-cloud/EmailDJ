from __future__ import annotations

from typing import Any

from app.config import Settings
from app.openai_client import OpenAIClient
from app.prompts import compile_blueprint_prompt
from app.schemas import ContactProfile, EmailBlueprint, SenderProfile, TargetAccountProfile, WebGenerateRequest


def _blueprint_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "identity": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "sender_name": {"type": ["string", "null"]},
                    "sender_company": {"type": "string"},
                    "prospect_name": {"type": "string"},
                    "prospect_title": {"type": "string"},
                    "prospect_company": {"type": "string"},
                },
                "required": ["sender_company", "prospect_name", "prospect_title", "prospect_company", "sender_name"],
            },
            "angle": {"type": "string"},
            "personalization_facts_used": {"type": "array", "items": {"type": "string"}},
            "structure": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "opener_hook": {"type": "string"},
                    "why_you_why_now": {"type": "string"},
                    "value_points": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 3},
                    "proof_line": {"type": ["string", "null"]},
                    "cta_line_locked": {"type": "string"},
                },
                "required": ["opener_hook", "why_you_why_now", "value_points", "proof_line", "cta_line_locked"],
            },
            "constraints": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "forbidden_claims": {"type": "array", "items": {"type": "string"}},
                    "max_facts_allowed": {"type": "integer"},
                    "target_word_count_range_by_length_slider": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "short": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                            "medium": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                            "long": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                        },
                        "required": ["short", "medium", "long"],
                    },
                    "must_include_cta_lock": {"type": "boolean"},
                },
                "required": [
                    "forbidden_claims",
                    "max_facts_allowed",
                    "target_word_count_range_by_length_slider",
                    "must_include_cta_lock",
                ],
            },
        },
        "required": ["identity", "angle", "personalization_facts_used", "structure", "constraints"],
    }


def _fallback_blueprint(
    req: WebGenerateRequest,
    sender_profile: SenderProfile,
    target_profile: TargetAccountProfile,
    contact_profile: ContactProfile,
) -> EmailBlueprint:
    sender_company = sender_profile.company_name or req.company_context.company_name or "Your Company"
    facts: list[str] = []
    for item in target_profile.proof_points[:2]:
        facts.append(item)
    for item in contact_profile.talking_points[:2]:
        facts.append(item)
    if req.company_context.company_notes:
        facts.append("manual input: " + req.company_context.company_notes[:160])
    if not facts:
        facts.append("manual input")

    value_points = []
    if target_profile.summary and target_profile.summary != "Unknown":
        value_points.append(target_profile.summary[:180])
    if sender_profile.notes_summary:
        value_points.append(sender_profile.notes_summary[:180])
    if contact_profile.role_summary and contact_profile.role_summary != "Unknown":
        value_points.append(contact_profile.role_summary[:180])
    while len(value_points) < 2:
        value_points.append("Role-specific relevance without unsupported claims.")

    cta = req.cta_offer_lock or req.company_context.cta_offer_lock or "Open to a quick chat to see if this is relevant?"

    return EmailBlueprint(
        identity={
            "sender_name": None,
            "sender_company": sender_company,
            "prospect_name": req.prospect.name,
            "prospect_title": req.prospect.title,
            "prospect_company": req.prospect.company,
        },
        angle="Outcome-led relevance with dated public triggers",
        personalization_facts_used=facts[:4],
        structure={
            "opener_hook": f"Noticed recent momentum at {req.prospect.company}.",
            "why_you_why_now": f"Given {req.prospect.title} priorities, this may be timely.",
            "value_points": value_points[:3],
            "proof_line": sender_profile.proof_points[0] if sender_profile.proof_points else None,
            "cta_line_locked": cta,
        },
        constraints={
            "forbidden_claims": [
                "No uncited metrics",
                "No guarantees",
            ],
            "max_facts_allowed": 4,
            "target_word_count_range_by_length_slider": {
                "short": [55, 75],
                "medium": [75, 110],
                "long": [110, 160],
            },
            "must_include_cta_lock": True,
        },
    )


async def compile_blueprint(
    *,
    req: WebGenerateRequest,
    sender_profile: SenderProfile,
    target_profile: TargetAccountProfile,
    contact_profile: ContactProfile,
    openai: OpenAIClient,
    settings: Settings,
) -> EmailBlueprint:
    payload = {
        "prospect": req.prospect.model_dump(),
        "research_text": req.research_text,
        "offer_lock": req.offer_lock,
        "cta_offer_lock": req.cta_offer_lock or req.company_context.cta_offer_lock,
        "cta_type": req.cta_type or req.company_context.cta_type,
        "company_context": req.company_context.model_dump(exclude_none=True),
        "sender_profile": sender_profile.model_dump(),
        "target_profile": target_profile.model_dump(),
        "contact_profile": contact_profile.model_dump(),
    }

    if openai.enabled():
        try:
            result = await openai.chat_json(
                messages=compile_blueprint_prompt(payload),
                reasoning_effort=settings.openai_reasoning_high,
                schema_name="email_blueprint",
                schema=_blueprint_schema(),
                max_completion_tokens=1200,
            )
            if result:
                return EmailBlueprint(**result)
        except Exception:
            pass

    return _fallback_blueprint(req, sender_profile, target_profile, contact_profile)


def merge_manual_overrides(
    *,
    req: WebGenerateRequest,
    sender_profile: SenderProfile,
    target_profile: TargetAccountProfile,
    contact_profile: ContactProfile,
) -> tuple[SenderProfile, TargetAccountProfile, ContactProfile]:
    # Manual overrides always win.
    if req.sender_profile_override is not None:
        sender_profile = req.sender_profile_override
    if req.target_profile_override is not None:
        target_profile = req.target_profile_override
    if req.contact_profile_override is not None:
        contact_profile = req.contact_profile_override

    if req.company_context.company_name:
        sender_profile.company_name = req.company_context.company_name
    if req.prospect.title:
        contact_profile.current_title = req.prospect.title
    if req.prospect.company:
        contact_profile.company = req.prospect.company
    if req.prospect.name:
        contact_profile.name = req.prospect.name
    return sender_profile, target_profile, contact_profile

