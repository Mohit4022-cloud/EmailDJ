from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.schemas import EmailBlueprint, WebStyleProfile


LEAKAGE_TOKENS = (
    "Validation warnings:",
    "template leakage",
    "prompt_template_hash",
    "repair_loop_enabled",
)


@dataclass
class ValidationState:
    violations: list[str]
    validator_attempt_count: int = 1
    repair_attempt_count: int = 0
    repaired: bool = False

    @property
    def passed(self) -> bool:
        return len(self.violations) == 0


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def _length_band(blueprint: EmailBlueprint, style: WebStyleProfile) -> tuple[int, int]:
    norm = max(0.0, min(1.0, (style.length + 1.0) / 2.0))
    target = blueprint.constraints.target_word_count_range_by_length_slider
    if norm < 0.33:
        return tuple(target.get("short", [55, 75]))  # type: ignore[return-value]
    if norm < 0.66:
        return tuple(target.get("medium", [75, 110]))  # type: ignore[return-value]
    return tuple(target.get("long", [110, 160]))  # type: ignore[return-value]


def _normalize_sentence(sentence: str) -> str:
    sentence = re.sub(r"\s+", " ", sentence.strip().lower())
    sentence = re.sub(r"[^a-z0-9\s]", "", sentence)
    return sentence


def validate_email(*, subject: str, body: str, blueprint: EmailBlueprint, style: WebStyleProfile) -> ValidationState:
    violations: list[str] = []
    cta = blueprint.structure.cta_line_locked.strip()
    if cta and cta not in body:
        violations.append("cta_lock_exact_missing")

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

    trimmed = body.strip()
    if trimmed and not trimmed.endswith((".", "!", "?")) and (not cta or trimmed != cta):
        violations.append("truncated_or_unclean_ending")

    min_words, max_words = _length_band(blueprint, style)
    wc = _word_count(body)
    if wc < min_words or wc > max_words:
        violations.append(f"word_count_out_of_band:{wc}:{min_words}-{max_words}")

    merged = f"{subject}\n{body}"
    for token in LEAKAGE_TOKENS:
        if token.lower() in merged.lower():
            violations.append("template_leakage_token")
            break

    return ValidationState(violations=violations)


def repair_email_deterministic(
    *,
    subject: str,
    body: str,
    blueprint: EmailBlueprint,
    style: WebStyleProfile,
    violations: list[str],
) -> tuple[str, str]:
    fixed_subject = (subject or "").strip()
    fixed_body = (body or "").replace("\r\n", "\n").strip()
    cta = blueprint.structure.cta_line_locked.strip()

    # Remove leakage lines.
    lines = []
    for line in fixed_body.split("\n"):
        if any(token.lower() in line.lower() for token in LEAKAGE_TOKENS):
            continue
        lines.append(line.strip())
    fixed_body = "\n".join([line for line in lines if line])

    # De-duplicate lines.
    seen: set[str] = set()
    deduped = []
    for line in fixed_body.split("\n"):
        key = _normalize_sentence(line)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(line)
    fixed_body = "\n".join(deduped).strip()

    # Ensure CTA exact and last line.
    if cta:
        filtered = [line for line in fixed_body.split("\n") if _normalize_sentence(line) != _normalize_sentence(cta)]
        fixed_body = "\n".join([line for line in filtered if line.strip()])
        fixed_body = (fixed_body + "\n" + cta).strip() if fixed_body else cta

    # Length adjustment.
    min_words, max_words = _length_band(blueprint, style)
    words = re.findall(r"\b\w+\b", fixed_body)
    if len(words) > max_words:
        truncated = " ".join(words[: max_words - 4])
        if not truncated.endswith((".", "!", "?")):
            truncated = truncated.rstrip(",;:") + "."
        fixed_body = f"{truncated}\n{cta}" if cta else truncated
    elif len(words) < min_words:
        padding = blueprint.structure.value_points[:2]
        if padding:
            addition = " ".join(point.strip().rstrip(".") + "." for point in padding if point.strip())
            fixed_body = (fixed_body + "\n" + addition).strip()
            if cta and cta not in fixed_body:
                fixed_body = fixed_body + "\n" + cta

    # Force exact CTA as final line after all adjustments.
    if cta:
        lines = [line for line in fixed_body.split("\n") if line.strip()]
        lines = [line for line in lines if _normalize_sentence(line) != _normalize_sentence(cta)]
        lines.append(cta)
        fixed_body = "\n".join(lines).strip()

    if fixed_body and not fixed_body.endswith((".", "!", "?")):
        fixed_body += "."

    if not fixed_subject:
        fixed_subject = (blueprint.angle or "Quick idea")[:78]

    return fixed_subject, fixed_body


def fallback_safe_email(blueprint: EmailBlueprint) -> tuple[str, str]:
    subject = f"Quick idea for {blueprint.identity.prospect_company}"[:78]
    body = "\n".join(
        [
            f"Hi {blueprint.identity.prospect_name.split()[0]},",
            blueprint.structure.why_you_why_now,
            blueprint.structure.value_points[0] if blueprint.structure.value_points else "Worth a quick look?",
            blueprint.structure.cta_line_locked,
        ]
    )
    return subject, body


def preset_diversity_violations(previews: list[dict[str, Any]]) -> list[str]:
    # Distinct by opener sentence, angle token, and structure (line count bands)
    if len(previews) < 2:
        return []
    seen_openers: set[str] = set()
    seen_signatures: set[str] = set()
    violations: list[str] = []
    for item in previews:
        body = str(item.get("body") or "")
        subject = str(item.get("subject") or "")
        opener = _normalize_sentence((re.split(r"(?<=[.!?])\s+|\n+", body)[0] if body else ""))
        line_count = len([line for line in body.split("\n") if line.strip()])
        signature = f"{_normalize_sentence(subject)}|{line_count}|{opener}"
        if opener and opener in seen_openers:
            violations.append("preset_diversity_opener_collision")
            break
        if signature in seen_signatures:
            violations.append("preset_diversity_structure_collision")
            break
        if opener:
            seen_openers.add(opener)
        seen_signatures.add(signature)
    return violations
