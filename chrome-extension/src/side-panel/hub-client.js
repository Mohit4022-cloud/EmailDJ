/**
 * Hub Client — Side Panel's interface to the Hub API.
 *
 * IMPLEMENTATION INSTRUCTIONS:
 * The Side Panel is the primary stateful process (not the service worker).
 *
 * Exports: connect(), generateEmail(payload), pollAssignments(), captureEdit(original, edited)
 *
 * State held in this module (module scope — persists for Side Panel lifetime):
 *   - eventSource: EventSource instance
 *   - currentTokenMap: tokenMap from the last PII pre-filter scrub
 *   - pollingInterval: setInterval handle
 *
 * connect():
 *   Establishes SSE connection to Hub /stream endpoint (if Hub supports persistent SSE).
 *   For MVP: SSE is per-request (EventSource on /generate). connect() sets up the
 *   keep-alive port to service worker instead:
 *   const port = chrome.runtime.connect({ name: 'keepalive' });
 *   port.onDisconnect.addListener(() => reconnect after 1 second);
 *
 * generateEmail(payload, sliderValue):
 *   1. POST to HUB_URL/generate with { payload, slider_value: sliderValue }.
 *   2. Use fetch() for the initial POST.
 *   3. The response is text/event-stream — read it via ReadableStream:
 *      const reader = response.body.getReader();
 *      Loop: read chunks, decode text, parse SSE events manually.
 *      On 'token' event: dispatch CustomEvent('emailToken', { detail: chunk })
 *      On 'done' event: dispatch CustomEvent('emailComplete')
 *      On 'error' event: dispatch CustomEvent('emailError', { detail: msg })
 *   4. Alternative (if fetch SSE is tricky): use EventSource with POST workaround
 *      (EventSource only supports GET — use fetch() ReadableStream approach above).
 *
 * pollAssignments():
 *   1. Fetch HUB_URL/assignments.
 *   2. Return { count, assignments } JSON.
 *   3. Called on Side Panel open and every 30 seconds:
 *      setInterval(pollAssignments, 30000)
 *
 * captureEdit(original, edited):
 *   1. POST to HUB_URL/webhooks/edit with { original_draft: original, final_edit: edited }.
 *   2. Fire-and-forget (no need to await response for UX).
 *   3. This is the most important data flywheel in the product — never skip this call.
 *
 * HUB_URL: read from chrome.storage.local or hardcoded for dev:
 *   const HUB_URL = 'http://localhost:8000';
 */

const HUB_URL = 'http://localhost:8000';  // TODO: read from chrome.storage.local in prod

let pollingInterval = null;
export let currentTokenMap = {};

export function connect() {
  // TODO: implement keep-alive port + reconnect logic per instructions above
  const port = chrome.runtime.connect({ name: 'keepalive' });
  port.onDisconnect.addListener(() => {
    setTimeout(connect, 1000);
  });
}

export async function generateEmail(payload, sliderValue = 5) {
  // TODO: implement fetch + ReadableStream SSE parsing per instructions above
  throw new Error('generateEmail not yet implemented');
}

export async function pollAssignments() {
  // TODO: implement per instructions above
  const res = await fetch(`${HUB_URL}/assignments`);
  if (!res.ok) throw new Error(`Assignments fetch failed: ${res.status}`);
  return res.json();
}

export async function captureEdit(original, edited) {
  // TODO: implement per instructions above — fire and forget
  fetch(`${HUB_URL}/webhooks/edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ original_draft: original, final_edit: edited }),
  }).catch(console.error);
}
