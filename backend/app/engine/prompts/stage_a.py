from __future__ import annotations

from typing import Any


def _list_lines(values: list[Any]) -> str:
    clean = [str(item).strip() for item in values if str(item).strip()]
    if not clean:
        return ""
    return "\n".join(f"- {item}" for item in clean)


def _field_text(value: Any) -> str:
    return str(value or "").strip()


def build_messages(payload: dict[str, Any], *, research_state: str = "grounded") -> list[dict[str, str]]:
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
{_field_text(user_company.get("product_summary"))}

Ideal Customer Profile:
{_field_text(user_company.get("icp_description"))}

Differentiators:
{_list_lines(list(user_company.get("differentiators") or []))}

Proof Points:
{_list_lines(list(user_company.get("proof_points") or []))}

Do-Not-Say List:
{_list_lines(list(user_company.get("do_not_say") or []))}

Additional Company Notes:
{_field_text(user_company.get("company_notes"))}

PROSPECT CONTEXT
Name: {_field_text(prospect.get("name"))}
Title: {_field_text(prospect.get("title"))}
Company: {_field_text(prospect.get("company"))}
Industry: {_field_text(prospect.get("industry"))}

prospect_notes:
{_field_text(prospect.get("notes"))}

research_text:
{_field_text(prospect.get("research_text"))}

LOCKED CTA
CTA Type: {str(cta.get("cta_type") or "question").strip() or "question"}
CTA Final Line (LOCKED): {str(cta.get("cta_final_line") or "").strip()}

SEMANTIC INPUT STATE
- research_state: {research_state}
- research_text contributes facts only when research_state is sparse or grounded.
- research_state=no_research means research_text contributes zero facts and cannot justify launches, posts, news, initiatives, or congratulatory hooks.
- research_state=sparse means keep hooks conservative and role-aware; do not overreach into fictional specificity.
- Blank field bodies and blank list sections are absent input, not evidence.

YOUR INSTRUCTIONS

STEP 1 - FACT EXTRACTION
- Extract all hard facts from input.
- Assign sequential fact_id values: fact_01, fact_02, ...
- Record exact source_field from the strict allowlist below.
- If info is not explicit in input, it is not a fact.

CRITICAL source_field rule: you must use ONLY these exact strings as source_field values.
No variations, no abbreviations, no invented names:
  "name"
  "title"
  "company"
  "industry"
  "prospect_notes"
  "research_text"
  "product_summary"
  "icp_description"
  "differentiators"
  "proof_points"
  "do_not_say"
  "company_notes"
  "cta_type"
  "cta_final_line"
The value must be copied exactly, including underscores.
Never add spaces inside a source_field token.
If a fact comes from research text about the prospect, source_field must be "research_text".
Never use "research", "research_activity", or any other variation.
If a fact cannot be attributed to one of these exact strings, do not include it.

EMPTY FIELD RULE:
- Blank field bodies and blank list sections contain zero facts.
- If a field has no usable signal, do not create a fact with that field as source_field.
- Placeholder/null-ish text must never appear anywhere in output, including hooks, assumptions, persona_cues, or allowed_personalization_fact_sources.

CONTAINMENT CHECK (run this before finalizing facts_from_input):
- For each fact ask: "If I removed every input field and only had this fact, could I identify which specific input field it came from?"
- If the answer is no, remove the fact as ungrounded.
- Do not include facts about how companies in this industry typically operate.
- Do not include competitor facts unless competitors are explicitly named in input fields.
- Do not include market trends, industry benchmarks, or sector norms unless explicitly stated in input fields.
- If research_text is sparse or empty, facts_from_input about the prospect should be few.
- Do not compensate for sparse input by importing training knowledge.
- In sparse-input conditions, set signal_strength honestly (often low).
- If research_state is no_research, prospect facts should come only from name/title/company and any non-empty prospect_notes.
- A brief with three grounded facts is better than ten facts with hallucinated content.

STEP 2 - CONSTRAINT MAPPING
- Determine which proof points are most relevant to this prospect.
- Add any context-specific phrases to do_not_say when warranted.

STEP 3 - INFERENCE LAYER
- For significant prospect facts, infer likely priorities as assumptions.
- Every assumption needs: text, confidence 0.0-0.85, and based_on_fact_ids.
- In sparse-input or no_research conditions, assumptions must be conservative, explicitly uncertain, and tied to role/title/company context only.

STEP 4 - HOOK IDENTIFICATION
- Grounded input may produce 3-5 hooks.
- sparse or no_research input should usually produce 1-3 conservative hooks.
- Hook quality bar: specific to this prospect, tied to business priority, and fact-backed.
- Assign hook_type from: pain | priority | initiative | tooling | trigger_event | other.
- Do not create event/news/post/congrats hooks unless directly grounded in usable research_text facts.

STEP 5 - PERSONA CUES
- Infer likely_kpis, likely_initiatives, day_to_day, and tools_stack from title/industry/research.
- Keep these as inferences, not facts.
- Do not use placeholder entries like "unknown" or "none provided".
- When research_state is no_research, keep persona cues generic to the role/title and avoid invented initiatives or tools.
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
- grounding_policy.allowed_personalization_fact_sources should list only exact source_field values with usable non-placeholder signal.
- Do not list fields that are blank, absent, or semantically no_research.

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
