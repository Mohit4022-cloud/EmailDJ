export class EmailEditor {
  constructor(container) {
    this.container = container;
    this.originalDraft = '';
    this.editorEl = null;
    this.render();
  }

  render() {
    this.container.innerHTML = `
      <div class="editor-frame" id="editorFrame" data-state="empty">
        <div class="editor-toolbar">
          <div>
            <div class="editor-kicker">Draft canvas</div>
            <div class="editor-title" id="draftCanvasTitle">Ready for first draft</div>
          </div>
          <button id="copyBtn" class="btn-secondary editor-copy-btn" disabled>Copy</button>
        </div>
        <div
          id="emailBody"
          class="editor"
          contenteditable="true"
          spellcheck="false"
          data-placeholder="Draft will stream here. Generate once, then use sliders to remix."
        ></div>
        <div class="meta" id="draftMeta">Draft not generated yet.</div>
      </div>
    `;
    this.frameEl = this.container.querySelector('#editorFrame');
    this.editorEl = this.container.querySelector('#emailBody');
    this.copyBtn = this.container.querySelector('#copyBtn');
    this.titleEl = this.container.querySelector('#draftCanvasTitle');
    this.metaEl = this.container.querySelector('#draftMeta');
    this.copyBtn?.addEventListener('click', () => this.copy());
  }

  reset() {
    if (!this.editorEl) return;
    this.editorEl.textContent = '';
    this.originalDraft = '';
    if (this.frameEl) this.frameEl.dataset.state = 'generating';
    if (this.titleEl) this.titleEl.textContent = 'Streaming draft';
    this.editorEl.dataset.placeholder = 'Draft is streaming into this canvas...';
    if (this.copyBtn) this.copyBtn.disabled = true;
    if (this.metaEl) this.metaEl.textContent = 'Generating draft...';
  }

  appendToken(token) {
    if (!this.editorEl) return;
    this.editorEl.appendChild(document.createTextNode(token));
    this.editorEl.scrollTop = this.editorEl.scrollHeight;
  }

  setContent(text) {
    if (!this.editorEl) return;
    this.editorEl.textContent = text;
    this.originalDraft = text;
    if (this.frameEl) this.frameEl.dataset.state = text ? 'ready' : 'empty';
    if (this.titleEl) this.titleEl.textContent = text ? 'Draft ready' : 'Ready for first draft';
    this.editorEl.dataset.placeholder = 'Draft will stream here. Generate once, then use sliders to remix.';
  }

  setText(text) {
    this.setContent(text);
  }

  markComplete(latencyMs = null) {
    this.originalDraft = this.getText();
    if (this.frameEl) this.frameEl.dataset.state = this.originalDraft ? 'ready' : 'empty';
    if (this.titleEl) this.titleEl.textContent = this.originalDraft ? 'Draft ready' : 'Ready for first draft';
    if (this.editorEl) {
      this.editorEl.dataset.placeholder = 'Draft will stream here. Generate once, then use sliders to remix.';
    }
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
