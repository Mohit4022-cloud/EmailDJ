from __future__ import annotations

import re

from .realize import word_band_for_brevity
from .types import EmailDraft, MessagePlan, NormalizedContext


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def _normalize_sentence(sentence: str) -> str:
    sentence = re.sub(r"\s+", " ", sentence.strip().lower())
    sentence = re.sub(r"[^a-z0-9\s]", "", sentence)
    return sentence


def _strip_forbidden(text: str) -> str:
    cleaned = text
    # Remove known leak markers and labels.
    patterns = [
        r"\brepeated_sentence_detected\b",
        r"\bword_count_out_of_band\b",
        r"\bunsupported claims\b",
        r"\brole-specific relevance\b",
        r"\bwhy it works\b",
        r"\bvalidation warnings\b",
        r"\bprompt_template_hash\b",
        r"\brubric\b",
        r"\bvalidator\b",
        r"\bsubject\s*:\s*",
        r"\bbody\s*:\s*",
    ]
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _dedupe_lines(body: str) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for line in body.split("\n"):
        entry = line.strip()
        if not entry:
            continue
        key = _normalize_sentence(entry)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return "\n".join(out)


def _hedge_unsourced(text: str) -> str:
    text = re.sub(r"\bnoticed\b", "came across", text, flags=re.IGNORECASE)
    text = re.sub(r"\brecent\b", "current", text, flags=re.IGNORECASE)
    return text


def repair_draft(draft: EmailDraft, plan: MessagePlan, ctx: NormalizedContext, violations: list[str]) -> EmailDraft:
    subject = _strip_forbidden(draft.subject)
    body = draft.body.replace("\r\n", "\n").strip()

    if "forbidden_substring" in violations:
        body = "\n".join(_strip_forbidden(line) for line in body.split("\n"))
        body = "\n".join(line for line in body.split("\n") if line.strip())

    if "unsourced_recent_claim" in violations:
        body = _hedge_unsourced(body)
        subject = _hedge_unsourced(subject)

    body = _dedupe_lines(body)

    cta = plan.cta_line_locked.strip()
    if cta:
        lines = [line.strip() for line in body.split("\n") if line.strip()]
        lines = [line for line in lines if _normalize_sentence(line) != _normalize_sentence(cta)]
        lines.append(cta)
        body = "\n\n".join(lines)

    _, max_words = word_band_for_brevity(int(ctx.sliders.get("brevity", 50)))
    wc = _word_count(body)
    if wc > max_words:
        words = re.findall(r"\S+", body)
        cta_words = re.findall(r"\S+", cta) if cta else []
        keep = max(20, max_words - len(cta_words) - 2)
        clipped = " ".join(words[:keep]).strip()
        if clipped and not clipped.endswith((".", "!", "?")):
            clipped = clipped.rstrip(",;:") + "."
        body = f"{clipped}\n\n{cta}" if cta else clipped

    if body and not body.endswith((".", "!", "?")):
        body += "."

    if not subject:
        role = ctx.prospect_title or "your team"
        subject = f"Idea for {role}"[:70]

    return EmailDraft(
        subject=subject[:70],
        body=body.strip(),
        subject_source=draft.subject_source or "repair",
        body_sources=list(draft.body_sources or []),
        selected_beat_ids=list(draft.selected_beat_ids or []),
    )
