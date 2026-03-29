"""CTA lock compliance policy — validates CTA shape and detects extra CTAs."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from email_generation.text_utils import collapse_ws, compact

POLICY_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Patterns from cta_templates.py
# ---------------------------------------------------------------------------

_TIMEBOX_PATTERN = re.compile(r"\b(?:15|20)\s*(?:-|to)?\s*(?:min|minute|minutes)\b", re.IGNORECASE)
_EITHER_OR_PATTERN = re.compile(
    r"\b(?:worth a look\??\s*/\s*not a priority\??|worth a look\??|not a priority\??)\b",
    re.IGNORECASE,
)
_DELIVERABLE_PATTERN = re.compile(
    r"\b(?:teardown|workflow|examples?|audit|breakdown|findings?|enforcement)\b",
    re.IGNORECASE,
)
_EXEC_TITLES_RE = re.compile(
    r"\b(ceo|chief executive officer|founder|co-founder|president|chief of staff)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Patterns from compliance_rules.py
# ---------------------------------------------------------------------------

_CTA_DURATION_PATTERN = re.compile(r"\b\d+\s*(?:-|to)?\s*\d*\s*(?:min|minute|minutes)\b")

_CTA_CHANNEL_HINTS = (
    "virtual coffee",
    "call",
    "quick call",
    "meeting",
    "demo",
    "walkthrough",
    "pilot",
    "book time",
    "chat",
    "deck",
    "next week",
)

_CTA_ASK_CUES = (
    "open to",
    "are you open",
    "would you",
    "could we",
    "can we",
    "worth trying",
    "worth a look",
    "if useful",
    "if helpful",
    "if you're open",
    "if you’re open",
    "want me to send",
    "can i send",
    "should i send",
    "happy to share",
    "happy to hop",
    "if this is on your radar",
    "if this is relevant",
)


# ---------------------------------------------------------------------------
# CTA shape validation and rendering (from cta_templates.py)
# ---------------------------------------------------------------------------


def has_specific_cta_shape(value: str | None) -> bool:
    """Return True if value contains timebox + deliverable + either-or suffix."""
    text = compact(value)
    if not text:
        return False
    return (
        _TIMEBOX_PATTERN.search(text) is not None
        and _DELIVERABLE_PATTERN.search(text) is not None
        and _EITHER_OR_PATTERN.search(text) is not None
    )


def _either_or_suffix() -> str:
    return "Worth a look / Not a priority?"


def _allow_either_or_suffix(*, preset_id: str | None = None, prospect_title: str | None = None) -> bool:
    preset = compact(preset_id).lower()
    title = compact(prospect_title)
    if preset == "straight_shooter":
        return False
    if _EXEC_TITLES_RE.search(title):
        return False
    return True


def _normalize_cta_type(value: str | None) -> str:
    return (value or "").strip().lower() or "time_ask"


def render_cta(
    *,
    cta_type: str | None,
    risk_surface: str,
    directness: int,
    preset_id: str | None = None,
    prospect_title: str | None = None,
    minutes: int = 15,
) -> str:
    bounded_minutes = 20 if minutes >= 20 else 15
    surface = compact(risk_surface) or "your highest-risk surface"
    kind = _normalize_cta_type(cta_type)
    allow_suffix = _allow_either_or_suffix(preset_id=preset_id, prospect_title=prospect_title)
    suffix = f" {_either_or_suffix()}" if allow_suffix else ""

    if kind == "curiosity":
        prefix = "Curious if this is useful"
        if directness >= 65:
            prefix = "Curious if this is worth pressure-testing now"
        return f"{prefix} for {surface}?"

    if kind == "permission":
        return (
            f"Would it be useful if I sent a short risk brief on {surface} "
            "with the first sequence changes we'd test?"
        )

    if kind == "async_audit":
        return (
            f"If you're open, I can send 3 examples we usually find on {surface} in week 1 "
            "and the workflow we'd recommend first."
        )

    if kind == "referral":
        return (
            f"If you are not the right owner for {surface}, would you point me to the person "
            "who handles outbound quality controls?"
        )

    if kind == "objection_friendly":
        return (
            f"Open to a {bounded_minutes}-min call so I can share a quick teardown of {surface} "
            f"+ what we'd automate first?{suffix}"
        )

    # Backward-compatible legacy CTA styles.
    if kind in {"value_asset"}:
        return (
            f"If you're open, I can send 3 examples we usually find on {surface} in week 1 "
            f"and the workflow we'd recommend first.{suffix}"
        )
    if kind in {"pilot", "event_invite"}:
        return (
            f"Open to a {bounded_minutes}-min call so I can share a quick teardown of {surface} "
            f"+ what we'd automate first?{suffix}"
        )
    if kind in {"time_ask", "question"}:
        tone = "Open to" if directness >= 50 else "If useful, open to"
        return (
            f"{tone} a {bounded_minutes}-min call to share a quick teardown of {surface} "
            f"and a recommended enforcement workflow?{suffix}"
        )

    # Default = calendar
    tone = "Open to" if directness >= 50 else "If useful, open to"
    return (
        f"{tone} a {bounded_minutes}-min call to share a quick teardown of {surface} "
        "and a recommended enforcement workflow?"
    )


def resolve_cta_lock(
    *,
    existing_lock: str | None,
    cta_type: str | None,
    risk_surface: str,
    directness: int,
    preset_id: str | None = None,
    prospect_title: str | None = None,
) -> str:
    lock = compact(existing_lock)
    if lock:
        return lock
    minutes = 20 if directness >= 66 else 15
    return render_cta(
        cta_type=cta_type,
        risk_surface=risk_surface,
        directness=directness,
        preset_id=preset_id,
        prospect_title=prospect_title,
        minutes=minutes,
    )


# ---------------------------------------------------------------------------
# CTA violation checks
# ---------------------------------------------------------------------------


def _is_additional_cta_line(line: str) -> bool:
    """Detect if a body line looks like an extra CTA."""
    normalized = collapse_ws((line or "").lower())
    if not normalized:
        return False
    has_channel_hint = _CTA_DURATION_PATTERN.search(normalized) is not None or any(
        hint in normalized for hint in _CTA_CHANNEL_HINTS
    )
    if not has_channel_hint:
        return False
    has_ask_cue = any(cue in normalized for cue in _CTA_ASK_CUES)
    is_question = "?" in normalized
    return has_ask_cue or is_question


def check_cta_violations(body: str, expected_cta: str) -> list[str]:
    """Return violation codes for CTA lock issues.

    Args:
        body: The email body text.
        expected_cta: The exact CTA string that must appear exactly once.

    Returns:
        List of violation code strings (empty if no violations).
    """
    violations: list[str] = []
    body_lines = [line.strip() for line in body.splitlines() if line.strip()]

    cta_matches = sum(1 for line in body_lines if line == expected_cta)
    if cta_matches != 1:
        violations.append("cta_lock_not_used_exactly_once")

    expected_cta_norm = collapse_ws(expected_cta).lower()
    for line in body_lines:
        if line == expected_cta:
            continue
        line_norm = collapse_ws(line).lower()
        if not line_norm:
            continue
        ratio = SequenceMatcher(None, expected_cta_norm, line_norm).ratio()
        if ratio >= 0.88 and (_is_additional_cta_line(line) or "?" in line):
            violations.append("cta_near_match_detected")
            break

    body_without_cta_lines: list[str] = []
    cta_removed = False
    for line in body_lines:
        if line == expected_cta and not cta_removed:
            cta_removed = True
            continue
        body_without_cta_lines.append(line)
    for line in body_without_cta_lines:
        if _is_additional_cta_line(line):
            violations.append("additional_cta_detected")
            break

    return violations
