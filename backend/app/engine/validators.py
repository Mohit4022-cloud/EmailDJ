from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


BANNED_PHRASES = [
    "touch base",
    "circle back",
    "synergy",
    "leverage",
    "game-changer",
    "revolutionary",
    "i hope this email finds you",
    "i wanted to reach out",
    "just checking in",
]

UNGROUNDED_PERSONALIZATION_MARKERS = [
    "saw your post",
    "noticed you",
    "congrats on",
    "just came across",
]


class ValidationIssue(ValueError):
    def __init__(self, codes: list[str], message: str = "validation_failed"):
        super().__init__(message)
        self.codes = list(codes)


def _codes_or_raise(codes: list[str]) -> None:
    if codes:
        raise ValidationIssue(codes)


def validate_messaging_brief(brief: dict[str, Any], *, source_text: str = "") -> None:
    codes: list[str] = []
    facts = list(brief.get("facts_from_input") or [])
    assumptions = list(brief.get("assumptions") or [])
    hooks = list(brief.get("hooks") or [])
    brief_quality = dict(brief.get("brief_quality") or {})

    if len(facts) < 1:
        codes.append("brief_missing_facts")
    if len(hooks) < 1:
        codes.append("brief_missing_hooks")

    for item in assumptions:
        conf = float(item.get("confidence") or 0.0)
        based = list(item.get("based_on_fact_ids") or [])
        if conf > 0.8 and len(based) == 0:
            codes.append("assumption_high_confidence_no_grounding")
            break

    source_lower = source_text.lower()
    for fact in facts:
        text = str(fact.get("text") or "").lower()
        if any(marker in text for marker in UNGROUNDED_PERSONALIZATION_MARKERS) and text not in source_lower:
            codes.append("fact_contains_ungrounded_behavior_claim")
            break

    if not brief_quality:
        codes.append("brief_missing_brief_quality")
    else:
        fact_count = int(brief_quality.get("fact_count") or 0)
        signal_strength = str(brief_quality.get("signal_strength") or "").strip().lower()
        confidence_ceiling = float(brief_quality.get("confidence_ceiling") or 0.0)

        if confidence_ceiling < 0.0 or confidence_ceiling > 1.0:
            codes.append("brief_quality_confidence_ceiling_out_of_range")

        is_thin_input = not bool(str(source_text or "").strip()) and fact_count < 3
        if is_thin_input and signal_strength != "low":
            codes.append("brief_quality_signal_strength_mismatch")

    _codes_or_raise(codes)


def validate_fit_map(fit_map: dict[str, Any], messaging_brief: dict[str, Any]) -> None:
    codes: list[str] = []
    hook_ids = {str(item.get("hook_id")) for item in messaging_brief.get("hooks") or []}
    fact_ids = {str(item.get("fact_id")) for item in messaging_brief.get("facts_from_input") or []}

    for hyp in fit_map.get("hypotheses") or []:
        if str(hyp.get("selected_hook_id")) not in hook_ids:
            codes.append("fit_unknown_hook_id")
            break
        supporting = list(hyp.get("supporting_fact_ids") or [])
        if not supporting:
            codes.append("fit_missing_supporting_facts")
            break
        if any(str(fid) not in fact_ids for fid in supporting):
            codes.append("fit_unknown_supporting_fact_id")
            break

    _codes_or_raise(codes)


def validate_angle_set(angle_set: dict[str, Any], messaging_brief: dict[str, Any], fit_map: dict[str, Any]) -> None:
    codes: list[str] = []
    angles = list(angle_set.get("angles") or [])
    if len(angles) < 3:
        codes.append("angle_set_too_small")
    hook_ids = {str(item.get("hook_id")) for item in messaging_brief.get("hooks") or []}
    hyp_ids = {str(item.get("fit_hypothesis_id")) for item in fit_map.get("hypotheses") or []}
    for angle in angles:
        if str(angle.get("selected_hook_id")) not in hook_ids:
            codes.append("angle_unknown_hook_id")
            break
        if str(angle.get("selected_fit_hypothesis_id")) not in hyp_ids:
            codes.append("angle_unknown_fit_hypothesis_id")
            break
    _codes_or_raise(codes)


def validate_message_atoms(atoms: dict[str, Any], *, cta_final_line: str, forbidden_patterns: list[str]) -> None:
    codes: list[str] = []
    if str(atoms.get("cta_line") or "").strip() != str(cta_final_line or "").strip():
        codes.append("atoms_cta_mismatch")
    used_hooks = list(atoms.get("used_hook_ids") or [])
    if len(used_hooks) < 1:
        codes.append("atoms_missing_used_hook_ids")
    opener = str(atoms.get("opener_line") or "").lower()
    for pattern in forbidden_patterns:
        token = str(pattern or "").strip().lower()
        if token and token in opener:
            codes.append("atoms_forbidden_opener_pattern")
            break
    _codes_or_raise(codes)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def _paragraphs(text: str) -> list[str]:
    return [chunk.strip() for chunk in re.split(r"\n\s*\n", text or "") if chunk.strip()]


def _is_non_generic_opener(opener_line: str) -> bool:
    lowered = opener_line.lower().strip()
    generic = [
        "hope this finds you well",
        "wanted to reach out",
        "quick note",
        "just checking in",
        "hi there",
    ]
    return bool(lowered) and not any(token in lowered for token in generic)


def _length_band(length: str) -> tuple[int, int]:
    key = str(length or "medium").strip().lower()
    if key == "short":
        return (40, 80)
    if key == "long":
        return (140, 220)
    return (80, 140)


def validate_email_draft(
    draft: dict[str, Any],
    *,
    brief: dict[str, Any],
    cta_final_line: str,
    sliders: dict[str, Any],
    personalization_threshold: float = 0.65,
) -> list[str]:
    codes: list[str] = []
    subject = str(draft.get("subject") or "").strip()
    body = str(draft.get("body") or "").strip()
    used_hook_ids = list(draft.get("used_hook_ids") or [])

    if len(subject) > 70:
        codes.append("subject_too_long")

    cta = str(cta_final_line or "").strip()
    if cta:
        if not body.endswith(cta):
            codes.append("cta_not_final_line")
        if body.count(cta) > 1:
            codes.append("duplicate_cta_line")

    lower_body = body.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lower_body or phrase in subject.lower():
            codes.append("banned_phrase")
            break

    facts_text = "\n".join(str(item.get("text") or "").lower() for item in brief.get("facts_from_input") or [])
    for marker in UNGROUNDED_PERSONALIZATION_MARKERS:
        if marker in lower_body and marker not in facts_text:
            codes.append("ungrounded_personalization_claim")
            break

    paras = _paragraphs(body)
    for i in range(len(paras)):
        for j in range(i + 1, len(paras)):
            if SequenceMatcher(a=paras[i].lower(), b=paras[j].lower()).ratio() >= 0.85:
                codes.append("repetition_detected")
                break
        if "repetition_detected" in codes:
            break

    length = str(sliders.get("length") or "medium")
    min_words, max_words = _length_band(length)
    wc = _word_count(body)
    if wc < min_words or wc > max_words:
        codes.append("word_count_out_of_band")

    tone_marker = float(sliders.get("framing", 0.5))
    if tone_marker >= personalization_threshold:
        opener = str(body.splitlines()[0] if body else "")
        if len(used_hook_ids) == 0:
            codes.append("personalization_missing_used_hook")
        if not _is_non_generic_opener(opener):
            codes.append("personalization_generic_opener")

    return codes


def normalize_qa_report(qa_report: dict[str, Any]) -> dict[str, Any]:
    report = dict(qa_report)
    issues = list(report.get("issues") or [])
    has_high = any(str(item.get("severity") or "").lower() == "high" for item in issues)
    pass_rewrite_needed = bool(report.get("pass_rewrite_needed")) or has_high
    report["pass_rewrite_needed"] = pass_rewrite_needed

    if pass_rewrite_needed and not report.get("rewrite_plan"):
        report["rewrite_plan"] = ["Tighten opener specificity.", "Remove fluff and keep one core ask."]
    return report
