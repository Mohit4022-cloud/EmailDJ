const callbacks = [];
let debounceTimer = null;

const RECORD_URL_PATTERN = /\/lightning\/r\/(Account|Lead|Contact|Opportunity)\/([a-zA-Z0-9]+)\/view/;

function handleNavigation(url) {
  const match = url.match(RECORD_URL_PATTERN);
  if (!match) return;

  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    const payload = { url, recordType: match[1], recordId: match[2] };
    callbacks.forEach((cb) => {
      try {
        cb(payload);
      } catch {
        // noop
      }
    });
  }, 300);
}

export function init() {
  const origPushState = history.pushState.bind(history);
  history.pushState = (...args) => {
    origPushState(...args);
    handleNavigation(window.location.href);
  };

  const origReplaceState = history.replaceState.bind(history);
  history.replaceState = (...args) => {
    origReplaceState(...args);
    handleNavigation(window.location.href);
  };

  window.addEventListener('popstate', () => handleNavigation(window.location.href));
  handleNavigation(window.location.href);
}

export function onNavigate(callback) {
  callbacks.push(callback);
}
