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
      <div id="emailBody" class="editor" contenteditable="true" spellcheck="false"></div>
      <div class="actions" style="margin-top:10px;">
        <button id="copyBtn" class="btn-secondary" disabled>Copy</button>
      </div>
      <details id="sourcesPanel" style="margin-top:8px;" hidden>
        <summary>Sources</summary>
        <div id="sourcesList" class="meta"></div>
      </details>
      <div class="meta" id="draftMeta">Draft not generated yet.</div>
    `;
    this.editorEl = this.container.querySelector('#emailBody');
    this.copyBtn = this.container.querySelector('#copyBtn');
    this.sourcesPanel = this.container.querySelector('#sourcesPanel');
    this.sourcesList = this.container.querySelector('#sourcesList');
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
    if (!this.sourcesPanel || !this.sourcesList) return;
    if (this.sources.length === 0) {
      this.sourcesPanel.hidden = true;
      this.sourcesList.innerHTML = '';
      return;
    }
    this.sourcesPanel.hidden = false;
    this.sourcesList.innerHTML = this.sources
      .map((item) => {
        const url = String(item?.url || '').trim();
        const published = String(item?.published_at || 'Unknown').trim();
        const retrieved = String(item?.retrieved_at || '').trim();
        const link = url ? `<a href="${url}" target="_blank" rel="noreferrer">${url}</a>` : 'Unknown';
        return `<div>${link}<br/><small>published: ${published} · retrieved: ${retrieved || 'Unknown'}</small></div>`;
      })
      .join('<hr/>');
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
