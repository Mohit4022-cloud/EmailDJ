export class EmailEditor {
  constructor(container) {
    this.container = container;
    this.originalDraft = '';
    this.editorEl = null;
    this.render();
  }

  render() {
    this.container.innerHTML = `
      <div id="emailBody" class="editor" contenteditable="true" spellcheck="false"></div>
      <div class="actions" style="margin-top:10px;">
        <button id="copyBtn" class="btn-secondary" disabled>Copy</button>
      </div>
      <div class="meta" id="draftMeta">Draft not generated yet.</div>
    `;
    this.editorEl = this.container.querySelector('#emailBody');
    this.copyBtn = this.container.querySelector('#copyBtn');
    this.metaEl = this.container.querySelector('#draftMeta');
    this.copyBtn?.addEventListener('click', () => this.copy());
  }

  reset() {
    if (!this.editorEl) return;
    this.editorEl.textContent = '';
    this.originalDraft = '';
    if (this.copyBtn) this.copyBtn.disabled = true;
    if (this.metaEl) this.metaEl.textContent = 'Generating draft...';
  }

  appendToken(token) {
    if (!this.editorEl) return;
    this.editorEl.appendChild(document.createTextNode(token));
    this.editorEl.scrollTop = this.editorEl.scrollHeight;
  }

  setText(text) {
    if (!this.editorEl) return;
    this.editorEl.textContent = text;
  }

  markComplete(latencyMs = null) {
    this.originalDraft = this.getText();
    if (this.copyBtn) this.copyBtn.disabled = !this.originalDraft;
    if (this.metaEl) {
      this.metaEl.textContent = latencyMs == null ? 'Draft complete.' : `Draft complete in ${latencyMs}ms.`;
    }
  }

  getText() {
    return this.editorEl?.innerText ?? '';
  }

  async copy() {
    const text = this.getText();
    if (!text) return;
    await navigator.clipboard.writeText(text);
  }
}
