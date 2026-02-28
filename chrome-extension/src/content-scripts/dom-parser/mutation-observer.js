import { observe as shadowObserve } from './shadow-dom-walker.js';

const observers = [];
const TARGET_SELECTORS = ['.slds-page-header', '[data-component-id="forceRecordDetail"]', '.slds-timeline'];
let dataChangeCallback = null;

export function setDataChangeCallback(cb) {
  dataChangeCallback = cb;
}

function attachObserver(element, selector) {
  const obs = new MutationObserver(() => {
    if (typeof dataChangeCallback === 'function') {
      dataChangeCallback({ source: 'mutation_observer', selector });
    }
  });
  obs.observe(element, { childList: true, subtree: false, characterData: true });
  observers.push(obs);

  const shadowObs = shadowObserve(element, () => {
    if (typeof dataChangeCallback === 'function') {
      dataChangeCallback({ source: 'mutation_observer_shadow', selector });
    }
  }, { childList: true, subtree: false });
  observers.push(shadowObs);
}

function waitForElement(selector, retries = 5, delay = 100) {
  const el = document.querySelector(selector);
  if (el) {
    attachObserver(el, selector);
    return;
  }
  if (retries === 0) {
    console.warn('[EmailDJ] Element not found:', selector);
    return;
  }
  setTimeout(() => waitForElement(selector, retries - 1, delay * 2), delay);
}

export function init() {
  TARGET_SELECTORS.forEach((selector) => waitForElement(selector));
}

export function teardown() {
  observers.forEach((obs) => obs.disconnect());
  observers.length = 0;
}
