/**
 * QuickGenerate — Main email generation UI component.
 *
 * IMPLEMENTATION INSTRUCTIONS:
 * Vanilla JS class (no framework dependency for MV3 compatibility).
 *
 * States:
 *   - 'idle':       Show ContextSummary + Generate button + PersonalizationSlider
 *   - 'generating': Show streaming skeleton with first words visible as SSE begins
 *   - 'complete':   Show full email in EmailEditor with Copy/Edit/Send actions
 *
 * Constructor(container: HTMLElement):
 *   this.container = container;
 *   this.state = 'idle';
 *   this.currentPayload = null;  // set by content script message
 *   this.sliderValue = 5;        // PersonalizationSlider default
 *   this.render();
 *   this.setupMessageListener();  // listen for PAYLOAD_READY from service worker
 *   this.pollAssignmentsOnMount();
 *
 * setupMessageListener():
 *   chrome.runtime.onMessage.addListener((msg) => {
 *     if (msg.type === 'PAYLOAD_READY') {
 *       this.currentPayload = msg.payload;
 *       this.currentTokenMap = msg.tokenMap;
 *       this.setState('idle');  // update context summary
 *     }
 *   });
 *
 * pollAssignmentsOnMount():
 *   hubClient.pollAssignments().then(({ count, assignments }) => {
 *     if (count > 0) this.showAssignmentBadge(count);
 *   }).catch(console.error);
 *   setInterval(() => this.pollAssignmentsOnMount(), 30000);
 *
 * onGenerateClick():
 *   this.setState('generating');
 *   Listen for emailToken events → pass to EmailEditor.appendToken(token)
 *   Listen for emailComplete → this.setState('complete')
 *   Listen for emailError → show error state with retry button
 *   hubClient.generateEmail(this.currentPayload, this.sliderValue)
 *
 * For cold accounts (no Context Vault data / accountId not found):
 *   Show "Researching [Company]..." skeleton with animated progress indicator.
 *   Do NOT show an error state — frame it as the system working hard for them.
 *
 * PersonalizationSlider:
 *   <input type="range" min="0" max="10" value="5">
 *   Label: "⚡ Efficiency" ←→ "🎯 Personalization"
 *   On change: update this.sliderValue
 *
 * render():
 *   Build DOM tree, attach event listeners. Use innerHTML for initial render.
 *
 * setState(newState):
 *   this.state = newState;
 *   Update DOM to reflect new state (show/hide elements).
 */

export class QuickGenerate {
  constructor(container) {
    this.container = container;
    this.state = 'idle';
    this.currentPayload = null;
    this.currentTokenMap = {};
    this.sliderValue = 5;
    // TODO: implement full class per instructions above
    this.render();
  }

  render() {
    // TODO: implement DOM construction per instructions above
    this.container.innerHTML = `
      <div class="quick-generate">
        <div class="context-summary" id="contextSummary">
          <p>Open a Salesforce Account record to begin.</p>
        </div>
        <div class="slider-container">
          <label>⚡ Efficiency
            <input type="range" id="personalizationSlider" min="0" max="10" value="5">
            🎯 Personalization
          </label>
        </div>
        <button id="generateBtn" class="generate-btn">Generate Email</button>
        <div class="email-editor-container" id="emailEditorContainer" style="display:none;"></div>
      </div>
    `;
    // TODO: attach event listeners
  }

  setState(newState) {
    this.state = newState;
    // TODO: update DOM per state
  }

  showAssignmentBadge(count) {
    // TODO: show badge on AssignedCampaigns tab
  }
}
