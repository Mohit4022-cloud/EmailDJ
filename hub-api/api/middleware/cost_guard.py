"""Cost guard middleware with Redis-backed throttle state."""

from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from infra.redis_client import get_redis

LLM_PREFIXES = ("/generate", "/research", "/campaigns")


class CostGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request.state.cost_throttled = False
        if not request.url.path.startswith(LLM_PREFIXES):
            return await call_next(request)

        account_id = request.headers.get("x-account-id", "default")
        redis = get_redis()
        ceiling = float(os.environ.get("MONTHLY_COST_CEILING", "100"))
        tripwire = ceiling * 3

        total = 0.0
        for key in ("cost_tier1", "cost_tier2", "cost_tier3"):
            raw = await redis.get(f"{key}:{account_id}")
            if raw is not None:
                total += float(raw)

        if total > tripwire:
            request.state.cost_throttled = True
            alerted = await redis.get(f"throttle_alerted:{account_id}")
            if not alerted:
                await redis.setex(f"throttle_alerted:{account_id}", 86400, "1")

        return await call_next(request)
