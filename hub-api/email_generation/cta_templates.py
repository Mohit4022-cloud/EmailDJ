"""CTA template helpers for specific, deliverable-based asks."""

from __future__ import annotations

import re


_TIMEBOX_PATTERN = re.compile(r"\b(?:15|20)\s*(?:-|to)?\s*(?:min|minute|minutes)\b", re.IGNORECASE)
_EITHER_OR_PATTERN = re.compile(
    r"\b(?:worth a look\??\s*/\s*not a priority\??|worth a look\??|not a priority\??)\b",
    re.IGNORECASE,
)
_DELIVERABLE_PATTERN = re.compile(
    r"\b(?:teardown|workflow|examples?|audit|breakdown|findings?|enforcement)\b",
    re.IGNORECASE,
)


def _compact(value: str | None) -> str:
    return " ".join(str(value or "").split())


def has_specific_cta_shape(value: str | None) -> bool:
    text = _compact(value)
    if not text:
        return False
    return (
        _TIMEBOX_PATTERN.search(text) is not None
        and _DELIVERABLE_PATTERN.search(text) is not None
        and _EITHER_OR_PATTERN.search(text) is not None
    )


def _either_or_suffix() -> str:
    return "Worth a look / Not a priority?"


def render_cta(
    *,
    cta_type: str | None,
    risk_surface: str,
    directness: int,
    minutes: int = 15,
) -> str:
    bounded_minutes = 20 if minutes >= 20 else 15
    surface = _compact(risk_surface) or "your highest-risk surface"
    kind = (cta_type or "").strip().lower()

    if kind in {"value_asset", "referral"}:
        return (
            f"If you're open, I can send 3 examples we usually find on {surface} in week 1 "
            f"and the workflow we'd recommend first. {_either_or_suffix()}"
        )
    if kind in {"pilot", "event_invite"}:
        return (
            f"Open to a {bounded_minutes}-min call so I can share a quick teardown of {surface} "
            f"+ what we'd automate first? {_either_or_suffix()}"
        )
    # Default to time ask / question.
    tone = "Open to" if directness >= 50 else "If useful, open to"
    return (
        f"{tone} a {bounded_minutes}-min call to share a quick teardown of {surface} "
        f"and a recommended enforcement workflow? {_either_or_suffix()}"
    )


def resolve_cta_lock(
    *,
    existing_lock: str | None,
    cta_type: str | None,
    risk_surface: str,
    directness: int,
) -> str:
    lock = _compact(existing_lock)
    if has_specific_cta_shape(lock):
        return lock
    minutes = 20 if directness >= 66 else 15
    return render_cta(
        cta_type=cta_type,
        risk_surface=risk_surface,
        directness=directness,
        minutes=minutes,
    )

