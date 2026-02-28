/**
 * Side Panel Entry Point
 *
 * IMPLEMENTATION INSTRUCTIONS:
 * Initializes all components when the side panel DOM is ready.
 *
 * 1. Import components:
 *    import { QuickGenerate } from './components/QuickGenerate.js';
 *    import { AssignedCampaigns } from './components/AssignedCampaigns.js';
 *    import { connect } from './hub-client.js';
 *
 * 2. On DOMContentLoaded:
 *    - Call connect() to establish keep-alive port to service worker.
 *    - Initialize QuickGenerate in #quickGenerateContainer.
 *    - Initialize AssignedCampaigns in #assignedCampaignsContainer.
 *    - Set up tab switching between "Generate" and "Campaigns" tabs.
 *
 * 3. Tab switching:
 *    The side panel has 2 tabs:
 *    - "Generate" (default): shows QuickGenerate + ContextSummary
 *    - "Campaigns": shows AssignedCampaigns
 *    Use simple CSS show/hide on click.
 *
 * 4. Listen for sync tick from service worker:
 *    chrome.runtime.onMessage.addListener((msg) => {
 *      if (msg.type === 'SYNC_TICK') {
 *        assignedCampaigns.refresh(); // re-poll on each alarm tick
 *      }
 *    });
 */

import { QuickGenerate } from './components/QuickGenerate.js';
import { AssignedCampaigns } from './components/AssignedCampaigns.js';
import { connect } from './hub-client.js';

document.addEventListener('DOMContentLoaded', () => {
  // TODO: implement full initialization per instructions above
  connect();

  const generateContainer = document.getElementById('quickGenerateContainer');
  const campaignsContainer = document.getElementById('assignedCampaignsContainer');

  if (generateContainer) new QuickGenerate(generateContainer);
  if (campaignsContainer) new AssignedCampaigns(campaignsContainer);

  // Tab switching
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.style.display = 'none');
      btn.classList.add('active');
      const panel = document.getElementById(btn.dataset.tab);
      if (panel) panel.style.display = 'block';
    });
  });

  chrome.runtime.onMessage.addListener((msg) => {
    // TODO: handle SYNC_TICK per instructions above
  });
});
