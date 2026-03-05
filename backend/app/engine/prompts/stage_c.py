from __future__ import annotations

import json
from typing import Any


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
    sliders: dict[str, Any],
    cta_final_line: str,
) -> list[dict[str, str]]:
    selected_angle = _select_angle(angle_set, message_atoms)
    slider_rules = _slider_instructions(sliders)
    banned = _global_banned_phrases() + [
        str(item).strip().lower() for item in (preset.get("banned_phrases_additions") or []) if str(item).strip()
    ]

    system = (
        "You are a Senior SDR writing one outbound email from a fully constrained brief. "
        "Research is complete, angle is chosen, atoms are compressed. Execute; do not brainstorm.\\n\\n"
        "RULE 1 - ATOMS ARE THE CEILING.\\n"
        "Do not introduce claims/facts/proof beyond message_atoms + grounded brief support.\\n\\n"
        "RULE 2 - SUBJECT QUALITY.\\n"
        "Subject must be specific, <70 chars, tied to angle entry point, no deception.\\n\\n"
        "RULE 3 - SINGLE ARC.\\n"
        "Body arc is opener -> value -> proof(if available) -> locked CTA.\\n\\n"
        "If message_atoms.proof_gap is true, omit proof sentence entirely.\\n\\n"
        "RULE 4 - LOCKED CTA.\\n"
        f"Final body line must exactly match: {cta_final_line}\\n\\n"
        "RULE 5 - STYLE IS SECONDARY TO GROUNDING.\\n"
        "Apply preset style without adding ungrounded content.\\n\\n"
        "RULE 6 - BANNED PHRASES ARE ABSOLUTE.\\n"
        "If phrase is banned, do not use it.\\n\\n"
        "Active settings: "
        f"tone={slider_rules['tone']} framing={slider_rules['framing']} stance={slider_rules['stance']} "
        f"body_words={slider_rules['min_words']}-{slider_rules['max_words']}.\\n\\n"
        "Output strict JSON only. No markdown. No commentary. Match EmailDraft schema exactly."
    )

    user_payload = {
        "locking": {"cta_final_line": cta_final_line},
        "message_atoms": message_atoms,
        "selected_angle": selected_angle,
        "messaging_brief": messaging_brief,
        "fit_map": fit_map,
        "preset": preset,
        "slider_rules": slider_rules,
        "banned_phrases": sorted(list(dict.fromkeys(banned))),
    }

    user = (
        "Write one cold outbound email.\\n"
        "INSTRUCTIONS:\\n"
        "1) Subject under 70 chars; specific to selected angle and prospect context.\\n"
        "2) Use atom-driven structure; one argument only.\\n"
        "3) The value_line atom must appear as a distinct sentence in the body. It may not be merged into opener/proof.\\n"
        "4) If message_atoms.proof_gap is true, omit proof sentence entirely and write a three-sentence email: "
        "opener -> value -> CTA line. Do not convert prospect facts into proof. "
        "If proof_gap is false, include proof_line as its own sentence.\\n"
        "5) End body with exact locked CTA and no text after CTA.\\n"
        "6) Keep body within configured word band.\\n"
        "7) No banned phrases and no ungrounded personalization claims.\\n"
        "8) Preserve selected_angle_id and used_hook_ids alignment with message_atoms.\\n"
        "9) Self-audit before output for schema, grounding, CTA lock, and length.\\n\\n"
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
    sliders: dict[str, Any],
    cta_final_line: str,
) -> list[dict[str, str]]:
    selected_angle = _select_angle(angle_set, message_atoms)
    slider_rules = _slider_instructions(sliders)

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
        "RULE 6 - BANNED PHRASES APPLY GLOBALLY + PER PRESET.\\n"
        "RULE 7 - SUBJECTS MUST BE DISTINCT AND <70 chars.\\n"
        "RULE 8 - PROOF GAP HANDLING.\\n"
        "If message_atoms.proof_gap is true, omit proof sentence across all successful variants.\\n\\n"
        "Output strict JSON only. No markdown. No commentary. Match BatchVariants schema exactly."
    )

    user_payload = {
        "locking": {"cta_final_line": cta_final_line},
        "message_atoms": message_atoms,
        "selected_angle": selected_angle,
        "messaging_brief": messaging_brief,
        "fit_map": fit_map,
        "presets": presets,
        "slider_rules": slider_rules,
        "global_banned_phrases": _global_banned_phrases(),
    }

    user = (
        "Generate one email variant per preset_id provided.\\n"
        "INSTRUCTIONS:\\n"
        "1) Return all requested presets in output.\\n"
        "2) Keep each body in configured word band.\\n"
        "3) Keep CTA locked as final line in every successful variant.\\n"
        "4) Use same core narrative across variants; style differs by preset only.\\n"
        "5) If a variant cannot be generated, emit preset-scoped error object and continue.\\n"
        "6) Cross-variant audit: no duplicate subject lines or opening sentences.\\n"
        "7) No banned phrases or ungrounded claims.\\n"
        "8) If message_atoms.proof_gap is true, do not invent proof and do not reuse prospect facts as proof.\\n\\n"
        f"CONTEXT JSON:\\n{json.dumps(user_payload, indent=2, ensure_ascii=True)}\\n\\n"
        "Output complete BatchVariants JSON only."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
