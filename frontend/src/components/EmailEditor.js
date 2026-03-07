export class EmailEditor {
  constructor(container) {
    this.container = container;
    this.originalDraft = '';
    this.editorEl = null;
    this.sources = [];
    this.render();
  }

  render() {
    this.container.innerHTML = `
      <article class="draft-card">
        <div class="draft-card-head">
          <div>
            <p class="eyebrow">Draft Canvas</p>
            <h3>Primary email draft</h3>
          </div>
          <button id="copyBtn" class="btn-secondary" disabled>Copy Draft</button>
        </div>
        <p class="draft-card-note">Generate once, then remix expression without changing the underlying brief, proof, or CTA lock.</p>
        <div
          id="emailBody"
          class="editor"
          contenteditable="true"
          spellcheck="false"
          data-placeholder="Generate a draft to start editing. This workspace stays anchored to the same messaging brief and deterministic QA checks."
        ></div>
        <div class="draft-card-foot">
          <div class="meta" id="draftMeta">Draft not generated yet.</div>
          <div class="draft-copy-note">Save Remix copies the current draft and feedback snapshot.</div>
        </div>
      </article>
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
    this.setSources([]);
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
  }

  setText(text) {
    this.setContent(text);
  }

  setSources(sources = []) {
    this.sources = Array.isArray(sources) ? sources : [];
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
