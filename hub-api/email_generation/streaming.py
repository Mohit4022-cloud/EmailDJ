"""SSE wrapper utilities."""

from __future__ import annotations

import json
import time
from typing import AsyncGenerator

from fastapi.responses import StreamingResponse

try:
    from sse_starlette.sse import EventSourceResponse
except Exception:  # pragma: no cover
    EventSourceResponse = None  # type: ignore[assignment]


async def _event_generator(request_id: str, generator: AsyncGenerator[str, None], done_extra: dict | None = None):
    sequence = 0
    yield {
        "event": "start",
        "data": {"request_id": request_id, "sequence": sequence, "timestamp": time.time()},
    }
    sequence += 1
    try:
        async for token in generator:
            yield {
                "event": "token",
                "data": {"request_id": request_id, "sequence": sequence, "timestamp": time.time(), "token": token},
            }
            sequence += 1
        done_data: dict = {"request_id": request_id, "sequence": sequence, "timestamp": time.time()}
        if done_extra:
            done_data.update(done_extra)
        yield {"event": "done", "data": done_data}
    except Exception as exc:
        yield {
            "event": "error",
            "data": {
                "request_id": request_id,
                "sequence": sequence,
                "timestamp": time.time(),
                "error": str(exc),
            },
        }


async def _raw_sse_stream(request_id: str, generator: AsyncGenerator[str, None], done_extra: dict | None = None):
    async for item in _event_generator(request_id, generator, done_extra):
        yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"


async def _eventsource_stream(request_id: str, generator: AsyncGenerator[str, None], done_extra: dict | None = None):
    async for item in _event_generator(request_id, generator, done_extra):
        yield {"event": item["event"], "data": json.dumps(item["data"])}


async def stream_response(request_id: str, generator: AsyncGenerator[str, None], done_extra: dict | None = None):
    if EventSourceResponse is not None:
        return EventSourceResponse(_eventsource_stream(request_id, generator, done_extra), ping=15)
    return StreamingResponse(_raw_sse_stream(request_id, generator, done_extra), media_type="text/event-stream")
