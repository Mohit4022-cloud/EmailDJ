"""Context Vault Pydantic models — core data schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ExtractionMetadata(BaseModel):
    selector_confidences: dict[str, float] = Field(default_factory=dict)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    salesforce_url: str = ""
    extraction_version: str = "1.0"


class ContactContext(BaseModel):
    contact_id: str | None = None
    name: str = ""
    title: str | None = None
    email: str | None = None
    role_inferred: str | None = None
    last_interaction_date: datetime | None = None
    sentiment: str | None = None


class VersionedSnapshot(BaseModel):
    snapshot_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    field_name: str = ""
    old_value: str | None = None
    new_value: str | None = None
    is_authoritative: bool = True
    conflict_flag: bool = False


class CompanyProfile(BaseModel):
    key_initiatives: list[str] = Field(default_factory=list)
    leadership_signals: list[str] = Field(default_factory=list)
    tech_stack_hints: list[str] = Field(default_factory=list)
    recent_news: list[str] = Field(default_factory=list)
    financial_signals: list[str] = Field(default_factory=list)
    icp_fit_score: int = Field(default=5, ge=1, le=10)
    research_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sources: list[str] = Field(default_factory=list)


class AccountContext(BaseModel):
    account_id: str
    account_name: str = ""
    domain: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    extracted_contacts: list[ContactContext] = Field(default_factory=list)
    decision_makers: list[str] = Field(default_factory=list)
    contract_status: Literal["prospect", "customer", "churned", "closed-lost"] | None = None
    budget: str | None = None
    timing: str | None = None
    next_action: str | None = None
    company_profile: CompanyProfile | None = None
    vault_version: int = 1
    last_enriched_at: datetime | None = None
    freshness: Literal["fresh", "aging", "stale"] = "stale"
    history: list[VersionedSnapshot] = Field(default_factory=list)

    @model_validator(mode="after")
    def compute_freshness(self) -> "AccountContext":
        if self.last_enriched_at is None:
            self.freshness = "stale"
            return self

        age_days = (datetime.now(timezone.utc) - self.last_enriched_at).days
        if age_days < 30:
            self.freshness = "fresh"
        elif age_days < 90:
            self.freshness = "aging"
        else:
            self.freshness = "stale"
        return self


class EmailDraft(BaseModel):
    draft_id: str
    account_id: str
    persona: str
    sequence_position: int = Field(ge=1, le=3)
    subject: str = ""
    body: str = ""
    send_window: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_tier: int = Field(default=2, ge=1, le=3)
    personalization_score: int = Field(default=5, ge=0, le=10)
