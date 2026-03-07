from __future__ import annotations

import re
from typing import Any

from evals.models import EvalCase

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"\b(?:\+?\d{1,2}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b")
_URL_RE = re.compile(r"\bhttps?://[^\s)]+", re.IGNORECASE)

_INSTRUCTIONAL_RESEARCH_PHRASES = (
    "ignore offer lock",
    "ignore previous instructions",
    "pitch",
    "override",
    "disregard",
    "instead pitch",
)


def redact_text(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = _URL_RE.sub("[REDACTED_URL]", text)
    return text


def _tone_target(style_profile: dict[str, float]) -> str:
    formality = float(style_profile.get("formality", 0.0))
    assertiveness = float(style_profile.get("assertiveness", 0.0))
    if formality >= 0.4 and assertiveness >= 0.2:
        return "formal, direct"
    if formality <= -0.3 and assertiveness >= 0.2:
        return "conversational, direct"
    if assertiveness <= -0.3:
        return "professional, diplomatic"
    return "professional, balanced"


def _allowed_facts_summary(research_text: str, max_chars: int = 220) -> str:
    text = " ".join((research_text or "").split())
    if not text:
        return "No additional research facts provided."
    lower = text.lower()
    if any(phrase in lower for phrase in _INSTRUCTIONAL_RESEARCH_PHRASES):
        return "Research includes conflicting instructions; only explicit factual context should be used."
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "..."
    return text


def build_allowed_context(case: EvalCase) -> dict[str, str]:
    return {
        "prospect_role": redact_text(case.prospect.get("title", "")),
        "prospect_company": redact_text(case.prospect.get("company", "")),
        "offer_lock": redact_text(case.offer_lock),
        "cta_lock": redact_text(case.cta_lock),
        "allowed_facts_summary": redact_text(_allowed_facts_summary(case.research_text)),
        "tone_target": _tone_target(case.style_profile),
    }


def redact_judge_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, str):
            redacted[key] = redact_text(value)
        elif isinstance(value, dict):
            redacted[key] = redact_judge_artifact(value)
        elif isinstance(value, list):
            redacted[key] = [redact_text(item) if isinstance(item, str) else item for item in value]
        else:
            redacted[key] = value
    return redacted

