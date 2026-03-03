"""Sentence-safe truncation helpers for prompt context fields."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TruncationResult:
    text: str
    was_truncated: bool
    boundary_used: str
    cut_mid_sentence: bool
    original_length: int
    final_length: int


_BULLET_BOUNDARY_RE = re.compile(r"\n(?:[-*•]|\d+[.)])\s+")
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?](?:\s+|$)")
_COMMA_BOUNDARY_RE = re.compile(r",(?:\s+|$)")
_HANGING_CONNECTOR_RE = re.compile(r"(?:\b(?:and|to|with)\b)\s*$", flags=re.IGNORECASE)


def _normalize_line_endings(value: str) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _trim_hanging_connectors(text: str) -> str:
    current = text.rstrip(" ,;:-")
    while _HANGING_CONNECTOR_RE.search(current):
        current = _HANGING_CONNECTOR_RE.sub("", current).rstrip(" ,;:-")
    return current


def _finalize_fragment(text: str, truncated: bool) -> str:
    compact = re.sub(r"[ \t]+", " ", text or "").strip()
    compact = _trim_hanging_connectors(compact)
    if not compact:
        return "..."
    if compact[-1] not in ".!?":
        compact = compact.rstrip(" ,;:-") + "."
    if _HANGING_CONNECTOR_RE.search(compact.rstrip(".!?")):
        compact = _trim_hanging_connectors(compact.rstrip(".!?"))
        compact = compact.rstrip(" ,;:-") + "."
    if truncated and compact[-1] not in ".!?":
        compact = compact + "."
    return compact


def _latest_double_newline(text: str, lower: int, upper: int) -> int | None:
    idx = text.rfind("\n\n", lower, upper + 1)
    if idx == -1:
        return None
    return idx


def _latest_bullet_boundary(text: str, lower: int, upper: int) -> int | None:
    boundary: int | None = None
    for match in _BULLET_BOUNDARY_RE.finditer(text):
        position = match.start()
        if lower <= position <= upper:
            boundary = position
    return boundary


def _latest_sentence_boundary(text: str, lower: int, upper: int) -> int | None:
    boundary: int | None = None
    for match in _SENTENCE_BOUNDARY_RE.finditer(text):
        position = match.end() - 1
        if lower <= position <= upper:
            boundary = position + 1
    return boundary


def _latest_comma_boundary(text: str, lower: int, upper: int) -> int | None:
    boundary: int | None = None
    for match in _COMMA_BOUNDARY_RE.finditer(text):
        position = match.end() - 1
        if not (lower <= position <= upper):
            continue
        candidate = text[: position + 1]
        if len(re.findall(r"[A-Za-z0-9']+", candidate)) < 8:
            continue
        boundary = position + 1
    return boundary


def _find_preferred_boundary(text: str, max_chars: int, window: int = 220) -> tuple[int | None, str]:
    if max_chars <= 0:
        return None, "none"
    upper = min(len(text), max_chars + max(0, window))
    lower = max(0, max_chars - max(0, window))

    boundary = _latest_double_newline(text, lower=lower, upper=upper)
    if boundary is not None and boundary >= max(1, int(max_chars * 0.45)):
        return boundary, "double_newline"

    boundary = _latest_bullet_boundary(text, lower=lower, upper=upper)
    if boundary is not None and boundary >= max(1, int(max_chars * 0.45)):
        return boundary, "bullet_boundary"

    boundary = _latest_sentence_boundary(text, lower=lower, upper=upper)
    if boundary is not None and boundary >= max(1, int(max_chars * 0.45)):
        return boundary, "sentence_boundary"

    boundary = _latest_comma_boundary(text, lower=lower, upper=upper)
    if boundary is not None and boundary >= max(1, int(max_chars * 0.45)):
        return boundary, "comma_boundary"

    return None, "none"


def truncate_sentence_safe(value: str, max_chars: int) -> TruncationResult:
    normalized = _normalize_line_endings(value)
    original_length = len(normalized)

    if max_chars <= 0:
        return TruncationResult(
            text="",
            was_truncated=bool(normalized),
            boundary_used="none",
            cut_mid_sentence=bool(normalized),
            original_length=original_length,
            final_length=0,
        )

    if len(normalized) <= max_chars:
        final_text = _finalize_fragment(normalized, truncated=False)
        return TruncationResult(
            text=final_text,
            was_truncated=False,
            boundary_used="none",
            cut_mid_sentence=False,
            original_length=original_length,
            final_length=len(final_text),
        )

    boundary_index, boundary_used = _find_preferred_boundary(normalized, max_chars=max_chars)
    if boundary_index is not None:
        trimmed = _finalize_fragment(normalized[:boundary_index], truncated=True)
        return TruncationResult(
            text=trimmed,
            was_truncated=True,
            boundary_used=boundary_used,
            cut_mid_sentence=False,
            original_length=original_length,
            final_length=len(trimmed),
        )

    forced = _finalize_fragment(normalized[:max_chars], truncated=True)
    return TruncationResult(
        text=forced,
        was_truncated=True,
        boundary_used="forced_boundary",
        cut_mid_sentence=True,
        original_length=original_length,
        final_length=len(forced),
    )
