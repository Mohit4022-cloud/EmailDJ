"""SSE wrapper utilities."""

from __future__ import annotations

import json
import time
from typing import Any, AsyncGenerator

from fastapi.responses import StreamingResponse
from pii.token_vault import detokenize

try:
    from sse_starlette.sse import EventSourceResponse
except Exception:  # pragma: no cover
    EventSourceResponse = None  # type: ignore[assignment]


async def _event_generator(
    request_id: str,
    generator: AsyncGenerator[Any, None],
    done_extra: dict | None = None,
    event_extra: dict | None = None,
    token_vault: dict[str, str] | None = None,
):
    def restore(value: Any) -> Any:
        if not token_vault:
            return value
        if isinstance(value, dict):
            return {k: restore(v) for k, v in value.items()}
        if isinstance(value, list):
            return [restore(item) for item in value]
        if isinstance(value, str):
            return detokenize(value, token_vault)
        return value

    sequence = 0
    common_payload = {"request_id": request_id, **(event_extra or {})}
    yield {
        "event": "start",
        "data": restore({**common_payload, "sequence": sequence, "timestamp": time.time()}),
    }
    sequence += 1
    try:
        async for token_payload in generator:
            token_data: dict = {"token": ""}
            if isinstance(token_payload, dict):
                token_data.update(token_payload)
            else:
                token_data["token"] = str(token_payload)
            yield {
                "event": "token",
                "data": restore({
                    **common_payload,
                    "sequence": sequence,
                    "timestamp": time.time(),
                    **token_data,
                }),
            }
            sequence += 1
        done_data: dict = {**common_payload, "sequence": sequence, "timestamp": time.time()}
        if done_extra:
            done_data.update(done_extra)
        yield {"event": "done", "data": restore(done_data)}
    except Exception as exc:
        yield {
            "event": "error",
            "data": restore({
                **common_payload,
                "sequence": sequence,
                "timestamp": time.time(),
                "error": str(exc),
            }),
        }


async def _raw_sse_stream(
    request_id: str,
    generator: AsyncGenerator[Any, None],
    done_extra: dict | None = None,
    event_extra: dict | None = None,
    token_vault: dict[str, str] | None = None,
):
    async for item in _event_generator(request_id, generator, done_extra, event_extra=event_extra, token_vault=token_vault):
        yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"


async def _eventsource_stream(
    request_id: str,
    generator: AsyncGenerator[Any, None],
    done_extra: dict | None = None,
    event_extra: dict | None = None,
    token_vault: dict[str, str] | None = None,
):
    async for item in _event_generator(request_id, generator, done_extra, event_extra=event_extra, token_vault=token_vault):
        yield {"event": item["event"], "data": json.dumps(item["data"])}


async def stream_response(
    request_id: str,
    generator: AsyncGenerator[Any, None],
    done_extra: dict | None = None,
    event_extra: dict | None = None,
    token_vault: dict[str, str] | None = None,
):
    if EventSourceResponse is not None:
        return EventSourceResponse(
            _eventsource_stream(request_id, generator, done_extra, event_extra=event_extra, token_vault=token_vault),
            ping=15,
        )
    return StreamingResponse(
        _raw_sse_stream(request_id, generator, done_extra, event_extra=event_extra, token_vault=token_vault),
        media_type="text/event-stream",
    )
