import { init as initNavDetector, onNavigate } from './dom-parser/navigation-detector.js';
import {
  init as initMutationObserver,
  teardown as teardownMutationObserver,
  setDataChangeCallback as setMutationDataChangeCallback,
} from './dom-parser/mutation-observer.js';
import {
  init as initPollingFallback,
  setDataChangeCallback as setPollingDataChangeCallback,
} from './dom-parser/polling-fallback.js';
import { queryWithFallback } from './dom-parser/selector-registry.js';
import { scrub } from './pii-prefilter.js';
import { build } from './payload-assembler.js';

const isSalesforceDomain = () =>
  window.location.hostname.includes('lightning.force.com') ||
  window.location.hostname.includes('salesforce.com');

function collectExtractedFields() {
  const fields = ['accountName', 'industry', 'employeeCount', 'openOpportunities', 'lastActivityDate', 'notes', 'activityTimeline'];
  const out = {};
  fields.forEach((field) => {
    out[field] = queryWithFallback(field);
  });
  return out;
}

function onDataCapture() {
  const extractedFields = collectExtractedFields();
  const { redacted, tokenMap } = scrub(JSON.stringify(extractedFields));
  const payload = build(JSON.parse(redacted));
  chrome.runtime.sendMessage({ type: 'PAYLOAD_READY', payload, tokenMap });
}

if (isSalesforceDomain()) {
  initNavDetector();
  initMutationObserver();
  initPollingFallback();

  setMutationDataChangeCallback(() => onDataCapture());
  setPollingDataChangeCallback(() => onDataCapture());

  onNavigate(() => {
    teardownMutationObserver();
    initMutationObserver();
    onDataCapture();
  });

  onDataCapture();
  chrome.runtime.sendMessage({ type: 'CONTENT_READY' });
}
