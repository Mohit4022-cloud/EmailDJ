# Frontend Architecture

Two client surfaces: Chrome Extension and Web App. Both are thin SSE consumers — all
intelligence lives in Hub API.

---

## Chrome Extension (`chrome-extension/`)

**Stack:** Vite + @crxjs/vite-plugin, vanilla JS, Manifest V3.

### Key MV3 Constraints

- **Service workers are ephemeral.** MV3 service workers can be terminated at any time.
  All persistent state must live in the Side Panel or Chrome storage.
- **Side Panel is a persistent process.** Unlike the service worker, the Side Panel
  (`src/side-panel/`) runs as a long-lived page and owns all session state.
- **No background pages.** MV3 removed background pages; all background logic runs in
  the service worker (with the above limitation).

### Subsystems

| Directory | Purpose |
|---|---|
| `src/background/` | MV3 service worker: message router, keep-alive ping, extension lifecycle |
| `src/content-scripts/` | Gmail DOM extraction (see 3-tier below) |
| `src/side-panel/` | Stateful UI: SSE consumer, draft display, remix/copy controls, PII prefilter |
| `public/icons/` | Extension icons |
| `manifest.json` | MV3 manifest: permissions, service worker entry, side panel config |

### 3-Tier DOM Parsing

Gmail is a complex SPA. Extraction uses three fallback tiers:

1. **Navigation detector** — intercepts `pushState`/`replaceState` and `popstate` events.
   Fastest; fires on SPA route changes before DOM settles.
2. **Mutation observer** — watches DOM subtree for account/contact panel mutations.
   Catches dynamic renders after navigation.
3. **Polling fallback** — periodic polling as a last resort for slow or unusual Gmail layouts.

Each tier hands off a `ProspectPayload` to the service worker via `postMessage`.

### PII Prefilter (Layer 1)

Before any data leaves the browser, the Side Panel runs a regex prefilter that strips
obvious PII (email addresses, phone numbers, SSNs) from the extracted payload. This is
Layer 1 of the 3-layer PII defense.

### Message Flow

```
Content Script → (postMessage) → Service Worker → (chrome.runtime.sendMessage) → Side Panel
Side Panel → (fetch POST) → Hub API → (SSE) → Side Panel
```

---

## Web App (`web-app/`)

**Stack:** Vite, vanilla JS, no framework.

### Subsystems

| Directory | Purpose |
|---|---|
| `src/api/` | API client: `POST /web/v1/generate`, `POST /web/v1/remix`, SSE consumer |
| `src/components/` | UI components: preset library, slider controls, draft display |
| `src/data/` | Static data (preset definitions, default values) |
| `src/main.js` | App bootstrap, routing, global state |
| `src/style.js` | Style utilities |
| `src/utils.js` | Shared utilities |

### SSE Consumption Pattern

```javascript
// 1. POST to get request_id + stream_url
const { request_id, stream_url } = await apiClient.generate(payload);

// 2. Open EventSource to stream URL
const es = new EventSource(stream_url);
es.addEventListener('token', (e) => appendToken(JSON.parse(e.data).token));
es.addEventListener('done', (e) => handleDone(JSON.parse(e.data)));
es.addEventListener('error', (e) => handleError(JSON.parse(e.data)));
```

SSE event schema: `docs/contracts/streaming_sse.md`

### State Model

The web app does not maintain server-side session state itself. It:
1. Receives `session_id` from `POST /web/v1/generate`.
2. Passes `session_id` back in `POST /web/v1/remix` for context continuity.
3. Hub API reconstructs session context from Redis.

---

## Build & Dev

```bash
# Extension
cd chrome-extension && npm install && npm run build  # or npm run dev

# Web app
cd web-app && npm install && npm run dev
```
