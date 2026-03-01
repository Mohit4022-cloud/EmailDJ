const VITE_HUB_URL =
  typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env.VITE_HUB_URL : undefined;
const HUB_URL = (VITE_HUB_URL || 'http://localhost:8000').replace(/\/$/, '');

export function parseSseBlock(block) {
  const lines = block.split('\n');
  let event = 'message';
  let data = '';
  for (const line of lines) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    if (line.startsWith('data:')) data += line.slice(5).trim();
  }
  if (!data) return { event, data: null };
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return { event, data };
  }
}

function betaKey() {
  try {
    return window.localStorage.getItem('emaildj_beta_key') || 'dev-beta-key';
  } catch {
    return 'dev-beta-key';
  }
}

function headers(extra = {}) {
  return {
    'Content-Type': 'application/json',
    'X-EmailDJ-Beta-Key': betaKey(),
    ...extra,
  };
}

export async function generateDraft(payload) {
  const res = await fetch(`${HUB_URL}/web/v1/generate`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Generate failed (${res.status})`);
  return res.json();
}

export async function remixDraft(payload) {
  const res = await fetch(`${HUB_URL}/web/v1/remix`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Remix failed (${res.status})`);
  return res.json();
}

export async function sendFeedback(payload) {
  const res = await fetch(`${HUB_URL}/web/v1/feedback`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Feedback failed (${res.status})`);
  return res.json();
}

export async function consumeStream(requestId, onEvent) {
  const res = await fetch(`${HUB_URL}/web/v1/stream/${requestId}`, {
    headers: { 'X-EmailDJ-Beta-Key': betaKey(), Accept: 'text/event-stream' },
  });
  if (!res.ok || !res.body) throw new Error(`Stream failed (${res.status})`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx;
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      if (!block.trim()) continue;
      onEvent(parseSseBlock(block));
    }
  }
}
