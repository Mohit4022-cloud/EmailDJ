# OpenAPI Contract Summary

Generated from `hub-api/openapi.json`.

- Endpoints: **24**
- Schemas: **37**

## Endpoints

| Method | Path | Tags | Request Schema | Response Schemas |
|---|---|---|---|---|
| GET | / | - | - | 200:object |
| GET | /assignments/poll | assignments | - | 200:inline, 422:HTTPValidationError |
| GET | /campaigns/{campaign_id} | campaigns | - | 200:inline, 422:HTTPValidationError |
| GET | /generate/stream/{request_id} | generate | - | 200:inline, 422:HTTPValidationError |
| GET | /research/{job_id}/status | research | - | 200:inline, 422:HTTPValidationError |
| GET | /vault/context/{prospect_id} | vault | - | 200:inline, 422:HTTPValidationError |
| GET | /web/v1/compliance/dashboard | web-mvp | - | 200:ComplianceDashboardResponse, 422:HTTPValidationError |
| GET | /web/v1/stream/{request_id} | web-mvp | - | 200:inline, 422:HTTPValidationError |
| POST | /assignments/{assignment_id}/accept | assignments | - | 200:inline, 422:HTTPValidationError |
| POST | /campaigns/ | campaigns | CampaignCreateRequest | 200:inline, 422:HTTPValidationError |
| POST | /campaigns/{campaign_id}/approve | campaigns | CampaignApproveRequest | 200:inline, 422:HTTPValidationError |
| POST | /campaigns/{campaign_id}/assign | campaigns | CampaignAssignRequest | 200:inline, 422:HTTPValidationError |
| POST | /generate/quick | generate | QuickGenerateRequest | 200:QuickGenerateAccepted, 422:HTTPValidationError |
| POST | /research/ | research | DeepResearchRequest | 200:inline, 422:HTTPValidationError |
| POST | /vault/context/{prospect_id}/invalidate | vault | - | 200:inline, 422:HTTPValidationError |
| POST | /vault/ingest | vault | VaultIngestRequest | 200:inline, 422:HTTPValidationError |
| POST | /vault/prefetch | vault | VaultPrefetchRequest | 200:inline, 422:HTTPValidationError |
| POST | /web/v1/feedback | web-mvp | WebFeedbackRequest | 200:inline, 422:HTTPValidationError |
| POST | /web/v1/generate | web-mvp | WebGenerateRequest | 200:WebGenerateAccepted, 422:HTTPValidationError |
| POST | /web/v1/preset-previews/batch | web-mvp | WebPresetPreviewBatchRequest | 200:WebPresetPreviewBatchResponse, 422:HTTPValidationError |
| POST | /web/v1/remix | web-mvp | WebRemixRequest | 200:WebRemixAccepted, 422:HTTPValidationError |
| POST | /webhooks/edit | webhooks | WebhookEditRequest | 200:inline, 422:HTTPValidationError |
| POST | /webhooks/reply | webhooks | WebhookReplyRequest | 200:inline, 422:HTTPValidationError |
| POST | /webhooks/send | webhooks | WebhookSendRequest | 200:inline, 422:HTTPValidationError |

## Schemas

| Schema | Properties | Required |
|---|---:|---:|
| CampaignApproveRequest | 2 | 1 |
| CampaignAssignRequest | 1 | 1 |
| CampaignCreateRequest | 2 | 2 |
| ComplianceDashboardDay | 3 | 3 |
| ComplianceDashboardResponse | 2 | 2 |
| ComplianceViolationBucket | 4 | 4 |
| DeepResearchRequest | 3 | 3 |
| ExtractionMetadataIn | 3 | 0 |
| HTTPValidationError | 1 | 0 |
| ProspectPayload | 9 | 1 |
| QuickGenerateAccepted | 2 | 2 |
| QuickGenerateRequest | 2 | 1 |
| ValidationError | 5 | 3 |
| VaultIngestRequest | 1 | 1 |
| VaultPrefetchRequest | 1 | 1 |
| WebCompanyContext | 5 | 0 |
| WebFeedbackRequest | 4 | 3 |
| WebGenerateAccepted | 3 | 3 |
| WebGenerateRequest | 8 | 3 |
| WebPresetPreviewBatchRequest | 7 | 7 |
| WebPresetPreviewBatchResponse | 3 | 2 |
| WebPreviewBatchMeta | 18 | 4 |
| WebPreviewEffectiveSliders | 4 | 4 |
| WebPreviewGlobalSliders | 4 | 4 |
| WebPreviewItem | 8 | 8 |
| WebPreviewPresetInput | 3 | 2 |
| WebPreviewProductContext | 4 | 3 |
| WebPreviewRawResearch | 3 | 1 |
| WebPreviewSliderOverrides | 4 | 0 |
| WebProspectInput | 5 | 3 |
| WebRemixAccepted | 2 | 2 |
| WebRemixRequest | 2 | 2 |
| WebStyleProfile | 4 | 0 |
| WebSummaryPack | 4 | 4 |
| WebhookEditRequest | 4 | 2 |
| WebhookReplyRequest | 4 | 0 |
| WebhookSendRequest | 5 | 2 |
