/** EmailDJ Background Service Worker (MV3). */

let keepalivePort = null;

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create('background-sync', { periodInMinutes: 1 });
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  console.log('[EmailDJ] installed/updated');
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || !message.type) return false;

  if (message.type === 'CONTENT_READY') {
    if (sender.tab?.id != null) {
      chrome.sidePanel.open({ tabId: sender.tab.id }).catch(() => {});
    }
    return false;
  }

  if (message.type === 'PAYLOAD_READY') {
    chrome.runtime.sendMessage({ type: 'PAYLOAD_READY', payload: message.payload, tokenMap: message.tokenMap }).catch(() => {});
    return false;
  }

  if (message.type === 'PING') {
    sendResponse({ alive: true });
    return true;
  }

  return false;
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== 'background-sync') return;
  chrome.runtime.sendMessage({ type: 'SYNC_TICK' }).catch(() => {});
});

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== 'keepalive') return;
  keepalivePort = port;
  port.onDisconnect.addListener(() => {
    if (keepalivePort === port) {
      keepalivePort = null;
    }
  });
});
