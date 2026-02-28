import { queryWithFallback } from './selector-registry.js';

let intervalId = null;
let lastKnownState = null;
let dataChangeCallback = null;

const FIELDS = ['accountName', 'industry', 'employeeCount', 'lastActivityDate', 'notes', 'activityTimeline'];

export function setDataChangeCallback(cb) {
  dataChangeCallback = cb;
}

function snapshot() {
  const out = {};
  FIELDS.forEach((field) => {
    out[field] = queryWithFallback(field);
  });
  return out;
}

function poll() {
  const current = snapshot();
  const changed = JSON.stringify(current) !== JSON.stringify(lastKnownState);
  if (!changed) return;

  if (lastKnownState) {
    for (const [field, value] of Object.entries(current)) {
      if (!lastKnownState[field]?.value && value?.value) {
        console.warn('[EmailDJ] polling_fallback detected missed field', {
          source: 'polling_fallback',
          missingField: field,
          value: value.value,
          timestamp: Date.now(),
        });
      }
    }
  }

  lastKnownState = current;
  if (typeof dataChangeCallback === 'function') {
    dataChangeCallback({ source: 'polling_fallback', fields: current });
  }
}

export function init() {
  if (intervalId) return;
  intervalId = setInterval(poll, 5000);
}

export function stop() {
  if (intervalId) {
    clearInterval(intervalId);
    intervalId = null;
  }
}
