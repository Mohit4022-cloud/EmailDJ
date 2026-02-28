export const SELECTORS = {
  accountName: [
    { selector: '[data-field="Name"] .slds-form-element__static', type: 'aria', confidence: 0.95, lastVerified: '2026-02-01' },
    { selector: '.slds-page-header__title .custom-truncate', type: 'slds', confidence: 0.85, lastVerified: '2026-02-01' },
    { selector: 'h1.slds-page-header__title', type: 'structural', confidence: 0.75, lastVerified: '2026-02-01' },
  ],
  industry: [
    { selector: '[data-field="Industry"] .slds-form-element__static', type: 'aria', confidence: 0.95, lastVerified: '2026-02-01' },
    { selector: '.industry .slds-form-element__static', type: 'slds', confidence: 0.7, lastVerified: '2026-02-01' },
  ],
  employeeCount: [
    { selector: '[data-field="NumberOfEmployees"] .slds-form-element__static', type: 'aria', confidence: 0.95, lastVerified: '2026-02-01' },
  ],
  annualRevenue: [
    { selector: '[data-field="AnnualRevenue"] .slds-form-element__static', type: 'aria', confidence: 0.95, lastVerified: '2026-02-01' },
  ],
  accountOwner: [
    { selector: '[data-field="OwnerId"] .slds-form-element__static', type: 'aria', confidence: 0.9, lastVerified: '2026-02-01' },
  ],
  lastActivityDate: [
    { selector: '[data-field="LastActivityDate"] .slds-form-element__static', type: 'aria', confidence: 0.9, lastVerified: '2026-02-01' },
  ],
  openOpportunities: [
    { selector: '.opportunity .slds-card__header-title', type: 'structural', confidence: 0.6, lastVerified: '2026-02-01' },
  ],
  notes: [
    { selector: '.slds-rich-text-area__content', type: 'slds', confidence: 0.8, lastVerified: '2026-02-01' },
    { selector: '[data-component-id="forceRelatedListSingleContainer"] .slds-truncate', type: 'structural', confidence: 0.5, lastVerified: '2026-02-01' },
  ],
  activityTimeline: [
    { selector: '.slds-timeline__item .slds-media__body', type: 'slds', confidence: 0.75, lastVerified: '2026-02-01' },
  ],
};

function textFor(element) {
  return (element?.textContent || '').trim();
}

export function queryWithFallback(field) {
  const selectors = SELECTORS[field] || [];
  for (const entry of selectors) {
    try {
      const el = document.querySelector(entry.selector);
      const text = textFor(el);
      if (el && text) {
        return {
          value: text,
          confidence: entry.confidence,
          selectorType: entry.type,
          selector: entry.selector,
        };
      }
    } catch {
      // continue
    }
  }
  return { value: null, confidence: 0, selectorType: null };
}
