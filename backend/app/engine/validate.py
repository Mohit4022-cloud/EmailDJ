from __future__ import annotations

import re

from .realize import word_band_for_brevity
from .types import EmailDraft, MessagePlan, NormalizedContext


FORBIDDEN_SUBSTRINGS = (
    "repeated_sentence_detected",
    "word_count_out_of_band",
    "subject",
    "body",
    "why it works",
    "unsupported claims",
    "role-specific relevance",
    "template leakage",
    "validation warnings",
    "prompt_template_hash",
    "rubric",
    "validator",
)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def violation_code(violation: str) -> str:
    return str(violation or "").split(":", 1)[0].strip()


def violation_codes(violations: list[str]) -> list[str]:
    return [violation_code(item) for item in violations if str(item or "").strip()]


def _normalize_sentence(sentence: str) -> str:
    sentence = re.sub(r"\s+", " ", sentence.strip().lower())
    sentence = re.sub(r"[^a-z0-9\s]", "", sentence)
    return sentence


def validate_draft(draft: EmailDraft, plan: MessagePlan, ctx: NormalizedContext) -> list[str]:
    violations: list[str] = []
    subject = (draft.subject or "").strip()
    body = (draft.body or "").strip()
    merged = f"{subject}\n{body}"

    if len(subject) > 70:
        violations.append(f"subject_too_long:{len(subject)}:70")

    if body != (draft.body or ""):
        violations.append("extra_trailing_whitespace")
    elif any(line != line.rstrip() for line in (draft.body or "").split("\n")):
        violations.append("extra_trailing_whitespace")

    if plan.cta_line_locked:
        cta = plan.cta_line_locked.strip()
        lines = body.splitlines()
        occurrences = sum(1 for line in lines if line.strip() == cta)
        if occurrences == 0:
            violations.append("cta_lock_exact_missing")
        else:
            if occurrences > 1:
                violations.append(f"duplicate_cta_line:{occurrences}")
            if lines and lines[-1].strip() != cta:
                violations.append("cta_not_final_line")

    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", body) if part.strip()]
    seen: set[str] = set()
    for sentence in sentences:
        key = _normalize_sentence(sentence)
        if not key:
            continue
        if key in seen:
            violations.append("repeated_sentence_detected")
            break
        seen.add(key)

    _, max_words = word_band_for_brevity(int(ctx.sliders.get("brevity", 50)))
    wc = _word_count(body)
    if wc > max_words:
        violations.append(f"word_count_out_of_band:{wc}:0-{max_words}")

    lowered = merged.lower()
    for token in FORBIDDEN_SUBSTRINGS:
        if token in lowered:
            violations.append("forbidden_substring")
            break

    if re.search(r"\b(recent|noticed)\b", lowered) and not ctx.signal_available:
        violations.append("unsourced_recent_claim")

    if body and not body.endswith((".", "?", "!")):
        violations.append("truncated_or_unclean_ending")

    return violations
