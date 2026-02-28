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


async def _event_generator(request_id: str, generator: AsyncGenerator[str, None]):
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
        yield {
            "event": "done",
            "data": {"request_id": request_id, "sequence": sequence, "timestamp": time.time()},
        }
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


async def _raw_sse_stream(request_id: str, generator: AsyncGenerator[str, None]):
    async for item in _event_generator(request_id, generator):
        yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"


async def stream_response(request_id: str, generator: AsyncGenerator[str, None]):
    if EventSourceResponse is not None:
        return EventSourceResponse(_event_generator(request_id, generator), ping=15)
    return StreamingResponse(_raw_sse_stream(request_id, generator), media_type="text/event-stream")
