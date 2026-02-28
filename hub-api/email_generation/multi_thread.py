"""
Multi-Thread Email Generation — narrative coherence across personas.

IMPLEMENTATION INSTRUCTIONS:
Exports:
  generate_master_brief(context: AccountContext) → str
  generate_persona_angle(brief: str, persona: str, other_personas: list[str]) → PersonaAngle
  draft_persona_email(angle: PersonaAngle, cross_thread_context: str) → str

PersonaAngle (dataclass or TypedDict):
  { persona: str, pain_points: list[str], value_props: list[str],
    do_not_mention: list[str], tone: str, opening_hook_options: list[str] }

generate_master_brief(context):
  - Tier 1 model call.
  - Input: full AccountContext JSON.
  - Output: ~500 token narrative covering:
    a. Account situation (what's happening at the company)
    b. Key terminology (words/phrases the buyer uses — quote from vault notes)
    c. Primary value prop framing for this specific account
    d. Competitive landscape hints (from notes, NOT speculation)
    e. Urgency signals (timing, budget cycle, recent changes)
  - Use get_master_brief_prompt() from prompt_templates.

generate_persona_angle(brief, persona, other_personas):
  - Tier 2 model call.
  - Persona options: 'CFO', 'VP_Ops', 'Head_IT', 'champion', 'VP_Sales'
  - For each persona: extract subset of brief relevant to their role.
  - Define do_not_mention: topics the other_personas threads will cover
    (to avoid cross-thread exposure).
  - Tone calibration: CFO=ROI/risk-focused, VP_Ops=efficiency-focused,
    Head_IT=technical/integration-focused, champion=peer-to-peer/authentic.
  - Return PersonaAngle.

draft_persona_email(angle, cross_thread_context):
  - Tier 2 model call.
  - System prompt MUST include: "No email should contain information that
    could ONLY be known if you'd spoken to another person at the company."
  - Include cross_thread_context (sanitized summaries of adjacent threads).
  - Use get_sequence_email_prompt() from prompt_templates.
  - The cross_thread_context example:
    "You are writing to the CFO. Do not mention you have contacted others at
    the company. You may subtly reference operational efficiency concerns as
    relevant to CFO's cost containment mandate."
  - Stagger send windows in metadata:
    - champion/peer: email_number=1, send_window='day_0'
    - adjacent stakeholders: email_number=2, send_window='day_3'
    - executives: email_number=3, send_window='day_7'
"""

from dataclasses import dataclass, field
from context_vault.models import AccountContext


@dataclass
class PersonaAngle:
    persona: str
    pain_points: list = field(default_factory=list)
    value_props: list = field(default_factory=list)
    do_not_mention: list = field(default_factory=list)
    tone: str = "professional"
    opening_hook_options: list = field(default_factory=list)


async def generate_master_brief(context: AccountContext) -> str:
    # TODO: implement per instructions above
    raise NotImplementedError("generate_master_brief not yet implemented")


async def generate_persona_angle(brief: str, persona: str, other_personas: list) -> PersonaAngle:
    # TODO: implement per instructions above
    raise NotImplementedError("generate_persona_angle not yet implemented")


async def draft_persona_email(angle: PersonaAngle, cross_thread_context: str) -> str:
    # TODO: implement per instructions above
    raise NotImplementedError("draft_persona_email not yet implemented")
