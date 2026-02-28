/**
 * EmailDJ Background Service Worker (MV3)
 *
 * IMPLEMENTATION INSTRUCTIONS:
 * Thin event router only. The Side Panel is the stateful process — this
 * service worker holds NO state between events.
 *
 * 1. chrome.runtime.onInstalled listener:
 *    - Set up alarm: chrome.alarms.create('background-sync', { periodInMinutes: 1 })
 *    - Open side panel on extension icon click via chrome.sidePanel.setPanelBehavior
 *      ({ openPanelOnActionClick: true })
 *    - Log 'EmailDJ installed/updated' to console.
 *
 * 2. chrome.runtime.onMessage listener:
 *    - Message type 'CONTENT_READY':
 *      Open the side panel for the current tab:
 *      chrome.sidePanel.open({ tabId: sender.tab.id })
 *    - Message type 'PAYLOAD_READY':
 *      Forward to side panel. Use chrome.runtime.sendMessage to all extension
 *      pages (the side panel listens on chrome.runtime.onMessage).
 *      Forward: { type: 'PAYLOAD_READY', payload: message.payload }
 *    - Message type 'PING':
 *      Respond with { alive: true } to support keep-alive from side panel.
 *
 * 3. chrome.alarms.onAlarm listener:
 *    - alarm.name === 'background-sync':
 *      Send { type: 'SYNC_TICK' } message to any open side panel pages.
 *      The side panel uses this to trigger assignment polling.
 *
 * 4. Keep-alive pattern (MV3 service workers terminate after 30s of inactivity):
 *    - The side panel maintains a chrome.runtime.connect() port named 'keepalive'.
 *    - Listen for chrome.runtime.onConnect: if port.name === 'keepalive',
 *      store the port reference. The connection itself keeps the worker alive.
 *    - Do NOT use setInterval for keep-alive — use the port connection approach.
 *
 * 5. DO NOT use chrome.webRequest (not in permissions).
 *    DO NOT store any user data in service worker global scope — it will be lost
 *    on service worker termination.
 */

chrome.runtime.onInstalled.addListener(() => {
  // TODO: implement per instructions above
  console.log('[EmailDJ] Service worker installed');
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // TODO: implement message routing per instructions above
  return false;
});

chrome.alarms.onAlarm.addListener((alarm) => {
  // TODO: implement alarm handling per instructions above
});

chrome.runtime.onConnect.addListener((port) => {
  // TODO: implement keep-alive port per instructions above
});
