/** Context summary block. */

export class ContextSummary {
  constructor(container) {
    this.container = container;
  }

  update(payload, vaultContext = null) {
    const freshness = vaultContext?.freshness ?? 'none';
    const freshnessLabel = {
      fresh: 'Context fresh',
      aging: 'Context aging',
      stale: 'Context stale - research recommended',
      none: 'No prior context - cold account',
    }[freshness] ?? 'No prior context';

    this.container.innerHTML = `
      <div class="context-summary-content">
        <div class="account-name">${payload?.accountName ?? 'Unknown Account'}</div>
        <div class="account-meta">
          ${payload?.industry ? `<span>${payload.industry}</span>` : ''}
          ${payload?.employeeCount ? `<span>${payload.employeeCount.toLocaleString()} employees</span>` : ''}
        </div>
        <div class="freshness-badge">${freshnessLabel}</div>
      </div>
    `;
  }
}
