/**
 * PII Pre-filter — Layer 1 of 3-layer PII defense.
 *
 * IMPLEMENTATION INSTRUCTIONS:
 * Runs BEFORE any data leaves the browser. Latency budget: <10ms.
 * Use regex ONLY — no NER, no model calls, no network requests.
 *
 * Exports: scrub(text) → { redacted: string, tokenMap: Record<string, string> }
 *
 * Regex patterns (high-confidence structured PII only):
 *   EMAIL:    /[^\s@]+@[^\s@]+\.[^\s@]+/g
 *   PHONE:    /\b\d{3}[-.]?\d{3}[-.]?\d{4}\b/g
 *   SSN:      /\b\d{3}-\d{2}-\d{4}\b/g
 *   CREDIT:   /\b(?:\d{4}[ -]?){3}\d{4}\b/g
 *
 * scrub(text):
 *   1. Initialize: counters for each type, tokenMap = {}.
 *   2. For each pattern:
 *      redacted = text.replace(pattern, (match) => {
 *        const token = `[TYPE_N]`;  // e.g., [EMAIL_1], [PHONE_2]
 *        tokenMap[token] = match;   // store real value
 *        counter++;
 *        return token;
 *      });
 *   3. NEVER write tokenMap to chrome.storage or localStorage.
 *      tokenMap is ephemeral — exists only in this function's return value.
 *      It will be sent to Hub via chrome.runtime.sendMessage alongside the payload,
 *      held in Side Panel memory only, and used for de-tokenization at render time.
 *   4. Return { redacted, tokenMap }.
 *
 * Performance note: run all patterns in sequence on the same string.
 * Target: <10ms for a 10KB notes string. Regex is fast enough.
 */

const PATTERNS = {
  EMAIL: /[^\s@]+@[^\s@]+\.[^\s@]+/g,
  PHONE: /\b\d{3}[-.]?\d{3}[-.]?\d{4}\b/g,
  SSN: /\b\d{3}-\d{2}-\d{4}\b/g,
  CREDIT: /\b(?:\d{4}[ -]?){3}\d{4}\b/g,
};

/**
 * @param {string} text
 * @returns {{ redacted: string, tokenMap: Record<string, string> }}
 */
export function scrub(text) {
  const source = typeof text === 'string' ? text : String(text ?? '');
  const tokenMap = {};
  let redacted = source;
  const counters = {};

  for (const [type, pattern] of Object.entries(PATTERNS)) {
    counters[type] = 0;
    // Reset lastIndex for global patterns
    pattern.lastIndex = 0;
    redacted = redacted.replace(pattern, (match) => {
      counters[type]++;
      const token = `[${type}_${counters[type]}]`;
      tokenMap[token] = match;
      return token;
    });
  }

  return { redacted, tokenMap };
}
