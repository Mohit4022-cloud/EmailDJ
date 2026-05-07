/** Hub client for side panel. */

const BUILD_ENV = import.meta.env || {};
export const DEFAULT_HUB_URL = 'http://127.0.0.1:8000';
const HUB_URL_STORAGE_KEY = 'emaildjHubUrl';
const BETA_KEY_STORAGE_KEY = 'emaildjBetaKey';

let pollingInterval = null;
let keepalivePort = null;
export let currentTokenMap = {};

export function normalizeHubUrl(value, fallback = DEFAULT_HUB_URL) {
  const raw = String(value || '').trim() || fallback;
  const trimmed = raw.replace(/\/+$/, '');
  try {
    const url = new URL(trimmed);
    if (!['http:', 'https:'].includes(url.protocol)) {
      return fallback;
    }
    return url.toString().replace(/\/+$/, '');
  } catch {
    return fallback;
  }
}

export function isProductionLikeEnv(env = BUILD_ENV) {
  return Boolean(env?.PROD) || String(env?.MODE || '').toLowerCase() === 'production';
}

export function isLocalHubUrl(value) {
  try {
    const url = new URL(value);
    return ['localhost', '127.0.0.1', '0.0.0.0', '::1', '[::1]'].includes(url.hostname);
  } catch {
    return true;
  }
}

export function assertLaunchSafeHubConfig({ env = BUILD_ENV, hubUrl = '', betaKey = '', rawHubUrl = '' } = {}) {
  if (!isProductionLikeEnv(env)) return;
  if (!String(rawHubUrl || '').trim()) {
    throw new Error(
      'Missing VITE_HUB_URL for a production extension runtime. Set it to the deployed hub-api root URL or save a runtime override.'
    );
  }
  const url = new URL(hubUrl);
  if (url.protocol !== 'https:' || isLocalHubUrl(hubUrl)) {
    throw new Error('Production extension hub URL must be a deployed https:// hub-api origin, not localhost.');
  }
  if (String(betaKey || '').trim() === 'dev-beta-key') {
    throw new Error('Production extension beta key cannot be dev-beta-key. Use a non-dev key or leave it empty for operator override.');
  }
}

export function resolveHubConfigFromValues({ env = BUILD_ENV, storedHubUrl = '', storedBetaKey = '' } = {}) {
  const rawHubUrl = storedHubUrl || env.VITE_HUB_URL || '';
  const hubUrl = normalizeHubUrl(rawHubUrl || DEFAULT_HUB_URL);
  const betaKey = String(storedBetaKey || env.VITE_EMAILDJ_BETA_KEY || '').trim();
  assertLaunchSafeHubConfig({ env, hubUrl, betaKey, rawHubUrl });
  return { hubUrl, betaKey };
}

async function readStoredConfig() {
  const storage = globalThis.chrome?.storage?.sync;
  if (!storage?.get) return {};
  try {
    return await storage.get([HUB_URL_STORAGE_KEY, BETA_KEY_STORAGE_KEY]);
  } catch {
    return {};
  }
}

export async function resolveHubConfig() {
  const stored = await readStoredConfig();
  return resolveHubConfigFromValues({
    storedHubUrl: stored[HUB_URL_STORAGE_KEY],
    storedBetaKey: stored[BETA_KEY_STORAGE_KEY],
  });
}

export async function saveHubConfig({ hubUrl = '', betaKey = '' } = {}) {
  const storage = globalThis.chrome?.storage?.sync;
  if (!storage?.set) {
    throw new Error('Chrome storage is unavailable.');
  }
  const config = resolveHubConfigFromValues({ storedHubUrl: hubUrl, storedBetaKey: betaKey });
  await storage.set({
    [HUB_URL_STORAGE_KEY]: config.hubUrl,
    [BETA_KEY_STORAGE_KEY]: config.betaKey,
  });
  return config;
}

export function buildHubHeaders(config, headers = {}) {
  const merged = { ...headers };
  if (config?.betaKey) {
    merged['X-EmailDJ-Beta-Key'] = config.betaKey;
  }
  return merged;
}

async function hubFetch(path, options = {}) {
  const config = await resolveHubConfig();
  return fetch(`${config.hubUrl}${path}`, {
    ...options,
    headers: buildHubHeaders(config, options.headers || {}),
  });
}

function parseSseBlock(block) {
  const lines = block.split('\n');
  let event = 'message';
  let data = '';
  for (const line of lines) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      data += line.slice(5).trim();
    }
  }
  if (!data) return { event, data: null };
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return { event, data };
  }
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function connect() {
  try {
    keepalivePort = chrome.runtime.connect({ name: 'keepalive' });
    keepalivePort.onDisconnect.addListener(() => {
      keepalivePort = null;
      setTimeout(connect, 1000);
    });
  } catch {
    setTimeout(connect, 1000);
  }

  if (!pollingInterval) {
    pollingInterval = setInterval(() => {
      pollAssignments().catch(() => {});
    }, 30000);
  }
}

async function startGenerate(payload, sliderValue = 5) {
  const start = await hubFetch('/generate/quick', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload, slider_value: sliderValue }),
  });
  if (!start.ok) {
    throw new Error(`Generate failed (${start.status})`);
  }
  return start.json();
}

async function consumeStream(requestId) {
  const streamRes = await hubFetch(`/generate/stream/${requestId}`, {
    method: 'GET',
    headers: { Accept: 'text/event-stream' },
  });

  if (!streamRes.ok || !streamRes.body) {
    throw new Error(`Stream failed (${streamRes.status})`);
  }

  const reader = streamRes.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let lastSequence = -1;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx;
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      if (!block.trim()) continue;

      const msg = parseSseBlock(block);
      if (msg.event === 'token') {
        const seq = msg.data?.sequence;
        if (typeof seq === 'number') {
          if (seq <= lastSequence) continue; // duplicate or out-of-order
          lastSequence = seq;
        }
        const token = msg.data?.token ?? '';
        window.dispatchEvent(new CustomEvent('emailToken', { detail: token }));
      } else if (msg.event === 'done') {
        window.dispatchEvent(new CustomEvent('emailComplete'));
      } else if (msg.event === 'error') {
        throw new Error(msg.data?.error || 'Unknown stream error');
      }
    }
  }
}

export async function generateEmail(payload, sliderValue = 5) {
  const maxAttempts = 3;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      if (attempt > 1) {
        window.dispatchEvent(new CustomEvent('emailRetry', { detail: attempt }));
      }
      const { request_id } = await startGenerate(payload, sliderValue);
      await consumeStream(request_id);
      return;
    } catch (err) {
      if (attempt >= maxAttempts) {
        window.dispatchEvent(new CustomEvent('emailError', { detail: String(err?.message || err) }));
        return;
      }
      await delay(300 * attempt);
    }
  }
}

export async function pollAssignments() {
  const res = await hubFetch('/assignments/poll?sdr_id=demo-sdr', {
    headers: { 'Cache-Control': 'no-cache' },
  });
  if (!res.ok) throw new Error(`Assignments fetch failed: ${res.status}`);
  return res.json();
}

export async function captureEdit(original, edited) {
  hubFetch('/webhooks/edit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ original_draft: original, final_edit: edited }),
  }).catch(console.error);
}

export async function sendAssignment(assignmentId, emailDraft, finalEdit) {
  return hubFetch('/webhooks/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ assignment_id: assignmentId, email_draft: emailDraft, final_edit: finalEdit }),
  });
}
