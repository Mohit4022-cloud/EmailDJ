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
