import { QuickGenerate } from './components/QuickGenerate.js';
import { AssignedCampaigns } from './components/AssignedCampaigns.js';
import { connect, pollAssignments } from './hub-client.js';

document.addEventListener('DOMContentLoaded', () => {
  connect();

  const generateContainer = document.getElementById('quickGenerateContainer');
  const campaignsContainer = document.getElementById('assignedCampaignsContainer');

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

  refreshAssignments();

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'SYNC_TICK') {
      refreshAssignments();
    }
  });
});
