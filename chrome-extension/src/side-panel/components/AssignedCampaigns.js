/** Assignment queue UI. */

import { EmailEditor } from './EmailEditor.js';
import { sendAssignment } from '../hub-client.js';

export class AssignedCampaigns {
  constructor(container) {
    this.container = container;
    this.assignments = [];
    this.render();
  }

  render() {
    this.container.innerHTML = `
      <div class="assigned-campaigns">
        <h3>Assigned Campaigns</h3>
        <div id="assignmentList" class="assignment-list">
          <p class="empty-state">No assignments yet.</p>
        </div>
      </div>
    `;
  }

  refresh(assignments) {
    this.assignments = assignments || [];
    const listEl = this.container.querySelector('#assignmentList');
    if (!listEl) return;

    if (this.assignments.length === 0) {
      listEl.innerHTML = '<p class="empty-state">No assignments yet. Assignments will appear here when a VP creates a campaign.</p>';
      return;
    }

    listEl.innerHTML = this.assignments.map((a) => `
      <div class="assignment-item" data-id="${a.id}" data-status="${a.status}">
        <div class="assignment-header">
          <span class="campaign-name">${a.campaign_name}</span>
          <span class="vp-name">from ${a.vp_name}</span>
        </div>
        <p class="rationale">${a.rationale_snippet}</p>
        <div class="assignment-meta">${a.account_count} accounts</div>
        <button class="review-btn" data-id="${a.id}">Review</button>
        <div class="review-pane" id="review-${a.id}" style="display:none; margin-top:8px;"></div>
      </div>
    `).join('');

    listEl.querySelectorAll('.review-btn').forEach((btn) => {
      btn.addEventListener('click', () => this.openReview(btn.dataset.id));
    });
  }

  openReview(id) {
    const pane = this.container.querySelector(`#review-${id}`);
    if (!pane) return;
    pane.style.display = 'block';
    pane.innerHTML = '<div class="email-editor-container"></div><button class="review-btn" id="send-btn">Send</button>';
    const editorContainer = pane.querySelector('.email-editor-container');
    const editor = new EmailEditor(editorContainer);
    editor.appendToken('Subject: Follow-up idea\n\nDraft loaded for review.');
    editor.markComplete();

    pane.querySelector('#send-btn')?.addEventListener('click', async () => {
      const text = editor.getText();
      await sendAssignment(id, text, text);
      pane.innerHTML += '<div style="margin-top:6px; color:#1B3A6B;">Sent.</div>';
    });
  }
}
