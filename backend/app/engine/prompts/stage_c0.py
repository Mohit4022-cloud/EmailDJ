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
    messaging_brief: dict[str, Any],
    fit_map: dict[str, Any],
    angle_set: dict[str, Any],
    selected_angle_id: str,
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
        "Each atom is exactly one sentence.\\n\\n"
        "RULE 2 - OPENER EARNS ATTENTION FAST.\\n"
        "No generic openers or vanity compliments. Start in the prospect world.\\n\\n"
        "RULE 3 - VALUE LINE NAMES OUTCOME.\\n"
        "Value must be an outcome, not a product feature list.\\n\\n"
        "RULE 4 - PROOF LINE IS HONEST.\\n"
        "Use a real proof point or set proof_line to empty string and carry proof risk. Never invent proof.\\n\\n"
        "RULE 5 - CTA LINE IS LOCKED.\\n"
        "Copy CTA exactly; no edits.\\n\\n"
        f"Active sliders: tone={_tone_instruction(tone)} framing={_framing_instruction(framing)} "
        f"stance={_stance_instruction(stance)} target_length={_length_instruction(length)}.\\n\\n"
        "Output strict JSON only. No markdown. No commentary. Match MessageAtoms schema exactly."
    )

    user = (
        "Build MessageAtoms for this campaign.\\n\\n"
        f"LOCKED CTA (copy verbatim):\\n{cta_final_line}\\n\\n"
        "SELECTED ANGLE:\\n"
        f"{json.dumps(selected, indent=2, ensure_ascii=True)}\\n\\n"
        "MESSAGING BRIEF:\\n"
        f"{json.dumps(messaging_brief, indent=2, ensure_ascii=True)}\\n\\n"
        "FITMAP:\\n"
        f"{json.dumps(fit_map, indent=2, ensure_ascii=True)}\\n\\n"
        "INSTRUCTIONS:\\n"
        "1) opener_line: one specific sentence tied to selected angle and grounded signal.\\n"
        "   Complexity test: read opener_line aloud. If it contains more than one comma or more than one connecting word "
        "(which, that, and, because, so), rewrite as two thoughts and keep only the stronger one.\\n"
        "2) value_line: one outcome sentence tied to angle value.\\n"
        "   Mechanism test: if value_line names a mechanism/feature (scoring, tracking, platform, tool, system), "
        "rewrite it to what happens after mechanism runs (time saved, revenue protected, variance reduced, headcount freed).\\n"
        "3) proof_line: one grounded proof sentence, or empty string if no applicable proof exists.\\n"
        "   Fact IDs are for grounding, not citation. Never include fact_id references in proof_line text. "
        "If you cannot write proof_line without inline citations, set proof_line to empty string.\\n"
        "4) cta_line: exact locked CTA.\\n"
        "5) selected_angle_id: preserve selected angle id.\\n"
        "6) used_hook_ids: non-empty and resolved to brief.hooks[].hook_id.\\n"
        "7) self-audit: no ungrounded claims, no generic opener, no CTA drift, no invented proof.\\n\\n"
        "Now output complete MessageAtoms JSON only."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
