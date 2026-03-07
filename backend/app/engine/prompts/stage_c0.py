from __future__ import annotations

import json
from typing import Any


def _tone_instruction(tone: float) -> str:
    if tone < 0.3:
        return "Formal business language. No contractions."
    if tone > 0.7:
        return "Peer-to-peer language. Contractions are fine."
    return "Professional but conversational."


def _framing_instruction(framing: float) -> str:
    if framing < 0.3:
        return "Lead with problem/pain framing."
    if framing > 0.7:
        return "Lead with outcome framing."
    return "Balance pain and outcome."


def _stance_instruction(stance: float) -> str:
    if stance < 0.3:
        return "Suggestive and tentative tone."
    if stance > 0.7:
        return "Direct and confident tone."
    return "Grounded confidence without aggression."


def _length_instruction(length: str) -> str:
    bands = {
        "short": "40-80 words",
        "medium": "80-140 words",
        "long": "140-220 words",
    }
    return bands.get(length, "80-140 words")


def build_messages(
    *,
    messaging_brief: dict[str, Any],
    fit_map: dict[str, Any],
    angle_set: dict[str, Any],
    selected_angle_id: str,
    preset_id: str,
    preset_contract: dict[str, Any],
    budget_plan: dict[str, Any],
    sliders: dict[str, Any],
    cta_final_line: str,
) -> list[dict[str, str]]:
    selected = next(
        (item for item in (angle_set.get("angles") or []) if str(item.get("angle_id") or "") == selected_angle_id),
        ((angle_set.get("angles") or [{}])[0] if angle_set.get("angles") else {}),
    )

    tone = float(sliders.get("tone", 0.4))
    framing = float(sliders.get("framing", 0.5))
    stance = float(sliders.get("stance", 0.5))
    length = str(sliders.get("length", "medium"))

    system = (
        "You are a master outbound copywriter focused on compression without information loss. "
        "Your job is not to write the final email. Build MessageAtoms that constrain the next stage.\\n\\n"
        "RULE 1 - ONE SENTENCE PER ATOM.\\n"
        "Each non-empty atom is exactly one sentence. proof_atom may be empty string when no external proof exists.\\n\\n"
        "RULE 2 - OPENER EARNS ATTENTION FAST.\\n"
        "No generic openers or vanity compliments. Start in the prospect world. "
        "opener_line must equal opener_atom, be one sentence, plain English, <=14 words, <=1 comma, and avoid Given/As/With/Considering openers unless the preset explicitly permits it.\\n\\n"
        "RULE 2A - DO NOT HIDE COMPLEXITY IN PUNCTUATION.\\n"
        "Avoid semicolons, colon-led pivots, or dash bridges in the opener. If secondary context matters, save it for a later atom.\\n\\n"
        "RULE 3 - VALUE ATOM NAMES OUTCOME.\\n"
        "Value must be an outcome, not a product feature list.\\n\\n"
        "RULE 4 - PROOF ATOM IS HONEST.\\n"
        "Proof must come from external evidence; prospect facts are not proof. "
        "Use a real proof point or set proof_atom to empty string. Never invent proof. "
        "If seller_proof_fact_count is 0 or selected_angle risk flags include proof_gap / seller_proof_gap, proof_atom must be empty string.\\n\\n"
        "RULE 4A - PROOF BASIS MUST TRAVEL.\\n"
        "Emit proof_basis with kind, source_fact_ids, source_hook_ids, source_fit_hypothesis_id, grounded_span, source_text, and proof_gap. "
        "If proof_basis.kind is capability_statement, assumption, or none, proof_atom should usually be empty string.\\n\\n"
        "RULE 5 - CTA IDEA VS CTA LINE.\\n"
        "cta_intent describes the ask concept in plain language. "
        "cta_atom and required_cta_line must both equal the locked final CTA exactly; no edits.\\n\\n"
        "RULE 6 - BUDGETS ARE LOCKED AT PLAN TIME.\\n"
        "target_word_budget must copy the provided budget plan exactly. "
        "target_sentence_budget must equal the number of non-empty atoms, counting CTA as one sentence.\\n\\n"
        "RULE 7 - HOOK IDS MUST BE UNIQUE.\\n"
        "used_hook_ids must be a deduped list. If the selected angle uses one hook, output that hook id exactly once.\\n\\n"
        "RULE 7A - CANONICAL HOOK LINEAGE MUST TRAVEL.\\n"
        "Emit canonical_hook_ids as the current grounded hook ids from the brief so downstream stages can validate lineage.\\n\\n"
        "RULE 7B - CTA LOCK MUST TRAVEL.\\n"
        "Emit cta_lock.final_line and cta_lock.normalized_final_line, both matching the locked CTA exactly.\\n\\n"
        f"Active sliders: tone={_tone_instruction(tone)} framing={_framing_instruction(framing)} "
        f"stance={_stance_instruction(stance)} target_length={_length_instruction(length)}.\\n\\n"
        "Output strict JSON only. No markdown. No commentary. Match MessageAtoms schema exactly."
    )

    user_payload = {
        "preset_id": preset_id,
        "locked_cta": cta_final_line,
        "preset_contract": preset_contract,
        "budget_plan": budget_plan,
        "selected_angle": selected,
        "messaging_brief": messaging_brief,
        "fit_map": fit_map,
    }

    user = (
        "Build MessageAtoms for this campaign.\\n\\n"
        f"CONTEXT JSON:\\n{json.dumps(user_payload, indent=2, ensure_ascii=True)}\\n\\n"
        "INSTRUCTIONS:\\n"
        "1) opener_atom: one specific sentence tied to selected angle and grounded signal. It must clearly reflect selected_angle.primary_pain and selected_angle.framing_type.\\n"
        "   Complexity test: read opener_atom aloud. If it contains more than one comma or more than one connecting word "
        "(which, that, and, because, so), rewrite as two thoughts and keep only the stronger one.\\n"
        "   On low-signal or no-research briefs, keep opener_atom to one clause and avoid role-accountability inflation.\\n"
        "   opener_line must equal opener_atom exactly. opener_contract must be {max_words:14, max_commas:1, plain_english_required:true, allow_leading_subordinate_clause:false}.\\n"
        "2) value_atom formula (use this structure exactly): "
        "\"[Persona's team] [specific verb: cut/reduced/protected/freed] "
        "[specific metric or outcome] [timeframe if available from proof points].\"\\n"
        "   If no metric exists in brief proof points, use: "
        "\"[Persona] gains [specific capability] without [specific cost or tradeoff].\"\\n"
        "   If neither form is possible from brief facts, use a direct yes-question: "
        "\"Is [specific outcome] something your team is actively trying to nail this quarter?\"\\n"
        "   value_atom may never be imperative. It is never a command. It is always about them.\\n"
        "   Do not hide mechanism language inside value_atom. Avoid trailing 'with', 'by', 'using', or 'through' clauses unless the outcome clause is already complete and concrete.\\n"
        "3) proof_atom: describe a result achieved by someone OTHER than the prospect. "
        "This is external evidence that the seller's product works.\\n"
        "   Proof formula: "
        "\"[Named customer or 'a [industry] team'] [achieved specific result] [using/after specific action].\"\\n"
        "   If no brief proof point supports this formula, set proof_atom to empty string \"\".\\n"
        "   Fact IDs are for grounding only; never include fact_id references inline.\\n"
        "   CRITICAL: never use the prospect's own facts as proof. Prospect context belongs in opener_atom only.\\n"
        "4) cta_intent: describe the ask concept in your own words without changing the final CTA line.\\n"
        "5) cta_atom: exact locked CTA. required_cta_line: exact locked CTA. cta_lock.final_line and cta_lock.normalized_final_line must also equal the locked CTA exactly.\\n"
        "6) preset_id: copy preset_id exactly.\\n"
        "7) selected_angle_id: preserve selected angle id.\\n"
        "8) used_hook_ids: non-empty, deduped, and resolved to brief.hooks[].hook_id. Include selected_angle.selected_hook_id exactly once.\\n"
        "9) canonical_hook_ids: include the current grounded hook ids from the brief after any sanitizer repair.\\n"
        "10) proof_basis: carry the selected angle proof basis honestly; do not upgrade its kind. source_hook_ids must resolve to the same canonical hook used by the selected angle.\\n"
        "11) target_word_budget: copy budget_plan.target_total_words exactly.\\n"
        "12) target_sentence_budget: count the non-empty atoms you produced, counting cta_atom as one sentence.\\n"
        "13) self-audit: no ungrounded claims, no generic opener, no CTA drift, no invented proof, no duplicate atoms, no duplicate hook ids.\\n\\n"
        "Now output complete MessageAtoms JSON only."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
