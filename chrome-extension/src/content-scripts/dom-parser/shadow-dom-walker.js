/**
 * Shadow DOM Walker — pierces Salesforce LWC shadow boundaries.
 *
 * IMPLEMENTATION INSTRUCTIONS:
 *
 * Exports: query(root, selector), observe(element, callback, options)
 *
 * Background: Salesforce Lightning Web Components (LWC) use synthetic shadow DOM.
 * Lightning Web Security (LWS) enforces closed shadow mode in Spring '26+.
 * Standard document.querySelector cannot pierce shadow roots.
 *
 * query(root, selector):
 *   Recursive shadow-piercing query:
 *   function query(root, selector) {
 *     // Try direct query first
 *     const direct = root.querySelector(selector);
 *     if (direct) return direct;
 *
 *     // Walk all children looking for shadow roots
 *     const allElements = root.querySelectorAll('*');
 *     for (const el of allElements) {
 *       if (el.shadowRoot) {
 *         const found = query(el.shadowRoot, selector);
 *         if (found) return found;
 *       }
 *       // Handle slotted content (accessible even in synthetic shadow)
 *       // No special handling needed — querySelectorAll includes slotted
 *     }
 *
 *     // If shadowRoot is null (closed mode): log and return null
 *     // (LWS closed mode blocks even this approach in Spring '26+)
 *     return null;
 *   }
 *   If a shadow root is inaccessible (throws), catch the error and log:
 *   console.warn('[EmailDJ] SHADOW_ACCESS_BLOCKED', { element: el.tagName, selector })
 *   Return null — caller handles missing data gracefully.
 *
 * observe(element, callback, options):
 *   Creates a MutationObserver on element. When new child nodes are added,
 *   recursively checks if they have shadow roots and attaches new observers.
 *   This handles the case where LWC components are dynamically added to the page.
 *   options: standard MutationObserver options (childList, subtree, etc.)
 *
 * Note: Performance concern — avoid calling query() on document root with broad
 * selectors. Always start from a known parent container (e.g., the record detail
 * panel) to limit the traversal scope.
 */

export function query(root, selector) {
  // TODO: implement recursive shadow-piercing query per instructions above
  try {
    const direct = root.querySelector(selector);
    if (direct) return direct;
    // TODO: walk shadow roots recursively
    return null;
  } catch (e) {
    console.warn('[EmailDJ] SHADOW_ACCESS_BLOCKED', { selector, error: e.message });
    return null;
  }
}

export function observe(element, callback, options = { childList: true, subtree: false }) {
  // TODO: implement recursive shadow observer per instructions above
  const observer = new MutationObserver(callback);
  observer.observe(element, options);
  return observer;
}
