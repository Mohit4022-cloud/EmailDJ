const VITE_HUB_URL =
  typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env.VITE_HUB_URL : undefined;
const HUB_URL = (VITE_HUB_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

function parsePythonDictPayload(raw) {
  if (!raw || raw[0] !== '{' || raw[raw.length - 1] !== '}') return null;
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
    const parsed = JSON.parse(data);
    if (typeof parsed === 'string') {
      const nested = parsed.trim();
      if ((nested.startsWith('{') && nested.endsWith('}')) || (nested.startsWith('[') && nested.endsWith(']'))) {
        try {
          return { event, data: JSON.parse(nested) };
        } catch {
          return { event, data: parsed };
        }
      }
    }
    return { event, data: parsed };
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

async function postJson(path, payload) {
  const res = await fetch(`${HUB_URL}${path}`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = body?.detail?.error || body?.detail?.message || body?.error || '';
    } catch {
      detail = '';
    }
    throw new Error(`${path} failed (${res.status})${detail ? `: ${detail}` : ''}`);
  }
  return res.json();
}

export async function generateDraft(payload) {
  return postJson('/web/v1/generate', payload);
}

export async function remixDraft(payload) {
  return postJson('/web/v1/remix', payload);
}

export async function sendFeedback(payload) {
  return postJson('/web/v1/feedback', payload);
}

export async function fetchRuntimeConfig() {
  const res = await fetch(`${HUB_URL}/web/v1/debug/config`, {
    method: 'GET',
    headers: { 'X-EmailDJ-Beta-Key': betaKey() },
  });
  if (!res.ok) throw new Error(`Runtime config failed (${res.status})`);
  return res.json();
}

export async function startTargetEnrichment(payload) {
  return postJson('/web/v1/enrich/target', payload);
}

export async function startProspectEnrichment(payload) {
  return postJson('/web/v1/enrich/prospect', payload);
}

export async function startSenderEnrichment(payload) {
  return postJson('/web/v1/enrich/sender', payload);
}

export async function fetchPresetPreview(payload) {
  return postJson('/web/v1/preset-preview', payload);
}

export async function fetchPresetPreviewsBatch(payload) {
  return postJson('/web/v1/preset-previews/batch', payload);
}

export async function startResearchJob(payload) {
  const res = await fetch(`${HUB_URL}/research/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = body?.detail?.error || body?.detail?.message || body?.error || '';
    } catch {
      detail = '';
    }
    throw new Error(`/research/ failed (${res.status})${detail ? `: ${detail}` : ''}`);
  }
  return res.json();
}

export async function fetchResearchJobStatus(jobId) {
  const res = await fetch(`${HUB_URL}/research/${encodeURIComponent(jobId)}/status`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = body?.detail?.error || body?.detail?.message || body?.error || '';
    } catch {
      detail = '';
    }
    throw new Error(`/research/{job_id}/status failed (${res.status})${detail ? `: ${detail}` : ''}`);
  }
  return res.json();
}

export async function consumeStream(requestId, onEvent, options = {}) {
  const signal = options?.signal;
  const res = await fetch(`${HUB_URL}/web/v1/stream/${requestId}`, {
    headers: { 'X-EmailDJ-Beta-Key': betaKey(), Accept: 'text/event-stream' },
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`Stream failed (${res.status})`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let lastSequence = -1;
  const drainBlocks = () => {
    let idx;
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      if (!block.trim()) continue;
      const parsed = parseSseBlock(block);
      if (parsed.event === 'token') {
        const seq = parsed.data?.sequence;
        if (typeof seq === 'number') {
          if (seq <= lastSequence) continue;
          lastSequence = seq;
        }
      }
      onEvent(parsed);
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      buffer = buffer.replace(/\r\n/g, '\n');
      drainBlocks();
      if (buffer.trim()) {
        const parsed = parseSseBlock(buffer);
        if (parsed.event === 'token') {
          const seq = parsed.data?.sequence;
          if (typeof seq !== 'number' || seq > lastSequence) onEvent(parsed);
        } else {
          onEvent(parsed);
        }
      }
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    buffer = buffer.replace(/\r\n/g, '\n');
    drainBlocks();
  }
}
