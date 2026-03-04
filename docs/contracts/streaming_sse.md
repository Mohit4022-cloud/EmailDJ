# Streaming SSE Contract

Source anchors:
- `hub-api/email_generation/streaming.py`
- `hub-api/api/routes/web_mvp.py`

## Endpoint
- `GET /web/v1/stream/{request_id}`
- Content type: `text/event-stream`

## Event Types
The backend emits these events in order:
1. `start`
2. `token` (0..N)
3. `done`

If an exception occurs during generation, backend emits `error`.

## Event Payloads
All events include:
- `request_id: string`
- `sequence: integer`
- `timestamp: float` (unix seconds)

### `start`
```json
{"event":"start","data":{"request_id":"...","sequence":0,"timestamp":1730000000.123}}
```

### `token`
Adds:
- `token: string`

```json
{"event":"token","data":{"request_id":"...","sequence":1,"timestamp":1730000000.456,"token":"Hi "}}
```

### `done`
Adds runtime metadata from `build_draft` result (fields present when available):
- `session_id`
- `mode`
- `provider`
- `model`
- `cascade_reason`
- `provider_attempt_count`
- `validator_attempt_count`
- `json_repair_count`
- `violation_retry_count`
- `repaired`
- `violation_codes`
- `violation_count`
- `enforcement_level`
- `repair_loop_enabled`

```json
{
  "event":"done",
  "data":{
    "request_id":"...",
    "sequence":120,
    "timestamp":1730000001.789,
    "session_id":"...",
    "mode":"real",
    "provider":"openai",
    "model":"gpt-5-nano",
    "provider_attempt_count":1,
    "validator_attempt_count":1,
    "json_repair_count":0,
    "violation_retry_count":0,
    "repaired":false,
    "violation_codes":[],
    "violation_count":0,
    "enforcement_level":"repair",
    "repair_loop_enabled":true
  }
}
```

### `error`
Adds:
- `error: string`

```json
{"event":"error","data":{"request_id":"...","sequence":4,"timestamp":1730000000.999,"error":"ctco_validation_failed: ..."}}
```

## Error Surface Notes
- Request/session lookup failures are raised before stream begins via HTTP error response in `web_mvp.py`.
- In-stream generation errors are surfaced as SSE `error` events by `streaming.py`.
