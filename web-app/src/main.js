import { consumeStream, generateDraft, remixDraft, sendFeedback } from './api/client.js';
import { EmailEditor } from './components/EmailEditor.js';
import { SDRPresetLibrary, presetToSliderState } from './components/SDRPresetLibrary.js';
import { SliderBoard } from './components/SliderBoard.js';
import { SDR_PRESETS } from './data/sdrPresets.js';
import { styleToPayload, styleKey } from './style.js';
import { debounce } from './utils.js';

const DEFAULT_COMPANY_CONTEXT = {
  company_name: 'Corsearch',
  company_url: 'https://corsearch.com',
  current_product: 'Trademark Search, Screening, and Brand Protection',
  other_products: 'Trademark Watching\nOnline Brand Protection\nDomain Monitoring',
  company_notes:
    'Corsearch helps legal and brand teams reduce trademark risk and protect brands across domains, marketplaces, and social platforms.',
};

const DEFAULT_TARGET_CONTEXT = {
  name: 'Alex Karp',
  title: 'CEO',
  company: 'Palantir',
  linkedin_url: '',
};

const DEFAULT_RESEARCH_TEXT =
  'Palantir is scaling enterprise AI initiatives through AIP and high-stakes government/commercial deployments. Outreach should stay executive-level, tie messaging quality to pipeline outcomes, and propose a low-friction pilot that shows measurable reply and conversion lift.';

function chooseDefaultString(value, fallback) {
  if (typeof value !== 'string') return fallback;
  return value.trim() ? value : fallback;
}

class WebApp {
  constructor(root) {
    this.root = root;
    this.sessionId = null;
    this.isGenerating = false;
    this.lastDraft = '';
    this.lastStyleKey = '';
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
      <div class="hero">
        <h1>EmailDJ Remix Studio</h1>
        <p>Paste research, generate once, then sculpt the draft with live sliders.</p>
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
            <label>Other Products / Services (used for mapping)</label>
            <textarea id="sellerOtherProducts" class="compact" placeholder="Prospect Enrichment&#10;Sequence QA&#10;Persona Research"></textarea>
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
    this.generateBtn = this.root.querySelector('#generateBtn');
    this.saveRemixBtn = this.root.querySelector('#saveRemixBtn');
    this.betaKeyInput = this.root.querySelector('#betaKey');
    this.presetLibraryMount = this.root.querySelector('#presetLibraryMount');
    this.sellerCompanyNameInput = this.root.querySelector('#sellerCompanyName');
    this.sellerCompanyUrlInput = this.root.querySelector('#sellerCompanyUrl');
    this.sellerCurrentProductInput = this.root.querySelector('#sellerCurrentProduct');
    this.sellerOtherProductsInput = this.root.querySelector('#sellerOtherProducts');
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
      this.sellerCompanyNotesInput,
    ]) {
      input?.addEventListener('input', () => this.persistCompanyContext());
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

    this.setStatus('Ready. Fill inputs and click Generate.');
  }

  applyPreset(preset) {
    if (!preset) return;
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
      other_products: chooseDefaultString(saved.other_products, DEFAULT_COMPANY_CONTEXT.other_products),
      company_notes: chooseDefaultString(saved.company_notes, DEFAULT_COMPANY_CONTEXT.company_notes),
    };
    this.sellerCompanyNameInput.value = merged.company_name;
    this.sellerCompanyUrlInput.value = merged.company_url;
    this.sellerCurrentProductInput.value = merged.current_product;
    this.sellerOtherProductsInput.value = merged.other_products;
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
    return {
      prospect: {
        name: this.prospectNameInput.value.trim(),
        title: this.prospectTitleInput.value.trim(),
        company: this.prospectCompanyInput.value.trim(),
        linkedin_url: this.prospectLinkedinInput.value.trim() || null,
      },
      research_text: this.researchInput.value.trim(),
      style_profile: styleToPayload(this.sliderBoard.getValues()),
      company_context: this.companyContextPayload(),
    };
  }

  validate(data) {
    if (!data.prospect.name || !data.prospect.title || !data.prospect.company) return 'Prospect name, title, and company are required.';
    if (!data.research_text || data.research_text.length < 20) return 'Paste at least 20 characters of research.';
    return '';
  }

  setStatus(text, pulse = false) {
    this.statusLine.textContent = text;
    this.statusLine.classList.toggle('pulse', pulse);
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

    this.isGenerating = true;
    this.generateBtn.disabled = true;
    this.setStatus('Remixing draft...', true);
    this.editor.reset();
    this.dispatchMetric('web_remix_started');

    const start = performance.now();
    try {
      const accepted = await remixDraft({ session_id: this.sessionId, style_profile: style });
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
    await consumeStream(requestId, (msg) => {
      if (msg.event === 'token') {
        this.editor.appendToken(msg.data?.token || '');
      }
    });
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
