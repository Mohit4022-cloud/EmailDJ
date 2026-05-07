import {
  consumeStream,
  fetchRuntimeConfig,
  generateDraft,
  generatePresetPreviewsBatch,
  presetPreviewBatchEnabled,
  remixDraft,
  sendFeedback,
} from './api/client.js';
import { EmailEditor } from './components/EmailEditor.js';
import { SDRPresetLibrary, presetToSliderState } from './components/SDRPresetLibrary.js';
import { SliderBoard } from './components/SliderBoard.js';
import { SDR_PRESETS } from './data/sdrPresets.js';
import { styleToPayload, styleKey } from './style.js';
import { applyStreamEvent, createStreamState } from './streamContract.js';
import { debounce } from './utils.js';

const VITE_RESPONSE_CONTRACT =
  typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env.VITE_RESPONSE_CONTRACT : undefined;
const VITE_ALLOW_MOCK_AI =
  typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env.VITE_ALLOW_MOCK_AI : undefined;
const RESPONSE_CONTRACT = String(VITE_RESPONSE_CONTRACT || 'legacy_text').trim().toLowerCase() === 'rc_tco_json_v1'
  ? 'rc_tco_json_v1'
  : 'legacy_text';

// Demo defaults are empty — populate via "Load demo data" button or fill manually.
// Demo fixture files live in hub-api/devtools/fixtures/ for dev/CI use.
const DEFAULT_COMPANY_CONTEXT = {
  company_name: '',
  company_url: '',
  current_product: '',
  cta_offer_lock: '',
  cta_type: '',
  other_products: '',
  company_notes: '',
};

const DEFAULT_TARGET_CONTEXT = {
  name: '',
  title: '',
  company: '',
  linkedin_url: '',
};

const DEFAULT_RESEARCH_TEXT = '';

function chooseDefaultString(value, fallback) {
  if (typeof value !== 'string') return fallback;
  return value.trim() ? value : fallback;
}

function envFlagEnabled(value) {
  const raw = String(value || '').trim().toLowerCase();
  return raw === '1' || raw === 'true' || raw === 'yes' || raw === 'on';
}

async function sha256Hex(text) {
  const cryptoApi = globalThis?.crypto?.subtle;
  if (!cryptoApi) return null;
  const bytes = new TextEncoder().encode(String(text || ''));
  const hash = await cryptoApi.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash)).map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

class WebApp {
  constructor(root) {
    this.root = root;
    this.sessionId = null;
    this.isGenerating = false;
    this.lastDraft = '';
    this.lastStyleKey = '';
    this.runtimeConfig = null;
    this.runtimeBadgeMeta = null;
    this.allowMockAi = envFlagEnabled(VITE_ALLOW_MOCK_AI);
    this.selectedPresetId = String(SDR_PRESETS?.[0]?.strategy_id || SDR_PRESETS?.[0]?.id || 'straight_shooter');
    this.remixDebounced = debounce(() => this.triggerRemix(), 250);
    this.render();
  }

  storageGet(key) {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  storageSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
      return true;
    } catch {
      return false;
    }
  }

  render() {
    this.root.innerHTML = `
      <div id="runtimeModeBadge" class="runtime-mode-badge mode-loading">Checking runtime mode...</div>
      <div class="hero">
        <h1>EmailDJ Remix Studio</h1>
        <p>Paste research, generate once, then sculpt the draft with live sliders.</p>
      </div>
      <div class="layout">
        <section class="panel workspace-panel" id="workspacePanel">
          <div class="panel-heading workspace-heading">
            <div>
              <div class="section-kicker">Draft Workspace</div>
              <h2>Email draft</h2>
            </div>
            <div class="workspace-actions">
              <button class="btn-secondary" id="saveRemixBtn" disabled>Save Remix</button>
              <div id="presetLibraryMount"></div>
            </div>
          </div>
          <div id="editorMount"></div>
          <div class="status workspace-status" id="statusLine"></div>
          <div class="remix-panel">
            <div class="panel-heading compact-heading">
              <div>
                <div class="section-kicker">Remix Controls</div>
                <h2>Tone sliders</h2>
              </div>
            </div>
            <div id="sliderBoard"></div>
          </div>
        </section>

        <section class="panel brief-panel" id="inputPanel">
          <div class="panel-heading">
            <div>
              <div class="section-kicker">Brief</div>
              <h2>Inputs</h2>
            </div>
          </div>
          <div class="field">
            <label>Beta Key</label>
            <input id="betaKey" placeholder="dev-beta-key" />
          </div>
          <div class="field">
            <label>Your Company Name (saved locally)</label>
            <input id="sellerCompanyName" placeholder="EmailDJ" />
          </div>
          <div class="row">
            <div class="field"><label>Company URL</label><input id="sellerCompanyUrl" placeholder="https://yourcompany.com" /></div>
            <div class="field"><label>Current Product / Service to Pitch</label><input id="sellerCurrentProduct" placeholder="Remix Studio" /></div>
          </div>
          <div class="field">
            <label>Other Products / Services (used for mapping)</label>
            <textarea id="sellerOtherProducts" class="compact" placeholder="Prospect Enrichment&#10;Sequence QA&#10;Persona Research"></textarea>
          </div>
          <div class="row">
            <div class="field">
              <label>CTA / Offer Lock text</label>
              <input id="ctaOfferLock" placeholder="Open to a quick chat to see if this is relevant?" />
            </div>
            <div class="field">
              <label>CTA Type (optional)</label>
              <select id="ctaType">
                <option value="">Not set</option>
                <option value="question">question</option>
                <option value="time_ask">time_ask</option>
                <option value="value_asset">value_asset</option>
                <option value="pilot">pilot</option>
                <option value="referral">referral</option>
                <option value="event_invite">event_invite</option>
              </select>
            </div>
          </div>
          <div class="field">
            <label>Company Notes (proof points, ICP, differentiation)</label>
            <textarea id="sellerCompanyNotes" class="compact" placeholder="What your product does best, who it helps, and why it wins."></textarea>
          </div>
          <hr />
          <div class="row">
            <div class="field"><label>Prospect Name</label><input id="prospectName" placeholder="Alex Doe" /></div>
            <div class="field"><label>Title</label><input id="prospectTitle" placeholder="SDR Manager" /></div>
          </div>
          <div class="row">
            <div class="field"><label>Company</label><input id="prospectCompany" placeholder="Acme" /></div>
            <div class="field"><label>LinkedIn URL (optional)</label><input id="prospectLinkedin" placeholder="https://linkedin.com/in/..." /></div>
          </div>
          <div class="field">
            <label>Deep Research Paste</label>
            <textarea id="researchText" placeholder="Paste account/prospect research here..."></textarea>
          </div>
          <div class="actions">
            <button class="btn-primary" id="generateBtn">Generate</button>
          </div>
        </section>
      </div>
    `;

    this.statusLine = this.root.querySelector('#statusLine');
    this.runtimeModeBadgeEl = this.root.querySelector('#runtimeModeBadge');
    this.generateBtn = this.root.querySelector('#generateBtn');
    this.saveRemixBtn = this.root.querySelector('#saveRemixBtn');
    this.betaKeyInput = this.root.querySelector('#betaKey');
    this.presetLibraryMount = this.root.querySelector('#presetLibraryMount');
    this.sellerCompanyNameInput = this.root.querySelector('#sellerCompanyName');
    this.sellerCompanyUrlInput = this.root.querySelector('#sellerCompanyUrl');
    this.sellerCurrentProductInput = this.root.querySelector('#sellerCurrentProduct');
    this.sellerOtherProductsInput = this.root.querySelector('#sellerOtherProducts');
    this.ctaOfferLockInput = this.root.querySelector('#ctaOfferLock');
    this.ctaTypeSelect = this.root.querySelector('#ctaType');
    this.sellerCompanyNotesInput = this.root.querySelector('#sellerCompanyNotes');
    this.prospectNameInput = this.root.querySelector('#prospectName');
    this.prospectTitleInput = this.root.querySelector('#prospectTitle');
    this.prospectCompanyInput = this.root.querySelector('#prospectCompany');
    this.prospectLinkedinInput = this.root.querySelector('#prospectLinkedin');
    this.researchInput = this.root.querySelector('#researchText');

    this.editor = new EmailEditor(this.root.querySelector('#editorMount'));
    this.sliderBoard = new SliderBoard(this.root.querySelector('#sliderBoard'), () => this.onSlidersChanged());
    this.presetLibrary = new SDRPresetLibrary(this.presetLibraryMount, {
      presets: SDR_PRESETS,
      onSelectPreset: (preset) => this.applyPreset(preset),
      getPreviewContext: () => this.previewContextPayload(),
      generatePreviewBatch: presetPreviewBatchEnabled() ? (payload) => this.generatePreviewBatch(payload) : null,
    });

    this.seedBetaKey();
    this.seedCompanyContext();
    this.seedTargetDefaults();

    this.generateBtn.addEventListener('click', () => this.generate());
    this.saveRemixBtn.addEventListener('click', () => this.saveRemix());
    this.betaKeyInput.addEventListener('change', () => {
      this.storageSet('emaildj_beta_key', this.betaKeyInput.value.trim() || 'dev-beta-key');
    });
    for (const input of [
      this.sellerCompanyNameInput,
      this.sellerCompanyUrlInput,
      this.sellerCurrentProductInput,
      this.sellerOtherProductsInput,
      this.ctaOfferLockInput,
      this.ctaTypeSelect,
      this.sellerCompanyNotesInput,
    ]) {
      input?.addEventListener('input', () => this.persistCompanyContext());
      input?.addEventListener('change', () => this.persistCompanyContext());
    }
    for (const input of [
      this.prospectNameInput,
      this.prospectTitleInput,
      this.prospectCompanyInput,
      this.prospectLinkedinInput,
      this.researchInput,
    ]) {
      input?.addEventListener('input', () => this.persistTargetDefaults());
    }

    this.refreshRuntimeConfig({ silent: true }).catch(() => {
      this.updateRuntimeModeBadge();
    });
    this.setStatus('Ready. Fill inputs and click Generate.');
  }

  applyPreset(preset) {
    if (!preset) return;
    this.selectedPresetId = String(preset.strategy_id || preset.id || 'straight_shooter');
    this.sliderBoard.setValues(presetToSliderState(preset), { emit: true });
    if (!this.sessionId) {
      this.setStatus(`Preset selected: ${preset.name}. Click Generate to create a draft.`);
      return;
    }
    this.setStatus(`Preset selected: ${preset.name}. Remixing...`, true);
  }

  seedBetaKey() {
    const key = this.storageGet('emaildj_beta_key') || 'dev-beta-key';
    this.storageSet('emaildj_beta_key', key);
    this.betaKeyInput.value = key;
  }

  seedCompanyContext() {
    let saved = {};
    try {
      saved = JSON.parse(this.storageGet('emaildj_company_context_v1') || '{}') || {};
    } catch {
      saved = {};
    }
    const merged = {
      company_name: chooseDefaultString(saved.company_name, DEFAULT_COMPANY_CONTEXT.company_name),
      company_url: chooseDefaultString(saved.company_url, DEFAULT_COMPANY_CONTEXT.company_url),
      current_product: chooseDefaultString(saved.current_product, DEFAULT_COMPANY_CONTEXT.current_product),
      cta_offer_lock: chooseDefaultString(saved.cta_offer_lock, DEFAULT_COMPANY_CONTEXT.cta_offer_lock),
      cta_type: chooseDefaultString(saved.cta_type, DEFAULT_COMPANY_CONTEXT.cta_type),
      other_products: chooseDefaultString(saved.other_products, DEFAULT_COMPANY_CONTEXT.other_products),
      company_notes: chooseDefaultString(saved.company_notes, DEFAULT_COMPANY_CONTEXT.company_notes),
    };
    this.sellerCompanyNameInput.value = merged.company_name;
    this.sellerCompanyUrlInput.value = merged.company_url;
    this.sellerCurrentProductInput.value = merged.current_product;
    this.sellerOtherProductsInput.value = merged.other_products;
    this.ctaOfferLockInput.value = merged.cta_offer_lock;
    this.ctaTypeSelect.value = merged.cta_type;
    this.sellerCompanyNotesInput.value = merged.company_notes;
    this.storageSet('emaildj_company_context_v1', JSON.stringify(merged));
  }

  seedTargetDefaults() {
    let saved = {};
    try {
      saved = JSON.parse(this.storageGet('emaildj_target_defaults_v1') || '{}') || {};
    } catch {
      saved = {};
    }
    const merged = {
      name: chooseDefaultString(saved.name, DEFAULT_TARGET_CONTEXT.name),
      title: chooseDefaultString(saved.title, DEFAULT_TARGET_CONTEXT.title),
      company: chooseDefaultString(saved.company, DEFAULT_TARGET_CONTEXT.company),
      linkedin_url: chooseDefaultString(saved.linkedin_url, DEFAULT_TARGET_CONTEXT.linkedin_url),
    };
    const savedResearch = chooseDefaultString(
      this.storageGet('emaildj_research_default_v1') || '',
      DEFAULT_RESEARCH_TEXT
    );

    this.prospectNameInput.value = merged.name;
    this.prospectTitleInput.value = merged.title;
    this.prospectCompanyInput.value = merged.company;
    this.prospectLinkedinInput.value = merged.linkedin_url;
    this.researchInput.value = savedResearch;

    this.storageSet('emaildj_target_defaults_v1', JSON.stringify(merged));
    this.storageSet('emaildj_research_default_v1', savedResearch);
  }

  companyContextPayload() {
    const raw = {
      company_name: this.sellerCompanyNameInput.value.trim(),
      company_url: this.sellerCompanyUrlInput.value.trim(),
      current_product: this.sellerCurrentProductInput.value.trim(),
      cta_offer_lock: this.ctaOfferLockInput.value.trim(),
      cta_type: this.ctaTypeSelect.value.trim(),
      other_products: this.sellerOtherProductsInput.value.trim(),
      company_notes: this.sellerCompanyNotesInput.value.trim(),
    };
    const payload = {};
    for (const [key, value] of Object.entries(raw)) {
      if (value) payload[key] = value;
    }
    return payload;
  }

  persistCompanyContext() {
    return this.storageSet('emaildj_company_context_v1', JSON.stringify(this.companyContextPayload()));
  }

  persistTargetDefaults() {
    const target = {
      name: this.prospectNameInput.value.trim(),
      title: this.prospectTitleInput.value.trim(),
      company: this.prospectCompanyInput.value.trim(),
      linkedin_url: this.prospectLinkedinInput.value.trim(),
    };
    const targetSaved = this.storageSet('emaildj_target_defaults_v1', JSON.stringify(target));
    const researchSaved = this.storageSet('emaildj_research_default_v1', this.researchInput.value.trim());
    return targetSaved && researchSaved;
  }

  payload() {
    const fullName = this.prospectNameInput.value.trim();
    // Derive first name client-side for greeting normalization
    const firstName = fullName.split(/\s+/)[0] || null;

    const offerLock = this.sellerCurrentProductInput.value.trim();
    const companyCtx = this.companyContextPayload();

    // Dedup: don't send current_product if it's the same string as offer_lock
    if (companyCtx.current_product && companyCtx.current_product === offerLock) {
      delete companyCtx.current_product;
    }

    return {
      prospect: {
        name: fullName,
        title: this.prospectTitleInput.value.trim(),
        company: this.prospectCompanyInput.value.trim(),
        linkedin_url: this.prospectLinkedinInput.value.trim() || null,
      },
      prospect_first_name: firstName,
      research_text: this.researchInput.value.trim(),
      offer_lock: offerLock,
      cta_offer_lock: this.ctaOfferLockInput.value.trim() || null,
      cta_type: this.ctaTypeSelect.value.trim() || null,
      preset_id: this.selectedPresetId,
      response_contract: RESPONSE_CONTRACT,
      pipeline_meta: {
        mode: 'generate',
        model_hint: 'gpt-5-nano',
      },
      style_profile: styleToPayload(this.sliderBoard.getValues()),
      company_context: companyCtx,
    };
  }

  previewContextPayload() {
    const fullName = this.prospectNameInput.value.trim();
    const firstName = fullName.split(/\s+/)[0] || null;
    const offerLock = this.sellerCurrentProductInput.value.trim();
    return {
      prospect: {
        name: fullName,
        title: this.prospectTitleInput.value.trim(),
        company: this.prospectCompanyInput.value.trim(),
        linkedin_url: this.prospectLinkedinInput.value.trim(),
      },
      prospect_first_name: firstName,
      research_text: this.researchInput.value.trim(),
      offer_lock: offerLock,
      company_context: this.companyContextPayload(),
      global_slider_state: this.sliderBoard.getValues(),
    };
  }

  async generatePreviewBatch(payload) {
    await this.assertRuntimeModeAllowed();
    return generatePresetPreviewsBatch(payload);
  }

  validate(data) {
    if (!data.prospect.name || !data.prospect.title || !data.prospect.company) return 'Prospect name, title, and company are required.';
    if (!data.research_text || data.research_text.length < 20) return 'Paste at least 20 characters of research.';
    if (!data.offer_lock) return 'Current Product / Service to Pitch is required.';
    return '';
  }

  setStatus(text, pulse = false) {
    this.statusLine.textContent = text;
    this.statusLine.classList.toggle('pulse', pulse);
  }

  runtimeMode() {
    const mode = String(
      this.runtimeConfig?.runtime_mode
        || this.runtimeConfig?.quick_generate_mode
        || ''
    ).trim().toLowerCase();
    return mode === 'real' || mode === 'mock' ? mode : 'unknown';
  }

  mockModeExplicitlyAllowed() {
    if (this.allowMockAi) return true;
    return this.storageGet('emaildj_allow_mock_ai') === '1';
  }

  updateRuntimeModeBadge(doneData = null) {
    const badgeEl = this.runtimeModeBadgeEl;
    if (!badgeEl) return;
    if (doneData && typeof doneData === 'object') {
      this.runtimeBadgeMeta = {
        provider: doneData.provider || '',
        model: doneData.model || '',
        repaired: Boolean(doneData.repaired),
        repairCount: Number(doneData?.json_repair_count || 0) + Number(doneData?.violation_retry_count || 0),
      };
    }

    const mode = this.runtimeMode();
    const meta = this.runtimeBadgeMeta || {};
    if (mode === 'real') {
      badgeEl.className = 'runtime-mode-badge mode-real';
      const providerLabel = meta.provider && meta.model ? ` · ${meta.provider}/${meta.model}` : '';
      const repairedNote = meta.repaired ? ` · repaired (${meta.repairCount || 1}x)` : '';
      badgeEl.textContent = `REAL AI${providerLabel}${repairedNote}`;
      return;
    }
    if (mode === 'mock') {
      badgeEl.className = 'runtime-mode-badge mode-mock';
      const explicit = this.mockModeExplicitlyAllowed() ? ' (explicitly allowed)' : ' (blocked for send)';
      badgeEl.textContent = `MOCK AI${explicit}`;
      return;
    }
    badgeEl.className = 'runtime-mode-badge mode-unknown';
    badgeEl.textContent = 'Runtime mode unknown';
  }

  async refreshRuntimeConfig({ silent = false } = {}) {
    try {
      const config = await fetchRuntimeConfig({ endpoint: 'generate', bucketKey: 'web-app' });
      this.runtimeConfig = config;
      this.updateRuntimeModeBadge();
      return config;
    } catch (error) {
      if (!silent) this.setStatus(String(error?.message || error));
      this.updateRuntimeModeBadge();
      return null;
    }
  }

  async assertRuntimeModeAllowed() {
    const config = await this.refreshRuntimeConfig({ silent: true });
    if (!config) {
      throw new Error('Unable to confirm runtime mode from /web/v1/debug/config.');
    }
    if (this.runtimeMode() === 'mock' && !this.mockModeExplicitlyAllowed()) {
      throw new Error(
        'Backend is in MOCK AI mode. Set USE_PROVIDER_STUB=0 on the server, or explicitly allow mock in UI via VITE_ALLOW_MOCK_AI=1.'
      );
    }
  }

  async generate() {
    if (this.isGenerating) return;
    const persisted = this.persistCompanyContext();
    const payload = this.payload();
    const validation = this.validate(payload);
    if (validation) {
      this.setStatus(validation);
      return;
    }
    try {
      await this.assertRuntimeModeAllowed();
    } catch (error) {
      this.setStatus(String(error?.message || error));
      return;
    }

    this.isGenerating = true;
    this.generateBtn.disabled = true;
    this.editor.reset();
    this.setStatus('Generating draft...', true);
    this.dispatchMetric('web_generate_started');

    const start = performance.now();
    try {
      const accepted = await generateDraft(payload);
      this.sessionId = accepted.session_id;
      await this.streamIntoEditor(accepted.request_id);
      const elapsed = Math.round(performance.now() - start);
      this.editor.markComplete(elapsed);
      this.lastDraft = this.editor.getText();
      this.lastStyleKey = styleKey(payload.style_profile);
      this.setStatus(persisted ? 'Draft ready. Adjust sliders to remix.' : 'Draft ready. Local save unavailable; adjust sliders to remix.');
      this.saveRemixBtn.disabled = false;
      this.dispatchMetric('web_generate_completed');
    } catch (error) {
      this.setStatus(String(error?.message || error));
    } finally {
      this.isGenerating = false;
      this.generateBtn.disabled = false;
      this.statusLine.classList.remove('pulse');
    }
  }

  onSlidersChanged() {
    if (!this.sessionId || this.isGenerating) return;
    this.remixDebounced();
  }

  async triggerRemix() {
    if (!this.sessionId || this.isGenerating) return;

    const style = styleToPayload(this.sliderBoard.getValues());
    const nextKey = styleKey(style);
    if (nextKey === this.lastStyleKey) return;
    try {
      await this.assertRuntimeModeAllowed();
    } catch (error) {
      this.setStatus(String(error?.message || error));
      return;
    }

    this.isGenerating = true;
    this.generateBtn.disabled = true;
    this.setStatus('Remixing draft...', true);
    this.editor.reset();
    this.dispatchMetric('web_remix_started');

    const start = performance.now();
    try {
      const accepted = await remixDraft({
        session_id: this.sessionId,
        preset_id: this.selectedPresetId,
        style_profile: style,
      });
      await this.streamIntoEditor(accepted.request_id);
      const elapsed = Math.round(performance.now() - start);
      this.editor.markComplete(elapsed);
      this.lastDraft = this.editor.getText();
      this.lastStyleKey = nextKey;
      this.setStatus('Remix applied.');
      this.dispatchMetric('web_remix_completed');
    } catch (error) {
      this.setStatus(String(error?.message || error));
    } finally {
      this.isGenerating = false;
      this.generateBtn.disabled = false;
      this.statusLine.classList.remove('pulse');
    }
  }

  async streamIntoEditor(requestId) {
    const streamState = createStreamState();
    let doneData = null;
    let finalText = '';
    await consumeStream(requestId, (msg) => {
      const outcome = applyStreamEvent(streamState, msg);
      if (!outcome?.accepted) return;
      if (outcome.reset) {
        this.editor.setContent('');
      }
      if (typeof outcome.appendToken === 'string' && outcome.appendToken) {
        this.editor.appendToken(outcome.appendToken);
      }
      if (outcome.error) {
        streamState.streamError = outcome.error;
      }
      if (outcome.done) {
        doneData = outcome.doneData || msg.data || null;
        const finalBody = typeof outcome.finalBody === 'string' ? outcome.finalBody.trim() : '';
        if (finalBody) {
          finalText = finalBody;
          this.editor.setContent(finalText);
          return;
        }
        if (streamState.streamBuffer) {
          finalText = streamState.streamBuffer;
          this.editor.setContent(finalText);
        }
      }
    });
    if (streamState.streamError) throw new Error(streamState.streamError);
    if (streamState.chunkSequenceMismatch) {
      throw new Error('Draft stream integrity check failed (chunk sequence mismatch).');
    }
    if (doneData?.stream_checksum) {
      const localChecksum = await sha256Hex(streamState.streamBuffer);
      if (localChecksum && localChecksum !== doneData.stream_checksum) {
        throw new Error('Draft stream integrity check failed (checksum mismatch).');
      }
      if (
        typeof doneData.total_chunks === 'number'
        && streamState.expectedChunkIndex
        && streamState.expectedChunkIndex !== doneData.total_chunks
      ) {
        throw new Error('Draft stream integrity check failed (missing chunk).');
      }
    }
    if (!this.editor.getText().trim() && !finalText.trim() && !doneData?.final?.body?.trim()) {
      throw new Error('Draft stream completed without any visible content.');
    }
    if (doneData) this.showModeBadge(doneData);
  }

  showModeBadge(doneData) {
    this.updateRuntimeModeBadge(doneData);
  }

  async saveRemix() {
    if (!this.sessionId) return;
    const draftAfter = this.editor.getText();
    if (!draftAfter) return;

    try {
      await sendFeedback({
        session_id: this.sessionId,
        draft_before: this.lastDraft || draftAfter,
        draft_after: draftAfter,
        style_profile: styleToPayload(this.sliderBoard.getValues()),
      });
      this.dispatchMetric('web_copy_clicked');
      await navigator.clipboard.writeText(draftAfter);
      this.lastDraft = draftAfter;
      this.setStatus('Remix saved and copied.');
    } catch (error) {
      this.setStatus(String(error?.message || error));
    }
  }

  dispatchMetric(name) {
    window.dispatchEvent(new CustomEvent('emaildj-metric', { detail: { name, ts: Date.now() } }));
  }
}

new WebApp(document.getElementById('app'));
