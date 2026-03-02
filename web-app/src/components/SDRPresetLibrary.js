function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function toNumber(value, fallback = 50) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return fallback;
  return clamp(Math.round(numeric), 0, 100);
}

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function sliderRows(preset) {
  const sliders = preset?.sliders || {};
  const formal = toNumber(sliders.formal);
  const outcome = toNumber(sliders.outcome);
  const long = toNumber(sliders.long);
  const diplomatic = toNumber(sliders.diplomatic);
  return [
    {
      key: 'formal',
      label: 'Formal <-> Casual',
      left: 'Formal',
      right: 'Casual',
      leftValue: formal,
      rightValue: 100 - formal,
    },
    {
      key: 'outcome',
      label: 'Problem <-> Outcome',
      left: 'Problem',
      right: 'Outcome',
      leftValue: 100 - outcome,
      rightValue: outcome,
    },
    {
      key: 'long',
      label: 'Short <-> Long',
      left: 'Short',
      right: 'Long',
      leftValue: 100 - long,
      rightValue: long,
    },
    {
      key: 'diplomatic',
      label: 'Bold <-> Diplomatic',
      left: 'Bold',
      right: 'Diplomatic',
      leftValue: 100 - diplomatic,
      rightValue: diplomatic,
    },
  ];
}

export function presetToSliderState(preset) {
  const sliders = preset?.sliders || {};
  const formal = toNumber(sliders.formal);
  return {
    formality: 100 - formal,
    orientation: toNumber(sliders.outcome),
    length: toNumber(sliders.long),
    assertiveness: toNumber(sliders.diplomatic),
  };
}

export class SDRPresetLibrary {
  constructor(container, options = {}) {
    this.container = container;
    this.presets = Array.isArray(options.presets) ? options.presets : [];
    this.onSelectPreset =
      typeof options.onSelectPreset === 'function' ? options.onSelectPreset : () => {};
    this.previewPresetId = this.presets[0]?.id ?? null;
    this.isOpen = false;

    this.onKeydown = (event) => {
      if (event.key === 'Escape' && this.isOpen) this.close();
    };

    this.render();
  }

  render() {
    this.container.innerHTML = `
      <button type="button" id="browsePresetsBtn" class="btn-secondary preset-trigger" aria-haspopup="dialog" aria-expanded="false">
        <span class="preset-trigger-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" focusable="false">
            <path d="M12 2l1.9 5.1L19 9l-5.1 1.9L12 16l-1.9-5.1L5 9l5.1-1.9L12 2zM19 14l.9 2.6L22.5 18l-2.6.9L19 21.5l-.9-2.6-2.6-.9 2.6-1.4L19 14zM6 14l.9 2.4 2.4.9-2.4.9L6 20.5l-.9-2.3-2.4-.9 2.4-.9L6 14z"></path>
          </svg>
        </span>
        <span>Browse Presets</span>
      </button>
      <div id="presetBackdrop" class="preset-modal-backdrop" hidden>
        <div class="preset-modal" role="dialog" aria-modal="true" aria-labelledby="presetLibraryTitle">
          <div class="preset-modal-head">
            <div>
              <h2 id="presetLibraryTitle">SDR Preset Library</h2>
              <p>Hover to preview. Click to apply.</p>
            </div>
            <button type="button" id="closePresetModalBtn" class="preset-close-btn" aria-label="Close preset library">
              <span aria-hidden="true">&times;</span>
            </button>
          </div>
          <div class="preset-modal-layout">
            <aside class="preset-left-pane">
              <div id="presetList" class="preset-list"></div>
            </aside>
            <section id="presetRightPane" class="preset-right-pane">
              <div id="presetMetaBlock" class="preset-meta-block"></div>
              <div id="presetEmailBlock" class="preset-email-block"></div>
            </section>
          </div>
        </div>
      </div>
    `;

    this.triggerBtn = this.container.querySelector('#browsePresetsBtn');
    this.backdrop = this.container.querySelector('#presetBackdrop');
    this.closeBtn = this.container.querySelector('#closePresetModalBtn');
    this.listEl = this.container.querySelector('#presetList');
    this.metaBlock = this.container.querySelector('#presetMetaBlock');
    this.emailBlock = this.container.querySelector('#presetEmailBlock');
    this.rightPane = this.container.querySelector('#presetRightPane');

    this.triggerBtn?.addEventListener('click', () => this.open());
    this.closeBtn?.addEventListener('click', () => this.close());
    this.backdrop?.addEventListener('click', (event) => {
      if (event.target === this.backdrop) this.close();
    });
    window.addEventListener('keydown', this.onKeydown);

    this.renderPresetList();
    this.renderPreview(this.getPreviewPreset());
  }

  open() {
    if (!this.backdrop || this.isOpen) return;
    this.isOpen = true;
    this.backdrop.hidden = false;
    this.triggerBtn?.setAttribute('aria-expanded', 'true');
    document.body.classList.add('preset-modal-open');
    const activeId = this.previewPresetId ?? this.presets[0]?.id;
    if (activeId != null) {
      const button = this.listEl?.querySelector(`[data-preset-id="${activeId}"]`);
      button?.focus();
    }
  }

  close() {
    if (!this.backdrop || !this.isOpen) return;
    this.isOpen = false;
    this.backdrop.hidden = true;
    this.triggerBtn?.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('preset-modal-open');
    this.triggerBtn?.focus();
  }

  getPresetById(id) {
    return this.presets.find((preset) => String(preset.id) === String(id)) || null;
  }

  getPreviewPreset() {
    return this.getPresetById(this.previewPresetId) || this.presets[0] || null;
  }

  setPreviewPreset(id) {
    const preset = this.getPresetById(id);
    if (!preset || this.previewPresetId === preset.id) return;
    this.previewPresetId = preset.id;
    this.renderPresetList();
    this.renderPreview(preset);
  }

  renderPresetList() {
    if (!this.listEl) return;
    this.listEl.innerHTML = this.presets
      .map((preset) => {
        const isActive = preset.id === this.previewPresetId;
        return `
          <button type="button" class="preset-item ${isActive ? 'is-active' : ''}" data-preset-id="${preset.id}">
            <span class="preset-item-title">${escapeHtml(preset.name)}</span>
            <span class="preset-item-subtitle">${escapeHtml(preset.frequency)}</span>
          </button>
        `;
      })
      .join('');

    this.listEl.querySelectorAll('.preset-item').forEach((item) => {
      const id = item.getAttribute('data-preset-id');
      item.addEventListener('mouseenter', () => this.setPreviewPreset(id));
      item.addEventListener('focus', () => this.setPreviewPreset(id));
      item.addEventListener('click', () => this.selectPreset(id));
    });
  }

  renderPreview(preset) {
    if (!preset || !this.metaBlock || !this.emailBlock) return;
    const rows = sliderRows(preset);
    this.rightPane?.classList.remove('preview-refresh');
    void this.rightPane?.offsetHeight;
    this.rightPane?.classList.add('preview-refresh');

    this.metaBlock.innerHTML = `
      <div class="preset-meta-grid">
        <article class="preset-card">
          <h3>EQ Vibe</h3>
          <p>${escapeHtml(preset.eqVibe)}</p>
        </article>
        <article class="preset-card">
          <h3>The Vibe</h3>
          <p>${escapeHtml(preset.vibe)}</p>
        </article>
      </div>
      <article class="preset-card preset-sliders-card">
        <h3>Slider Settings</h3>
        <div class="preset-slider-rows">
          ${rows
            .map(
              (row) => `
              <div class="preset-slider-row">
                <div class="preset-slider-head">
                  <span>${escapeHtml(row.label)}</span>
                  <span>${escapeHtml(row.right)} ${row.rightValue}%</span>
                </div>
                <div class="preset-progress-track">
                  <div class="preset-progress-fill" style="width:${row.rightValue}%"></div>
                </div>
                <div class="preset-slider-foot">
                  <span>${escapeHtml(row.left)} ${row.leftValue}%</span>
                  <span>${escapeHtml(row.right)} ${row.rightValue}%</span>
                </div>
              </div>
            `
            )
            .join('')}
        </div>
      </article>
      <article class="preset-card">
        <h3>Why it works</h3>
        <p>${escapeHtml(preset.whyItWorks)}</p>
      </article>
    `;

    const subject = escapeHtml(preset.sampleEmail?.subject || '');
    const body = escapeHtml(preset.sampleEmail?.body || '').replaceAll('\n', '<br>');
    this.emailBlock.innerHTML = `
      <h3>Email Preview</h3>
      <div class="preset-email-card">
        <div class="preset-email-label">Subject</div>
        <div class="preset-email-subject">${subject}</div>
        <div class="preset-email-divider"></div>
        <div class="preset-email-body">${body}</div>
      </div>
    `;
  }

  selectPreset(id) {
    const preset = this.getPresetById(id);
    if (!preset) return;
    this.onSelectPreset(preset);
    this.close();
  }

  destroy() {
    window.removeEventListener('keydown', this.onKeydown);
  }
}

