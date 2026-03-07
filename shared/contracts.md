# Shared Contracts (MVP 0.5)

Key request/response schemas live in `backend/app/schemas.py`.

## Core runtime contracts
- `WebGenerateRequest` -> `WebGenerateAccepted`
- `WebRemixRequest` -> `WebRemixAccepted`
- `TargetEnrichmentRequest` -> `EnrichmentAccepted`
- `SenderEnrichmentRequest` -> `EnrichmentAccepted`
- `PresetPreviewRequest` -> `PresetPreviewResponse`
- `PresetPreviewBatchRequest` -> `PresetPreviewBatchResponse`
- `ResearchRequest` -> `ResearchCreateResponse` / `ResearchStatusResponse`

## Core domain contracts
- `EmailBlueprint`
- `SenderProfile`
- `TargetAccountProfile`
- `ContactProfile`
- `Citation`
- `ValidationResult`

## SSE event shapes
- `start`
- `progress`
- `tool_call`
- `tool_result`
- `token`
- `result`
- `done`
- `error`
