"""
SSE Streaming — wraps async token generators in EventSourceResponse.

IMPLEMENTATION INSTRUCTIONS:
Exports: stream_response(generator: AsyncGenerator) → EventSourceResponse

1. Import EventSourceResponse from sse_starlette.sse.
2. Define an async generator wrapper that formats SSE events:
   async def event_generator(token_gen):
     try:
       async for token in token_gen:
         yield { "event": "token", "data": token }
       yield { "event": "done", "data": "" }
     except Exception as e:
       yield { "event": "error", "data": str(e) }

3. Return EventSourceResponse(event_generator(generator)).

4. SSE event format (sse_starlette handles serialization):
   event: token
   data: <chunk_text>

   event: done
   data:

   event: error
   data: <error_message>

5. Side Panel's EventSource listener behavior (for reference, implemented in JS):
   - On "token" event: append data to EmailEditor contenteditable div.
   - On "done" event: mark draft complete, show Copy/Edit/Send buttons.
   - On "error" event: show error state with retry button.

6. The key UX metric: time-to-first-visible-word (TFVW).
   Target: <400ms from click. This is achieved by streaming start, not waiting
   for full generation. The user sees words appearing in ~800ms total.

7. Set ping_interval=15 to keep SSE connection alive during inference.
"""

from typing import AsyncGenerator


async def stream_response(generator: AsyncGenerator):
    # TODO: implement per instructions above
    raise NotImplementedError("stream_response not yet implemented")
