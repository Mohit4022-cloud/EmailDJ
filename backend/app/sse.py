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
    *,
    request_id: str,
    generator: AsyncGenerator[dict[str, Any], None],
    done_extra: dict[str, Any] | None = None,
):
    sequence = 0
    yield {"event": "start", "data": {"request_id": request_id, "sequence": sequence, "timestamp": time.time()}}
    sequence += 1
    try:
        async for item in generator:
            event_name = str(item.get("event") or "progress")
            data = dict(item.get("data") or {})
            data["request_id"] = request_id
            data["sequence"] = sequence
            data["timestamp"] = time.time()
            yield {"event": event_name, "data": data}
            sequence += 1
        done_payload = {"request_id": request_id, "sequence": sequence, "timestamp": time.time()}
        if done_extra:
            done_payload.update(done_extra)
        yield {"event": "done", "data": done_payload}
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


async def _raw_stream(request_id: str, generator: AsyncGenerator[dict[str, Any], None], done_extra: dict[str, Any] | None):
    async for item in _event_generator(request_id=request_id, generator=generator, done_extra=done_extra):
        yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"


async def _eventsource_stream(request_id: str, generator: AsyncGenerator[dict[str, Any], None], done_extra: dict[str, Any] | None):
    async for item in _event_generator(request_id=request_id, generator=generator, done_extra=done_extra):
        yield {"event": item["event"], "data": json.dumps(item["data"])}


async def stream_response(
    *,
    request_id: str,
    generator: AsyncGenerator[dict[str, Any], None],
    done_extra: dict[str, Any] | None = None,
):
    if EventSourceResponse is not None:
        return EventSourceResponse(_eventsource_stream(request_id, generator, done_extra), ping=15)
    return StreamingResponse(_raw_stream(request_id, generator, done_extra), media_type="text/event-stream")

