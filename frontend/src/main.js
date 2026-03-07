import './styles.css';
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
import { buildStageTimeline, buildTraceMeta, buildValidationNotes, classifyStudioStatus } from './studioStatus.js';
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

function sliderStateToGenerationSliders(sliderState) {
  const state = sliderState || {};
  const tone = 1 - (Number(state.formality || 50) / 100);
  const framing = Number(state.orientation || 50) / 100;
  const stance = Number(state.assertiveness || 50) / 100;
  const lengthValue = Number(state.length || 50);
  let length = 'medium';
  if (lengthValue <= 33) length = 'short';
  else if (lengthValue >= 67) length = 'long';
  return {
    tone: Math.max(0, Math.min(1, Number(tone.toFixed(2)))),
    framing: Math.max(0, Math.min(1, Number(framing.toFixed(2)))),
    length,
    stance: Math.max(0, Math.min(1, Number(stance.toFixed(2)))),
  };
}

function stripUnknown(items = []) {
  return (Array.isArray(items) ? items : []).map((item) => String(item || '').trim()).filter(Boolean);
}

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function shortId(value) {
  const text = String(value || '').trim();
  if (!text) return 'Not started';
  return text.length <= 12 ? text : `${text.slice(0, 8)}...`;
}

function stageStatusClass(status) {
  const normalized = String(status || 'pending').trim().toLowerCase().replaceAll('_', '-');
  if (normalized.includes('fail') || normalized.includes('error')) return 'status-failed';
  if (normalized.includes('pass')) return 'status-passed';
  if (normalized.includes('complete') || normalized.includes('ready')) return 'status-complete';
  if (normalized.includes('rewrite')) return 'status-loading';
  return `status-${normalized || 'pending'}`;
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
    this.lastDoneData = null;
    this.lastStageEvents = [];
    this.currentSources = [];
    this.lastRunAt = '';
    this.statusTone = 'neutral';
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
      <div class="studio-shell">
        <section class="studio-hero">
          <div class="hero-copy">
            <p class="eyebrow">AI-first outbound drafting</p>
            <h1>EmailDJ Remix Studio</h1>
            <p class="hero-body">Build one reusable messaging brief from seller and prospect context, then remix delivery without changing the facts, proof, or CTA lock.</p>
            <div class="hero-trust-row">
              <span class="hero-tag">Fail closed output</span>
              <span class="hero-tag">Stable MessagingBrief logic</span>
              <span class="hero-tag">Deterministic validators visible</span>
            </div>
          </div>
          <div class="hero-side">
            <div id="runtimeModeBadge" class="runtime-mode-badge mode-loading">Checking runtime mode...</div>
            <section class="hero-status-card" id="statusCard" data-tone="neutral">
              <p class="eyebrow">System status</p>
              <div class="hero-status-copy">
                <h2 class="status-headline" id="statusHeadline">Ready to steer</h2>
                <div class="status" id="statusLine">Seller context + prospect context feed one reusable intelligence artifact. Generate once, then remix the expression.</div>
              </div>
              <div class="hero-actions">
                <button class="btn-primary" id="generateBtn">Generate Draft</button>
                <button class="btn-secondary" id="saveRemixBtn" disabled>Save Remix</button>
              </div>
            </section>
          </div>
        </section>

        <div class="studio-layout">
          <aside class="control-rail">
            <section class="step-card">
              <div class="step-head">
                <div>
                  <p class="eyebrow">Step 1</p>
                  <h2>Seller context</h2>
                  <p class="step-copy">Capture the stable business truth the draft should preserve across every preset, slider move, and rewrite.</p>
                </div>
                <div class="step-tag">Reusable brief input</div>
              </div>
              <div class="field-stack">
                <div class="field">
                  <label>Beta Key</label>
                  <input id="betaKey" placeholder="dev-beta-key" />
                </div>
                <div class="field">
                  <label>Your Company Name (saved locally)</label>
                  <input id="sellerCompanyName" placeholder="EmailDJ" />
                </div>
                <div class="row">
                  <div class="field">
                    <label>Company URL</label>
                    <input id="sellerCompanyUrl" placeholder="https://yourcompany.com" />
                  </div>
                  <div class="field">
                    <label>Current Product / Service to Pitch</label>
                    <input id="sellerCurrentProduct" placeholder="Remix Studio" />
                  </div>
                </div>
                <div class="field">
                  <label>Seller Offerings (what you sell)</label>
                  <textarea id="sellerOfferings" class="compact" placeholder="Brand monitoring&#10;Trademark enforcement&#10;Marketplace takedowns"></textarea>
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
                  <div class="label-row">
                    <span>Company Notes (proof points, ICP, differentiation)</span>
                    <span class="action-row">
                      <button class="btn-secondary" id="senderAiBtn" type="button">AI Clean / Structure</button>
                    </span>
                  </div>
                  <textarea id="sellerCompanyNotes" class="compact" placeholder="What your product does best, who it helps, and why it wins."></textarea>
                  <small id="senderRefreshMeta" class="meta"></small>
                </div>
                <div class="field">
                  <label>Internal Modules (never shared with generation)</label>
                  <textarea id="sellerInternalModules" class="compact" placeholder="Internal workflow tags only"></textarea>
                </div>
              </div>
            </section>

            <section class="step-card">
              <div class="step-head">
                <div>
                  <p class="eyebrow">Step 2</p>
                  <h2>Prospect context</h2>
                  <p class="step-copy">Ground the draft in the actual person and account, then enrich only through cited, tool-based research.</p>
                </div>
                <div class="step-tag">Account + person</div>
              </div>
              <div class="field-stack">
                <div class="row">
                  <div class="field">
                    <label>Prospect Name</label>
                    <input id="prospectName" placeholder="Alex Doe" />
                  </div>
                  <div class="field">
                    <div class="label-row">
                      <span>Title</span>
                      <span class="action-row">
                        <button class="btn-secondary" id="prospectAiBtn" type="button">AI</button>
                        <button class="btn-secondary" id="prospectRefreshBtn" type="button">Refresh</button>
                      </span>
                    </div>
                    <input id="prospectTitle" placeholder="SDR Manager" />
                    <small id="prospectRefreshMeta" class="meta"></small>
                  </div>
                </div>
                <div class="row">
                  <div class="field">
                    <div class="label-row">
                      <span>Company</span>
                      <span class="action-row">
                        <button class="btn-secondary" id="targetAiBtn" type="button">AI</button>
                        <button class="btn-secondary" id="targetRefreshBtn" type="button">Refresh</button>
                      </span>
                    </div>
                    <input id="prospectCompany" placeholder="Acme" />
                    <small id="targetRefreshMeta" class="meta"></small>
                  </div>
                  <div class="field">
                    <label>LinkedIn URL (optional)</label>
                    <input id="prospectLinkedin" placeholder="https://linkedin.com/in/..." />
                  </div>
                </div>
                <div class="field">
                  <label>Target Company URL/domain (optional)</label>
                  <input id="prospectCompanyUrl" placeholder="https://acme.com" />
                </div>
              </div>
            </section>

            <section class="step-card">
              <div class="step-head">
                <div>
                  <p class="eyebrow">Step 3</p>
                  <h2>Research and evidence</h2>
                  <p class="step-copy">Paste the high-signal research that should anchor the stable brief. Enrichment appends cited context instead of guessing.</p>
                </div>
                <div class="step-tag">Tool-only retrieval</div>
              </div>
              <div class="field-stack">
                <div class="field">
                  <label>Deep Research Paste</label>
                  <textarea id="researchText" placeholder="Paste account/prospect research here..."></textarea>
                </div>
              </div>
            </section>
          </aside>

          <main class="workspace-column">
            <section class="workspace-card">
              <div class="workspace-head">
                <div class="workspace-copy">
                  <p class="eyebrow">Step 4</p>
                  <h2>Draft workspace</h2>
                  <p class="workspace-copy">Presets and sliders sculpt expression only. The brief, proof, and CTA logic stay grounded to the same run.</p>
                </div>
                <div class="summary-chip-row">
                  <span class="session-chip" id="sessionChip">Session · Not started</span>
                  <span class="preset-chip" id="workspacePresetChip">Preset · Straight Shooter</span>
                </div>
              </div>

              <div class="workspace-shell">
                <div class="preset-summary-card">
                  <div class="preset-summary-head">
                    <div>
                      <p class="eyebrow">Preset overlay</p>
                      <h3 class="preset-summary-title" id="selectedPresetName">Straight Shooter</h3>
                    </div>
                    <div id="presetLibraryMount"></div>
                  </div>
                  <p class="preset-summary-copy" id="selectedPresetCopy">Direct wedge + proof + focused CTA.</p>
                  <div class="summary-chip-row" id="selectedPresetMeta"></div>
                </div>

                <div id="sliderBoard"></div>
                <div id="editorMount"></div>
              </div>
            </section>

            <section class="diagnostics-grid">
              <article class="diagnostic-card">
                <div class="diagnostic-head">
                  <div>
                    <p class="eyebrow">System</p>
                    <h3>Run confidence</h3>
                  </div>
                </div>
                <div class="signal-grid" id="signalGrid"></div>
              </article>

              <article class="diagnostic-card">
                <div class="diagnostic-head">
                  <div>
                    <p class="eyebrow">Step 5</p>
                    <h3>QA and trace</h3>
                  </div>
                </div>
                <div class="trace-meta-grid" id="traceMeta"></div>
                <ul class="validation-list" id="validationList"></ul>
                <ul class="trace-list" id="traceTimeline"></ul>
              </article>

              <article class="diagnostic-card">
                <div class="diagnostic-head">
                  <div>
                    <p class="eyebrow">Grounding</p>
                    <h3>Sources</h3>
                  </div>
                </div>
                <div class="diagnostic-empty" id="sourcesEmpty">Sources from enrichment and generation will appear here after a run.</div>
                <ul class="source-list" id="sourcesList"></ul>
              </article>
            </section>
          </main>
        </div>
      </div>
    `;

    this.statusLine = this.root.querySelector('#statusLine');
    this.statusHeadline = this.root.querySelector('#statusHeadline');
    this.statusCard = this.root.querySelector('#statusCard');
    this.runtimeModeBadgeEl = this.root.querySelector('#runtimeModeBadge');
    this.generateBtn = this.root.querySelector('#generateBtn');
    this.saveRemixBtn = this.root.querySelector('#saveRemixBtn');
    this.presetLibraryMount = this.root.querySelector('#presetLibraryMount');
    this.sessionChip = this.root.querySelector('#sessionChip');
    this.workspacePresetChip = this.root.querySelector('#workspacePresetChip');
    this.selectedPresetNameEl = this.root.querySelector('#selectedPresetName');
    this.selectedPresetCopyEl = this.root.querySelector('#selectedPresetCopy');
    this.selectedPresetMetaEl = this.root.querySelector('#selectedPresetMeta');
    this.signalGrid = this.root.querySelector('#signalGrid');
    this.traceMeta = this.root.querySelector('#traceMeta');
    this.validationList = this.root.querySelector('#validationList');
    this.traceTimeline = this.root.querySelector('#traceTimeline');
    this.sourcesEmpty = this.root.querySelector('#sourcesEmpty');
    this.sourcesList = this.root.querySelector('#sourcesList');

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
    this.setStatus('Seller context + prospect context feed one reusable intelligence artifact. Generate once, then remix the expression.');
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
    const sliderState = this.sliderBoard.getValues();

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
      mode: 'single',
      preset_id: this.selectedPresetId,
      style_profile: styleToPayload(sliderState),
      sliders: sliderStateToGenerationSliders(sliderState),
      company_context: companyCtx,
      sender_profile_override: this.enrichedSenderProfile || null,
      target_profile_override: this.enrichedTargetProfile || null,
      contact_profile_override: this.enrichedContactProfile || null,
      pipeline_meta: {
        mode: 'generate',
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

  selectedPreset() {
    return SDR_PRESETS.find(
      (preset) => String(preset.strategy_id || preset.id || '') === String(this.selectedPresetId || '')
    ) || SDR_PRESETS[0] || null;
  }

  syncPresetSummary() {
    const preset = this.selectedPreset();
    if (!preset) return;
    if (this.selectedPresetNameEl) this.selectedPresetNameEl.textContent = preset.name;
    if (this.selectedPresetCopyEl) this.selectedPresetCopyEl.textContent = preset.vibe || preset.whyItWorks || '';
    if (this.selectedPresetMetaEl) {
      this.selectedPresetMetaEl.innerHTML = [
        `<span class="summary-chip">${escapeHtml(preset.frequency || 'Preset')}</span>`,
        `<span class="summary-chip">${escapeHtml(preset.eqVibe || 'Style modifier')}</span>`,
        `<span class="summary-chip">Brief stays locked</span>`,
      ].join('');
    }
    if (this.workspacePresetChip) this.workspacePresetChip.textContent = `Preset · ${preset.name}`;
    if (this.sessionChip) {
      this.sessionChip.textContent = this.sessionId ? `Session · ${shortId(this.sessionId)}` : 'Session · Not started';
    }
  }

  syncDiagnostics() {
    this.syncPresetSummary();

    const statusInfo = classifyStudioStatus(this.statusLine?.textContent || '', this.statusLine?.classList.contains('pulse'));
    this.statusTone = statusInfo.tone;
    if (this.statusHeadline) this.statusHeadline.textContent = statusInfo.title;
    if (this.statusCard) this.statusCard.dataset.tone = statusInfo.tone;

    const preset = this.selectedPreset();
    const stageStats = Array.isArray(this.lastDoneData?.stage_stats) ? this.lastDoneData.stage_stats : [];
    const validationNotes = buildValidationNotes(stageStats, this.lastDoneData);
    const traceMeta = buildTraceMeta(this.lastDoneData);
    const stageTimeline = buildStageTimeline(stageStats, this.lastStageEvents);

    if (this.signalGrid) {
      const signalCards = [
        {
          label: 'Run state',
          value: statusInfo.title,
          detail: statusInfo.detail,
        },
        {
          label: 'Current preset',
          value: preset?.name || 'Not selected',
          detail: preset?.whyItWorks || 'Presets act as style modifiers, not separate template worlds.',
        },
        {
          label: 'Remix guardrail',
          value: 'Stable brief',
          detail: 'Slider changes keep the same narrative, proof, and CTA lock.',
        },
        {
          label: 'Last completed',
          value: this.lastRunAt || 'No completed run',
          detail: this.lastDoneData?.repaired
            ? `Repair loop applied ${Number(this.lastDoneData?.repair_attempt_count || 1)}x before final output.`
            : 'Deterministic validators remain active on every run.',
        },
      ];
      this.signalGrid.innerHTML = signalCards
        .map(
          (item) => `
            <section class="signal-card">
              <span class="signal-label">${escapeHtml(item.label)}</span>
              <div class="signal-value">${escapeHtml(item.value)}</div>
              <p class="signal-detail">${escapeHtml(item.detail)}</p>
            </section>
          `
        )
        .join('');
    }

    if (this.traceMeta) {
      this.traceMeta.innerHTML = traceMeta.length
        ? traceMeta
            .map(
              ([label, value]) => `
                <div class="trace-meta">
                  <span>${escapeHtml(label)}</span>
                  <code>${escapeHtml(value)}</code>
                </div>
              `
            )
            .join('')
        : `<div class="diagnostic-empty">No trace metadata yet. Generate a draft to inspect the run contract.</div>`;
    }

    if (this.validationList) {
      this.validationList.innerHTML = validationNotes.length
        ? validationNotes
            .map(
              (item) => `
                <li class="validation-item">
                  <span class="validation-code ${stageStatusClass(item.code)}">${escapeHtml(String(item.code).replaceAll('_', ' '))}</span>
                  <span>${escapeHtml(item.message)}</span>
                </li>
              `
            )
            .join('')
        : `<li class="validation-item"><span>No validator exceptions on the current draft.</span></li>`;
    }

    if (this.traceTimeline) {
      this.traceTimeline.innerHTML = stageTimeline.length
        ? stageTimeline
            .map(
              (item) => `
                <li class="trace-item">
                  <div class="trace-item-head">
                    <span class="trace-stage">${escapeHtml(item.label)}</span>
                    <span class="trace-stage-status ${stageStatusClass(item.status)}">${escapeHtml(String(item.status || 'pending').replaceAll('_', ' '))}</span>
                  </div>
                  <div class="trace-stage-meta">
                    ${escapeHtml(
                      [item.elapsedMs ? `${item.elapsedMs}ms` : '', item.model || '', item.finalValidationStatus || item.rawValidationStatus || '']
                        .filter(Boolean)
                        .join(' · ')
                    )}
                  </div>
                </li>
              `
            )
            .join('')
        : `<li class="trace-item"><span class="diagnostic-empty">Stage events will stream here as soon as generation starts.</span></li>`;
    }

    if (this.sourcesList && this.sourcesEmpty) {
      this.sourcesList.innerHTML = this.currentSources
        .map((item) => {
          const url = String(item?.url || '').trim();
          const published = String(item?.published_at || 'Unknown').trim();
          const retrieved = String(item?.retrieved_at || 'Unknown').trim();
          const link = url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a>` : 'Unknown';
          return `
            <li class="source-item">
              <div class="source-item-head">
                <span class="source-chip">Source</span>
                <span class="source-item-meta">published ${escapeHtml(published)}</span>
              </div>
              <div>${link}</div>
              <div class="source-item-meta">retrieved ${escapeHtml(retrieved)}</div>
            </li>
          `;
        })
        .join('');
      this.sourcesEmpty.style.display = this.currentSources.length ? 'none' : '';
    }
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
    this.statusCard?.classList.toggle('pulse', pulse);
    this.syncDiagnostics();
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
      this.syncDiagnostics();
      return;
    }

    badgeEl.className = 'runtime-mode-badge mode-unknown';
    const reason = !configured
      ? 'provider unavailable'
      : !enabled
      ? 'disabled'
      : 'deterministic';
    badgeEl.textContent = `LLM Draft: OFF (deterministic) · ${reason}${lastRun}`;
    this.syncDiagnostics();
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
    this.syncDiagnostics();
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
    this.lastDoneData = null;
    this.lastStageEvents = [];
    this.currentSources = [];
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
      this.lastRunAt = nowPretty();
      this.setStatus(persisted ? 'Draft ready. Adjust sliders to remix.' : 'Draft ready.');
      this.saveRemixBtn.disabled = false;
    } catch (error) {
      this.setStatus(String(error?.message || error));
    } finally {
      this.isGenerating = false;
      this.generateBtn.disabled = false;
      this.statusLine.classList.remove('pulse');
      this.statusCard?.classList.remove('pulse');
      this.syncDiagnostics();
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
    this.lastDoneData = null;
    this.lastStageEvents = [];
    this.currentSources = [];
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
      this.lastRunAt = nowPretty();
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
      this.statusCard?.classList.remove('pulse');
      this.syncDiagnostics();
    }
  }

  async streamIntoEditor(requestId, options = {}) {
    const streamState = createStreamState();
    let doneData = null;
    let finalText = '';

    await consumeStream(
      requestId,
      (msg) => {
        if (msg.event === 'stage' || msg.event === 'progress') {
          const stage = String(msg?.data?.stage || '');
          const status = String(msg?.data?.status || '');
          const note = String(msg?.data?.message || '');
          if (msg.event === 'stage') {
            const nextStage = {
              stage,
              status,
              elapsed_ms: Number(msg?.data?.elapsed_ms || 0),
              model: String(msg?.data?.model || ''),
            };
            const existingIndex = this.lastStageEvents.findIndex((item) => String(item?.stage || '') === stage);
            if (existingIndex >= 0) this.lastStageEvents.splice(existingIndex, 1, nextStage);
            else this.lastStageEvents.push(nextStage);
            this.syncDiagnostics();
          }
          this.setStatus(note || [stage, status].filter(Boolean).join(' · ') || 'Working...', true);
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
          if (doneData && doneData.ok === false) {
            const err = doneData?.error || {};
            const trace = doneData?.trace_id ? ` (trace: ${doneData.trace_id})` : '';
            streamState.streamError = `${String(err?.message || 'Generation failed')}${trace}`;
            return;
          }
          const variants = Array.isArray(doneData?.variants) ? doneData.variants : [];
          if (variants.length > 0) {
            const successCount = variants.filter(
              (item) =>
                typeof item?.subject === 'string' &&
                item.subject.trim() &&
                typeof item?.body === 'string' &&
                item.body.trim()
            ).length;
            const failureCount = Math.max(0, variants.length - successCount);
            if (failureCount > 0) {
              this.setStatus(`Generated ${successCount}/${variants.length} preset variants.`);
            } else {
              this.setStatus(`Generated ${variants.length} preset variants.`);
            }
          }
          const finalSubject =
            typeof doneData?.subject === 'string'
              ? doneData.subject.trim()
              : typeof doneData?.final?.subject === 'string'
              ? doneData.final.subject.trim()
              : typeof outcome.finalSubject === 'string'
              ? outcome.finalSubject.trim()
              : '';
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
    const doneFinalBody =
      typeof doneData?.body === 'string'
        ? doneData.body.trim()
        : typeof doneData?.final?.body === 'string'
        ? doneData.final.body.trim()
        : '';
    const doneFinalSubject =
      typeof doneData?.subject === 'string'
        ? doneData.subject.trim()
        : typeof doneData?.final?.subject === 'string'
        ? doneData.final.subject.trim()
        : (() => {
            const variants = Array.isArray(doneData?.variants) ? doneData.variants : [];
            const first = variants.find(
              (item) =>
                typeof item?.subject === 'string' &&
                item.subject.trim() &&
                typeof item?.body === 'string' &&
                item.body.trim()
            );
            return typeof first?.subject === 'string' ? first.subject.trim() : '';
          })();
    if (!this.editor.getText().trim() && !finalText.trim() && !doneFinalBody && !doneFinalSubject) {
      throw new Error('Draft stream completed without content.');
    }
    if (doneData?.sources) {
      this.currentSources = Array.isArray(doneData.sources) ? doneData.sources : [];
      this.editor.setSources(doneData.sources);
    }
    this.lastDoneData = doneData || null;
    if (doneData) this.updateRuntimeModeBadge(doneData);
    this.syncDiagnostics();
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
    this.statusCard?.classList.remove('pulse');
    this.syncDiagnostics();
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
      this.statusCard?.classList.remove('pulse');
      this.syncDiagnostics();
    } catch (error) {
      this.setStatus(String(error?.message || error));
      this.statusLine.classList.remove('pulse');
      this.statusCard?.classList.remove('pulse');
      this.syncDiagnostics();
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
