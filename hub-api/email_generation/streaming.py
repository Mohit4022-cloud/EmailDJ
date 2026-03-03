"""SSE wrapper utilities."""

from __future__ import annotations

import json
import time
from typing import Any, AsyncGenerator

from fastapi.responses import StreamingResponse

try:
    from sse_starlette.sse import EventSourceResponse
except Exception:  # pragma: no cover
    EventSourceResponse = None  # type: ignore[assignment]


async def _event_generator(
    request_id: str,
    generator: AsyncGenerator[Any, None],
    done_extra: dict | None = None,
    event_extra: dict | None = None,
):
    sequence = 0
    common_payload = {"request_id": request_id, **(event_extra or {})}
    yield {
        "event": "start",
        "data": {**common_payload, "sequence": sequence, "timestamp": time.time()},
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
                "data": {
                    **common_payload,
                    "sequence": sequence,
                    "timestamp": time.time(),
                    **token_data,
                },
            }
            sequence += 1
        done_data: dict = {**common_payload, "sequence": sequence, "timestamp": time.time()}
        if done_extra:
            done_data.update(done_extra)
        yield {"event": "done", "data": done_data}
    except Exception as exc:
        yield {
            "event": "error",
            "data": {
                **common_payload,
                "sequence": sequence,
                "timestamp": time.time(),
                "error": str(exc),
            },
        }


async def _raw_sse_stream(
    request_id: str,
    generator: AsyncGenerator[Any, None],
    done_extra: dict | None = None,
    event_extra: dict | None = None,
):
    async for item in _event_generator(request_id, generator, done_extra, event_extra=event_extra):
        yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"


async def _eventsource_stream(
    request_id: str,
    generator: AsyncGenerator[Any, None],
    done_extra: dict | None = None,
    event_extra: dict | None = None,
):
    async for item in _event_generator(request_id, generator, done_extra, event_extra=event_extra):
        yield {"event": item["event"], "data": json.dumps(item["data"])}


async def stream_response(
    request_id: str,
    generator: AsyncGenerator[Any, None],
    done_extra: dict | None = None,
    event_extra: dict | None = None,
):
    if EventSourceResponse is not None:
        return EventSourceResponse(_eventsource_stream(request_id, generator, done_extra, event_extra=event_extra), ping=15)
    return StreamingResponse(
        _raw_sse_stream(request_id, generator, done_extra, event_extra=event_extra),
        media_type="text/event-stream",
    )
