from __future__ import annotations

import json
from typing import Any


def _slider_instructions(sliders: dict[str, Any]) -> list[str]:
    tone = float(sliders.get("tone", 0.4))
    framing = float(sliders.get("framing", 0.5))
    stance = float(sliders.get("stance", 0.5))
    length = str(sliders.get("length", "medium"))

    out: list[str] = []
    if tone < 0.3:
        out.append("Use formal business language. No contractions.")
    elif tone > 0.7:
        out.append("Write like a peer, not a salesperson. Contractions OK.")
    else:
        out.append("Use professional but conversational tone.")

    if framing < 0.3:
        out.append("Lead with the problem/pain the prospect likely faces.")
    elif framing > 0.7:
        out.append("Lead with the outcome/result the prospect could achieve.")
    else:
        out.append("Balance current pain and practical outcomes.")

    if stance < 0.3:
        out.append("Be tentative. Suggest, do not over-assert.")
    elif stance > 0.7:
        out.append("Be direct and confident. State your point of view clearly.")
    else:
        out.append("Be confident but tactful.")

    if length == "short":
        out.append("Keep body in 40-80 words.")
    elif length == "long":
        out.append("Keep body in 140-220 words.")
    else:
        out.append("Keep body in 80-140 words.")
    return out


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
    instructions = _slider_instructions(sliders)
    banned = [
        "touch base",
        "circle back",
        "synergy",
        "leverage",
        "game-changer",
        "revolutionary",
        "I hope this email finds you",
        "I wanted to reach out",
        "just checking in",
    ]
    return [
        {
            "role": "system",
            "content": (
                "Write a cold outbound email using the atoms and angle provided. "
                "Apply the style rules from the preset. Do NOT add facts not in the brief. "
                "Do NOT use phrases in do_not_say or banned phrases lists. "
                "Subject must be under 70 characters. "
                f"Body must end with this exact CTA line: '{cta_final_line}'. "
                "Output strict JSON. No preamble. Output JSON only, no commentary."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "messaging_brief": messaging_brief,
                    "fit_map": fit_map,
                    "angle_set": angle_set,
                    "message_atoms": message_atoms,
                    "preset": preset,
                    "slider_instructions": instructions,
                    "banned_phrases": banned,
                    "cta_final_line": cta_final_line,
                },
                ensure_ascii=True,
            ),
        },
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
    instructions = _slider_instructions(sliders)
    return [
        {
            "role": "system",
            "content": (
                "Generate one email variant per preset in the variants array. "
                "Each variant is independently styled. Use the SAME angle and atoms for all variants. "
                "If you cannot generate a valid email for a preset, return an error object for that preset only. "
                "Do not omit any preset. Output strict JSON. No preamble. Output JSON only, no commentary."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "messaging_brief": messaging_brief,
                    "fit_map": fit_map,
                    "angle_set": angle_set,
                    "message_atoms": message_atoms,
                    "presets": presets,
                    "slider_instructions": instructions,
                    "cta_final_line": cta_final_line,
                },
                ensure_ascii=True,
            ),
        },
    ]
