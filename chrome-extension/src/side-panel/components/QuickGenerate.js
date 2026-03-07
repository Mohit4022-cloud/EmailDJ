/** Main Quick Generate UI component. */

import { generateEmail, pollAssignments } from '../hub-client.js';
import { ContextSummary } from './ContextSummary.js';
import { EmailEditor } from './EmailEditor.js';
import { PersonalizationSlider } from './PersonalizationSlider.js';

export class QuickGenerate {
  constructor(container) {
    this.container = container;
    this.state = 'idle';
    this.currentPayload = null;
    this.currentTokenMap = {};
    this.sliderValue = 5;
    this.emailEditor = null;
    this.personalizationSlider = null;
    this._pollInterval = null;
    this._listenersAttached = false;
    this._handlers = null;
    this.render();
    this.setupMessageListener();
    this.pollAssignmentsOnMount();
  }

  setupMessageListener() {
    if (this._listenersAttached) return;
    this._listenersAttached = true;
    chrome.runtime.onMessage.addListener((msg) => {
      if (msg.type === 'PAYLOAD_READY') {
        this.currentPayload = msg.payload;
        this.currentTokenMap = msg.tokenMap || {};
        this.setState('idle');
      }
    });
  }

  pollAssignmentsOnMount() {
    pollAssignments().then(({ count }) => {
      if (count > 0) this.showAssignmentBadge(count);
    }).catch(() => {});
    if (!this._pollInterval) {
      this._pollInterval = setInterval(() => this.pollAssignmentsOnMount(), 30000);
    }
  }

  render() {
    this.container.innerHTML = `
      <div class="quick-generate">
        <div class="context-summary" id="contextSummary"></div>
        <div class="slider-container" id="sliderContainer">
        </div>
        <button id="generateBtn" class="generate-btn">Generate Email</button>
        <button id="retryBtn" class="generate-btn" style="display:none; margin-top:8px;">Retry</button>
        <div id="statusLine" style="margin-top:8px; font-size:12px; color:#666;"></div>
        <div class="email-editor-container" id="emailEditorContainer" style="display:none;"></div>
      </div>
    `;

    this.contextSummary = new ContextSummary(this.container.querySelector('#contextSummary'));
    this.contextSummary.update(this.currentPayload, null);

    const sliderContainer = this.container.querySelector('#sliderContainer');
    if (sliderContainer) {
      this.personalizationSlider = new PersonalizationSlider(sliderContainer, (value) => {
        this.sliderValue = value;
      });
      this.personalizationSlider.setValue(this.sliderValue);
    }

    this.container.querySelector('#generateBtn')?.addEventListener('click', () => this.onGenerateClick());
    this.container.querySelector('#retryBtn')?.addEventListener('click', () => this.onGenerateClick());
  }

  setState(newState, errorText = '') {
    this.state = newState;
    const status = this.container.querySelector('#statusLine');
    const btn = this.container.querySelector('#generateBtn');
    const retryBtn = this.container.querySelector('#retryBtn');
    if (!status || !btn || !retryBtn) return;

    if (newState === 'idle') {
      status.textContent = this.currentPayload ? 'Context ready.' : 'Open a Salesforce Account record to begin.';
      btn.disabled = !this.currentPayload;
      retryBtn.style.display = 'none';
      this.contextSummary.update(this.currentPayload, null);
    } else if (newState === 'generating') {
      status.textContent = 'Generating draft...';
      btn.disabled = true;
      retryBtn.style.display = 'none';
    } else if (newState === 'complete') {
      status.textContent = 'Draft complete.';
      btn.disabled = false;
      retryBtn.style.display = 'none';
    } else if (newState === 'error') {
      status.textContent = errorText || 'Generation failed. Please retry.';
      btn.disabled = false;
      retryBtn.style.display = 'block';
    }
  }

  onGenerateClick() {
    if (!this.currentPayload) return;

    this.setState('generating');
    const editorContainer = this.container.querySelector('#emailEditorContainer');
    editorContainer.style.display = 'block';
    editorContainer.innerHTML = '';
    this.emailEditor = new EmailEditor(editorContainer);

    if (this._handlers) {
      window.removeEventListener('emailToken', this._handlers.onToken);
      window.removeEventListener('emailComplete', this._handlers.onComplete);
      window.removeEventListener('emailError', this._handlers.onError);
    }

    const onToken = (ev) => this.emailEditor?.appendToken(ev.detail || '');
    const onComplete = () => {
      this.emailEditor?.markComplete();
      this.setState('complete');
      cleanup();
    };
    const onError = (ev) => {
      this.setState('error', ev?.detail || 'Generation failed. Please retry.');
      cleanup();
    };
    const onRetry = () => {
      this.emailEditor?.clear();
      this.setState('generating');
    };

    const cleanup = () => {
      window.removeEventListener('emailToken', onToken);
      window.removeEventListener('emailComplete', onComplete);
      window.removeEventListener('emailError', onError);
      window.removeEventListener('emailRetry', onRetry);
      this._handlers = null;
    };

    this._handlers = { onToken, onComplete, onError, onRetry };
    window.addEventListener('emailToken', onToken);
    window.addEventListener('emailComplete', onComplete);
    window.addEventListener('emailError', onError);
    window.addEventListener('emailRetry', onRetry);

    generateEmail(this.currentPayload, this.sliderValue).catch((err) => {
      this.setState('error', String(err?.message || err));
      cleanup();
    });
  }

  showAssignmentBadge(count) {
    const badge = document.getElementById('assignmentBadge');
    if (!badge) return;
    badge.textContent = String(count);
    badge.style.display = 'inline-block';
  }
}
