/**
 * Navigation Detector — Tier 1 of 3-tier hybrid DOM system.
 *
 * IMPLEMENTATION INSTRUCTIONS:
 * Detects Salesforce SPA navigation using two methods.
 *
 * Exports: init(), onNavigate(callback)
 *
 * Method 1 — history.pushState / replaceState monkey-patch:
 *   const origPushState = history.pushState.bind(history);
 *   history.pushState = (...args) => {
 *     origPushState(...args);
 *     handleNavigation(window.location.href);
 *   };
 *   Same for history.replaceState.
 *   Also listen: window.addEventListener('popstate', () => handleNavigation(location.href))
 *
 * Method 2 — chrome.runtime message from background:
 *   chrome.runtime.onMessage.addListener((msg) => {
 *     if (msg.type === 'NAV_UPDATED') handleNavigation(msg.url);
 *   });
 *   (Note: background worker's chrome.webNavigation.onHistoryStateUpdated sends this —
 *   but webNavigation permission is NOT in our manifest. Implement Method 1 only for MVP.
 *   Method 2 is a stub for future use when we add webNavigation permission.)
 *
 * handleNavigation(url):
 *   - Check if URL matches Salesforce record pattern:
 *     /\/lightning\/r\/(Account|Lead|Contact|Opportunity)\/[a-zA-Z0-9]+\/view/
 *   - If match: debounce 300ms, then fire registered callbacks with { url, recordType, recordId }
 *   - If no match: ignore (user navigated to non-record page).
 *
 * Debounce implementation:
 *   let debounceTimer;
 *   function debounced(fn, delay) {
 *     clearTimeout(debounceTimer);
 *     debounceTimer = setTimeout(fn, delay);
 *   }
 *
 * onNavigate(callback): register a callback, stored in callbacks array.
 */

const callbacks = [];
let debounceTimer = null;

const RECORD_URL_PATTERN = /\/lightning\/r\/(Account|Lead|Contact|Opportunity)\/([a-zA-Z0-9]+)\/view/;

function handleNavigation(url) {
  // TODO: implement debounce + pattern matching + callback firing per instructions above
}

export function init() {
  // TODO: monkey-patch history.pushState and replaceState, add popstate listener
}

export function onNavigate(callback) {
  callbacks.push(callback);
}
