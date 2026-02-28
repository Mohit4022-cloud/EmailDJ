/**
 * Mutation Observer — Tier 2 of 3-tier hybrid DOM system.
 *
 * IMPLEMENTATION INSTRUCTIONS:
 * Observe 3–5 known Salesforce Lightning containers — NOT the full document.
 *
 * Exports: init(), teardown()
 *
 * Target containers (observe EACH separately, NOT document root):
 *   1. '.slds-page-header'                           → record title / account name
 *   2. '[data-component-id="forceRecordDetail"]'     → detail fields (industry, size, etc.)
 *   3. '.slds-timeline'                               → activity timeline
 *   (Optional additions if they stabilize: '.slds-card__body', '[data-record-id]')
 *
 * For each container:
 *   - Use { childList: true, subtree: false, characterData: true } observer config.
 *   - NEVER use { subtree: true } on document.body — this is the Mixmax anti-pattern
 *     that causes memory leaks and performance degradation on Salesforce.
 *   - For Salesforce LWC Shadow DOM boundaries: delegate to shadowDomWalker.observe().
 *
 * Element availability with exponential backoff:
 *   function waitForElement(selector, retries = 5, delay = 100) {
 *     const el = document.querySelector(selector);
 *     if (el) return attachObserver(el);
 *     if (retries === 0) return console.warn('[EmailDJ] Element not found:', selector);
 *     setTimeout(() => waitForElement(selector, retries - 1, delay * 2), delay);
 *   }
 *   Backoff: 100ms, 200ms, 400ms, 800ms, 1600ms.
 *
 * On mutation detected:
 *   - Extract relevant data from the mutated container.
 *   - Call the onDataChange callback (registered via setDataChangeCallback).
 *
 * teardown():
 *   - Disconnect all active MutationObserver instances.
 *   - Call when navigation detector fires (re-init after navigation).
 */

import { observe as shadowObserve } from './shadow-dom-walker.js';

const observers = [];
const TARGET_SELECTORS = [
  '.slds-page-header',
  '[data-component-id="forceRecordDetail"]',
  '.slds-timeline',
];

let dataChangeCallback = null;

export function setDataChangeCallback(cb) {
  dataChangeCallback = cb;
}

function attachObserver(element, selector) {
  // TODO: create MutationObserver, attach to element, store in observers array
}

function waitForElement(selector, retries = 5, delay = 100) {
  // TODO: implement with exponential backoff per instructions above
}

export function init() {
  // TODO: call waitForElement for each TARGET_SELECTOR
}

export function teardown() {
  observers.forEach(obs => obs.disconnect());
  observers.length = 0;
}
