from __future__ import annotations

import re
from dataclasses import dataclass

from .types import EmailDraft


WORD_TOKEN_RE = re.compile(r"\b[\w']+\b")
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")

MECHANICAL_VALIDATION_CODES = {
    "word_count_out_of_band",
    "subject_too_long",
    "cta_not_final_line",
    "cta_lock_exact_missing",
    "duplicate_cta_line",
    "extra_trailing_whitespace",
    "truncated_or_unclean_ending",
}


@dataclass(slots=True)
class PostprocessResult:
    draft: EmailDraft
    applied: list[str]


def word_count(text: str) -> int:
    return len(WORD_TOKEN_RE.findall(text or ""))


def violation_code(violation: str) -> str:
    return str(violation or "").split(":", 1)[0].strip()


def violation_codes(violations: list[str]) -> list[str]:
    return [violation_code(v) for v in violations if str(v or "").strip()]


def has_any_mechanical_violations(violations: list[str]) -> bool:
    return any(code in MECHANICAL_VALIDATION_CODES for code in violation_codes(violations))


def has_only_mechanical_violations(violations: list[str]) -> bool:
    codes = violation_codes(violations)
    return bool(codes) and all(code in MECHANICAL_VALIDATION_CODES for code in codes)


def _normalize_subject(subject: str) -> str:
    return re.sub(r"\s+", " ", str(subject or "").strip())


def _trim_subject(subject: str, limit: int = 70) -> str:
    normalized = _normalize_subject(subject)
    if len(normalized) <= limit:
        return normalized
    clipped = normalized[:limit].rstrip(" ,;:-")
    return clipped or normalized[:limit]


def _normalize_body_whitespace(body: str) -> str:
    lines = [line.rstrip() for line in str(body or "").replace("\r\n", "\n").split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _hard_cut_to_words(text: str, max_words: int) -> str:
    if max_words <= 0:
        return ""
    words = WORD_TOKEN_RE.findall(text)
    if len(words) <= max_words:
        return text.strip()
    clipped = " ".join(words[:max_words]).strip()
    if clipped and not clipped.endswith((".", "!", "?")):
        clipped = clipped.rstrip(",;:") + "."
    return clipped


def _split_sentences(text: str) -> list[str]:
    collapsed = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    if not collapsed:
        return []
    parts = [part.strip() for part in SENTENCE_BOUNDARY_RE.split(collapsed) if part.strip()]
    if len(parts) <= 1:
        alt = [part.strip() for part in re.split(r"\s*[;:]\s+", collapsed) if part.strip()]
        if len(alt) > 1:
            return alt
    return parts


def _join_narrative_parts(greeting_line: str, narrative_text: str) -> str:
    chunks: list[str] = []
    if greeting_line.strip():
        chunks.append(greeting_line.strip())
    if narrative_text.strip():
        chunks.append(narrative_text.strip())
    if not chunks:
        return "Hi there,"
    return "\n\n".join(chunks).strip()


def _compose_body(narrative: str, cta_line: str) -> str:
    cta = str(cta_line or "").strip()
    if not cta:
        return narrative.strip()
    if not narrative.strip():
        return cta
    return f"{narrative.strip()}\n\n{cta}"


def deterministic_budget_clamp(
    *,
    body: str,
    max_words: int,
    cta_line: str,
    min_words: int | None = None,
) -> tuple[str, list[str]]:
    del min_words

    applied: list[str] = []
    normalized = _normalize_body_whitespace(body)
    if normalized != str(body or "").replace("\r\n", "\n").strip():
        applied.append("normalize_whitespace")

    cta = str(cta_line or "").strip()
    lines = normalized.split("\n") if normalized else []

    if cta:
        cta_positions = [idx for idx, line in enumerate(lines) if line.strip() == cta]
        if len(cta_positions) != 1 or (cta_positions and cta_positions[0] != len(lines) - 1):
            applied.append("enforce_cta_final_line")
        if not cta_positions:
            applied.append("enforce_cta_final_line")
        if len(cta_positions) > 1:
            applied.append("dedupe_cta")
        if cta_positions and cta_positions[0] < len(lines) - 1:
            applied.append("remove_trailing_after_cta")
        if cta_positions:
            lines = lines[: cta_positions[0]]

    narrative_lines = list(lines)
    if cta:
        before = len(narrative_lines)
        narrative_lines = [line for line in narrative_lines if line.strip() != cta]
        if len(narrative_lines) != before and "dedupe_cta" not in applied:
            applied.append("dedupe_cta")

    narrative = _normalize_body_whitespace("\n".join(narrative_lines))

    first_non_empty = next((line.strip() for line in narrative.split("\n") if line.strip()), "")
    greeting_line = first_non_empty

    remaining_lines = [line.strip() for line in narrative.split("\n") if line.strip()]
    if greeting_line and remaining_lines and remaining_lines[0] == greeting_line:
        remaining_lines = remaining_lines[1:]
    remaining_text = " ".join(remaining_lines).strip()

    candidate = _compose_body(_join_narrative_parts(greeting_line, remaining_text), cta)
    if max_words > 0 and word_count(candidate) > max_words:
        cta_words = word_count(cta)
        greeting_words = word_count(greeting_line)
        budget_for_rest = max(0, max_words - cta_words - greeting_words)

        sentences = _split_sentences(remaining_text)
        kept = list(sentences)
        while kept:
            preview_narrative = _join_narrative_parts(greeting_line, " ".join(kept))
            preview_body = _compose_body(preview_narrative, cta)
            if word_count(preview_body) <= max_words:
                break
            kept.pop()

        if len(kept) != len(sentences):
            applied.append("trim_to_max_words")

        if kept:
            remaining_text = " ".join(kept).strip()
        else:
            hard = _hard_cut_to_words(remaining_text, budget_for_rest)
            if hard != remaining_text:
                if "trim_to_max_words" not in applied:
                    applied.append("trim_to_max_words")
                applied.append("hard_word_cut")
            remaining_text = hard

    narrative_final = _join_narrative_parts(greeting_line, remaining_text)
    final_body = _compose_body(narrative_final, cta)

    if not final_body.strip():
        final_body = _compose_body("", cta)

    final_body = _normalize_body_whitespace(final_body)
    if cta:
        body_lines = [line.rstrip() for line in final_body.split("\n")]
        body_lines = [line for line in body_lines if line.strip()]
        deduped_lines: list[str] = []
        for line in body_lines:
            stripped = line.strip()
            if stripped == cta:
                continue
            if cta in stripped:
                stripped = stripped.replace(cta, " ").strip()
                if stripped:
                    applied.append("remove_inline_cta_echo")
            if stripped:
                deduped_lines.append(stripped)
        body_lines = deduped_lines
        if body_lines and body_lines[-1].strip():
            body_lines.append("")
        body_lines.append(cta)
        final_body = "\n".join(body_lines).strip()

    if cta:
        lines = [line.strip() for line in final_body.split("\n") if line.strip()]
        tail_start = max(0, len(lines) - 3)
        tail_questions = [idx for idx in range(tail_start, len(lines)) if "?" in lines[idx]]
        if len(tail_questions) > 1:
            filtered: list[str] = []
            for idx, line in enumerate(lines):
                if idx in tail_questions and line != cta:
                    continue
                filtered.append(line)
            lines = [line for line in filtered if line != cta]
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(cta)
            final_body = "\n".join(lines).strip()
            applied.append("dedupe_tail_interrogatives")

    return final_body, list(dict.fromkeys(applied))


def deterministic_postprocess_draft(
    draft: EmailDraft,
    *,
    max_words: int,
    cta_line: str,
    subject_limit: int = 70,
) -> PostprocessResult:
    applied: list[str] = []

    trimmed_subject = _trim_subject(draft.subject, limit=subject_limit)
    if trimmed_subject != _normalize_subject(draft.subject):
        applied.append("trim_subject_to_70")

    body, body_applied = deterministic_budget_clamp(body=draft.body, max_words=max_words, cta_line=cta_line)
    applied.extend(body_applied)

    out = EmailDraft(
        subject=trimmed_subject,
        body=body,
        subject_source=draft.subject_source,
        body_sources=list(draft.body_sources or []),
        selected_beat_ids=list(draft.selected_beat_ids or []),
    )
    return PostprocessResult(draft=out, applied=list(dict.fromkeys(applied)))
