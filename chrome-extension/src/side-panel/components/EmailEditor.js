/**
 * EmailEditor — Streaming email display and editing component.
 *
 * IMPLEMENTATION INSTRUCTIONS:
 *
 * Exports: EmailEditor (class)
 *
 * Constructor(container: HTMLElement):
 *   Creates a contenteditable div for the email body.
 *   Stores original AI draft for captureEdit() diff.
 *
 * appendToken(token: string):
 *   Called for each SSE token during streaming.
 *   Append token to the contenteditable div's textContent.
 *   Implementation: append to a text node (not innerHTML) to avoid XSS.
 *   const textNode = document.createTextNode(token);
 *   this.editorEl.appendChild(textNode);
 *   this.editorEl.scrollTop = this.editorEl.scrollHeight;
 *
 * markComplete():
 *   Called when SSE 'done' event fires.
 *   - Save this.originalDraft = this.editorEl.innerText (the AI-generated version)
 *   - Show action buttons: Copy, "Send via Gmail", "Send via Outreach" (stub)
 *   - Add blur listener to detect edits: capture edited version for feedback.
 *
 * onCopyClick():
 *   navigator.clipboard.writeText(this.editorEl.innerText)
 *   Show "Copied!" flash (brief CSS transition).
 *
 * onSendGmailClick():
 *   const subject = this.extractSubject();  // first line of email or "Re: {AccountName}"
 *   const body = encodeURIComponent(this.editorEl.innerText);
 *   window.open(`mailto:?subject=${subject}&body=${body}`);
 *
 * onSendOutreachClick():
 *   // Phase 2 stub — show "Coming soon" tooltip
 *   console.log('[EmailDJ] Outreach integration coming in Phase 2');
 *
 * onEditorBlur():
 *   const edited = this.editorEl.innerText;
 *   if (edited !== this.originalDraft) {
 *     // User made edits — capture for feedback flywheel
 *     import('../hub-client.js').then(({ captureEdit }) => {
 *       captureEdit(this.originalDraft, edited);
 *     });
 *   }
 *
 * IMPORTANT: The edit capture (onEditorBlur → captureEdit) is the most important
 * data flywheel in the entire product. Every SDR edit teaches the prompt templates
 * what to improve. Never skip this call.
 */

export class EmailEditor {
  constructor(container) {
    this.container = container;
    this.originalDraft = '';
    this.editorEl = null;
    this.render();
  }

  render() {
    // TODO: implement DOM construction per instructions above
    this.container.innerHTML = `
      <div class="email-editor-wrapper">
        <div id="emailBody" contenteditable="true" class="email-body"
             style="min-height: 200px; padding: 12px; border: 1px solid #ccc;
                    font-family: sans-serif; white-space: pre-wrap;"></div>
        <div class="email-actions" id="emailActions" style="display:none;">
          <button id="copyBtn">Copy</button>
          <button id="gmailBtn">Send via Gmail</button>
          <button id="outreachBtn" title="Coming in Phase 2" disabled>Send via Outreach</button>
        </div>
      </div>
    `;
    this.editorEl = this.container.querySelector('#emailBody');
    // TODO: attach event listeners for blur, copy, gmail, outreach
  }

  appendToken(token) {
    // TODO: implement safe text node append per instructions above
    if (!this.editorEl) return;
    const textNode = document.createTextNode(token);
    this.editorEl.appendChild(textNode);
    this.editorEl.scrollTop = this.editorEl.scrollHeight;
  }

  markComplete() {
    // TODO: implement per instructions above
    this.originalDraft = this.editorEl?.innerText ?? '';
    const actionsEl = this.container.querySelector('#emailActions');
    if (actionsEl) actionsEl.style.display = 'flex';
    if (this.editorEl) {
      this.editorEl.addEventListener('blur', () => this.onEditorBlur(), { once: false });
    }
  }

  onEditorBlur() {
    // TODO: implement edit capture per instructions above
    const edited = this.editorEl?.innerText ?? '';
    if (edited !== this.originalDraft) {
      import('../hub-client.js').then(({ captureEdit }) => {
        captureEdit(this.originalDraft, edited);
      }).catch(console.error);
    }
  }
}
