/**
 * ContextSummary — Displays extracted CRM context for current account.
 *
 * IMPLEMENTATION INSTRUCTIONS:
 * Shows what EmailDJ knows about the current account before generation.
 *
 * Constructor(container: HTMLElement):
 *   Renders a compact summary of the current AccountContext.
 *
 * update(payload: PayloadObject, vaultContext: AccountContext | null):
 *   Render the account data:
 *   - Account name + industry + employee count (from payload)
 *   - Context Vault freshness badge:
 *     fresh (green) → "Context fresh"
 *     aging (yellow) → "Context aging (last updated X days ago)"
 *     stale (red) → "Context stale — research recommended"
 *     no vault → "No prior context — cold account"
 *   - Last activity date
 *   - Key signals (decision makers, budget hints, timing)
 *   - Quality score (1-100) as a progress bar
 *
 * Clicking "Research Company" (shown for stale/cold accounts):
 *   - POST to HUB_URL/research with { account_id, domain, company_name }
 *   - Show "Researching {Company}..." with animated dots
 *   - On completion: update the context display
 *
 * Design: compact, scannable. SDR should be able to read it in 5 seconds.
 * Use color coding: green/yellow/red for freshness.
 */

export class ContextSummary {
  constructor(container) {
    this.container = container;
    // TODO: implement per instructions above
  }

  update(payload, vaultContext = null) {
    // TODO: render account context summary per instructions above
    const freshness = vaultContext?.freshness ?? 'none';
    const freshnessLabel = {
      fresh: '🟢 Context fresh',
      aging: '🟡 Context aging',
      stale: '🔴 Context stale — research recommended',
      none: '⚪ No prior context — cold account',
    }[freshness] ?? '⚪ No prior context';

    this.container.innerHTML = `
      <div class="context-summary-content">
        <div class="account-name">${payload?.accountName ?? 'Unknown Account'}</div>
        <div class="account-meta">
          ${payload?.industry ? `<span>${payload.industry}</span>` : ''}
          ${payload?.employeeCount ? `<span>${payload.employeeCount.toLocaleString()} employees</span>` : ''}
        </div>
        <div class="freshness-badge">${freshnessLabel}</div>
        ${(freshness === 'stale' || freshness === 'none') ? '<button id="researchBtn">Research Company</button>' : ''}
      </div>
    `;
  }
}
