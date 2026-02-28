"""
PII Redaction Middleware — Layer 2 of 3-layer PII defense.

IMPLEMENTATION INSTRUCTIONS:
1. Subclass Starlette's BaseHTTPMiddleware.
2. In dispatch(): intercept only POST/PUT/PATCH requests with
   Content-Type: application/json.
3. Read the raw request body, parse as JSON.
4. Recursively walk all string fields in the JSON object.
5. For each string value, call presidio_redactor.analyze_and_anonymize(text).
6. Replace the string value with the anonymized result.
7. Store the (original → synthetic) mapping in request.state.token_vault
   (a plain dict, request-scoped, never persisted).
8. Re-encode the modified JSON as the new request body so downstream
   route handlers receive only anonymized data.
9. After the response is generated, call token_vault detokenize on any
   string fields in the response body that contain tokens — restoring
   real values before sending to the Side Panel.
10. Use format-preserving synthetic replacements (not blanking):
    - Names: random first names from a fixed seed list
    - Amounts: [BUDGET_AMOUNT]
    - Dates: shift by random ±30 days (preserving seasonality)
11. Log redaction stats (entity types found, counts) to a metrics counter.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class PiiRedactionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # TODO: implement per instructions above
        response = await call_next(request)
        return response
