"""Runtime policy helpers for compliance enforcement and debug sampling."""

from __future__ import annotations

import os

ALLOWED_ENFORCEMENT_LEVELS = ("warn", "repair", "block")


def _bool_from_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def repair_loop_enabled() -> bool:
    return _bool_from_env("EMAILDJ_REPAIR_LOOP_ENABLED", True)


def strict_lock_enforcement_level() -> str:
    level = os.environ.get("EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL", "repair").strip().lower() or "repair"
    if level in ALLOWED_ENFORCEMENT_LEVELS:
        return level
    return "repair"


def debug_success_sample_rate() -> float:
    raw = os.environ.get("EMAILDJ_DEBUG_SUCCESS_SAMPLE_RATE", "0.01").strip() or "0.01"
    try:
        value = float(raw)
    except ValueError:
        return 0.01
    return max(0.0, min(1.0, value))

