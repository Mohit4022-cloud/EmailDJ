from __future__ import annotations

import json
from typing import Any


def _infer_cta(email_draft: dict[str, Any], cta_final_line: str | None) -> str:
    explicit = str(cta_final_line or "").strip()
    if explicit:
        return explicit
    body = str(email_draft.get("body") or "")
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def build_messages(
    email_draft: dict[str, Any],
    messaging_brief: dict[str, Any],
    message_atoms: dict[str, Any] | None = None,
    cta_final_line: str | None = None,
    preset_contract: dict[str, Any] | None = None,
    budget_plan: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    locked_cta = _infer_cta(email_draft, cta_final_line)
    atoms = dict(message_atoms or {})
    contract = dict(preset_contract or {})
    plan = dict(budget_plan or {})

    system = (
        "You are a tough SDR QA reviewer. Your job is not to rewrite the email; "
        "your job is to produce an evidence-backed QAReport with executable fixes.\\n\\n"
        "RULE 1 - QUOTE EVIDENCE.\\n"
        "Every issue must include quoted evidence snippets under 15 words.\\n\\n"
        "RULE 2 - SURGICAL FIXES.\\n"
        "Each fix_instruction must specify what to change, what to use as replacement source, and why.\\n\\n"
        "RULE 3 - SEVERITY DISCIPLINE.\\n"
        "high = likely deletion risk and must force rewrite; medium = material but non-blocking; low = polish only.\\n\\n"
        "RULE 4 - PASS IS VALID.\\n"
        "If no high-severity issue exists, pass_rewrite_needed may be false.\\n\\n"
        "RULE 5 - REWRITE PLAN MUST BE EXECUTABLE.\\n"
        "If rewrite is needed, provide ordered, concrete, independently executable steps.\\n\\n"
        "RULE 6 - PRESET CONTRACT IS ACTIVE.\\n"
        "Evaluate the draft against the preset contract, not generic email taste.\\n\\n"
        "RULE 7 - BUDGET PLAN IS ACTIVE.\\n"
        "Determine whether the plan itself was unrealistic or whether generation drifted from it.\\n\\n"
        "Output strict JSON only. No markdown. No commentary. Match QAReport schema exactly."
    )

    user_payload = {
        "email_draft": email_draft,
        "messaging_brief": messaging_brief,
        "message_atoms": atoms,
        "preset_contract": contract,
        "budget_plan": plan,
        "locked_cta": locked_cta,
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
        ],
    }

    user = (
        "Critique this draft against brief and atoms.\\n"
        "INSTRUCTIONS:\\n"
        "1) Evaluate credibility, specificity, structure, spam risk, personalization, CTA integrity, length, tone, and preset contract fit.\\n"
        "2) Flag only real issues; do not invent filler feedback.\\n"
        "3) pass_rewrite_needed=true if any high-severity issue exists.\\n"
        "4) rewrite_plan: if rewrite needed, ordered action list (max 8 actions); else single no-rewrite entry.\\n"
        "5) risk_flags: include hallucinated_proof / ungrounded_personalization / cta_mismatch / deep_structural_failure / clean where applicable.\\n"
        "6) State whether budget failure came from bad planning or generation drift whenever word count or sentence count is at issue.\\n"
        "7) Use budget_plan.target_total_words and budget_plan.target_sentence_count when judging plan-following, "
        "while preset_contract remains the hard outer contract.\\n"
        "8) Jargon-stacking check: if any sentence contains three or more abstract corporate nouns in sequence "
        "(hygiene, pipeline, cadence, process, alignment, SLA, methodology, framework), flag as tone severity high.\\n"
        "9) Use these preset-specific issue types when they apply: "
        "word_count_out_of_band, opener_too_soft_for_preset, proof_density_too_low, "
        "too_many_sentences_for_preset, tone_mismatch_for_preset, cta_not_in_expected_form.\\n"
        "10) Self-audit: every issue has quoted evidence + actionable fix instruction.\\n\\n"
        f"CONTEXT JSON:\\n{json.dumps(user_payload, indent=2, ensure_ascii=True)}\\n\\n"
        "Output complete QAReport JSON only."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
