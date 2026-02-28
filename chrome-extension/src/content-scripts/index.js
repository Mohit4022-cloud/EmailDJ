/**
 * EmailDJ Content Script Entry Point
 *
 * IMPLEMENTATION INSTRUCTIONS:
 * Bootstrap file — initializes the 3-tier DOM parsing system in order.
 *
 * 1. Import all modules:
 *    import { init as initNavDetector } from './dom-parser/navigation-detector.js';
 *    import { init as initMutationObserver } from './dom-parser/mutation-observer.js';
 *    import { init as initPollingFallback } from './dom-parser/polling-fallback.js';
 *    import { scrub } from './pii-prefilter.js';
 *    import { build } from './payload-assembler.js';
 *
 * 2. Initialize tiers in order:
 *    initNavDetector();
 *    initMutationObserver();
 *    initPollingFallback();
 *
 * 3. Data capture event handler (called by all 3 tiers when data changes):
 *    async function onDataCapture(extractedFields) {
 *      const { redacted, tokenMap } = scrub(JSON.stringify(extractedFields));
 *      const payload = build(JSON.parse(redacted));
 *      chrome.runtime.sendMessage({ type: 'PAYLOAD_READY', payload, tokenMap });
 *    }
 *
 * 4. Register this handler with each tier:
 *    navigationDetector.onNavigate(() => {
 *      // re-extract after navigation, pass to onDataCapture
 *    });
 *
 * 5. Send initial ready signal to service worker:
 *    chrome.runtime.sendMessage({ type: 'CONTENT_READY' });
 *
 * 6. Guard: only run on Salesforce Lightning pages (check window.location.hostname).
 *    If not on a Salesforce domain, exit immediately.
 */

// TODO: implement per instructions above

const isSalesforceDomain = () =>
  window.location.hostname.includes('lightning.force.com') ||
  window.location.hostname.includes('salesforce.com');

if (isSalesforceDomain()) {
  // TODO: import and initialize tiers, register event handlers
  chrome.runtime.sendMessage({ type: 'CONTENT_READY' });
}
