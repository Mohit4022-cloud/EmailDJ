export function query(root, selector) {
  try {
    const direct = root.querySelector(selector);
    if (direct) return direct;

    const nodes = root.querySelectorAll('*');
    for (const el of nodes) {
      if (el.shadowRoot) {
        const found = query(el.shadowRoot, selector);
        if (found) return found;
      }
    }
    return null;
  } catch (e) {
    console.warn('[EmailDJ] SHADOW_ACCESS_BLOCKED', { selector, error: e.message });
    return null;
  }
}

export function observe(element, callback, options = { childList: true, subtree: false }) {
  const observer = new MutationObserver((mutations) => {
    callback(mutations);
    for (const mutation of mutations) {
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType === 1 && node.shadowRoot) {
          observe(node.shadowRoot, callback, options);
        }
      });
    }
  });
  observer.observe(element, options);
  return observer;
}
