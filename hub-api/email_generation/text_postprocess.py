"""Text post-processing helpers for density and repetition control."""

from __future__ import annotations

import re


_REPEATED_FILLER_PATTERN = re.compile(
    r"\b(?:credible|specific|at scale|meaningful|robust)\b(?:\s*(?:,|and)\s*\b(?:credible|specific|at scale|meaningful|robust)\b)+",
    re.IGNORECASE,
)

_LOW_DENSITY_PHRASES = (
    "in terms of",
    "at the end of the day",
    "it is worth noting that",
    "to be clear",
    "really",
    "very",
)


def _compact(value: str | None) -> str:
    return " ".join(str(value or "").split())


def split_sentences(text: str) -> list[str]:
    normalized = _compact(text)
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+", normalized)
    return [part.strip() for part in parts if part.strip()]


def dedupe_sentences(text: str) -> str:
    output: list[str] = []
    seen: set[str] = set()
    for sentence in split_sentences(text):
        key = re.sub(r"[^a-z0-9 ]", "", sentence.lower())
        if key in seen:
            continue
        seen.add(key)
        output.append(sentence)
    return " ".join(output).strip()


def compress_fluff(text: str) -> str:
    cleaned = _compact(text)
    if not cleaned:
        return cleaned
    cleaned = _REPEATED_FILLER_PATTERN.sub("credible and specific", cleaned)
    for phrase in _LOW_DENSITY_PHRASES:
        cleaned = re.sub(rf"\b{re.escape(phrase)}\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def enforce_information_density(text: str) -> str:
    return compress_fluff(dedupe_sentences(text))

