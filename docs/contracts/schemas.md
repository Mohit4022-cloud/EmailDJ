# Schema Field Reference

<!-- AUTO-DRAFTED: review before merge -->

Source: `hub-api/api/schemas.py`
Generated on: **2026-03-02**

Field-level documentation for all Pydantic request/response models.
For the endpoint-level overview see [`openapi.md`](openapi.md).

---

## Supporting Models

### `ExtractionMetadataIn`
Metadata attached to a prospect payload describing how the DOM extraction was performed.

| Field | Type | Required | Description |
|---|---|---|---|
| `selectorConfidences` | `dict[str, float]` | no | Per-field CSS selector confidence scores (0.0–1.0) |
| `extractedAt` | `datetime \| null` | no | UTC timestamp when DOM extraction occurred |
| `salesforceUrl` | `str \| null` | no | URL of the Salesforce record that was parsed |

---

### `ProspectPayload`
Account-level CRM data extracted from Salesforce by the Chrome Extension.

| Field | Type | Required | Description |
|---|---|---|---|
| `accountId` | `str` | **yes** | Salesforce Account ID (15 or 18 char) |
| `accountName` | `str \| null` | no | Account name |
| `industry` | `str \| null` | no | Industry classification from CRM |
| `employeeCount` | `int \| null` | no | Employee headcount |
| `openOpportunities` | `list[str] \| null` | no | Open opportunity names/summaries |
| `lastActivityDate` | `str \| null` | no | ISO date of last logged CRM activity |
| `notes` | `list[str]` | no | CRM note snippets (default: `[]`) |
| `activityTimeline` | `list[str]` | no | Activity log entries (default: `[]`) |
| `extractionMetadata` | `ExtractionMetadataIn \| null` | no | DOM extraction provenance |

---

### `WebProspectInput`
Contact-level prospect information for the Web MVP generation flow.

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `name` | `str` | **yes** | 1–120 chars | Full name of the prospect |
| `title` | `str` | **yes** | 1–120 chars | Job title |
| `company` | `str` | **yes** | 1–160 chars | Company name |
| `company_url` | `str \| null` | no | max 400 chars | Company website URL |
| `linkedin_url` | `str \| null` | no | — | LinkedIn profile URL |

---

### `WebStyleProfile`
Four-axis style control for email tone. All values default to `0.0` (neutral center).

| Field | Type | Required | Range | Description |
|---|---|---|---|---|
| `formality` | `float` | no | −1.0 to 1.0 | −1 = casual, +1 = formal |
| `orientation` | `float` | no | −1.0 to 1.0 | −1 = problem-led, +1 = outcome-led |
| `length` | `float` | no | −1.0 to 1.0 | −1 = short/punchy, +1 = long/detailed |
| `assertiveness` | `float` | no | −1.0 to 1.0 | −1 = diplomatic, +1 = bold/direct |

---

### `WebCompanyContext`
Seller company information. `current_product` is informational only — `offer_lock` in the
request is the sole pitch anchor injected into generation.

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `company_name` | `str \| null` | no | max 160 chars | Seller company name |
| `company_url` | `str \| null` | no | max 400 chars | Seller company website |
| `current_product` | `str \| null` | no | max 240 chars | Informational only — NOT injected into prompt |
| `other_products` | `str \| null` | no | max 8000 chars | Other products/offerings (context only) |
| `company_notes` | `str \| null` | no | max 8000 chars | Freeform company context |

---

## Request Models

### `QuickGenerateRequest`
Chrome Extension quick-generate flow. Produces a single email via SSE.

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `payload` | `ProspectPayload` | **yes** | — | CRM-extracted account data |
| `slider_value` | `int` | no | 0–10, default `5` | Personalization depth (0=efficiency, 10=deep personalization) |

---

### `WebGenerateRequest`
Web MVP initial generation. Creates a session and returns a stream URL.

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `prospect` | `WebProspectInput` | **yes** | — | Contact-level prospect data |
| `prospect_first_name` | `str \| null` | no | max 60 chars | First name override for greeting; derived from `prospect.name` if omitted |
| `research_text` | `str` | **yes** | 20–20000 chars | Raw research paste about the prospect/company |
| `offer_lock` | `str` | **yes** | 1–240 chars | Single pitch anchor — the ONLY thing the email may pitch |
| `cta_offer_lock` | `str \| null` | no | max 500 chars | Exact CTA text lock (legacy field name) |
| `cta_type` | `Literal[…] \| null` | no | see values below | CTA intent type |
| `preset_id` | `str \| null` | no | max 80 chars | Generation strategy preset (e.g., `straight_shooter`) |
| `style_profile` | `WebStyleProfile` | no | — | Four-axis style sliders (default: all 0.0) |
| `company_context` | `WebCompanyContext` | no | — | Seller company context |

`cta_type` values: `question`, `time_ask`, `value_asset`, `pilot`, `referral`, `event_invite`

---

### `WebRemixRequest`
Remix an existing session with a new style profile or preset.

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `session_id` | `str` | **yes** | min 1 char | Session ID from a prior `WebGenerateAccepted` response |
| `preset_id` | `str \| null` | no | max 80 chars | New preset to apply for this remix |
| `style_profile` | `WebStyleProfile` | **yes** | — | Updated style sliders |

---

### `WebFeedbackRequest`
Capture a user's edit of a generated draft for training signal.

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `session_id` | `str` | **yes** | min 1 char | Session ID |
| `draft_before` | `str` | **yes** | 1–40000 chars | AI-generated draft text |
| `draft_after` | `str` | **yes** | 1–40000 chars | User-edited final text |
| `style_profile` | `WebStyleProfile` | no | — | Style profile active at feedback time |

---

### `WebPreviewProductContext`
Product context for the preset preview batch pipeline.

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `product_name` | `str` | **yes** | 1–240 chars | Product/offering name |
| `one_line_value` | `str` | **yes** | 1–500 chars | Single-sentence value proposition |
| `proof_points` | `list[str]` | no | max 8 items | Supporting proof points |
| `target_outcome` | `str` | **yes** | 1–160 chars | Desired buyer outcome |

---

### `WebPreviewRawResearch`
Research input for the preset preview batch pipeline.

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `deep_research_paste` | `str` | **yes** | 1–30000 chars | Raw research text about the prospect |
| `company_notes` | `str \| null` | no | max 8000 chars | Additional company notes |
| `extra_constraints` | `str \| null` | no | max 2000 chars | Freeform additional generation constraints |

---

### `WebPreviewGlobalSliders`
Global slider defaults for the preset preview batch (0–100 scale, not −1.0 to 1.0).

| Field | Type | Required | Range | Description |
|---|---|---|---|---|
| `formality` | `int` | **yes** | 0–100 | Global formality baseline |
| `brevity` | `int` | **yes** | 0–100 | Global brevity baseline |
| `directness` | `int` | **yes** | 0–100 | Global directness baseline |
| `personalization` | `int` | **yes** | 0–100 | Global personalization baseline |

---

### `WebPreviewSliderOverrides`
Per-preset slider overrides applied on top of `WebPreviewGlobalSliders`.
All fields are optional (null = use global default).

| Field | Type | Required | Range |
|---|---|---|---|
| `formality` | `int \| null` | no | 0–100 |
| `brevity` | `int \| null` | no | 0–100 |
| `directness` | `int \| null` | no | 0–100 |
| `personalization` | `int \| null` | no | 0–100 |

---

### `WebPreviewPresetInput`
Single preset entry within a batch preview request.

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `preset_id` | `str` | **yes** | 1–80 chars | Preset identifier (e.g., `straight_shooter`) |
| `label` | `str` | **yes** | 1–120 chars | Display label shown to user |
| `slider_overrides` | `WebPreviewSliderOverrides` | no | — | Per-preset slider adjustments |

---

### `WebPresetPreviewBatchRequest`
Full batch preview request. Up to 20 presets in a single call.

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `prospect` | `WebProspectInput` | **yes** | — | Contact-level prospect data |
| `prospect_first_name` | `str \| null` | no | max 60 chars | First name override for greeting normalization |
| `product_context` | `WebPreviewProductContext` | **yes** | — | Product details for generation |
| `raw_research` | `WebPreviewRawResearch` | **yes** | — | Research input |
| `global_sliders` | `WebPreviewGlobalSliders` | **yes** | — | Global slider baseline |
| `presets` | `list[WebPreviewPresetInput]` | **yes** | 1–20 items | Presets to generate |
| `offer_lock` | `str` | **yes** | 1–240 chars | Must match `product_context.product_name` |
| `cta_lock` | `str \| null` | no | max 500 chars | Legacy CTA lock field |
| `cta_lock_text` | `str \| null` | no | max 500 chars | CTA lock override text (takes precedence if set) |
| `cta_type` | `Literal[…] \| null` | no | same as WebGenerateRequest | CTA intent type |
| `hook_strategy` | `Literal[…] \| null` | no | `research_anchored`, `risk_framed`, `domain_hook`, `outcome_hook` | Hook framing override |

---

## Response Models

### `QuickGenerateAccepted`
Returned by `POST /generate/quick`.

| Field | Type | Description |
|---|---|---|
| `request_id` | `str` | Unique request ID for polling the stream |
| `stream_url` | `str` | SSE endpoint: `GET /generate/stream/{request_id}` |

---

### `WebGenerateAccepted`
Returned by `POST /web/v1/generate`.

| Field | Type | Description |
|---|---|---|
| `request_id` | `str` | Unique request ID for this generation |
| `session_id` | `str` | Session ID for subsequent remix/feedback calls |
| `stream_url` | `str` | SSE endpoint: `GET /web/v1/stream/{request_id}` |

---

### `WebRemixAccepted`
Returned by `POST /web/v1/remix`.

| Field | Type | Description |
|---|---|---|
| `request_id` | `str` | New request ID for the remix stream |
| `stream_url` | `str` | SSE endpoint: `GET /web/v1/stream/{request_id}` |

---

### `WebPresetPreviewBatchResponse`
Returned by `POST /web/v1/preset-previews/batch`.

| Field | Type | Required | Description |
|---|---|---|---|
| `previews` | `list[WebPreviewItem]` | **yes** (≥1) | One item per preset requested |
| `meta` | `WebPreviewBatchMeta` | **yes** | Pipeline observability metadata |
| `summary_pack` | `WebSummaryPack \| null` | no | Research summary pack (enabled via `EMAILDJ_PREVIEW_INCLUDE_SUMMARY_PACK=1`) |

#### `WebPreviewItem`
| Field | Type | Description |
|---|---|---|
| `preset_id` | `str` | Preset identifier |
| `label` | `str` | Display label |
| `effective_sliders` | `WebPreviewEffectiveSliders` | Final resolved slider values (global + overrides) |
| `vibeLabel` | `str` | Short vibe descriptor (e.g., "Direct & Efficient") |
| `vibeTags` | `list[str]` | 2–4 vibe tag chips |
| `whyItWorks` | `list[str]` | 3 bullet-point rationale items |
| `subject` | `str` | Generated email subject line |
| `body` | `str` | Generated email body |

#### `WebPreviewBatchMeta`
Key observability fields:

| Field | Type | Description |
|---|---|---|
| `pipeline_version` | `str` | Pipeline version string |
| `provider` | `str` | LLM provider used (e.g., `openai`) |
| `model` | `str \| null` | Model name used |
| `repair_attempt_count` | `int` | Number of repair loop iterations |
| `repaired` | `bool` | Whether output required repair |
| `violation_codes` | `list[str]` | Violation codes that were detected/repaired |
| `enforcement_level` | `Literal["warn","repair","block"]` | Active enforcement level |
| `cache_hit` | `bool` | Whether the response was served from cache |
| `latency_ms` | `int` | Total generation latency in milliseconds |

---

### `ComplianceDashboardResponse`
Returned by `GET /web/v1/compliance/dashboard`.

| Field | Type | Description |
|---|---|---|
| `days` | `list[ComplianceDashboardDay]` | One entry per day, newest first |
| `generated_at` | `str` | ISO timestamp of when the dashboard was computed |

#### `ComplianceDashboardDay`
| Field | Type | Description |
|---|---|---|
| `date` | `str` | ISO date (YYYY-MM-DD) |
| `buckets` | `list[ComplianceViolationBucket]` | Per-violation-type counts |
| `total_violations` | `int` | Total violations for the day |

#### `ComplianceViolationBucket`
| Field | Type | Description |
|---|---|---|
| `violation_type` | `str` | Violation code (see `docs/policy/validator_rules.md`) |
| `total` | `int` | Total occurrences |
| `remix` | `int` | Occurrences in remix flow |
| `preview` | `int` | Occurrences in preview flow |

---

## Webhook + Vault + Assignment Models

### `VaultIngestRequest` / `VaultPrefetchRequest` / `VaultContextResponse`
| Model | Key Fields |
|---|---|
| `VaultIngestRequest` | `payload: ProspectPayload` |
| `VaultPrefetchRequest` | `account_ids: list[str]` (≥1) |
| `VaultContextResponse` | `account_id: str`, `context: dict` |

### `WebhookEditRequest`
| Field | Type | Required | Description |
|---|---|---|---|
| `assignment_id` | `str \| null` | no | Campaign assignment ID (if applicable) |
| `account_id` | `str \| null` | no | Salesforce Account ID |
| `original_draft` | `str` | **yes** | AI-generated draft |
| `final_edit` | `str` | **yes** | User-edited final text |

### `AssignmentsPollResponse`
| Field | Type | Description |
|---|---|---|
| `count` | `int` | Number of pending assignments |
| `assignments` | `list[AssignmentSummaryResponse]` | Summary of each assignment |
