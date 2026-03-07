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
    rewrite_context: dict[str, Any] | None = None,
    preset_contract: dict[str, Any] | None = None,
    budget_plan: dict[str, Any] | None = None,
    sliders: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    slider_payload = dict(sliders or {})
    contract = dict(preset_contract or {})
    plan = dict(budget_plan or {})
    patch_context = dict(rewrite_context or {})
    tone = float(slider_payload.get("tone", 0.4))
    length = str(slider_payload.get("length", "medium"))
    min_words, max_words = _length_band(length)
    if isinstance(plan.get("allowed_min_words"), int) and isinstance(plan.get("allowed_max_words"), int):
        min_words = int(plan["allowed_min_words"])
        max_words = int(plan["allowed_max_words"])

    rewrite_plan = list(qa_report.get("rewrite_plan") or [])
    current_body = str(email_draft.get("body") or "").strip()
    current_word_count = len(current_body.replace("\n", " ").split()) if current_body else 0
    words_needed_to_min = max(0, min_words - current_word_count)
    words_over_max = max(0, current_word_count - max_words)

    system = (
        "You are a Senior SDR Editor executing a QA rewrite plan. "
        "This is patch-mode editing: return sentence-indexed edit operations, not a redrafted email.\\n\\n"
        "RULE 1 - EXECUTE PLAN IN ORDER.\\n"
        "Do not skip, reorder, or invent extra actions. Each action is scoped to one issue_code and target.\\n\\n"
        "RULE 2 - MINIMUM CHANGE PRINCIPLE.\\n"
        "Change only text needed to satisfy each fix instruction.\\n\\n"
        "RULE 2A - PATCH OUTPUT ONLY.\\n"
        "Return EmailRewritePatch JSON with preserve_sentence_indexes and sentence_operations. Do not return subject/body text.\\n\\n"
        "RULE 3 - ATOMS BOUNDARY REMAINS ACTIVE.\\n"
        "Do not add claims/facts/proof beyond atoms + grounded brief support.\\n\\n"
        "RULE 4 - CTA LOCK.\\n"
        f"Final body line must remain exactly: {cta_final_line}\\n\\n"
        "RULE 5 - DO NOT TOUCH CLEAN TEXT.\\n"
        "If sentence was not targeted by plan/issues, leave it unchanged and include it in preserve_sentence_indexes.\\n\\n"
        "RULE 6 - HANDLE BLOCKED ACTIONS SAFELY.\\n"
        "If action conflicts with atoms boundary, do partial safe execution and keep grounding intact.\\n\\n"
        "RULE 7 - PRESET CONTRACT IS ACTIVE.\\n"
        "Rewrite toward the preset contract for word band, sentence count, opener directness, proof density, and CTA placement.\\n\\n"
        "RULE 8 - BUDGET PLAN IS ACTIVE.\\n"
        "Use budget_plan to tighten or expand only where needed. Preserve the authored narrative while bringing it back inside plan.\\n\\n"
        "RULE 9 - UNSUPPORTED CONTENT MUST BE REMOVED, NOT REPLACED WITH INVENTION.\\n"
        "If an action targets unsupported proof or unsupported initiative language, delete or narrow that claim only.\\n\\n"
        "RULE 10 - VALIDATE BEFORE OUTPUT.\\n"
        "Check schema, banned phrases, CTA lock, preserve list, preset contract, budget plan, and unresolved high-severity failures.\\n\\n"
        f"Active settings: tone={_tone_instruction(tone)} body_words={min_words}-{max_words} "
        f"target_words={plan.get('target_total_words', '')} target_sentences={plan.get('target_sentence_count', '')}.\\n\\n"
        "Output strict JSON only. No markdown. No commentary. Match EmailRewritePatch schema exactly."
    )

    user_payload = {
        "locked_cta": cta_final_line,
        "original_email_draft": email_draft,
        "qa_report": qa_report,
        "rewrite_plan": rewrite_plan,
        "message_atoms": message_atoms,
        "messaging_brief": messaging_brief,
        "rewrite_context": patch_context,
        "preset_contract": contract,
        "budget_plan": plan,
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
        "1) Map each rewrite_plan action object to the exact sentence indexes in rewrite_context before editing.\\n"
        "2) Output preserve_sentence_indexes for every untouched sentence index that must remain verbatim.\\n"
        "3) sentence_operations may use only: keep, rewrite, insert_after, delete.\\n"
        "4) Preserve preset_id, selected_angle_id, and used_hook_ids exactly.\\n"
        "5) Never emit an operation that changes CTA wording or places content after the CTA.\\n"
        "6) For opener complexity, rewrite only the opener sentence unless another issue explicitly requires more.\\n"
        "7) For unsupported proof or initiative issues, remove or narrow only the targeted span; do not add substitute proof.\\n"
        "8) If the body is under the minimum word floor, prefer one grounded middle-sentence insert_after operation rather than rewriting preserved sentences.\\n"
        "9) Keep the opener at one clear thought and keep preserved sentences verbatim.\\n"
        "10) Validate the patch against schema, atoms grounding, preserve list discipline, CTA lock, preset contract, and budget plan.\\n\\n"
        f"CONTEXT JSON:\\n{json.dumps(user_payload, indent=2, ensure_ascii=True)}\\n\\n"
        f"BUDGET STATUS: current_body_words={current_word_count}, allowed_min_words={min_words}, "
        f"allowed_max_words={max_words}, words_needed_to_min={words_needed_to_min}, words_over_max={words_over_max}.\\n\\n"
        "Output complete EmailRewritePatch JSON only."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_salvage_messages(
    *,
    email_draft: dict[str, Any],
    message_atoms: dict[str, Any],
    messaging_brief: dict[str, Any],
    cta_final_line: str,
    preset_contract: dict[str, Any],
    budget_plan: dict[str, Any],
    failure_code: str,
) -> list[dict[str, str]]:
    contract = dict(preset_contract or {})
    plan = dict(budget_plan or {})
    system = (
        "You are doing one bounded salvage edit on an already-written SDR email. "
        "This is not a fresh rewrite. Adjust only enough to satisfy the preset contract.\\n\\n"
        "RULE 1 - ONLY FIX THE MECHANICAL MISS.\\n"
        "The only allowed target is the isolated mechanical failure provided.\\n\\n"
        "RULE 2 - PRESERVE AUTHORSHIP.\\n"
        "Keep the draft's angle, language, and structure intact unless a tiny edit is required for the band fix.\\n\\n"
        "RULE 3 - NO NEW CLAIMS.\\n"
        "Do not add facts, proof, hooks, or personalization beyond the existing draft and grounded atoms.\\n\\n"
        "RULE 4 - CTA LOCK.\\n"
        f"Final body line must remain exactly: {cta_final_line}\\n\\n"
        "RULE 5 - PRESERVE METADATA.\\n"
        "Keep preset_id, selected_angle_id, and used_hook_ids unchanged.\\n\\n"
        "RULE 6 - BUDGET PLAN IS ACTIVE.\\n"
        "Use the budget plan as the narrow edit target. Do not expand salvage into a second draft.\\n\\n"
        "Output strict JSON only. No markdown. No commentary. Match EmailDraft schema exactly."
    )

    user_payload = {
        "failure_code": failure_code,
        "email_draft": email_draft,
        "message_atoms": message_atoms,
        "messaging_brief": messaging_brief,
        "preset_contract": contract,
        "budget_plan": plan,
        "locked_cta": cta_final_line,
    }

    user = (
        "Make one narrow salvage edit.\\n"
        "INSTRUCTIONS:\\n"
        "1) If over the preset contract band, compress by shortening or removing the least essential narrative text only.\\n"
        "2) If under the preset contract band, expand the body before the CTA using grounded wording already present in the draft, atoms, or brief. "
        "Add as many concise middle sentences as needed to reach the minimum word floor; do not stop if the first expansion still lands under the floor.\\n"
        "3) Do not replace the draft with a new template or canned preset body.\\n"
        "4) Preserve the selected angle, used_hook_ids, and exact CTA line.\\n"
        "5) Use budget_plan.target_total_words as the preferred landing point and stay within budget_plan.allowed_min_words/allowed_max_words.\\n"
        "6) Keep the opener simple; expand the middle of the email before the CTA instead of stacking clauses into the first sentence.\\n"
        "7) Self-audit for word band, sentence count, grounding, and CTA exactness before output.\\n\\n"
        f"CONTEXT JSON:\\n{json.dumps(user_payload, indent=2, ensure_ascii=True)}\\n\\n"
        "Output complete EmailDraft JSON only."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
