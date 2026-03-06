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
        "You operate by four laws:\\n"
        "LAW 1 - FACTS ARE EXPLICIT INPUT ONLY.\\n"
        "If you cannot point to a specific input field, it is not a fact.\\n\\n"
        "LAW 2 - RELEVANCE IS NOT PROOF.\\n"
        "Prospect/company context may justify relevance. It never proves seller effectiveness.\\n\\n"
        "LAW 3 - HYPOTHESES MUST BE LABELED.\\n"
        "Any interpretation, priority guess, or business implication belongs in assumptions or inferred_relevance.\\n\\n"
        "LAW 4 - STRONG CLAIMS REQUIRE STRONG EVIDENCE.\\n"
        "High confidence and strong evidence_strength require explicit seller proof plus grounded prospect context.\\n\\n"
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
- Record fact_kind for every fact:
  - prospect_context: name, title, company, industry, prospect_notes, research_text
  - seller_context: product_summary, icp_description, differentiators, company_notes, do_not_say
  - seller_proof: proof_points only
  - cta: cta_type, cta_final_line
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
- Do not extract CTA lines or banned-phrase lists as evidence for signal strength unless needed for policy tracking.
- Do not duplicate the same seller sentence across multiple facts just because similar input fields overlap.

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
- Separate what is known from what is inferred:
  - grounded fact = explicit input only
  - inferred hypothesis = plausible but uncertain interpretation of prospect context
  - seller support = seller-side differentiator or proof only
- Prospect/company context may explain why outreach could matter.
- Prospect/company context must never appear as seller proof.
- Add any context-specific phrases to do_not_say when warranted.

STEP 3 - INFERENCE LAYER
- For significant prospect facts, infer likely priorities as assumptions.
- Every assumption needs:
  - assumption_kind = "inferred_hypothesis"
  - text
  - confidence 0.0-0.85
  - confidence_label = low | medium | high
  - based_on_fact_ids
- In sparse-input or no_research conditions, assumptions must be conservative, explicitly uncertain, and tied to role/title/company context only.
- If input is thin, prefer medium or low confidence. High confidence is rare.

STEP 4 - HOOK IDENTIFICATION
- Grounded input may produce 3-5 hooks.
- sparse or no_research input should usually produce 1-3 conservative hooks.
- Every hook must separate four layers:
  - grounded_observation = explicit prospect-side fact only
  - inferred_relevance = why that observation may matter, written as a hypothesis when needed
  - seller_support = seller-side support only; may be empty when no seller proof/support exists
  - hook_text = compressed outreach angle that faithfully reflects the three fields above
- Assign hook_type from: pain | priority | initiative | tooling | trigger_event | other.
- Do not create event/news/post/congrats hooks unless directly grounded in usable research_text facts.
- Do not imply recent events, launches, rollouts, initiatives, or urgency unless directly grounded in research_text facts.
- Do not convert titles into certainties.
- Do not turn possible relevance into clear business need.
- seller_fact_ids may cite seller_context or seller_proof facts only.
- If seller_support is empty, add risk flag seller_proof_gap.
- confidence_level = low | medium | high.
- evidence_strength = weak | moderate | strong.
- high confidence or strong evidence_strength require at least one seller_proof fact plus grounded prospect context.

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
- Also populate prohibited_overreach with concrete internal warnings such as:
  - unsupported_recency
  - unsupported_initiative
  - prospect_as_proof
  - role_as_certainty
  - placeholder_as_evidence

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
  "grounded_fact_count": <int>,
  "prospect_context_fact_count": <int>,
  "seller_context_fact_count": <int>,
  "seller_proof_fact_count": <int>,
  "cta_fact_count": <int>,
  "confidence_ceiling": <float>,
  "signal_strength": "high" | "medium" | "low",
  "overreach_risk": "low" | "medium" | "high",
  "quality_notes": [<string>, ...]
}}

signal_strength rules:
- high: grounded prospect context + explicit seller proof + at least one strong hook
- medium: either grounded research OR explicit seller proof exists, but the case is not strong enough for high
- low: sparse role/company context with no grounded research and no explicit seller proof

NON-NEGOTIABLE FORBIDDEN BEHAVIOR
- Never use prospect context as proof that the seller works.
- Do not imply specific initiatives without evidence.
- Do not imply recent events without evidence.
- Never use placeholders or null-ish strings as evidence.
- Never invent urgency.
- When research_state is no_research, prefer low-confidence, role-aware, generic relevance over fake specificity.

Also include top-level brief_id as a non-empty string.

Now output complete MessagingBrief JSON only."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
