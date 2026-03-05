from __future__ import annotations

import json
from typing import Any


def _length_band(length: str) -> tuple[int, int]:
    if length == "short":
        return (40, 80)
    if length == "long":
        return (140, 220)
    return (80, 140)


def _tone_instruction(tone: float) -> str:
    if tone < 0.3:
        return "Formal. No contractions."
    if tone > 0.7:
        return "Peer-to-peer. Contractions allowed."
    return "Professional but conversational."


def build_messages(
    *,
    email_draft: dict[str, Any],
    qa_report: dict[str, Any],
    messaging_brief: dict[str, Any],
    message_atoms: dict[str, Any],
    cta_final_line: str,
    sliders: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    slider_payload = dict(sliders or {})
    tone = float(slider_payload.get("tone", 0.4))
    length = str(slider_payload.get("length", "medium"))
    min_words, max_words = _length_band(length)

    rewrite_plan = list(qa_report.get("rewrite_plan") or [])

    system = (
        "You are a Senior SDR Editor executing a QA rewrite plan. "
        "This is surgical editing: execute plan actions in order with minimum viable changes.\\n\\n"
        "RULE 1 - EXECUTE PLAN IN ORDER.\\n"
        "Do not skip, reorder, or invent extra actions.\\n\\n"
        "RULE 2 - MINIMUM CHANGE PRINCIPLE.\\n"
        "Change only text needed to satisfy each fix instruction.\\n\\n"
        "RULE 3 - ATOMS BOUNDARY REMAINS ACTIVE.\\n"
        "Do not add claims/facts/proof beyond atoms + grounded brief support.\\n\\n"
        "RULE 4 - CTA LOCK.\\n"
        f"Final body line must remain exactly: {cta_final_line}\\n\\n"
        "RULE 5 - DO NOT TOUCH CLEAN TEXT.\\n"
        "If sentence was not targeted by plan/issues, leave it unchanged.\\n\\n"
        "RULE 6 - HANDLE BLOCKED ACTIONS SAFELY.\\n"
        "If action conflicts with atoms boundary, do partial safe execution and keep grounding intact.\\n\\n"
        "RULE 7 - VALIDATE BEFORE OUTPUT.\\n"
        "Check schema, banned phrases, CTA lock, length, and unresolved high-severity failures.\\n\\n"
        f"Active settings: tone={_tone_instruction(tone)} body_words={min_words}-{max_words}.\\n\\n"
        "Output strict JSON only. No markdown. No commentary. Match EmailDraft schema exactly."
    )

    user_payload = {
        "locked_cta": cta_final_line,
        "original_email_draft": email_draft,
        "qa_report": qa_report,
        "rewrite_plan": rewrite_plan,
        "message_atoms": message_atoms,
        "messaging_brief": messaging_brief,
        "slider_rules": {
            "tone": _tone_instruction(tone),
            "length": length,
            "min_words": min_words,
            "max_words": max_words,
        },
        "global_banned_phrases": [
            "touch base",
            "circle back",
            "synergy",
            "leverage",
            "game-changer",
            "revolutionary",
            "i hope this email finds you",
            "i wanted to reach out",
            "just checking in",
            "quick question",
            "i came across your profile",
            "i know you're busy",
            "let me know your thoughts",
            "hope to hear from you",
            "i noticed you",
            "saw your recent post",
            "congrats on",
        ],
    }

    user = (
        "Execute the rewrite plan on the original draft.\\n"
        "INSTRUCTIONS:\\n"
        "1) Map each plan action to exact text span before editing.\\n"
        "2) Apply actions sequentially with minimal edits.\\n"
        "3) Preserve preset_id, selected_angle_id, and used_hook_ids unless explicitly changed by plan.\\n"
        "4) Keep all untouched, non-flagged text identical.\\n"
        "5) Enforce exact locked CTA as final line; delete any trailing text after CTA.\\n"
        "6) Validate final draft for credibility, personalization grounding, banned phrases, schema, and word band.\\n"
        "7) For unresolved hard credibility failures, return deterministic failure-compatible output behavior (no fabrication).\\n\\n"
        f"CONTEXT JSON:\\n{json.dumps(user_payload, indent=2, ensure_ascii=True)}\\n\\n"
        "Output complete EmailDraft JSON only."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
