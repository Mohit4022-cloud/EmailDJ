from __future__ import annotations

import re
from typing import Literal


ResearchState = Literal["no_research", "sparse", "grounded"]

PLACEHOLDER_FACT_TEXTS = {
    "",
    "n/a",
    "na",
    "none",
    "none provided.",
    "unknown",
}

PLACEHOLDER_RESEARCH_TEXTS = {
    *PLACEHOLDER_FACT_TEXTS,
    "limited public context.",
    "limited public context",
    "no research.",
    "no research",
    "no specific research available for this account.",
    "no specific research available for this account",
    "no verifiable external research provided.",
    "no verifiable external research provided",
    "no verifiable research available.",
    "no verifiable research available",
}


def normalize_placeholder_text(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def is_placeholder_fact_text(text: object) -> bool:
    return normalize_placeholder_text(text) in PLACEHOLDER_FACT_TEXTS


def is_semantic_no_research(text: object) -> bool:
    return normalize_placeholder_text(text) in PLACEHOLDER_RESEARCH_TEXTS


def usable_research_text(text: object) -> str:
    cleaned = str(text or "").strip()
    return "" if is_semantic_no_research(cleaned) else cleaned


def classify_research_state(text: object) -> ResearchState:
    cleaned = usable_research_text(text)
    if not cleaned:
        return "no_research"

    lowered = cleaned.lower()
    if any(
        token in lowered
        for token in (
            "http://",
            "https://",
            "announced",
            "launched",
            "hired",
            "funding",
            "posted",
            "published",
            "rolled out",
            "expanded",
            "centralized",
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
            "2024",
            "2025",
            "2026",
        )
    ):
        return "grounded"

    if len(re.findall(r"\b\w+\b", lowered)) >= 12:
        return "grounded"

    return "sparse"


def has_meaningful_research(text: object) -> bool:
    return classify_research_state(text) != "no_research"


def has_grounded_research_signal(text: object) -> bool:
    return classify_research_state(text) == "grounded"
