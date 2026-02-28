/**
 * Selector Registry — 4-tier selector priority cascade.
 *
 * IMPLEMENTATION INSTRUCTIONS:
 *
 * Exports: SELECTORS (object), queryWithFallback(field)
 *
 * For each logical field, define an array of selectors in priority order:
 *   [1] ARIA/data-attributes (most stable, Salesforce unlikely to change)
 *   [2] Structural/hierarchical (nth child in known container)
 *   [3] SLDS semantic classes (may change with Salesforce releases)
 *   [4] Positional/index (most fragile — last resort)
 *
 * Each selector entry:
 *   { selector: string, type: 'aria'|'structural'|'slds'|'positional',
 *     confidence: number (0.0-1.0), lastVerified: 'YYYY-MM-DD' }
 *
 * SELECTORS object (define ALL fields below):
 *   accountName: [
 *     { selector: '[data-field="Name"] .slds-form-element__static', type: 'aria',
 *       confidence: 0.95, lastVerified: '2026-02-01' },
 *     { selector: '.slds-page-header__title .custom-truncate', type: 'slds',
 *       confidence: 0.85, lastVerified: '2026-02-01' },
 *     { selector: 'h1.slds-page-header__title', type: 'structural',
 *       confidence: 0.75, lastVerified: '2026-02-01' },
 *   ],
 *   industry: [ ... ],          // Account.Industry field
 *   employeeCount: [ ... ],     // Account.NumberOfEmployees
 *   annualRevenue: [ ... ],     // Account.AnnualRevenue
 *   accountOwner: [ ... ],      // Account.Owner.Name
 *   lastActivityDate: [ ... ],  // Last activity timestamp
 *   openOpportunities: [ ... ], // Open opp count/names
 *   notes: [ ... ],             // Notes field text
 *   activityTimeline: [ ... ],  // Activity timeline items
 *
 * queryWithFallback(field):
 *   selectors = SELECTORS[field] || [];
 *   for (const entry of selectors) {
 *     try {
 *       const el = document.querySelector(entry.selector);
 *       if (el && el.textContent.trim()) {
 *         return { value: el.textContent.trim(), confidence: entry.confidence,
 *                  selectorType: entry.type, selector: entry.selector };
 *       }
 *     } catch(e) { continue; }
 *   }
 *   return { value: null, confidence: 0, selectorType: null };
 */

export const SELECTORS = {
  // TODO: populate all field selectors per instructions above with real Salesforce selectors
  accountName: [
    { selector: '[data-field="Name"] .slds-form-element__static', type: 'aria', confidence: 0.95, lastVerified: '2026-02-01' },
    { selector: '.slds-page-header__title', type: 'slds', confidence: 0.85, lastVerified: '2026-02-01' },
  ],
  industry: [
    { selector: '[data-field="Industry"] .slds-form-element__static', type: 'aria', confidence: 0.95, lastVerified: '2026-02-01' },
  ],
  employeeCount: [
    { selector: '[data-field="NumberOfEmployees"] .slds-form-element__static', type: 'aria', confidence: 0.95, lastVerified: '2026-02-01' },
  ],
  lastActivityDate: [
    { selector: '[data-field="LastActivityDate"] .slds-form-element__static', type: 'aria', confidence: 0.90, lastVerified: '2026-02-01' },
  ],
  notes: [
    { selector: '.slds-rich-text-area__content', type: 'slds', confidence: 0.80, lastVerified: '2026-02-01' },
  ],
  activityTimeline: [
    { selector: '.slds-timeline__item .slds-media__body', type: 'slds', confidence: 0.75, lastVerified: '2026-02-01' },
  ],
};

export function queryWithFallback(field) {
  // TODO: implement 4-tier cascade per instructions above
  const selectors = SELECTORS[field] || [];
  for (const entry of selectors) {
    try {
      const el = document.querySelector(entry.selector);
      if (el && el.textContent.trim()) {
        return {
          value: el.textContent.trim(),
          confidence: entry.confidence,
          selectorType: entry.type,
          selector: entry.selector,
        };
      }
    } catch (e) {
      continue;
    }
  }
  return { value: null, confidence: 0, selectorType: null };
}
