"""
Context Vault Pydantic models — core data schemas.

IMPLEMENTATION INSTRUCTIONS:
1. All models use Pydantic v2 (BaseModel, Field, model_validator).
2. Define the following models:

ExtractionMetadata:
  - selector_confidences: dict[str, float]  # field → confidence score
  - extracted_at: datetime
  - salesforce_url: str
  - extraction_version: str = "1.0"

ContactContext:
  - contact_id: str | None
  - name: str
  - title: str | None
  - email: str | None  # will be tokenized — never raw PII in LLM context
  - role_inferred: str | None  # 'champion'|'decision_maker'|'influencer'|'user'
  - last_interaction_date: datetime | None
  - sentiment: str | None  # 'positive'|'neutral'|'negative'

VersionedSnapshot:
  - snapshot_date: datetime
  - field_name: str
  - old_value: str | None
  - new_value: str | None
  - is_authoritative: bool = True
  - conflict_flag: bool = False

CompanyProfile:
  - key_initiatives: list[str]
  - leadership_signals: list[str]
  - tech_stack_hints: list[str]
  - recent_news: list[str]
  - financial_signals: list[str]
  - icp_fit_score: int  # 1-10
  - research_date: datetime
  - sources: list[str]

AccountContext:
  - account_id: str
  - account_name: str
  - domain: str | None
  - industry: str | None
  - employee_count: int | None
  - extracted_contacts: list[ContactContext] = []
  - decision_makers: list[str] = []
  - contract_status: str | None  # 'prospect'|'customer'|'churned'|'closed-lost'
  - budget: str | None  # tokenized — stored as [BUDGET_AMOUNT] or range description
  - timing: str | None  # e.g., "Q2 2026", "evaluating in 6 months"
  - next_action: str | None
  - company_profile: CompanyProfile | None = None
  - vault_version: int = 1
  - last_enriched_at: datetime | None = None
  - freshness: str  # computed — see validator below
  - history: list[VersionedSnapshot] = []

  Freshness validator (model_validator, mode='after'):
    if last_enriched_at is None: freshness = 'stale'
    elif (now - last_enriched_at).days < 30: freshness = 'fresh'
    elif (now - last_enriched_at).days < 90: freshness = 'aging'
    else: freshness = 'stale'

EmailDraft:
  - draft_id: str
  - account_id: str
  - persona: str  # 'CFO'|'VP_Ops'|'Head_IT'|'champion'
  - sequence_position: int  # 1, 2, or 3
  - subject: str
  - body: str
  - send_window: str | None  # e.g., "day_0", "day_3", "day_7"
  - generated_at: datetime
  - model_tier: int  # 1, 2, or 3
  - personalization_score: int  # 0-10 slider value used
"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field, model_validator


# TODO: implement all models per instructions above
# Placeholder stubs to allow imports without error:

class ExtractionMetadata(BaseModel):
    selector_confidences: dict = Field(default_factory=dict)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    salesforce_url: str = ""
    extraction_version: str = "1.0"


class ContactContext(BaseModel):
    contact_id: Optional[str] = None
    name: str = ""
    title: Optional[str] = None
    email: Optional[str] = None
    role_inferred: Optional[str] = None
    last_interaction_date: Optional[datetime] = None
    sentiment: Optional[str] = None


class VersionedSnapshot(BaseModel):
    snapshot_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    field_name: str = ""
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    is_authoritative: bool = True
    conflict_flag: bool = False


class CompanyProfile(BaseModel):
    key_initiatives: list[str] = Field(default_factory=list)
    leadership_signals: list[str] = Field(default_factory=list)
    tech_stack_hints: list[str] = Field(default_factory=list)
    recent_news: list[str] = Field(default_factory=list)
    financial_signals: list[str] = Field(default_factory=list)
    icp_fit_score: int = 5
    research_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sources: list[str] = Field(default_factory=list)


class AccountContext(BaseModel):
    account_id: str
    account_name: str = ""
    domain: Optional[str] = None
    industry: Optional[str] = None
    employee_count: Optional[int] = None
    extracted_contacts: list[ContactContext] = Field(default_factory=list)
    decision_makers: list[str] = Field(default_factory=list)
    contract_status: Optional[str] = None
    budget: Optional[str] = None
    timing: Optional[str] = None
    next_action: Optional[str] = None
    company_profile: Optional[CompanyProfile] = None
    vault_version: int = 1
    last_enriched_at: Optional[datetime] = None
    freshness: str = "stale"
    history: list[VersionedSnapshot] = Field(default_factory=list)

    @model_validator(mode="after")
    def compute_freshness(self) -> "AccountContext":
        # TODO: implement freshness decay per instructions
        if self.last_enriched_at is None:
            self.freshness = "stale"
        else:
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
    sequence_position: int
    subject: str = ""
    body: str = ""
    send_window: Optional[str] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_tier: int = 2
    personalization_score: int = 5
