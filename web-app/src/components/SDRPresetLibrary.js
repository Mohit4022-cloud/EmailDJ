import {
  buildPresetPreviewBatchPayload,
  buildPreviewCacheKey,
  buildPreviewContextHash,
  buildVibeMetadata,
  buildWhyItWorksBullets,
  normalizePreviewContext,
  normalizeSliderState,
  resolveEffectiveSliderState,
  sliderRowsFromState,
} from './presetPreviewUtils.js';

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

function statusLabel(status) {
  if (status === 'loading') return 'Generating...';
  if (status === 'ready') return 'Ready';
  if (status === 'error') return 'Failed';
  return '';
}

function previewFallbackSubject(context) {
  const company = context?.prospect?.company || context?.company_context?.company_name || 'your team';
  return `Quick idea for ${company}`;
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

export function buildPresetMetaHtml(preview) {
  const rows = sliderRowsFromState(preview?.sliderSummary || normalizeSliderState({}));
  const tags = Array.isArray(preview?.vibeTags) ? preview.vibeTags.slice(0, 4) : [];
  const whyItems = Array.isArray(preview?.whyItWorks) ? preview.whyItWorks.slice(0, 3) : [];

  return `
    <article class="preset-card">
      <h3>The Vibe</h3>
      <p>${escapeHtml(preview?.vibeLabel || '')}</p>
      ${tags.length ? `<div class="preset-vibe-tags">${tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join('')}</div>` : ''}
    </article>
    <article class="preset-card">
      <h3>Why it works</h3>
      <ul class="preset-why-list">
        ${whyItems.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}
      </ul>
    </article>
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
  `;
}

function buildEmailSkeletonHtml() {
  return `
    <div class="preset-email-card">
      <div class="preset-email-label">Subject</div>
      <div class="preset-email-skeleton-line w-70"></div>
      <div class="preset-email-divider"></div>
      <div class="preset-email-skeleton-line w-95"></div>
      <div class="preset-email-skeleton-line w-88"></div>
      <div class="preset-email-skeleton-line w-92"></div>
      <div class="preset-email-skeleton-line w-70"></div>
    </div>
  `;
}

function buildEmailErrorHtml(presetId, message) {
  return `
    <div class="preset-email-card preset-email-error">
      <div class="preset-email-error-title">Preview unavailable</div>
      <div class="preset-email-error-message">${escapeHtml(message || 'Generation failed for this preset.')}</div>
      <button type="button" class="btn-secondary preset-retry-btn" data-retry-preset-id="${escapeHtml(presetId)}">Retry</button>
    </div>
  `;
}

function normalizeBodyText(value) {
  return String(value || '')
    .replaceAll('\r\n', '\n')
    .replaceAll('\\r\\n', '\n')
    .replaceAll('\\n', '\n');
}

function buildReadyEmailHtml(preview) {
  const subject = escapeHtml(preview?.subject || '');
  const body = escapeHtml(normalizeBodyText(preview?.body || '')).replaceAll('\n', '<br>');
  return `
    <div class="preset-email-card">
      <div class="preset-email-label">Subject</div>
      <div class="preset-email-subject">${subject}</div>
      <div class="preset-email-divider"></div>
      <div class="preset-email-body">${body}</div>
    </div>
  `;
}

export class SDRPresetLibrary {
  constructor(container, options = {}) {
    this.container = container;
    this.presets = Array.isArray(options.presets) ? options.presets : [];
    this.onSelectPreset =
      typeof options.onSelectPreset === 'function' ? options.onSelectPreset : () => {};
    this.getPreviewContext =
      typeof options.getPreviewContext === 'function' ? options.getPreviewContext : () => ({});
    this.generatePreviewBatch =
      typeof options.generatePreviewBatch === 'function' ? options.generatePreviewBatch : null;

    this.previewPresetId = this.presets[0]?.id ?? null;
    this.isOpen = false;
    this.activeContextHash = '';
    this.previewCache = new Map();
    this.previewEntries = new Map();
    this.inflightBatches = new Map();
    this.previewFetchDebounceMs =
      Number.isFinite(Number(options.previewFetchDebounceMs)) && Number(options.previewFetchDebounceMs) >= 0
        ? Number(options.previewFetchDebounceMs)
        : 120;
    this.previewFetchTimer = null;
    this.previewFetchToken = 0;

    this.onKeydown = (event) => {
      if (event.key === 'Escape' && this.isOpen) this.close();
    };

    if (options.autoRender !== false) this.render();
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
    `;

    this.modalHost = document.createElement('div');
    this.modalHost.innerHTML = `
      <div id="presetBackdrop" class="preset-modal-backdrop" hidden>
        <div class="preset-modal" role="dialog" aria-modal="true" aria-labelledby="presetLibraryTitle">
          <div class="preset-modal-head">
            <div>
              <h2 id="presetLibraryTitle">SDR Preset Library</h2>
              <p>Live AI preview for every preset using your current context.</p>
            </div>
            <button type="button" id="closePresetModalBtn" class="preset-close-btn" aria-label="Close preset library">
              <span aria-hidden="true">&times;</span>
            </button>
          </div>
          <div class="preset-modal-layout">
            <aside class="preset-left-pane">
              <div id="presetList" class="preset-list"></div>
            </aside>
            <section class="preset-center-pane">
              <div id="presetEmailBlock" class="preset-email-block"></div>
            </section>
            <aside id="presetRightPane" class="preset-right-pane">
              <div id="presetMetaBlock" class="preset-meta-block"></div>
            </aside>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(this.modalHost);

    this.triggerBtn = this.container.querySelector('#browsePresetsBtn');
    this.backdrop = this.modalHost.querySelector('#presetBackdrop');
    this.closeBtn = this.modalHost.querySelector('#closePresetModalBtn');
    this.listEl = this.modalHost.querySelector('#presetList');
    this.metaBlock = this.modalHost.querySelector('#presetMetaBlock');
    this.emailBlock = this.modalHost.querySelector('#presetEmailBlock');
    this.rightPane = this.modalHost.querySelector('#presetRightPane');

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
    if (this.isOpen) return;
    if (!this.backdrop) {
      this.isOpen = true;
      this.refreshPreviews();
      return;
    }
    this.isOpen = true;
    this.backdrop.hidden = false;
    this.triggerBtn?.setAttribute('aria-expanded', 'true');
    document.body.classList.add('preset-modal-open');
    this.refreshPreviews();

    const activeId = this.previewPresetId ?? this.presets[0]?.id;
    if (activeId != null) {
      const button = this.listEl?.querySelector(`[data-preset-id="${activeId}"]`);
      button?.focus();
    }
  }

  close() {
    if (!this.isOpen) return;
    if (!this.backdrop) {
      this.isOpen = false;
      return;
    }
    this.isOpen = false;
    this.backdrop.hidden = true;
    this.triggerBtn?.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('preset-modal-open');
    this.triggerBtn?.focus();
  }

  normalizeContext() {
    return normalizePreviewContext(this.getPreviewContext() || {});
  }

  getPresetById(id) {
    return this.presets.find((preset) => String(preset.id) === String(id)) || null;
  }

  getPreviewPreset() {
    return this.getPresetById(this.previewPresetId) || this.presets[0] || null;
  }

  getPreviewEntry(presetId) {
    return this.previewEntries.get(String(presetId)) || null;
  }

  buildBasePreviewEntry(preset, context) {
    const sliderSummary = resolveEffectiveSliderState(context.global_slider_state, preset);
    const vibe = buildVibeMetadata(preset, sliderSummary);
    return {
      status: 'idle',
      subject: '',
      body: '',
      whyItWorks: buildWhyItWorksBullets(preset),
      vibeLabel: vibe.label,
      vibeTags: vibe.tags,
      sliderSummary,
      errorMessage: '',
    };
  }

  refreshPreviews() {
    const context = this.normalizeContext();
    const contextHash = buildPreviewContextHash(context);
    this.activeContextHash = contextHash;

    const missing = [];
    for (const preset of this.presets) {
      const presetId = String(preset.id);
      const key = buildPreviewCacheKey(contextHash, preset.id);
      const cached = this.previewCache.get(key);
      const base = this.buildBasePreviewEntry(preset, context);

      if (cached) {
        this.previewEntries.set(presetId, { ...base, ...cached, status: 'ready', errorMessage: '' });
        continue;
      }
      this.previewEntries.set(presetId, { ...base, status: 'loading' });
      missing.push(preset);
    }

    this.renderPresetList();
    this.renderPreview(this.getPreviewPreset());
    if (missing.length > 0) {
      this.scheduleMissingPreviews(missing, context, contextHash);
    }
  }

  scheduleMissingPreviews(presets, context, contextHash) {
    if (!Array.isArray(presets) || presets.length === 0) return;
    const token = ++this.previewFetchToken;
    if (this.previewFetchTimer) {
      clearTimeout(this.previewFetchTimer);
      this.previewFetchTimer = null;
    }
    const run = () => {
      this.previewFetchTimer = null;
      if (token !== this.previewFetchToken) return;
      void this.generateMissingPreviews(presets, context, contextHash);
    };
    if (this.previewFetchDebounceMs <= 0) {
      run();
      return;
    }
    this.previewFetchTimer = setTimeout(run, this.previewFetchDebounceMs);
  }

  async generateMissingPreviews(presets, context, contextHash) {
    if (!this.generatePreviewBatch) {
      this.markPreviewBatchUnavailable(presets, context, 'Preview batch pipeline is disabled.');
      return;
    }
    let result;
    try {
      result = await this.generateMissingPreviewsBatch(presets, context, contextHash);
    } catch (error) {
      result = { ok: false, error: String(error?.message || error || 'Preview batch generation failed.') };
    }
    if (!result.ok) {
      this.markPreviewBatchUnavailable(presets, context, result.error || 'Preview batch generation failed.');
    }
  }

  markPreviewBatchUnavailable(presets, context, message) {
    for (const preset of presets) {
      const existing = this.getPreviewEntry(preset.id) || this.buildBasePreviewEntry(preset, context);
      this.previewEntries.set(String(preset.id), {
        ...existing,
        status: 'error',
        errorMessage: String(message || 'Preview batch pipeline unavailable.'),
      });
    }
    this.renderPresetList();
    this.renderPreview(this.getPreviewPreset());
  }

  async generateMissingPreviewsBatch(presets, context, contextHash) {
    if (!this.generatePreviewBatch) return { ok: false, error: 'Preview batch pipeline is disabled.' };
    const batchKey = `${contextHash}:batch`;
    let promise = this.inflightBatches.get(batchKey);

    if (!promise) {
      promise = this.generatePreviewBatch(buildPresetPreviewBatchPayload(context, presets));
      this.inflightBatches.set(batchKey, promise);
    }

    try {
      const response = await promise;
      if (contextHash !== this.activeContextHash) return { ok: true };

      const responsePreviews = Array.isArray(response?.previews) ? response.previews : [];
      const byPresetId = new Map(
        responsePreviews
          .map((item) => [String(item?.preset_id || ''), item])
          .filter((entry) => entry[0])
      );

      const unresolved = [];
      for (const preset of presets) {
        const source = byPresetId.get(String(preset.id));
        const base = this.buildBasePreviewEntry(preset, context);
        if (!source) {
          unresolved.push(preset.name);
          this.previewEntries.set(String(preset.id), {
            ...base,
            status: 'error',
            errorMessage: 'Preset missing in batch response.',
          });
          continue;
        }

        const preview = {
          ...base,
          subject: String(source.subject || '').trim() || previewFallbackSubject(context),
          body: String(source.body || '').trim(),
          vibeLabel: String(source.vibeLabel || base.vibeLabel || ''),
          vibeTags:
            Array.isArray(source.vibeTags) && source.vibeTags.length > 0
              ? source.vibeTags.map((tag) => String(tag)).slice(0, 4)
              : base.vibeTags,
          whyItWorks:
            Array.isArray(source.whyItWorks) && source.whyItWorks.length > 0
              ? source.whyItWorks.map((item) => String(item)).slice(0, 3)
              : base.whyItWorks,
        };
        const key = buildPreviewCacheKey(contextHash, preset.id);
        this.previewCache.set(key, preview);
        this.previewEntries.set(String(preset.id), { ...preview, status: 'ready', errorMessage: '' });
      }

      this.renderPresetList();
      this.renderPreview(this.getPreviewPreset());
      if (unresolved.length > 0) {
        return { ok: false, error: `Missing batch previews for ${unresolved.join(', ')}.` };
      }
      return { ok: true };
    } catch (error) {
      return { ok: false, error: String(error?.message || error || 'Preview batch generation failed.') };
    } finally {
      this.inflightBatches.delete(batchKey);
    }
  }

  setPreviewPreset(id) {
    const preset = this.getPresetById(id);
    if (!preset || this.previewPresetId === preset.id) return;
    this.previewPresetId = preset.id;
    this.renderPresetList();
    this.renderPreview(preset);

    if (!this.isOpen) return;
    const context = this.normalizeContext();
    const contextHash = buildPreviewContextHash(context);
    this.activeContextHash = contextHash;
    const key = buildPreviewCacheKey(contextHash, preset.id);
    const entry = this.getPreviewEntry(preset.id);
    if (this.previewCache.has(key) || entry?.status === 'ready' || entry?.status === 'loading') return;
    if (this.previewFetchTimer || this.inflightBatches.has(`${contextHash}:batch`)) return;
    const base = this.buildBasePreviewEntry(preset, context);
    this.previewEntries.set(String(preset.id), { ...base, status: 'loading', errorMessage: '' });
    this.renderPresetList();
    this.renderPreview(preset);
    this.scheduleMissingPreviews([preset], context, contextHash);
  }

  renderPresetList() {
    if (!this.listEl) return;
    this.listEl.innerHTML = this.presets
      .map((preset) => {
        const isActive = String(preset.id) === String(this.previewPresetId);
        const entry = this.getPreviewEntry(preset.id);
        const status = entry?.status || 'idle';
        return `
          <button type="button" class="preset-item ${isActive ? 'is-active' : ''}" data-preset-id="${preset.id}">
            <span class="preset-item-title">${escapeHtml(preset.name)}</span>
            <span class="preset-item-subtitle">${escapeHtml(preset.frequency)}</span>
            <span class="preset-item-status is-${status}">${escapeHtml(statusLabel(status))}</span>
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
    this.emailBlock.innerHTML = '';
    this.metaBlock.innerHTML = '';
    this.rightPane?.classList.remove('preview-refresh');
    void this.rightPane?.offsetHeight;
    this.rightPane?.classList.add('preview-refresh');

    const context = this.normalizeContext();
    const entry = this.getPreviewEntry(preset.id) || this.buildBasePreviewEntry(preset, context);
    this.metaBlock.innerHTML = buildPresetMetaHtml(entry);

    let emailHtml = buildEmailSkeletonHtml();
    if (entry.status === 'ready') {
      emailHtml = buildReadyEmailHtml(entry);
    } else if (entry.status === 'error') {
      emailHtml = buildEmailErrorHtml(preset.id, entry.errorMessage);
    }
    this.emailBlock.innerHTML = `
      <h3>Email Preview</h3>
      ${emailHtml}
    `;
    this.emailBlock.querySelector('.preset-retry-btn')?.addEventListener('click', () => this.retryPreset(preset.id));
  }

  retryPreset(id) {
    const preset = this.getPresetById(id);
    if (!preset) return;
    const context = this.normalizeContext();
    const contextHash = buildPreviewContextHash(context);
    this.activeContextHash = contextHash;

    const base = this.buildBasePreviewEntry(preset, context);
    this.previewEntries.set(String(preset.id), { ...base, status: 'loading', errorMessage: '' });
    this.renderPresetList();
    this.renderPreview(preset);
    this.scheduleMissingPreviews([preset], context, contextHash);
  }

  selectPreset(id) {
    const preset = this.getPresetById(id);
    if (!preset) return;
    this.onSelectPreset(preset);
    this.close();
  }

  destroy() {
    if (this.previewFetchTimer) {
      clearTimeout(this.previewFetchTimer);
      this.previewFetchTimer = null;
    }
    window.removeEventListener('keydown', this.onKeydown);
    if (this.modalHost?.parentNode) this.modalHost.parentNode.removeChild(this.modalHost);
  }
}
