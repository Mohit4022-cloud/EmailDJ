const VITE_HUB_URL =
  typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env.VITE_HUB_URL : undefined;
const HUB_URL = (VITE_HUB_URL || 'http://localhost:8000').replace(/\/$/, '');
const VITE_PRESET_PREVIEW_PIPELINE =
  typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env.VITE_PRESET_PREVIEW_PIPELINE : undefined;

function parsePythonDictPayload(raw) {
  if (!raw || raw[0] !== '{' || raw[raw.length - 1] !== '}') return null;
  // Legacy server payloads may use Python repr dicts (single-quoted keys/values).
  const normalized = raw
    .replace(/\bNone\b/g, 'null')
    .replace(/\bTrue\b/g, 'true')
    .replace(/\bFalse\b/g, 'false')
    .replace(/([{,]\s*)'([^'\\]*(?:\\.[^'\\]*)*)'\s*:/g, '$1"$2":')
    .replace(/:\s*'([^'\\]*(?:\\.[^'\\]*)*)'(\s*[,}])/g, (_m, value, tail) => {
      const escaped = value.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
      return `: "${escaped}"${tail}`;
    });
  try {
    return JSON.parse(normalized);
  } catch {
    return null;
  }
}

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
    return { event, data: parsePythonDictPayload(data) || data };
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

export async function generateDraftText(payload) {
  const accepted = await generateDraft(payload);
  let draft = '';
  await consumeStream(accepted.request_id, (event) => {
    if (event.event !== 'token') return;
    draft += event.data?.token || '';
  });
  return draft.trim();
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
  const drainBlocks = () => {
    let idx;
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      if (!block.trim()) continue;
      onEvent(parseSseBlock(block));
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      buffer = buffer.replace(/\r\n/g, '\n');
      drainBlocks();
      if (buffer.trim()) onEvent(parseSseBlock(buffer));
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    buffer = buffer.replace(/\r\n/g, '\n');
    drainBlocks();
  }
}

export function presetPreviewBatchEnabled() {
  const raw = String(VITE_PRESET_PREVIEW_PIPELINE || 'on').trim().toLowerCase();
  return raw !== 'off' && raw !== '0' && raw !== 'false';
}

export async function generatePresetPreviewsBatch(payload) {
  const res = await fetch(`${HUB_URL}/web/v1/preset-previews/batch`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = body?.detail?.error || body?.detail?.message || body?.error || '';
    } catch {
      detail = '';
    }
    throw new Error(`Preset preview batch failed (${res.status})${detail ? `: ${detail}` : ''}`);
  }
  return res.json();
}
