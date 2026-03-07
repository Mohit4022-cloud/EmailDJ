from __future__ import annotations

import json
from typing import Any

from ..preset_contract import resolve_output_contract


def _length_band(length: str) -> tuple[int, int]:
    if length == "short":
        return (40, 80)
    if length == "long":
        return (140, 220)
    return (80, 140)


def _slider_instructions(sliders: dict[str, Any]) -> dict[str, str]:
    tone = float(sliders.get("tone", 0.4))
    framing = float(sliders.get("framing", 0.5))
    stance = float(sliders.get("stance", 0.5))
    length = str(sliders.get("length", "medium"))

    if tone < 0.3:
        tone_instruction = "Formal business language. No contractions."
    elif tone > 0.7:
        tone_instruction = "Peer-to-peer style. Contractions allowed."
    else:
        tone_instruction = "Professional but conversational."

    if framing < 0.3:
        framing_instruction = "Lead with pain/friction."
    elif framing > 0.7:
        framing_instruction = "Lead with outcomes/results."
    else:
        framing_instruction = "Balance pain and outcome."

    if stance < 0.3:
        stance_instruction = "Suggestive and measured."
    elif stance > 0.7:
        stance_instruction = "Direct and confident."
    else:
        stance_instruction = "Grounded confidence."

    min_words, max_words = _length_band(length)
    return {
        "tone": tone_instruction,
        "framing": framing_instruction,
        "stance": stance_instruction,
        "length": length,
        "min_words": str(min_words),
        "max_words": str(max_words),
    }


def _select_angle(angle_set: dict[str, Any], message_atoms: dict[str, Any]) -> dict[str, Any]:
    selected_id = str(message_atoms.get("selected_angle_id") or "")
    angles = list(angle_set.get("angles") or [])
    if selected_id:
        for angle in angles:
            if str(angle.get("angle_id") or "") == selected_id:
                return angle
    return angles[0] if angles else {}


def _global_banned_phrases() -> list[str]:
    return [
        "touch base",
        "circle back",
        "synergy",
        "leverage",
        "game-changer",
        "revolutionary",
        "i hope this email finds you",
        "i hope this finds you",
        "i wanted to reach out",
        "just checking in",
        "quick question",
        "i came across your profile",
        "i noticed you",
        "saw your recent post",
        "congrats on",
        "i know you're busy",
        "i'll keep this brief",
        "does that make sense",
        "let me know your thoughts",
        "hope to hear from you",
    ]


def build_single_messages(
    *,
    messaging_brief: dict[str, Any],
    fit_map: dict[str, Any],
    angle_set: dict[str, Any],
    message_atoms: dict[str, Any],
    preset: dict[str, Any],
    preset_contract: dict[str, Any],
    budget_plan: dict[str, Any],
    sliders: dict[str, Any],
    cta_final_line: str,
) -> list[dict[str, str]]:
    selected_angle = _select_angle(angle_set, message_atoms)
    slider_rules = _slider_instructions(sliders)
    banned = _global_banned_phrases() + [
        str(item).strip().lower() for item in (preset.get("banned_phrases_additions") or []) if str(item).strip()
    ]
    target_word_range = dict(preset_contract.get("target_word_range") or {})
    sentence_guidance = dict(preset_contract.get("sentence_count_guidance") or {})
    system = (
        "You are a Senior SDR writing one outbound email from a fully constrained brief. "
        "Research is complete, angle is chosen, atoms are compressed. Execute; do not brainstorm.\\n\\n"
        "RULE 1 - ATOMS ARE THE CEILING.\\n"
        "Do not introduce claims/facts/proof beyond message_atoms + grounded brief support.\\n\\n"
        "RULE 1A - SELECTED ANGLE MUST SHAPE THE COPY.\\n"
        "The opener, subject, and middle copy must clearly reflect selected_angle.primary_pain, selected_angle.primary_value_motion, selected_angle.primary_proof_basis, and selected_angle.framing_type.\\n\\n"
        "RULE 1B - DO NOT REBUILD THE ARGUMENT FROM RAW CONTEXT.\\n"
        "message_atoms and selected_angle are the active source of truth. Use the brief only to support wording already implied by that chosen angle.\\n\\n"
        "RULE 2 - SUBJECT QUALITY.\\n"
        "Subject must be specific, <70 chars, tied to angle entry point, no deception.\\n\\n"
        "RULE 3 - SINGLE ARC.\\n"
        "Body arc is opener -> value -> proof(if available) -> locked CTA. "
        "Realize the atoms; do not invent a second structure.\\n\\n"
        "If message_atoms.proof_atom is empty, omit proof sentence entirely. Capability language may stay in the value sentence, but do not smuggle proof into the middle of the draft.\\n\\n"
        "RULE 4 - LOCKED CTA.\\n"
        f"Final body line must exactly match: {cta_final_line}\\n\\n"
        "RULE 5 - PRESET CONTRACT IS ACTIVE.\\n"
        "Match the preset contract for word band, sentence count, opener directness, proof density, and CTA placement.\\n\\n"
        "RULE 6 - BUDGET PLAN IS ACTIVE.\\n"
        "Stay inside budget_plan targets. Do not add extra proof or bridge sentences unless budget_plan clearly allows it.\\n\\n"
        "RULE 6A - OPENER DISCIPLINE IS ACTIVE.\\n"
        "Do not use the opener to absorb budget pressure. If extra words are needed, expand the middle of the email with one grounded sentence, not a clause-stacked opener.\\n\\n"
        "RULE 7 - STYLE IS SECONDARY TO GROUNDING.\\n"
        "Apply preset style without adding ungrounded content.\\n\\n"
        "RULE 8 - BANNED PHRASES ARE ABSOLUTE.\\n"
        "If phrase is banned, do not use it.\\n\\n"
        "Active settings: "
        f"tone={slider_rules['tone']} framing={slider_rules['framing']} stance={slider_rules['stance']} "
        f"body_words={budget_plan.get('allowed_min_words', target_word_range.get('min', slider_rules['min_words']))}-"
        f"{budget_plan.get('allowed_max_words', target_word_range.get('max', slider_rules['max_words']))} "
        f"target_words={budget_plan.get('target_total_words', target_word_range.get('min', slider_rules['min_words']))} "
        f"target_sentences={budget_plan.get('target_sentence_count', sentence_guidance.get('target_min', 3))}.\\n\\n"
        "Output strict JSON only. No markdown. No commentary. Match EmailDraft schema exactly."
    )

    user_payload = {
        "locking": {"cta_final_line": cta_final_line},
        "message_atoms": message_atoms,
        "selected_angle": selected_angle,
        "messaging_brief": messaging_brief,
        "fit_map": fit_map,
        "preset": preset,
        "preset_contract": preset_contract,
        "budget_plan": budget_plan,
        "slider_rules": slider_rules,
        "banned_phrases": sorted(list(dict.fromkeys(banned))),
    }

    user = (
        "Write one cold outbound email.\\n"
        "INSTRUCTIONS:\\n"
        "1) Subject under 70 chars; specific to selected angle and prospect context.\\n"
        "2) Use atom-driven structure; one argument only.\\n"
        "3) The value_atom must appear as a distinct sentence in the body. It may not be merged into opener/proof.\\n"
        "3a) The opener must realize selected_angle.primary_pain and framing_type without adding extra subordinate clauses.\\n"
        "3b) If selected_angle.primary_proof_basis signals capability_statement or none, do not create a proof sentence from it.\\n"
        "4) If message_atoms.proof_atom is empty, omit proof sentence entirely. "
        "Use a three-sentence email only when that still satisfies budget_plan.allowed_min_words. "
        "If the three-sentence version would land under the minimum word floor, add one grounded impact sentence before the CTA. "
        "That extra sentence must elaborate the selected hook or value atom using only supported prospect context or seller context. "
        "Do not convert prospect facts into proof. "
        "If proof_atom is not empty, include proof_atom as its own sentence and add a short grounded impact sentence only when needed to reach the minimum word floor.\\n"
        "5) End body with exact locked CTA and no text after CTA.\\n"
        "6) Keep body within budget_plan allowed_min_words/allowed_max_words, and aim for budget_plan.target_total_words.\\n"
        "7) Match budget_plan.target_sentence_count and do not exceed budget_plan.allowed_max_sentences. "
        "If body_words would otherwise fall short, prefer adding one concise middle sentence over stretching the opener with extra clauses.\\n"
        "8) Match preset_contract opener_directness, proof_density, and assertiveness without adding claims.\\n"
        "9) No banned phrases and no ungrounded personalization claims.\\n"
        "10) Preserve selected_angle_id and used_hook_ids alignment with message_atoms.\\n"
        "11) Use message_atoms.required_cta_line as the exact final line. cta_intent is concept-only and may not replace it.\\n"
        "12) Self-audit before output for schema, grounding, CTA lock, preset contract, budget plan, and length.\\n\\n"
        f"CONTEXT JSON:\\n{json.dumps(user_payload, indent=2, ensure_ascii=True)}\\n\\n"
        "Output complete EmailDraft JSON only."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_batch_messages(
    *,
    messaging_brief: dict[str, Any],
    fit_map: dict[str, Any],
    angle_set: dict[str, Any],
    message_atoms: dict[str, Any],
    presets: list[dict[str, Any]],
    budget_plan_by_preset: dict[str, dict[str, Any]] | None = None,
    sliders: dict[str, Any],
    cta_final_line: str,
) -> list[dict[str, str]]:
    selected_angle = _select_angle(angle_set, message_atoms)
    slider_rules = _slider_instructions(sliders)
    presets_with_contracts = [
        {
            **preset,
            "preset_contract": resolve_output_contract(preset, length=slider_rules["length"]),
            "budget_plan": dict((budget_plan_by_preset or {}).get(str(preset.get("preset_id") or ""), {})),
        }
        for preset in presets
    ]
    system = (
        "You are generating a preset library from one fixed campaign narrative. "
        "Produce one variant per preset.\\n\\n"
        "RULE 1 - SAME ARGUMENT, DIFFERENT STYLE.\\n"
        "All variants must share the same core argument and atoms.\\n\\n"
        "RULE 2 - ATOMS ARE THE CEILING FOR ALL VARIANTS.\\n"
        "No variant can introduce external claims/facts/proof.\\n\\n"
        "RULE 3 - VARIANTS MUST BE DISTINCT.\\n"
        "Distinct structure/rhythm/voice by preset; avoid synonym-only rewrites.\\n\\n"
        "RULE 4 - ISOLATED FAILURE.\\n"
        "If one preset cannot be produced, return an error for that preset only.\\n\\n"
        "RULE 5 - LOCKED CTA FOR EVERY VARIANT.\\n"
        f"Every body must end exactly with: {cta_final_line}\\n\\n"
        "RULE 6 - PRESET CONTRACTS ARE ACTIVE.\\n"
        "Each preset variant must satisfy its own contract for target word band, sentence count, opener directness, proof density, and CTA placement.\\n\\n"
        "RULE 7 - BUDGET PLANS ARE ACTIVE.\\n"
        "Each preset variant must follow its own budget plan, not just the generic length tier.\\n\\n"
        "RULE 8 - BANNED PHRASES APPLY GLOBALLY + PER PRESET.\\n"
        "RULE 9 - SUBJECTS MUST BE DISTINCT AND <70 chars.\\n"
        "RULE 10 - PROOF GAP HANDLING.\\n"
        "If message_atoms.proof_atom is empty, omit proof sentence across all successful variants.\\n\\n"
        "Output strict JSON only. No markdown. No commentary. Match BatchVariants schema exactly."
    )

    user_payload = {
        "locking": {"cta_final_line": cta_final_line},
        "message_atoms": message_atoms,
        "selected_angle": selected_angle,
        "messaging_brief": messaging_brief,
        "fit_map": fit_map,
        "presets": presets_with_contracts,
        "slider_rules": slider_rules,
        "global_banned_phrases": _global_banned_phrases(),
    }

    user = (
        "Generate one email variant per preset_id provided.\\n"
        "INSTRUCTIONS:\\n"
        "1) Return all requested presets in output.\\n"
        "2) Keep each body in configured word band.\\n"
        "3) Keep CTA locked as final line in every successful variant.\\n"
        "4) Use same core narrative across variants; style differs by preset contract only.\\n"
        "5) If a variant cannot be generated, emit preset-scoped error object and continue.\\n"
        "6) Cross-variant audit: no duplicate subject lines or opening sentences.\\n"
        "7) Keep each variant inside its preset_contract target_word_range and its preset-specific budget_plan.\\n"
        "8) No banned phrases or ungrounded claims.\\n"
        "9) If message_atoms.proof_atom is empty, do not invent proof and do not reuse prospect facts as proof.\\n\\n"
        f"CONTEXT JSON:\\n{json.dumps(user_payload, indent=2, ensure_ascii=True)}\\n\\n"
        "Output complete BatchVariants JSON only."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
