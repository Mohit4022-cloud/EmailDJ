import { QuickGenerate } from './components/QuickGenerate.js';
import { AssignedCampaigns } from './components/AssignedCampaigns.js';
import { connect, pollAssignments, resolveHubConfig, saveHubConfig } from './hub-client.js';

document.addEventListener('DOMContentLoaded', () => {
  connect();

  const generateContainer = document.getElementById('quickGenerateContainer');
  const campaignsContainer = document.getElementById('assignedCampaignsContainer');
  const settingsPanel = document.getElementById('settingsPanel');

  const quickGenerate = generateContainer ? new QuickGenerate(generateContainer) : null;
  const assignedCampaigns = campaignsContainer ? new AssignedCampaigns(campaignsContainer) : null;

  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach((p) => { p.style.display = 'none'; });
      btn.classList.add('active');
      const panel = document.getElementById(btn.dataset.tab);
      if (panel) panel.style.display = 'block';
    });
  });

  async function refreshAssignments() {
    if (!assignedCampaigns) return;
    try {
      const data = await pollAssignments();
      assignedCampaigns.refresh(data.assignments || []);
      if ((data.count || 0) > 0) {
        const badge = document.getElementById('assignmentBadge');
        if (badge) {
          badge.style.display = 'inline-block';
          badge.textContent = String(data.count);
        }
      }
    } catch {
      // noop
    }
  }

  async function hydrateSettings() {
    if (!settingsPanel) return;
    const hubUrlInput = document.getElementById('hubUrlInput');
    const betaKeyInput = document.getElementById('betaKeyInput');
    const settingsStatus = document.getElementById('settingsStatus');
    const saveSettingsBtn = document.getElementById('saveSettingsBtn');
    if (!hubUrlInput || !betaKeyInput || !saveSettingsBtn) return;

    try {
      const config = await resolveHubConfig();
      hubUrlInput.value = config.hubUrl;
      betaKeyInput.value = config.betaKey;
      if (settingsStatus) settingsStatus.textContent = 'Configuration loaded.';
    } catch {
      if (settingsStatus) settingsStatus.textContent = 'Configuration unavailable.';
    }

    saveSettingsBtn.addEventListener('click', async () => {
      try {
        const config = await saveHubConfig({
          hubUrl: hubUrlInput.value,
          betaKey: betaKeyInput.value,
        });
        hubUrlInput.value = config.hubUrl;
        betaKeyInput.value = config.betaKey;
        if (settingsStatus) settingsStatus.textContent = 'Configuration saved.';
      } catch (error) {
        if (settingsStatus) settingsStatus.textContent = String(error?.message || error);
      }
    });
  }

  refreshAssignments();
  hydrateSettings();

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'SYNC_TICK') {
      refreshAssignments();
    }
  });
});
