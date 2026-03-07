"""Beta access middleware for /web/v1 routes."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from infra.redis_client import get_redis


def _allowed_keys() -> set[str]:
    raw = os.environ.get("EMAILDJ_WEB_BETA_KEYS", "dev-beta-key")
    return {part.strip() for part in raw.split(",") if part.strip()}


def _rate_limit_per_min() -> int:
    raw = os.environ.get("EMAILDJ_WEB_RATE_LIMIT_PER_MIN", "30").strip()
    try:
        value = int(raw)
    except ValueError:
        return 30
    return max(value, 1)


def _minute_bucket() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M")


def _should_rate_limit(request: Request) -> bool:
    # Stream polling should not consume the same quota as generation requests.
    return request.method.upper() == "POST"


class WebBetaAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not path.startswith("/web/v1"):
            return await call_next(request)
        # Browser CORS preflight requests do not include custom auth headers.
        if request.method == "OPTIONS":
            return await call_next(request)

        key = request.headers.get("x-emaildj-beta-key", "").strip()
        if not key or key not in _allowed_keys():
            return JSONResponse(status_code=401, content={"error": "unauthorized_beta_key"})

        if _should_rate_limit(request):
            redis = get_redis()
            bucket = _minute_bucket()
            rate_key = f"web_mvp:ratelimit:{key}:{bucket}"
            count = await redis.incr(rate_key)
            if count == 1:
                await redis.expire(rate_key, 70)
            if count > _rate_limit_per_min():
                return JSONResponse(status_code=429, content={"error": "rate_limited"})

        request.state.web_beta_key = key
        return await call_next(request)
