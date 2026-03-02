import { styleToPayload } from '../style.js';
import {
  buildPreviewCacheKey,
  buildPreviewContextHash,
  buildVibeMetadata,
  buildWhyItWorksBullets,
  normalizePreviewContext,
  normalizeSliderState,
  parseGeneratedDraft,
  resolveEffectiveSliderState,
  sanitizePreviewEmail,
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

function buildSafeProspect(context) {
  return {
    name: context.prospect.name || 'there',
    title: context.prospect.title || 'Revenue Leader',
    company: context.prospect.company || 'your company',
    linkedin_url: context.prospect.linkedin_url || null,
  };
}

function buildSafeResearchText(context, preset) {
  const research = context.research_text;
  const presetGuidance = [
    `Preset style: ${preset.name}.`,
    `Vibe guidance: ${preset.vibe || 'Use a clear SDR style tailored to this preset.'}`,
    `Keep the output specific, factual, and non-generic.`,
  ].join(' ');

  const combined = [research, presetGuidance].filter(Boolean).join('\n\n').trim();
  if (combined.length >= 20) return combined;
  return [
    'No deep research was provided. Use the prospect and company context only.',
    presetGuidance,
    'Return a realistic SDR subject and body with no placeholders.',
  ].join(' ');
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

function buildReadyEmailHtml(preview) {
  const subject = escapeHtml(preview?.subject || '');
  const body = escapeHtml(preview?.body || '').replaceAll('\n', '<br>');
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
    this.generatePreviewDraft =
      typeof options.generatePreviewDraft === 'function' ? options.generatePreviewDraft : async () => '';
    this.maxPreviewConcurrency = clamp(Number(options.maxPreviewConcurrency) || 3, 1, 4);

    this.previewPresetId = this.presets[0]?.id ?? null;
    this.isOpen = false;
    this.activeContextHash = '';
    this.previewCache = new Map();
    this.previewEntries = new Map();
    this.inflightPreviews = new Map();

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
    if (!this.backdrop || this.isOpen) return;
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
    if (!this.backdrop || !this.isOpen) return;
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
      void this.generateMissingPreviews(missing, context, contextHash);
    }
  }

  async generateMissingPreviews(presets, context, contextHash) {
    const queue = [...presets];
    const workerCount = Math.min(this.maxPreviewConcurrency, queue.length);

    const worker = async () => {
      while (queue.length > 0) {
        const nextPreset = queue.shift();
        if (!nextPreset) return;
        await this.generatePreviewForPreset(nextPreset, context, contextHash);
      }
    };

    await Promise.all(Array.from({ length: workerCount }, () => worker()));
  }

  buildPreviewPayload(preset, context) {
    const effectiveSliders = resolveEffectiveSliderState(context.global_slider_state, preset);
    return {
      prospect: buildSafeProspect(context),
      research_text: buildSafeResearchText(context, preset),
      style_profile: styleToPayload(effectiveSliders),
      company_context: {
        company_name: context.company_context.company_name || undefined,
        company_url: context.company_context.company_url || undefined,
        current_product: context.company_context.current_product || undefined,
        other_products: context.company_context.other_products || undefined,
        company_notes: context.company_context.company_notes || undefined,
      },
    };
  }

  async generatePreviewForPreset(preset, context, contextHash) {
    const key = buildPreviewCacheKey(contextHash, preset.id);
    let promise = this.inflightPreviews.get(key);

    if (!promise) {
      promise = (async () => {
        const payload = this.buildPreviewPayload(preset, context);
        const draft = await this.generatePreviewDraft(payload);
        const parsed = parseGeneratedDraft(draft, context.prospect.company);
        const sanitized = sanitizePreviewEmail(parsed, context);
        const preview = {
          ...this.buildBasePreviewEntry(preset, context),
          subject: sanitized.subject || previewFallbackSubject(context),
          body: sanitized.body || '',
        };
        this.previewCache.set(key, preview);
        return preview;
      })();
      this.inflightPreviews.set(key, promise);
    }

    try {
      const preview = await promise;
      if (contextHash !== this.activeContextHash) return;
      this.previewEntries.set(String(preset.id), {
        ...this.buildBasePreviewEntry(preset, context),
        ...preview,
        status: 'ready',
        errorMessage: '',
      });
      this.renderPresetList();
      if (this.previewPresetId === preset.id) this.renderPreview(preset);
    } catch (error) {
      if (contextHash !== this.activeContextHash) return;
      const existing = this.getPreviewEntry(preset.id) || this.buildBasePreviewEntry(preset, context);
      this.previewEntries.set(String(preset.id), {
        ...existing,
        status: 'error',
        errorMessage: String(error?.message || error || 'Generation failed'),
      });
      this.renderPresetList();
      if (this.previewPresetId === preset.id) this.renderPreview(preset);
    } finally {
      this.inflightPreviews.delete(key);
    }
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
    void this.generatePreviewForPreset(preset, context, contextHash);
  }

  selectPreset(id) {
    const preset = this.getPresetById(id);
    if (!preset) return;
    this.onSelectPreset(preset);
    this.close();
  }

  destroy() {
    window.removeEventListener('keydown', this.onKeydown);
    if (this.modalHost?.parentNode) this.modalHost.parentNode.removeChild(this.modalHost);
  }
}
