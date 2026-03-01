import { consumeStream, generateDraft, remixDraft, sendFeedback } from './api/client.js';
import { EmailEditor } from './components/EmailEditor.js';
import { SliderBoard } from './components/SliderBoard.js';
import { styleToPayload, styleKey } from './style.js';
import { debounce } from './utils.js';

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

    this.editor = new EmailEditor(this.root.querySelector('#editorMount'));
    this.sliderBoard = new SliderBoard(this.root.querySelector('#sliderBoard'), () => this.onSlidersChanged());

    this.seedBetaKey();

    this.generateBtn.addEventListener('click', () => this.generate());
    this.saveRemixBtn.addEventListener('click', () => this.saveRemix());
    this.betaKeyInput.addEventListener('change', () => {
      window.localStorage.setItem('emaildj_beta_key', this.betaKeyInput.value.trim() || 'dev-beta-key');
    });

    this.setStatus('Ready. Fill inputs and click Generate.');
  }

  seedBetaKey() {
    const key = window.localStorage.getItem('emaildj_beta_key') || 'dev-beta-key';
    window.localStorage.setItem('emaildj_beta_key', key);
    this.betaKeyInput.value = key;
  }

  payload() {
    return {
      prospect: {
        name: this.root.querySelector('#prospectName').value.trim(),
        title: this.root.querySelector('#prospectTitle').value.trim(),
        company: this.root.querySelector('#prospectCompany').value.trim(),
        linkedin_url: this.root.querySelector('#prospectLinkedin').value.trim() || null,
      },
      research_text: this.root.querySelector('#researchText').value.trim(),
      style_profile: styleToPayload(this.sliderBoard.getValues()),
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
      this.setStatus('Draft ready. Adjust sliders to remix.');
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
