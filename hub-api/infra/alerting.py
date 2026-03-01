"""Outbound alert sinks for operational events."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)


def _timeout_seconds() -> float:
    raw = os.environ.get("ALERT_SINK_TIMEOUT_SECONDS", "5").strip()
    try:
        value = float(raw)
    except ValueError:
        value = 5.0
    if value <= 0:
        return 5.0
    return value


async def send_slack_alert(payload: dict) -> None:
    url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        return

    try:
        async with httpx.AsyncClient(timeout=_timeout_seconds()) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
    except Exception as exc:
        logger.error("provider_failure_slack_alert_failed", extra={"error": str(exc)})


async def send_metrics_event(payload: dict) -> None:
    url = os.environ.get("PROVIDER_FAILURE_METRICS_WEBHOOK_URL", "").strip()
    if not url:
        return

    try:
        async with httpx.AsyncClient(timeout=_timeout_seconds()) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
    except Exception as exc:
        logger.error("provider_failure_metrics_emit_failed", extra={"error": str(exc)})


async def emit_provider_failure_alert(payload: dict) -> None:
    results = await asyncio.gather(
        send_slack_alert(payload),
        send_metrics_event(payload),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, Exception):
            logger.error("provider_failure_alert_emit_failed", extra={"error": str(result)})
