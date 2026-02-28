/** Streaming email display + edit capture component. */

export class EmailEditor {
  constructor(container) {
    this.container = container;
    this.originalDraft = '';
    this.editorEl = null;
    this.render();
  }

  render() {
    this.container.innerHTML = `
      <div class="email-editor-wrapper">
        <div id="emailBody" contenteditable="true" class="email-body"
             style="min-height: 200px; padding: 12px; border: 1px solid #ccc;
                    font-family: sans-serif; white-space: pre-wrap;"></div>
        <div class="email-actions" id="emailActions" style="display:none;">
          <button id="copyBtn">Copy</button>
          <button id="gmailBtn">Send via Gmail</button>
          <button id="outreachBtn" title="Coming in Phase 2" disabled>Send via Outreach</button>
        </div>
      </div>
    `;
    this.editorEl = this.container.querySelector('#emailBody');
    this.container.querySelector('#copyBtn')?.addEventListener('click', () => this.onCopyClick());
    this.container.querySelector('#gmailBtn')?.addEventListener('click', () => this.onSendGmailClick());
    this.container.querySelector('#outreachBtn')?.addEventListener('click', () => this.onSendOutreachClick());
    this.editorEl?.addEventListener('blur', () => this.onEditorBlur());
  }

  appendToken(token) {
    if (!this.editorEl) return;
    const textNode = document.createTextNode(token);
    this.editorEl.appendChild(textNode);
    this.editorEl.scrollTop = this.editorEl.scrollHeight;
  }

  markComplete() {
    this.originalDraft = this.editorEl?.innerText ?? '';
    const actionsEl = this.container.querySelector('#emailActions');
    if (actionsEl) actionsEl.style.display = 'flex';
  }

  onCopyClick() {
    if (!this.editorEl) return;
    navigator.clipboard.writeText(this.editorEl.innerText).catch(() => {});
  }

  onSendGmailClick() {
    if (!this.editorEl) return;
    const text = this.editorEl.innerText || '';
    const firstLine = text.split('\n')[0] || 'Quick idea';
    const subject = encodeURIComponent(firstLine.replace(/^Subject:\s*/i, ''));
    const body = encodeURIComponent(text);
    window.open(`mailto:?subject=${subject}&body=${body}`);
  }

  onSendOutreachClick() {
    console.log('[EmailDJ] Outreach integration coming in Phase 2');
  }

  onEditorBlur() {
    const edited = this.editorEl?.innerText ?? '';
    if (edited !== this.originalDraft) {
      import('../hub-client.js')
        .then(({ captureEdit }) => captureEdit(this.originalDraft, edited))
        .catch(console.error);
    }
  }

  getText() {
    return this.editorEl?.innerText ?? '';
  }
}
