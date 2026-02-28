"""
Cost Guard Middleware — budget enforcement layer.

IMPLEMENTATION INSTRUCTIONS:
1. Subclass Starlette's BaseHTTPMiddleware.
2. Extract account_id from the Authorization header (JWT claim or API key lookup).
3. On each request to LLM-touching endpoints (/generate, /research, /campaigns):
   a. Read `monthly_cost_counter:{account_id}` from Redis.
   b. Read the account's plan cost ceiling from Redis (or DB cache).
   c. If counter > 3x the plan's implied COGS allocation:
      - Set request.state.cost_throttled = True
      - Alert via Slack webhook (POST to SLACK_WEBHOOK_URL) — send ONCE per
        throttle activation (use Redis flag `throttle_alerted:{account_id}`
        with TTL = 24hr to avoid spam).
   d. If counter is within budget: set request.state.cost_throttled = False.
4. Track cost per tier separately in Redis keys:
   `cost_tier1:{account_id}`, `cost_tier2:{account_id}`, `cost_tier3:{account_id}`
5. Cost is updated POST-request by route handlers (not here) — this middleware
   only reads and gates.
6. At end of billing month (UTC), reset counters. Use a Redis expiry set to
   end-of-month UTC timestamp.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CostGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # TODO: implement per instructions above
        request.state.cost_throttled = False
        response = await call_next(request)
        return response
