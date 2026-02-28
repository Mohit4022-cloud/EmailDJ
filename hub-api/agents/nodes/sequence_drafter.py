"""
Sequence Drafter Node — multi-thread email sequence generation.

IMPLEMENTATION INSTRUCTIONS:
This is the most token-intensive node. Scale: 50 accounts × 3 personas × 3 emails
= 450 model calls. Use asyncio batching with concurrency limit to avoid rate limits.

For EACH account in state["audience"]:
  Step 1 — Generate Account Master Brief:
    - Tier 1 model call (GPT-4o or Claude Sonnet).
    - Input: full AccountContext from vault + CRM data.
    - Output: master_brief (str) — account-level story, key terminology, value prop
      framing. ~500 tokens. This brief is shared by all personas.
    - Call email_generation.multi_thread.generate_master_brief(context).

  Step 2 — Generate Persona Angles (CFO, VP Ops, Head of IT):
    - Tier 2 model call per persona.
    - For each persona, extract the subset of master_brief relevant to that role.
    - Define "Do Not Mention" list: topics the other personas are hearing
      that could expose multi-threading.
    - Call email_generation.multi_thread.generate_persona_angle(
        brief, persona, other_personas).

  Step 3 — Draft 3-email sequence per persona:
    - Tier 2 model call per email.
    - Include cross_thread_context: "You are writing to [PERSONA]. Do not mention
      you have contacted others at the company. You may subtly reference
      [ADJACENT_PAIN_POINT] as relevant to [PERSONA]'s interests."
    - Key constraint: "No email should contain information that could ONLY be
      known if you'd spoken to another person at the company."
    - Email 1: opener (personalized, value-prop focused)
    - Email 2: follow-up (different angle, social proof)
    - Email 3: break-up (low-pressure, leave door open)
    - Stagger send windows in metadata: champion first, adjacent stakeholders
      2–3 days later, executives after initial engagement signals.
    - Call email_generation.multi_thread.draft_persona_email(angle, cross_ctx).

Batching:
  - Use asyncio.gather() with semaphore (max 10 concurrent calls) to avoid
    OpenAI/Anthropic rate limits.
  - Process accounts in batches of 10.

Store all sequences in state["sequences"] as:
  { "{account_id}_{persona}": [email1, email2, email3] }
"""

from agents.state import AgentState


async def sequence_drafter_node(state: AgentState) -> AgentState:
    # TODO: implement per instructions above
    raise NotImplementedError("sequence_drafter_node not yet implemented")
