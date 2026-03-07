from __future__ import annotations

import json
from typing import Any


def build_messages(messaging_brief: dict[str, Any], fit_map: dict[str, Any]) -> list[dict[str, str]]:
    brief_json = json.dumps(messaging_brief, indent=2, ensure_ascii=True)
    fitmap_json = json.dumps(fit_map, indent=2, ensure_ascii=True)

    system = (
        "You are a B2B creative director building the angle library for outbound. "
        "Your job is not to write an email. Produce 3-5 genuinely distinct angles for the same campaign.\\n\\n"
        "RULE 1 - DISTINCTNESS.\\n"
        "Angles must start from meaningfully different entry points in the prospect world.\\n\\n"
        "RULE 1A - DISTINCTNESS MUST BE EXPLICIT.\\n"
        "Each angle must expose primary_pain, primary_value_motion, primary_proof_basis, framing_type, and risk_level so the next stage can depend on the exact chosen angle.\\n\\n"
        "RULE 1B - DISTINCTNESS MUST CHANGE THE PITCH.\\n"
        "If two angles would lead to the same opener, same value sentence, or same proof role with light paraphrase, they are not distinct enough.\\n\\n"
        "RULE 2 - FITMAP AS COMPASS.\\n"
        "Use fit hypotheses and ranks as primary guidance, but allow justified rank overrides.\\n\\n"
        "RULE 3 - RISK FLAGS MUST TRAVEL.\\n"
        "Carry hypothesis risk flags into each angle and add new angle-specific flags when needed.\\n\\n"
        "RULE 4 - CTA BRIDGE.\\n"
        "Each angle must include a natural cta_question_suggestion.\\n\\n"
        "RULE 5 - HONEST PERSONA FIT.\\n"
        "Score persona_fit_score conservatively and contextually.\\n\\n"
        "Output strict JSON only. No markdown. No commentary. Match AngleSet schema exactly."
    )

    user = f"""Design an angle library for this campaign.

MESSAGING BRIEF
{brief_json}

FITMAP
{fitmap_json}

AVAILABLE ANGLE TYPES
- why_you_why_now
- problem_led
- outcome_led
- proof_led
- objection_prebunk

YOUR INSTRUCTIONS

STEP 1 - TERRAIN SURVEY
Internally identify strongest fact, strongest proof, timing signal quality, and top persona concerns.

STEP 2 - DISQUALIFICATION RULES
- why_you_why_now is disqualified when no real timing signal exists.
- proof_led is disqualified when all hypotheses have proof_gap.
- objection_prebunk is disqualified when brief_quality.signal_strength is low.

STEP 3 - BUILD 3-5 ANGLES
For each angle include:
- angle_id sequential (angle_01, angle_02...)
- angle_type (qualified types only)
- rank
- persona_fit_score
- selected_hook_id (must exist in brief.hooks)
- selected_fit_hypothesis_id (must exist in fit_map.hypotheses)
- pain, impact, value, proof
- proof_basis copied/adapted honestly from the selected fit hypothesis
- primary_pain
- primary_value_motion
- primary_proof_basis
- framing_type
- risk_level
- cta_question_suggestion
- risk_flags (inherited + new)

STEP 4 - RANKING
Primary rank signal: persona fit x fit-map confidence proxy.
Tie-breakers: timing signal, proof quality, fewer risk flags.
If override needed, add risk flag rank_override:<reason>.

STEP 5 - DISTINCTNESS SELF-AUDIT
- No duplicate angle types.
- No duplicate selected_hook_id.
- No duplicate effective tuple: primary_pain + primary_value_motion + primary_proof_basis + framing_type.
- No near-duplicate entry point, opener thesis, or proof role.
- At least one skeptical score (<0.65) when signal is medium/low.
- All IDs resolve to source structures.

Now output complete AngleSet JSON only."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
