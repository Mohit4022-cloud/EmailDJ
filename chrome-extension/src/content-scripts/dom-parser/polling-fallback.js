/**
 * Polling Fallback — Tier 3 of 3-tier hybrid DOM system.
 *
 * IMPLEMENTATION INSTRUCTIONS:
 * Safety net and regression detector. Runs every 5000ms.
 *
 * Exports: init(), stop()
 *
 * init():
 *   intervalId = setInterval(poll, 5000);
 *
 * poll():
 *   1. Extract data using broad structural selectors (see selector-registry.js).
 *      Call queryWithFallback() for each key field.
 *   2. Compare result against lastKnownState (stored in module scope):
 *      const changed = JSON.stringify(current) !== JSON.stringify(lastKnownState);
 *   3. If NOT changed: do nothing (avoid redundant Hub API calls).
 *   4. If changed:
 *      a. Identify which fields changed.
 *      b. For each new field that doesn't exist in lastKnownState:
 *         console.warn('[EmailDJ] polling_fallback detected missed field', {
 *           source: 'polling_fallback',
 *           missingField: fieldName,
 *           value: newValue,
 *           timestamp: Date.now(),
 *         });
 *         This structured log feeds the team's regression investigation queue.
 *      c. Update lastKnownState.
 *      d. Call the dataChangeCallback if registered.
 *   5. Do NOT fire full payload event from the poller — the mutation observer
 *      handles that. Poller is for detection/logging only.
 *
 * stop():
 *   clearInterval(intervalId);
 *
 * Regression detection: if the poller consistently finds data the MutationObserver
 * missed, it means a new Salesforce LWC has been deployed that broke our selectors.
 * The structured logs help the team identify which selector needs updating.
 */

import { queryWithFallback } from './selector-registry.js';

let intervalId = null;
let lastKnownState = null;
let dataChangeCallback = null;

export function setDataChangeCallback(cb) {
  dataChangeCallback = cb;
}

function poll() {
  // TODO: implement extraction, comparison, and regression logging per instructions above
}

export function init() {
  intervalId = setInterval(poll, 5000);
}

export function stop() {
  if (intervalId) {
    clearInterval(intervalId);
    intervalId = null;
  }
}
