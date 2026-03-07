from __future__ import annotations

import json
from typing import Any


def build_messages(messaging_brief: dict[str, Any]) -> list[dict[str, str]]:
    brief_json = json.dumps(messaging_brief, indent=2, ensure_ascii=True)

    system = (
        "You are a Senior Account Executive preparing fit reasoning for a high-stakes outbound motion. "
        "Your job is not to write an email. Build a ranked FitMap that answers: "
        "Why should this person at this company care about this product right now?\\n\\n"
        "RULE 1 - GROUND EVERYTHING.\\n"
        "Every hypothesis must reference at least one fact_id or assumption_id from MessagingBrief.\\n\\n"
        "RULE 2 - PROOF MUST BE REAL.\\n"
        "The proof field must reference seller-side support from the brief, or explicitly state proof gap. "
        "Prospect facts are never proof. If seller proof is absent, use the exact phrase "
        "\"Proof gap: no seller proof provided in brief.\"\\n\\n"
        "RULE 2A - CLASSIFY PROOF HONESTLY.\\n"
        "Every hypothesis must include proof_basis.kind as one of: hard_proof, soft_signal, capability_statement, assumption, none. "
        "Hard proof = grounded seller proof with concrete evidence. Soft signal = grounded seller proof without hard metrics. "
        "Capability statement = honest capability language with no proof claim. Assumption = explicitly framed inference. "
        "none = exact proof gap.\\n\\n"
        "RULE 3 - WHY NOW MUST BE EARNED.\\n"
        "Use real timing signals when present; otherwise mark as evergreen and do not manufacture urgency.\\n\\n"
        "RULE 4 - NO INVENTED NUMBERS.\\n"
        "If the brief lacks explicit metrics, keep impact qualitative. Do not invent percentages, timeframes, or revenue deltas.\\n\\n"
        "RULE 5 - RANK HONESTLY.\\n"
        "Rank using confidence, persona relevance, and evidence quality.\\n\\n"
        "Output strict JSON only. No markdown. No commentary. Match FitMap schema exactly."
    )

    user = f"""Build a FitMap from this MessagingBrief.

MESSAGING BRIEF
{brief_json}

YOUR INSTRUCTIONS

STEP 1 - PERSONA REALITY CHECK
Internally evaluate day-to-day concerns, downside risk, upside metrics, and decision influence.

STEP 2 - BUILD THE CHAIN
For each hypothesis provide:
- pain: specific persona friction.
- impact: concrete cost (time, revenue, missed targets, risk, team drag).
- value: specific outcome from the offered solution.
- proof: seller-side proof/support from brief.hooks[].seller_support or seller_proof facts, or the exact proof gap statement.
- proof_basis: include kind, source_fact_ids, source_hook_ids, source_fit_hypothesis_id, grounded_span, source_text, proof_gap.
- proof_basis.kind rules:
  - hard_proof only when seller-side evidence supports a concrete proof claim.
  - soft_signal only when seller-side evidence is real but not metric-grade.
  - capability_statement when honest capability language is the strongest grounded option.
  - assumption when the claim is explicitly inferential.
  - none only with the exact proof gap phrase.
- supporting_fact_ids: list only the exact fact ids you actually used to justify the hypothesis.
- impact: if no explicit metric exists in those supporting facts, keep it qualitative and bounded.

STEP 3 - WHY NOW
- If a trigger exists, ground why_now with source IDs and only use prospect-side grounded observation.
- If no trigger exists, use evergreen framing honestly.

STEP 4 - SCORE AND RANK
- confidence in [0.0, 1.0].
- Rank from strongest to weakest with tie-breakers favoring timing signal and proof quality.

STEP 5 - RISK FLAGS
Apply flags where relevant:
- proof_gap
- assumption_heavy
- low_persona_fit
- no_timing_signal
- do_not_say_conflict

STEP 6 - SELF-AUDIT
Before output:
- Every selected_hook_id exists in brief.hooks[].hook_id.
- Every supporting_fact_id exists in brief.facts_from_input[].fact_id.
- proof is either grounded in seller-side evidence or exactly "Proof gap: no seller proof provided in brief."
- proof_basis must agree with proof text and source ids.
- why_now is grounded or honestly evergreen.
- ranking is consistent with confidence and evidence.

Now output complete FitMap JSON only."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
