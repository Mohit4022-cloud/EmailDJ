from __future__ import annotations

from typing import Any


def derive_repair_actions(judge_result: dict[str, Any]) -> list[dict[str, str]]:
    if str(judge_result.get("status")) != "scored":
        return []

    scores = judge_result.get("scores") or {}
    flags = {str(flag).strip() for flag in judge_result.get("flags", []) if str(flag).strip()}
    actions: list[dict[str, str]] = []

    relevance = int(scores.get("relevance_to_prospect", 0) or 0)
    personalization = int(scores.get("personalization_quality", 0) or 0)
    credibility = int(scores.get("credibility_no_overclaim", 0) or 0)
    cta_quality = int(scores.get("cta_quality", 0) or 0)
    tone = int(scores.get("tone_match", 0) or 0)

    if relevance <= 3 or personalization <= 3 or "insufficient_personalization" in flags:
        actions.append(
            {
                "tag": "HOOK_TOO_GENERIC",
                "action": "Increase research hooks and require at least one specific factual detail in the opening sentence.",
                "reason": "Relevance/personalization is weak for the target prospect context.",
            }
        )
    if credibility <= 3 or "auto_fail_guaranteed_outcome" in flags:
        actions.append(
            {
                "tag": "CREDIBILITY_OVERCLAIM",
                "action": "Rewrite claims with hedged language and remove unsupported numbers or guarantees.",
                "reason": "Credibility signals indicate overclaim risk.",
            }
        )
    if cta_quality <= 3 or "weak_cta" in flags:
        actions.append(
            {
                "tag": "CTA_WEAK",
                "action": "Swap CTA template type to a low-friction, explicit single ask and enforce final-line CTA lock.",
                "reason": "CTA is not clear or not sufficiently actionable.",
            }
        )
    if tone <= 3 or "tone_mismatch" in flags:
        actions.append(
            {
                "tag": "TONE_MISMATCH",
                "action": "Adjust tone instruction/style slider toward professional-neutral wording and remove hype punctuation.",
                "reason": "Tone does not align with enterprise outbound expectations.",
            }
        )
    if "verbosity_padding_detected" in flags:
        actions.append(
            {
                "tag": "VERBOSITY_PADDING",
                "action": "Constrain body length and remove repetitive filler while preserving one core value proposition.",
                "reason": "Length is being used without additional signal.",
            }
        )
    if "judge_pandering_detected" in flags:
        actions.append(
            {
                "tag": "JUDGE_PANDERING",
                "action": "Remove meta-evaluation language and refocus copy on prospect value and concrete business context.",
                "reason": "Output contains judge-directed or meta-explanatory content.",
            }
        )

    return _dedupe_actions(actions)


def _dedupe_actions(actions: list[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for action in actions:
        tag = action.get("tag", "").strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        output.append(action)
    return output

