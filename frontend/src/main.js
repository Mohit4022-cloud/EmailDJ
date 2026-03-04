import {
  consumeStream,
  fetchPresetPreviewsBatch,
  fetchPresetPreview,
  fetchResearchJobStatus,
  fetchRuntimeConfig,
  generateDraft,
  remixDraft,
  sendFeedback,
  startResearchJob,
  startProspectEnrichment,
  startSenderEnrichment,
  startTargetEnrichment,
} from './api/client.js';
import { EmailEditor } from './components/EmailEditor.js';
import { SDRPresetLibrary, presetToSliderState } from './components/SDRPresetLibrary.js';
import { SliderBoard } from './components/SliderBoard.js';
import { SDR_PRESETS } from './data/sdrPresets.js';
import { styleToPayload, styleKey } from './style.js';
import { applyStreamEvent, createStreamState } from './streamContract.js';
import { debounce } from './utils.js';

const DEFAULT_COMPANY_CONTEXT = {
  company_name: '',
  company_url: '',
  current_product: '',
  cta_offer_lock: '',
  cta_type: '',
  seller_offerings: '',
  internal_modules: '',
  company_notes: '',
};

const DEFAULT_TARGET_CONTEXT = {
  name: '',
  title: '',
  company: '',
  company_url: '',
  linkedin_url: '',
};

const DEFAULT_RESEARCH_TEXT = '';

function chooseDefaultString(value, fallback) {
  if (typeof value !== 'string') return fallback;
  return value.trim() ? value : fallback;
}

async function sha256Hex(text) {
  const cryptoApi = globalThis?.crypto?.subtle;
  if (!cryptoApi) return null;
  const bytes = new TextEncoder().encode(String(text || ''));
  const hash = await cryptoApi.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash)).map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

function nowPretty() {
  const now = new Date();
  return now.toLocaleString();
}

function firstName(raw) {
  return String(raw || '').trim().split(/\s+/)[0] || null;
}

function stripUnknown(items = []) {
  return (Array.isArray(items) ? items : []).map((item) => String(item || '').trim()).filter(Boolean);
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
    this.selectedPresetId = String(SDR_PRESETS?.[0]?.strategy_id || SDR_PRESETS?.[0]?.id || 'straight_shooter');
    this.remixDebounced = debounce(() => this.triggerRemix(), 200);
    this.activeRemixController = null;

    this.enrichedTargetProfile = null;
    this.enrichedContactProfile = null;
    this.enrichedSenderProfile = null;

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
        <p>Generate once, then sculpt with live sliders. Enrichment uses cited, cached tool results.</p>
      </div>
      <div class="layout">
        <section class="panel" id="inputPanel">
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
            <label>Seller Offerings (what you sell)</label>
            <textarea id="sellerOfferings" class="compact" placeholder="Brand monitoring&#10;Trademark enforcement&#10;Marketplace takedowns"></textarea>
          </div>
          <div class="field">
            <label>Internal Modules (never shared)</label>
            <textarea id="sellerInternalModules" class="compact" placeholder="Internal workflow tags only"></textarea>
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
            <label style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
              <span>Company Notes (proof points, ICP, differentiation)</span>
              <span style="display:inline-flex;align-items:center;gap:6px;">
                <button class="btn-secondary" id="senderAiBtn" type="button">AI Clean/Structure</button>
                <small id="senderRefreshMeta" class="meta"></small>
              </span>
            </label>
            <textarea id="sellerCompanyNotes" class="compact" placeholder="What your product does best, who it helps, and why it wins."></textarea>
          </div>
          <hr />
          <div class="row">
            <div class="field"><label>Prospect Name</label><input id="prospectName" placeholder="Alex Doe" /></div>
            <div class="field">
              <label style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
                <span>Title</span>
                <span style="display:inline-flex;align-items:center;gap:6px;">
                  <button class="btn-secondary" id="prospectAiBtn" type="button">AI</button>
                  <button class="btn-secondary" id="prospectRefreshBtn" type="button">Refresh</button>
                </span>
              </label>
              <input id="prospectTitle" placeholder="SDR Manager" />
              <small id="prospectRefreshMeta" class="meta"></small>
            </div>
          </div>
          <div class="row">
            <div class="field">
              <label style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
                <span>Company</span>
                <span style="display:inline-flex;align-items:center;gap:6px;">
                  <button class="btn-secondary" id="targetAiBtn" type="button">AI</button>
                  <button class="btn-secondary" id="targetRefreshBtn" type="button">Refresh</button>
                </span>
              </label>
              <input id="prospectCompany" placeholder="Acme" />
              <small id="targetRefreshMeta" class="meta"></small>
            </div>
            <div class="field"><label>LinkedIn URL (optional)</label><input id="prospectLinkedin" placeholder="https://linkedin.com/in/..." /></div>
          </div>
          <div class="field"><label>Target Company URL/domain (optional)</label><input id="prospectCompanyUrl" placeholder="https://acme.com" /></div>
          <div class="field">
            <label>Deep Research Paste</label>
            <textarea id="researchText" placeholder="Paste account/prospect research here..."></textarea>
          </div>
          <div class="actions">
            <button class="btn-primary" id="generateBtn">Generate</button>
            <button class="btn-secondary" id="saveRemixBtn" disabled>Save Remix</button>
            <div id="presetLibraryMount"></div>
          </div>
          <div class="status" id="statusLine"></div>
        </section>

        <section class="panel">
          <div id="sliderBoard"></div>
          <div id="editorMount"></div>
        </section>
      </div>
    `;

    this.statusLine = this.root.querySelector('#statusLine');
    this.runtimeModeBadgeEl = this.root.querySelector('#runtimeModeBadge');
    this.generateBtn = this.root.querySelector('#generateBtn');
    this.saveRemixBtn = this.root.querySelector('#saveRemixBtn');
    this.presetLibraryMount = this.root.querySelector('#presetLibraryMount');

    this.betaKeyInput = this.root.querySelector('#betaKey');
    this.sellerCompanyNameInput = this.root.querySelector('#sellerCompanyName');
    this.sellerCompanyUrlInput = this.root.querySelector('#sellerCompanyUrl');
    this.sellerCurrentProductInput = this.root.querySelector('#sellerCurrentProduct');
    this.sellerOfferingsInput = this.root.querySelector('#sellerOfferings');
    this.sellerInternalModulesInput = this.root.querySelector('#sellerInternalModules');
    this.ctaOfferLockInput = this.root.querySelector('#ctaOfferLock');
    this.ctaTypeSelect = this.root.querySelector('#ctaType');
    this.sellerCompanyNotesInput = this.root.querySelector('#sellerCompanyNotes');

    this.prospectNameInput = this.root.querySelector('#prospectName');
    this.prospectTitleInput = this.root.querySelector('#prospectTitle');
    this.prospectCompanyInput = this.root.querySelector('#prospectCompany');
    this.prospectCompanyUrlInput = this.root.querySelector('#prospectCompanyUrl');
    this.prospectLinkedinInput = this.root.querySelector('#prospectLinkedin');
    this.researchInput = this.root.querySelector('#researchText');

    this.targetAiBtn = this.root.querySelector('#targetAiBtn');
    this.targetRefreshBtn = this.root.querySelector('#targetRefreshBtn');
    this.targetRefreshMeta = this.root.querySelector('#targetRefreshMeta');
    this.prospectAiBtn = this.root.querySelector('#prospectAiBtn');
    this.prospectRefreshBtn = this.root.querySelector('#prospectRefreshBtn');
    this.prospectRefreshMeta = this.root.querySelector('#prospectRefreshMeta');
    this.senderAiBtn = this.root.querySelector('#senderAiBtn');
    this.senderRefreshMeta = this.root.querySelector('#senderRefreshMeta');

    this.editor = new EmailEditor(this.root.querySelector('#editorMount'));
    this.sliderBoard = new SliderBoard(this.root.querySelector('#sliderBoard'), () => this.onSlidersChanged());
    this.presetLibrary = new SDRPresetLibrary(this.presetLibraryMount, {
      presets: SDR_PRESETS,
      onSelectPreset: (preset) => this.applyPreset(preset),
      getPreviewContext: () => this.previewContextPayload(),
      generatePreview: (payload) => this.generatePresetPreview(payload),
      generatePreviewBatch: (payload) => this.generatePresetPreviewBatch(payload),
      maxConcurrentPreviews: 3,
    });

    this.seedBetaKey();
    this.seedCompanyContext();
    this.seedTargetDefaults();

    this.generateBtn.addEventListener('click', () => this.generate());
    this.saveRemixBtn.addEventListener('click', () => this.saveRemix());
    this.targetAiBtn.addEventListener('click', () => this.runCompanyResearch(false));
    this.targetRefreshBtn.addEventListener('click', () => this.runCompanyResearch(true));
    this.prospectAiBtn.addEventListener('click', () => this.enrichProspect(false));
    this.prospectRefreshBtn.addEventListener('click', () => this.enrichProspect(true));
    this.senderAiBtn.addEventListener('click', () => this.enrichSender(false));

    this.betaKeyInput.addEventListener('change', () => {
      this.storageSet('emaildj_beta_key', this.betaKeyInput.value.trim() || 'dev-beta-key');
    });

    for (const input of [
      this.sellerCompanyNameInput,
      this.sellerCompanyUrlInput,
      this.sellerCurrentProductInput,
      this.sellerOfferingsInput,
      this.sellerInternalModulesInput,
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
      this.prospectCompanyUrlInput,
      this.prospectLinkedinInput,
      this.researchInput,
    ]) {
      input?.addEventListener('input', () => this.persistTargetDefaults());
    }

    this.refreshRuntimeConfig({ silent: true }).catch(() => this.updateRuntimeModeBadge());
    this.setStatus('Ready. Fill inputs and click Generate.');
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
      seller_offerings: chooseDefaultString(saved.seller_offerings || saved.other_products, DEFAULT_COMPANY_CONTEXT.seller_offerings),
      internal_modules: chooseDefaultString(saved.internal_modules, DEFAULT_COMPANY_CONTEXT.internal_modules),
      company_notes: chooseDefaultString(saved.company_notes, DEFAULT_COMPANY_CONTEXT.company_notes),
    };
    this.sellerCompanyNameInput.value = merged.company_name;
    this.sellerCompanyUrlInput.value = merged.company_url;
    this.sellerCurrentProductInput.value = merged.current_product;
    this.sellerOfferingsInput.value = merged.seller_offerings;
    this.sellerInternalModulesInput.value = merged.internal_modules;
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
      company_url: chooseDefaultString(saved.company_url, DEFAULT_TARGET_CONTEXT.company_url),
      linkedin_url: chooseDefaultString(saved.linkedin_url, DEFAULT_TARGET_CONTEXT.linkedin_url),
    };
    const savedResearch = chooseDefaultString(this.storageGet('emaildj_research_default_v1') || '', DEFAULT_RESEARCH_TEXT);

    this.prospectNameInput.value = merged.name;
    this.prospectTitleInput.value = merged.title;
    this.prospectCompanyInput.value = merged.company;
    this.prospectCompanyUrlInput.value = merged.company_url;
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
      seller_offerings: this.sellerOfferingsInput.value.trim(),
      internal_modules: this.sellerInternalModulesInput.value.trim(),
      company_notes: this.sellerCompanyNotesInput.value.trim(),
    };
    const payload = {};
    for (const [key, value] of Object.entries(raw)) {
      if (value) payload[key] = value;
    }
    return payload;
  }

  targetPayload() {
    return {
      name: this.prospectNameInput.value.trim(),
      title: this.prospectTitleInput.value.trim(),
      company: this.prospectCompanyInput.value.trim(),
      company_url: this.prospectCompanyUrlInput.value.trim(),
      linkedin_url: this.prospectLinkedinInput.value.trim(),
    };
  }

  persistCompanyContext() {
    return this.storageSet('emaildj_company_context_v1', JSON.stringify(this.companyContextPayload()));
  }

  persistTargetDefaults() {
    const target = this.targetPayload();
    const targetSaved = this.storageSet('emaildj_target_defaults_v1', JSON.stringify(target));
    const researchSaved = this.storageSet('emaildj_research_default_v1', this.researchInput.value.trim());
    return targetSaved && researchSaved;
  }

  payload() {
    const target = this.targetPayload();
    const offerLock = this.sellerCurrentProductInput.value.trim();
    const companyCtx = this.companyContextPayload();

    if (companyCtx.current_product && companyCtx.current_product === offerLock) {
      delete companyCtx.current_product;
    }

    return {
      prospect: {
        name: target.name,
        title: target.title,
        company: target.company,
        company_url: target.company_url || null,
        linkedin_url: target.linkedin_url || null,
      },
      prospect_first_name: firstName(target.name),
      research_text: this.researchInput.value.trim(),
      offer_lock: offerLock,
      cta_offer_lock: this.ctaOfferLockInput.value.trim() || null,
      cta_type: this.ctaTypeSelect.value.trim() || null,
      preset_id: this.selectedPresetId,
      style_profile: styleToPayload(this.sliderBoard.getValues()),
      company_context: companyCtx,
      sender_profile_override: this.enrichedSenderProfile || null,
      target_profile_override: this.enrichedTargetProfile || null,
      contact_profile_override: this.enrichedContactProfile || null,
      pipeline_meta: {
        mode: 'generate',
        model_hint: 'gpt-5-nano',
      },
    };
  }

  previewContextPayload() {
    const target = this.targetPayload();
    return {
      session_id: this.sessionId || null,
      prospect: {
        name: target.name,
        title: target.title,
        company: target.company,
        company_url: target.company_url,
        linkedin_url: target.linkedin_url,
      },
      prospect_first_name: firstName(target.name),
      research_text: this.researchInput.value.trim(),
      offer_lock: this.sellerCurrentProductInput.value.trim(),
      company_context: this.companyContextPayload(),
      global_slider_state: this.sliderBoard.getValues(),
    };
  }

  async generatePresetPreview(payload) {
    return fetchPresetPreview(payload);
  }

  async generatePresetPreviewBatch(payload) {
    return fetchPresetPreviewsBatch(payload);
  }

  validate(data) {
    if (!data.prospect.name || !data.prospect.title || !data.prospect.company) {
      return 'Prospect name, title, and company are required.';
    }
    if (!data.research_text || data.research_text.length < 20) {
      return 'Paste at least 20 characters of research.';
    }
    if (!data.offer_lock) {
      return 'Current Product / Service to Pitch is required.';
    }
    return '';
  }

  setStatus(text, pulse = false) {
    this.statusLine.textContent = text;
    this.statusLine.classList.toggle('pulse', pulse);
  }

  llmDraftMode() {
    const configured = Boolean(this.runtimeConfig?.provider_configured);
    const enabled = Boolean(this.runtimeConfig?.llm_drafting_enabled);
    if (configured && enabled) return 'llm';
    return 'deterministic';
  }

  updateRuntimeModeBadge(doneData = null) {
    const badgeEl = this.runtimeModeBadgeEl;
    if (!badgeEl) return;
    if (doneData && typeof doneData === 'object') {
      this.runtimeBadgeMeta = {
        provider: doneData.provider || '',
        model: doneData.model || '',
        repaired: Boolean(doneData.repaired),
        repairCount: Number(doneData?.repair_attempt_count || 0),
        draftSource:
          String(doneData?.draft_source || '') ||
          String(doneData?.final?.debug?.draft_source || '') ||
          '',
      };
    }

    const mode = this.llmDraftMode();
    const configured = Boolean(this.runtimeConfig?.provider_configured);
    const enabled = Boolean(this.runtimeConfig?.llm_drafting_enabled);
    const meta = this.runtimeBadgeMeta || {};
    const lastRun = meta.draftSource ? ` · last run: ${meta.draftSource}` : '';
    if (mode === 'llm') {
      badgeEl.className = 'runtime-mode-badge mode-real';
      const providerLabel = meta.provider && meta.model ? ` · ${meta.provider}/${meta.model}` : '';
      const repairedNote = meta.repaired ? ` · repaired (${meta.repairCount || 1}x)` : '';
      badgeEl.textContent = `LLM Draft: ON (OpenAI)${providerLabel}${lastRun}${repairedNote}`;
      return;
    }

    badgeEl.className = 'runtime-mode-badge mode-unknown';
    const reason = !configured
      ? 'provider unavailable'
      : !enabled
      ? 'disabled'
      : 'deterministic';
    badgeEl.textContent = `LLM Draft: OFF (deterministic) · ${reason}${lastRun}`;
  }

  async refreshRuntimeConfig({ silent = false } = {}) {
    try {
      const config = await fetchRuntimeConfig();
      this.runtimeConfig = config;
      this.updateRuntimeModeBadge();
      return config;
    } catch (error) {
      if (!silent) this.setStatus(String(error?.message || error));
      this.updateRuntimeModeBadge();
      return null;
    }
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

  async generate() {
    if (this.isGenerating) return;
    const persisted = this.persistCompanyContext();
    const payload = this.payload();
    const validation = this.validate(payload);
    if (validation) {
      this.setStatus(validation);
      return;
    }

    this.isGenerating = true;
    this.generateBtn.disabled = true;
    this.editor.reset();
    this.setStatus('Generating draft...', true);

    const start = performance.now();
    try {
      const accepted = await generateDraft(payload);
      this.sessionId = accepted.session_id;
      await this.streamIntoEditor(accepted.request_id);
      const elapsed = Math.round(performance.now() - start);
      this.editor.markComplete(elapsed);
      this.lastDraft = this.editor.getText();
      this.lastStyleKey = styleKey(payload.style_profile);
      this.setStatus(persisted ? 'Draft ready. Adjust sliders to remix.' : 'Draft ready.');
      this.saveRemixBtn.disabled = false;
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

    if (this.activeRemixController) {
      this.activeRemixController.abort();
    }
    const controller = new AbortController();
    this.activeRemixController = controller;

    this.isGenerating = true;
    this.generateBtn.disabled = true;
    this.setStatus('Remixing draft...', true);
    this.editor.reset();

    const start = performance.now();
    try {
      const accepted = await remixDraft({
        session_id: this.sessionId,
        preset_id: this.selectedPresetId,
        style_profile: style,
      });
      await this.streamIntoEditor(accepted.request_id, { signal: controller.signal });
      const elapsed = Math.round(performance.now() - start);
      this.editor.markComplete(elapsed);
      this.lastDraft = this.editor.getText();
      this.lastStyleKey = nextKey;
      this.setStatus('Remix applied.');
    } catch (error) {
      if (String(error?.name || '') !== 'AbortError') {
        this.setStatus(String(error?.message || error));
      }
    } finally {
      if (this.activeRemixController === controller) this.activeRemixController = null;
      this.isGenerating = false;
      this.generateBtn.disabled = false;
      this.statusLine.classList.remove('pulse');
    }
  }

  async streamIntoEditor(requestId, options = {}) {
    const streamState = createStreamState();
    let doneData = null;
    let finalText = '';

    await consumeStream(
      requestId,
      (msg) => {
        if (msg.event === 'progress') {
          const stage = String(msg?.data?.stage || '');
          const note = String(msg?.data?.message || '');
          this.setStatus(note || stage || 'Working...', true);
          return;
        }

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
          const finalSubject = typeof doneData?.final?.subject === 'string' ? doneData.final.subject.trim() : '';
          const finalBody = typeof outcome.finalBody === 'string' ? outcome.finalBody.trim() : '';
          if (finalSubject || finalBody) {
            const composed =
              finalSubject && finalBody && !finalBody.startsWith(finalSubject)
                ? `${finalSubject}\n\n${finalBody}`
                : finalBody || finalSubject;
            finalText = composed;
            this.editor.setContent(finalText);
            return;
          }
          if (streamState.streamBuffer) {
            finalText = streamState.streamBuffer;
            this.editor.setContent(finalText);
          }
        }
      },
      options
    );

    if (streamState.streamError) throw new Error(streamState.streamError);
    if (streamState.chunkSequenceMismatch) {
      throw new Error('Draft stream integrity check failed (chunk sequence mismatch).');
    }
    if (doneData?.stream_checksum) {
      const localChecksum = await sha256Hex(streamState.streamBuffer);
      if (localChecksum && localChecksum !== doneData.stream_checksum) {
        throw new Error('Draft stream integrity check failed (checksum mismatch).');
      }
    }
    const doneFinalBody = typeof doneData?.final?.body === 'string' ? doneData.final.body.trim() : '';
    const doneFinalSubject = typeof doneData?.final?.subject === 'string' ? doneData.final.subject.trim() : '';
    if (!this.editor.getText().trim() && !finalText.trim() && !doneFinalBody && !doneFinalSubject) {
      throw new Error('Draft stream completed without content.');
    }
    if (doneData?.sources) {
      this.editor.setSources(doneData.sources);
    }
    if (doneData) this.updateRuntimeModeBadge(doneData);
  }

  async runEnrichment(accepted, initialMessage) {
    let result = null;
    this.setStatus(initialMessage, true);
    await consumeStream(accepted.request_id, (msg) => {
      if (msg.event === 'progress') {
        this.setStatus(String(msg?.data?.message || msg?.data?.stage || 'Working...'), true);
        return;
      }
      if (msg.event === 'result') {
        result = msg?.data || null;
        return;
      }
      if (msg.event === 'error') {
        throw new Error(String(msg?.data?.error || 'Enrichment failed.'));
      }
    });
    this.statusLine.classList.remove('pulse');
    return result;
  }

  appendResearchBlock(title, lines, citations) {
    const existing = this.researchInput.value.trim();
    const body = stripUnknown(lines).join('\n- ');
    const cites = (Array.isArray(citations) ? citations : [])
      .map((item) => `- ${item.url || 'Unknown'} (published: ${item.published_at || 'Unknown'})`)
      .join('\n');
    const block = [
      `## ${title}`,
      body ? `- ${body}` : '- Unknown',
      cites ? 'Citations:\n' + cites : 'Citations:\n- Unknown',
    ].join('\n');
    this.researchInput.value = existing ? `${existing}\n\n${block}` : block;
    this.persistTargetDefaults();
  }

  parseDomainFromInput(raw) {
    const text = String(raw || '').trim();
    if (!text) return '';
    try {
      const value = text.includes('://') ? text : `https://${text}`;
      const host = new URL(value).hostname.replace(/^www\./i, '');
      return host || text.replace(/^https?:\/\//i, '').replace(/^www\./i, '').split('/')[0];
    } catch {
      return text.replace(/^https?:\/\//i, '').replace(/^www\./i, '').split('/')[0];
    }
  }

  async pollResearchJob(jobId, timeoutMs = 120000) {
    const started = Date.now();
    while (true) {
      const status = await fetchResearchJobStatus(jobId);
      const state = String(status?.status || '').toLowerCase();
      const progress = String(status?.progress || '').trim();
      if (progress) this.setStatus(progress, true);
      if (state === 'complete') return status;
      if (state === 'failed') {
        throw new Error(String(status?.error || 'Research job failed.'));
      }
      if (Date.now() - started > timeoutMs) {
        throw new Error('Research job timed out.');
      }
      await new Promise((resolve) => setTimeout(resolve, 1200));
    }
  }

  applyResearchResult(result) {
    if (!result) throw new Error('Research completed without a result payload.');

    if (typeof result === 'string') {
      const existing = this.researchInput.value.trim();
      this.researchInput.value = existing ? `${existing}\n\n${result}` : result;
      this.persistTargetDefaults();
      return;
    }

    const domain = String(result?.domain || '').trim();
    if (domain && domain.toLowerCase() !== 'unknown') {
      this.prospectCompanyUrlInput.value = `https://${domain}`;
    }

    const profile = {
      official_domain: domain || 'Unknown',
      summary: String(result?.summary || 'Unknown'),
      icp: String(result?.ICP || 'Unknown'),
      products: Array.isArray(result?.products) ? result.products : [],
      differentiators: Array.isArray(result?.differentiators) ? result.differentiators : [],
      proof_points: Array.isArray(result?.proof_points) ? result.proof_points : [],
      recent_news: Array.isArray(result?.news) ? result.news : [],
      citations: Array.isArray(result?.citations) ? result.citations : [],
      confidence: 0.6,
    };
    this.enrichedTargetProfile = profile;

    const summaryLines = [
      profile.summary,
      ...(profile.products || []).slice(0, 3).map((item) => `Product: ${item}`),
      ...(profile.differentiators || []).slice(0, 3).map((item) => `Differentiator: ${item}`),
      ...(profile.proof_points || []).slice(0, 3).map((item) => `Proof: ${item}`),
      ...(profile.recent_news || []).slice(0, 3).map((item) => `${item.date || 'Unknown'} — ${item.headline}: ${item.why_it_matters}`),
    ];
    this.appendResearchBlock('Target Account Research', summaryLines, profile.citations || []);
    this.targetRefreshMeta.textContent = `Last refreshed: ${nowPretty()}`;
    this.persistTargetDefaults();
  }

  async runCompanyResearch(refresh = false) {
    const companyName = this.prospectCompanyInput.value.trim();
    const domain = this.parseDomainFromInput(this.prospectCompanyUrlInput.value.trim());
    if (!companyName && !domain) {
      this.setStatus('Enter prospect company (or target company URL/domain) before running Company AI.');
      return;
    }

    const accountIdSource = companyName || domain;
    const accountId = String(accountIdSource || 'account')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 80) || 'account';

    try {
      this.setStatus(refresh ? 'Refreshing company research...' : 'Starting company research...', true);
      const accepted = await startResearchJob({
        account_id: accountId,
        domain: domain || null,
        company_name: companyName || null,
      });
      const completed = await this.pollResearchJob(accepted.job_id);
      this.applyResearchResult(completed?.result);
      this.setStatus('Company research complete.');
      this.statusLine.classList.remove('pulse');
    } catch (error) {
      this.setStatus(String(error?.message || error));
      this.statusLine.classList.remove('pulse');
    }
  }

  async enrichTarget(refresh = false) {
    const companyName = this.prospectCompanyInput.value.trim();
    const companyUrl = this.prospectCompanyUrlInput.value.trim();
    if (!companyName && !companyUrl) {
      this.setStatus('Enter prospect company (or target company URL) before running Target AI.');
      return;
    }
    try {
      const accepted = await startTargetEnrichment({
        company_name: companyName || null,
        company_url: companyUrl || null,
        refresh,
      });
      const result = await this.runEnrichment(accepted, 'Enriching target account...');
      const profile = result?.target_profile;
      if (!profile) throw new Error('Target enrichment returned no profile.');
      this.enrichedTargetProfile = profile;

      const domain = String(profile.official_domain || '').trim();
      if (domain && domain !== 'Unknown') {
        this.prospectCompanyUrlInput.value = `https://${domain}`;
      }
      const summaryLines = [
        profile.summary,
        ...(profile.products || []).slice(0, 3).map((item) => `Product: ${item}`),
        ...(profile.differentiators || []).slice(0, 3).map((item) => `Differentiator: ${item}`),
        ...(profile.proof_points || []).slice(0, 3).map((item) => `Proof: ${item}`),
        ...(profile.recent_news || []).slice(0, 3).map((item) => `${item.date || 'Unknown'} — ${item.headline}: ${item.why_it_matters}`),
      ];
      this.appendResearchBlock('Target Account Research', summaryLines, profile.citations || []);

      this.targetRefreshMeta.textContent = `Last refreshed: ${nowPretty()}`;
      this.setStatus('Target account enrichment complete.');
      this.persistTargetDefaults();
    } catch (error) {
      this.setStatus(String(error?.message || error));
    }
  }

  async enrichProspect(refresh = false) {
    const companyAnchor = this.prospectCompanyInput.value.trim() || this.prospectCompanyUrlInput.value.trim();
    if (!companyAnchor) {
      this.setStatus('Enter target company first, then run Prospect AI.');
      return;
    }
    const name = this.prospectNameInput.value.trim();
    if (!name) {
      this.setStatus('Enter prospect name before running Prospect AI.');
      return;
    }
    try {
      const accepted = await startProspectEnrichment({
        prospect_name: name,
        prospect_title: this.prospectTitleInput.value.trim() || null,
        prospect_company: this.prospectCompanyInput.value.trim() || null,
        prospect_linkedin_url: this.prospectLinkedinInput.value.trim() || null,
        target_company_name: this.prospectCompanyInput.value.trim() || null,
        target_company_url: this.prospectCompanyUrlInput.value.trim() || null,
        refresh,
      });
      const result = await this.runEnrichment(accepted, 'Enriching prospect profile...');
      const profile = result?.contact_profile;
      if (!profile) throw new Error('Prospect enrichment returned no profile.');
      this.enrichedContactProfile = profile;

      if (profile.current_title && profile.current_title !== 'Unknown') {
        this.prospectTitleInput.value = profile.current_title;
      }
      const lines = [
        profile.role_summary,
        ...(profile.talking_points || []).slice(0, 4),
        ...(profile.related_news || []).slice(0, 3).map((item) => `${item.date || 'Unknown'} — ${item.headline}: ${item.why_it_matters}`),
        ...(profile.inferred_kpis_or_priorities || []).slice(0, 3),
      ];
      this.appendResearchBlock('Prospect Research', lines, profile.citations || []);

      this.prospectRefreshMeta.textContent = `Last refreshed: ${nowPretty()}`;
      this.setStatus('Prospect enrichment complete.');
      this.persistTargetDefaults();
    } catch (error) {
      this.setStatus(String(error?.message || error));
    }
  }

  async enrichSender() {
    try {
      const accepted = await startSenderEnrichment({
        company_name: this.sellerCompanyNameInput.value.trim() || null,
        current_product: this.sellerCurrentProductInput.value.trim() || null,
        company_notes: this.sellerCompanyNotesInput.value.trim() || null,
        other_products: this.sellerOfferingsInput.value.trim() || null,
      });
      const result = await this.runEnrichment(accepted, 'Structuring sender profile...');
      const profile = result?.sender_profile;
      if (!profile) throw new Error('Sender enrichment returned no profile.');
      this.enrichedSenderProfile = profile;

      const lines = [];
      if (profile.structured_icp) lines.push(`ICP: ${profile.structured_icp}`);
      for (const d of profile.differentiation || []) lines.push(`Differentiation: ${d}`);
      for (const p of profile.proof_points || []) lines.push(`Proof: ${p}`);
      if (profile.notes_summary) lines.push(profile.notes_summary);
      this.sellerCompanyNotesInput.value = lines.join('\n');
      this.senderRefreshMeta.textContent = `Last refreshed: ${nowPretty()}`;
      this.persistCompanyContext();
      this.setStatus('Sender profile structured.');
    } catch (error) {
      this.setStatus(String(error?.message || error));
    }
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
      await navigator.clipboard.writeText(draftAfter);
      this.lastDraft = draftAfter;
      this.setStatus('Remix saved and copied.');
    } catch (error) {
      this.setStatus(String(error?.message || error));
    }
  }
}

new WebApp(document.getElementById('app'));
