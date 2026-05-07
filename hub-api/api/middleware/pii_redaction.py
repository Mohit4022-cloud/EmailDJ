"""Ingress/egress PII redaction middleware."""

from __future__ import annotations

import json
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from pii.presidio_redactor import analyze_and_anonymize
from pii.token_vault import detokenize, tokenize


async def _set_request_body(request: Request, body: bytes) -> None:
    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive  # type: ignore[attr-defined]
    request._body = body  # type: ignore[attr-defined]


def _walk_and_redact(value: Any, vault: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {k: _walk_and_redact(v, vault) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk_and_redact(v, vault) for v in value]
    if isinstance(value, str):
        stage1 = analyze_and_anonymize(value)
        vault.update(stage1.vault)
        stage2 = tokenize(stage1.redacted)
        vault.update(stage2.vault)
        return stage2.text
    return value


def _walk_and_detokenize(value: Any, vault: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {k: _walk_and_detokenize(v, vault) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk_and_detokenize(v, vault) for v in value]
    if isinstance(value, str):
        return detokenize(value, vault)
    return value


class PiiRedactionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request.state.token_vault = {}

        if request.method in {"POST", "PUT", "PATCH"} and request.headers.get("content-type", "").startswith("application/json"):
            raw = await request.body()
            if raw:
                payload = json.loads(raw.decode("utf-8"))
                redacted = _walk_and_redact(payload, request.state.token_vault)
                await _set_request_body(request, json.dumps(redacted).encode("utf-8"))

        response = await call_next(request)

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        if not hasattr(response, "body"):
            return response
        body = getattr(response, "body", b"")
        if not body:
            return response

        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            return response

        detok = _walk_and_detokenize(payload, request.state.token_vault)
        encoded = json.dumps(detok).encode("utf-8")
        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(content=encoded, status_code=response.status_code, headers=headers, media_type="application/json")
