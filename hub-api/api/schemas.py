"""Public request/response contracts for MVP endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ExtractionMetadataIn(BaseModel):
    selectorConfidences: dict[str, float] = Field(default_factory=dict)
    extractedAt: datetime | None = None
    salesforceUrl: str | None = None


class ProspectPayload(BaseModel):
    accountId: str
    accountName: str | None = None
    industry: str | None = None
    employeeCount: int | None = None
    openOpportunities: list[str] | None = None
    lastActivityDate: str | None = None
    notes: list[str] = Field(default_factory=list)
    activityTimeline: list[str] = Field(default_factory=list)
    extractionMetadata: ExtractionMetadataIn | None = None


class QuickGenerateRequest(BaseModel):
    payload: ProspectPayload
    slider_value: int = Field(default=5, ge=0, le=10)


class QuickGenerateAccepted(BaseModel):
    request_id: str
    stream_url: str


class WebProspectInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=120)
    company: str = Field(min_length=1, max_length=160)
    company_url: str | None = Field(default=None, max_length=400)
    linkedin_url: str | None = None


class WebStyleProfile(BaseModel):
    formality: float = Field(default=0.0, ge=-1.0, le=1.0)
    orientation: float = Field(default=0.0, ge=-1.0, le=1.0)
    length: float = Field(default=0.0, ge=-1.0, le=1.0)
    assertiveness: float = Field(default=0.0, ge=-1.0, le=1.0)


class WebCompanyContext(BaseModel):
    company_name: str | None = Field(default=None, max_length=160)
    company_url: str | None = Field(default=None, max_length=400)
    current_product: str | None = Field(default=None, max_length=240)
    other_products: str | None = Field(default=None, max_length=8000)
    company_notes: str | None = Field(default=None, max_length=8000)


class WebGenerateRequest(BaseModel):
    prospect: WebProspectInput
    research_text: str = Field(min_length=20, max_length=20000)
    style_profile: WebStyleProfile = Field(default_factory=WebStyleProfile)
    company_context: WebCompanyContext = Field(default_factory=WebCompanyContext)


class WebGenerateAccepted(BaseModel):
    request_id: str
    session_id: str
    stream_url: str


class WebRemixRequest(BaseModel):
    session_id: str = Field(min_length=1)
    style_profile: WebStyleProfile


class WebRemixAccepted(BaseModel):
    request_id: str
    stream_url: str


class WebFeedbackRequest(BaseModel):
    session_id: str = Field(min_length=1)
    draft_before: str = Field(min_length=1, max_length=40000)
    draft_after: str = Field(min_length=1, max_length=40000)
    style_profile: WebStyleProfile = Field(default_factory=WebStyleProfile)


class WebPreviewProductContext(BaseModel):
    product_name: str = Field(min_length=1, max_length=240)
    one_line_value: str = Field(min_length=1, max_length=500)
    proof_points: list[str] = Field(default_factory=list, max_length=8)
    target_outcome: str = Field(min_length=1, max_length=160)


class WebPreviewRawResearch(BaseModel):
    deep_research_paste: str = Field(min_length=1, max_length=30000)
    company_notes: str | None = Field(default=None, max_length=8000)
    extra_constraints: str | None = Field(default=None, max_length=2000)


class WebPreviewGlobalSliders(BaseModel):
    formality: int = Field(ge=0, le=100)
    brevity: int = Field(ge=0, le=100)
    directness: int = Field(ge=0, le=100)
    personalization: int = Field(ge=0, le=100)


class WebPreviewSliderOverrides(BaseModel):
    formality: int | None = Field(default=None, ge=0, le=100)
    brevity: int | None = Field(default=None, ge=0, le=100)
    directness: int | None = Field(default=None, ge=0, le=100)
    personalization: int | None = Field(default=None, ge=0, le=100)


class WebPreviewPresetInput(BaseModel):
    preset_id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    slider_overrides: WebPreviewSliderOverrides = Field(default_factory=WebPreviewSliderOverrides)


class WebPresetPreviewBatchRequest(BaseModel):
    prospect: WebProspectInput
    product_context: WebPreviewProductContext
    raw_research: WebPreviewRawResearch
    global_sliders: WebPreviewGlobalSliders
    presets: list[WebPreviewPresetInput] = Field(min_length=1, max_length=20)


class WebSummaryPack(BaseModel):
    facts: list[str] = Field(min_length=4, max_length=4)
    hooks: list[str] = Field(min_length=3, max_length=3)
    likely_priorities: list[str] = Field(min_length=3, max_length=3)
    keywords: list[str] = Field(min_length=6, max_length=6)


class WebPreviewEffectiveSliders(BaseModel):
    formality: int = Field(ge=0, le=100)
    brevity: int = Field(ge=0, le=100)
    directness: int = Field(ge=0, le=100)
    personalization: int = Field(ge=0, le=100)


class WebPreviewItem(BaseModel):
    preset_id: str
    label: str
    effective_sliders: WebPreviewEffectiveSliders
    vibeLabel: str
    vibeTags: list[str] = Field(min_length=2, max_length=4)
    whyItWorks: list[str] = Field(min_length=3, max_length=3)
    subject: str
    body: str


class WebPreviewBatchMeta(BaseModel):
    pipeline_version: str
    provider: str
    cache_hit: bool
    latency_ms: int = Field(ge=0)


class WebPresetPreviewBatchResponse(BaseModel):
    previews: list[WebPreviewItem] = Field(min_length=1)
    meta: WebPreviewBatchMeta
    summary_pack: WebSummaryPack | None = None


class VaultIngestRequest(BaseModel):
    payload: ProspectPayload


class VaultPrefetchRequest(BaseModel):
    account_ids: list[str] = Field(min_length=1)


class VaultContextResponse(BaseModel):
    account_id: str
    context: dict[str, Any]


class AssignmentSummaryResponse(BaseModel):
    id: str
    campaign_name: str
    vp_name: str
    account_count: int
    rationale_snippet: str
    created_at: str
    status: str


class AssignmentsPollResponse(BaseModel):
    count: int
    assignments: list[AssignmentSummaryResponse]


class WebhookEditRequest(BaseModel):
    assignment_id: str | None = None
    account_id: str | None = None
    original_draft: str
    final_edit: str


class WebhookSendRequest(BaseModel):
    assignment_id: str
    account_id: str | None = None
    email_draft: str
    final_edit: str | None = None
    sent_at: datetime | None = None


class WebhookReplyRequest(BaseModel):
    account_id: str | None = None
    contact_id: str | None = None
    reply_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_payload: dict[str, Any] = Field(default_factory=dict)
