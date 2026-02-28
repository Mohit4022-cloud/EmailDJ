"""
Prompt Templates — all LLM prompt construction logic.

IMPLEMENTATION INSTRUCTIONS:
Exports:
  get_quick_generate_prompt(payload, account_context, slider_value) → str | list[BaseMessage]
  get_extraction_prompt(raw_notes) → list[BaseMessage]
  get_master_brief_prompt(account_context) → list[BaseMessage]
  get_persona_angle_prompt(brief, persona, other_personas) → list[BaseMessage]
  get_sequence_email_prompt(angle, cross_thread_context, email_number) → list[BaseMessage]

get_quick_generate_prompt(payload, account_context, slider_value):
  - Slider 0 (efficiency): short, direct email. Lead with business outcome.
    Template: 3 sentences max. Clear CTA. No fluff.
  - Slider 10 (personalization): deeply personalized. Reference specific
    account details, recent news, personal pain points.
    Template: 5–8 sentences. Demonstrate research.
  - Interpolate: at slider=5, blend both approaches.
  - System prompt: "You are an expert B2B SDR writing a cold email to {role}
    at {company}. Write in first person as the SDR. Be authentic, not salesy.
    Never use clichés like 'I hope this finds you well' or 'reaching out to
    touch base'. Lead with value."
  - Include in user message: account context (industry, size, status, pain points
    from vault), payload (recent activity), slider instruction.
  - IMPORTANT: If account_context is None (cold account), use payload data only
    and note "No prior context available — research recommended."

get_extraction_prompt(raw_notes):
  - System: "Extract structured account intelligence from CRM notes. Only extract
    explicit information — never infer or hallucinate."
  - Define JSON schema in prompt (strict mode function calling preferred).

get_master_brief_prompt(account_context):
  - Tier 1 prompt. Produce: account story, key value prop framing, terminology
    the buyer uses (quote directly from vault notes), competitive landscape hints.

get_persona_angle_prompt(brief, persona, other_personas):
  - Produce PersonaAngle: { pain_points: list, value_props: list, do_not_mention: list,
    tone: str, opening_hook_options: list[str] }
  - do_not_mention is derived from what the other_personas threads will cover.

get_sequence_email_prompt(angle, cross_thread_context, email_number):
  - email_number 1: opener — high personalization, clear ask
  - email_number 2: different angle, social proof, case study reference
  - email_number 3: break-up — low pressure, leave door open
  - Include cross_thread_context constraint in system prompt.
"""


def get_quick_generate_prompt(payload: dict, account_context, slider_value: int) -> list:
    # TODO: implement per instructions above
    raise NotImplementedError("get_quick_generate_prompt not yet implemented")


def get_extraction_prompt(raw_notes: str) -> list:
    # TODO: implement per instructions above
    raise NotImplementedError("get_extraction_prompt not yet implemented")


def get_master_brief_prompt(account_context) -> list:
    # TODO: implement per instructions above
    raise NotImplementedError("get_master_brief_prompt not yet implemented")


def get_persona_angle_prompt(brief: str, persona: str, other_personas: list) -> list:
    # TODO: implement per instructions above
    raise NotImplementedError("get_persona_angle_prompt not yet implemented")


def get_sequence_email_prompt(angle: dict, cross_thread_context: str, email_number: int) -> list:
    # TODO: implement per instructions above
    raise NotImplementedError("get_sequence_email_prompt not yet implemented")
