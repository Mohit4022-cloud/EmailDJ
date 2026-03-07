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
        "Every issue must include one exact draft quote under 15 words.\\n\\n"
        "RULE 2 - SURGICAL FIXES.\\n"
        "Each fix_instruction must specify what to change, what to use as replacement source, and why.\\n\\n"
        "RULE 3 - SEVERITY DISCIPLINE.\\n"
        "high = likely deletion risk and must force rewrite; medium = material but non-blocking; low = polish only.\\n\\n"
        "RULE 4 - PASS IS VALID.\\n"
        "If no high-severity issue exists, pass_rewrite_needed may be false.\\n\\n"
        "RULE 5 - STRUCTURED ISSUE OBJECTS ONLY.\\n"
        "Each issue must include issue_code, type, offending_span_or_target_section, evidence_quote, evidence, "
        "why_it_fails, fix_instruction, and expected_effect. Use type as the nearest legacy category or preset issue type. "
        "Set evidence to a one-item list containing the same exact quote as evidence_quote.\\n\\n"
        "RULE 6 - REWRITE PLAN MUST BE EXECUTABLE.\\n"
        "If rewrite is needed, provide ordered rewrite_plan action objects mapped issue-by-issue.\\n\\n"
        "RULE 6A - OPENER COMPLEXITY IS HIGH SEVERITY.\\n"
        "If the opener is clause-stacked, lead-subordinate, or bloated, mark it high severity and instruct a surgical opener-only rewrite.\\n\\n"
        "RULE 6B - PRESERVATION DISCIPLINE.\\n"
        "When only one sentence is bad, say which untouched sentences should remain verbatim. Do not imply a full redraft when a local patch is enough.\\n\\n"
        "RULE 7 - CTA TEXT IS IMMUTABLE.\\n"
        "If locked_cta is already exact, you may only flag placement or duplication. Never propose alternate CTA wording.\\n\\n"
        "RULE 8 - PRESET CONTRACT IS ACTIVE.\\n"
        "Evaluate the draft against the preset contract, not generic email taste.\\n\\n"
        "RULE 9 - BUDGET PLAN IS ACTIVE.\\n"
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
        "4) Each issue object must include: issue_code, type, severity, offending_span_or_target_section, evidence_quote, "
        "evidence, why_it_fails, fix_instruction, expected_effect.\\n"
        "5) rewrite_plan: if rewrite needed, ordered action objects (max 8) with issue_code, target, action, "
        "replacement_guidance, preserve, expected_effect; else return [].\\n"
        "5a) Prefer sentence-local targets and preserve guidance precise enough for patch-mode rewrite.\\n"
        "6) risk_flags: include hallucinated_proof / ungrounded_personalization / cta_mismatch / deep_structural_failure / clean where applicable.\\n"
        "7) State whether budget failure came from bad planning or generation drift whenever word count or sentence count is at issue.\\n"
        "8) Use budget_plan.target_total_words and budget_plan.target_sentence_count when judging plan-following, "
        "while preset_contract remains the hard outer contract.\\n"
        "9) Jargon-stacking check: if any sentence contains three or more abstract corporate nouns in sequence "
        "(hygiene, pipeline, cadence, process, alignment, SLA, methodology, framework), flag as tone severity high.\\n"
        "10) Use these preset-specific issue types when they apply: "
        "word_count_out_of_band, opener_too_soft_for_preset, proof_density_too_low, "
        "too_many_sentences_for_preset, tone_mismatch_for_preset, cta_not_in_expected_form.\\n"
        "11) For unsupported proof or unsupported initiative language, quote the exact sentence and instruct removal or narrowing only.\\n"
        "12) If locked_cta already matches exactly, any CTA issue must say to keep the text unchanged and only fix placement/singularity.\\n"
        "13) If opener complexity is the issue, instruct preserving untouched middle sentences and CTA verbatim.\\n"
        "14) If proof is vague or unsupported, quote the exact sentence and instruct deletion or narrowing only; never ask rewrite to invent replacement proof.\\n"
        "15) Self-audit: every issue must quote real draft text and every rewrite action must point to a specific target.\\n\\n"
        f"CONTEXT JSON:\\n{json.dumps(user_payload, indent=2, ensure_ascii=True)}\\n\\n"
        "Output complete QAReport JSON only."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
