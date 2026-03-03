"""Redis metrics persistence for policy runner — keeps policy_runner.py pure."""

from __future__ import annotations

from datetime import datetime, timezone

from email_generation.policies.policy_runner import ViolationReport

POLICY_VERSION = "1.0.0"

_TTL = 3 * 24 * 60 * 60  # 3 days, matching existing compliance key TTL


async def persist_policy_metrics(report: ViolationReport, session_id: str | None = None) -> None:
    """Write Redis counters for policy violations.

    Increments per-rule, per-day counters and per-session repair count.
    Silently swallows errors to avoid blocking the main response path.

    Args:
        report: ViolationReport returned by policy_runner.run().
        session_id: Optional session identifier for per-session repair tracking.
    """
    try:
        from infra.redis_client import get_redis

        redis = get_redis()
        day = datetime.now(timezone.utc).strftime("%Y%m%d")

        for rule in report.rules:
            if rule.violations:
                key = f"policy:violation:{rule.rule_name}:{day}"
                await redis.incr(key)
                await redis.expire(key, _TTL)

        if report.repair_count > 0 and session_id:
            rk = f"policy:repair_count:{session_id}"
            await redis.incrby(rk, report.repair_count)
            await redis.expire(rk, _TTL)

    except Exception:  # noqa: BLE001
        pass  # metrics are best-effort; never block the response
