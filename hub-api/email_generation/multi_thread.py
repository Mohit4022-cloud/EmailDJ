"""Multi-thread drafting helpers."""

from __future__ import annotations

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
    return (
        f"Account {context.account_name or context.account_id} in {context.industry or 'unknown industry'} "
        f"has status {context.contract_status or 'prospect'} and timing {context.timing or 'unspecified'}."
    )


async def generate_persona_angle(brief: str, persona: str, other_personas: list) -> PersonaAngle:
    tone = {
        "CFO": "ROI and risk aware",
        "VP_Ops": "efficiency-first",
        "Head_IT": "technical and integration-focused",
        "champion": "peer-to-peer",
    }.get(persona, "professional")
    return PersonaAngle(
        persona=persona,
        pain_points=["operational drag"],
        value_props=["faster outbound execution"],
        do_not_mention=list(other_personas),
        tone=tone,
        opening_hook_options=[f"{persona}: quick idea based on your current priorities"],
    )


async def draft_persona_email(angle: PersonaAngle, cross_thread_context: str) -> str:
    return (
        f"Subject: Idea for {angle.persona}\n\n"
        f"I put together one recommendation tied to {angle.value_props[0]}. "
        f"{cross_thread_context}"
    )
