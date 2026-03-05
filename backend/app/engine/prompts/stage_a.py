from __future__ import annotations

import json
from typing import Any


def _list_lines(values: list[Any]) -> str:
    clean = [str(item).strip() for item in values if str(item).strip()]
    if not clean:
        return "- None provided."
    return "\n".join(f"- {item}" for item in clean)


def build_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    user_company = dict(payload.get("user_company") or {})
    prospect = dict(payload.get("prospect") or {})
    cta = dict(payload.get("cta") or {})

    system = (
        "You are a Senior SDR Strategy Director with 15 years building outbound campaigns. "
        "Your job is not to write an email. Your job is to build a Source of Truth document "
        "called MessagingBrief.\\n\\n"
        "You operate by three laws:\\n"
        "LAW 1 - FACTS ONLY IN facts_from_input.\\n"
        "A fact must be explicitly present in input fields. If you cannot point to a field, it is not a fact. "
        "Do not infer in this section.\\n\\n"
        "LAW 2 - INFERENCES ARE ASSUMPTIONS.\\n"
        "Any prediction or logical leap belongs in assumptions with based_on_fact_ids and honest confidence. "
        "Most inferences should be in the 0.5 to 0.75 range.\\n\\n"
        "LAW 3 - HOOKS MUST EARN THEIR PLACE.\\n"
        "A hook is valid only if it cites at least one fact_id from facts_from_input. "
        "Discard ungrounded hooks; 3 strong hooks are better than 5 weak hooks.\\n\\n"
        "Output strict JSON only. No markdown. No commentary. Match MessagingBrief schema exactly."
    )

    user = f"""Build a MessagingBrief for this outbound campaign.

USER COMPANY PROFILE
Product Summary:
{str(user_company.get("product_summary") or "").strip() or "None provided."}

Ideal Customer Profile:
{str(user_company.get("icp_description") or "").strip() or "None provided."}

Differentiators:
{_list_lines(list(user_company.get("differentiators") or []))}

Proof Points:
{_list_lines(list(user_company.get("proof_points") or []))}

Do-Not-Say List:
{_list_lines(list(user_company.get("do_not_say") or []))}

Additional Company Notes:
{str(user_company.get("company_notes") or "").strip() or "None provided."}

PROSPECT CONTEXT
Name: {str(prospect.get("name") or "").strip() or "Unknown"}
Title: {str(prospect.get("title") or "").strip() or "Unknown"}
Company: {str(prospect.get("company") or "").strip() or "Unknown"}
Industry: {str(prospect.get("industry") or "").strip() or "Unknown"}

Prospect Notes:
{str(prospect.get("notes") or "").strip() or "None provided."}

Research / Recent Activity:
{str(prospect.get("research_text") or "").strip() or "None provided."}

LOCKED CTA
CTA Type: {str(cta.get("cta_type") or "question").strip() or "question"}
CTA Final Line (LOCKED): {str(cta.get("cta_final_line") or "").strip()}

YOUR INSTRUCTIONS

STEP 1 - FACT EXTRACTION
- Extract all hard facts from input.
- Assign sequential fact_id values: fact_01, fact_02, ...
- Record exact source_field (research_text, prospect_notes, proof_points, etc).
- If info is not explicit in input, it is not a fact.

STEP 2 - CONSTRAINT MAPPING
- Determine which proof points are most relevant to this prospect.
- Add any context-specific phrases to do_not_say when warranted.

STEP 3 - INFERENCE LAYER
- For significant prospect facts, infer likely priorities as assumptions.
- Every assumption needs: text, confidence 0.0-0.85, and based_on_fact_ids.

STEP 4 - HOOK IDENTIFICATION
- Produce 3-5 hooks grounded in facts.
- Hook quality bar: specific to this prospect, tied to business priority, and fact-backed.
- Assign hook_type from: pain | priority | initiative | tooling | trigger_event | other.

STEP 5 - PERSONA CUES
- Infer likely_kpis, likely_initiatives, day_to_day, and tools_stack from title/industry/research.
- Keep these as inferences, not facts.
- persona_cues.notes must be included (empty string allowed).

STEP 6 - FORBIDDEN CLAIM PATTERNS
- Populate forbidden_claim_patterns with ungrounded personalization/performance claims to avoid.
- Always include patterns like:
  - saw your recent post
  - noticed you recently
  - congrats on [anything not in research_text]

STEP 7 - COMPLETENESS SIGNAL
- grounding_policy.no_new_facts = true
- grounding_policy.no_ungrounded_personalization = true
- grounding_policy.allowed_personalization_fact_sources should list only fields with usable grounded signal.

Also include top-level brief_quality:
{{
  "fact_count": <int>,
  "assumption_count": <int>,
  "hook_count": <int>,
  "has_research": <true|false>,
  "confidence_ceiling": <float>,
  "signal_strength": "high" | "medium" | "low",
  "quality_notes": [<string>, ...]
}}

signal_strength rules:
- high: fact_count >= 6 AND has_research is true AND hook_count >= 3
- medium: fact_count >= 3 OR has_research is true
- low: fact_count < 3 AND has_research is false

Also include top-level brief_id as a non-empty string.

Now output complete MessagingBrief JSON only."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
