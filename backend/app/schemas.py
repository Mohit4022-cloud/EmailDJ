from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class Citation(BaseModel):
    url: str = Field(min_length=1, max_length=1200)
    retrieved_at: str = Field(min_length=1)
    published_at: str = Field(default="Unknown")


class NewsItem(BaseModel):
    date: str = Field(default="Unknown")
    headline: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    url: str = Field(min_length=1)


class TargetAccountProfile(BaseModel):
    official_domain: str = Field(default="Unknown")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    products: list[str] = Field(default_factory=list)
    summary: str = Field(default="Unknown")
    icp: str = Field(default="Unknown")
    differentiators: list[str] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)
    recent_news: list[NewsItem] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    last_refreshed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_source_urls: list[str] = Field(default_factory=list)
    tool_run_trace_id: str = Field(default="")


class ContactProfile(BaseModel):
    name: str = Field(default="Unknown")
    current_title: str = Field(default="Unknown")
    company: str = Field(default="Unknown")
    role_summary: str = Field(default="Unknown")
    talking_points: list[str] = Field(default_factory=list)
    related_news: list[NewsItem] = Field(default_factory=list)
    inferred_kpis_or_priorities: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    last_refreshed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_source_urls: list[str] = Field(default_factory=list)
    tool_run_trace_id: str = Field(default="")


class SenderProfile(BaseModel):
    company_name: str = Field(default="")
    structured_icp: str = Field(default="")
    differentiation: list[str] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)
    notes_summary: str = Field(default="")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    citations: list[Citation] = Field(default_factory=list)
    last_refreshed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tool_run_trace_id: str = Field(default="")


class WebProspectInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=160)
    company: str = Field(min_length=1, max_length=200)
    company_url: str | None = Field(default=None, max_length=400)
    linkedin_url: str | None = Field(default=None, max_length=500)


class WebStyleProfile(BaseModel):
    formality: float = Field(default=0.0, ge=-1.0, le=1.0)
    orientation: float = Field(default=0.0, ge=-1.0, le=1.0)
    length: float = Field(default=0.0, ge=-1.0, le=1.0)
    assertiveness: float = Field(default=0.0, ge=-1.0, le=1.0)


class WebCompanyContext(BaseModel):
    company_name: str | None = Field(default=None, max_length=200)
    company_url: str | None = Field(default=None, max_length=400)
    current_product: str | None = Field(default=None, max_length=300)
    other_products: str | None = Field(default=None, max_length=8000)
    seller_offerings: str | list[str] | None = Field(default=None)
    internal_modules: str | list[str] | None = Field(default=None)
    company_notes: str | None = Field(default=None, max_length=12000)
    cta_offer_lock: str | None = Field(default=None, max_length=500)
    cta_type: Literal["question", "time_ask", "value_asset", "pilot", "referral", "event_invite"] | None = None


class WebPipelineMeta(BaseModel):
    mode: str | None = Field(default=None, max_length=40)
    model_hint: str | None = Field(default=None, max_length=120)
    request_id: str | None = Field(default=None, max_length=120)
    throttled: bool | None = None


class WebGenerateRequest(BaseModel):
    prospect: WebProspectInput
    prospect_first_name: str | None = Field(default=None, max_length=60)
    research_text: str = Field(min_length=1, max_length=50000)
    offer_lock: str = Field(min_length=1, max_length=320)
    cta_offer_lock: str | None = Field(default=None, max_length=500)
    cta_type: Literal["question", "time_ask", "value_asset", "pilot", "referral", "event_invite"] | None = None
    preset_id: str | None = Field(default=None, max_length=120)
    response_contract: Literal["legacy_text", "email_json_v1", "rc_tco_json_v1"] = Field(default="legacy_text")
    pipeline_meta: WebPipelineMeta | None = None
    style_profile: WebStyleProfile = Field(default_factory=WebStyleProfile)
    company_context: WebCompanyContext = Field(default_factory=WebCompanyContext)
    sender_profile_override: SenderProfile | None = None
    target_profile_override: TargetAccountProfile | None = None
    contact_profile_override: ContactProfile | None = None


class WebGenerateAccepted(BaseModel):
    request_id: str
    session_id: str
    stream_url: str


class WebRemixRequest(BaseModel):
    session_id: str = Field(min_length=1)
    preset_id: str | None = Field(default=None, max_length=120)
    style_profile: WebStyleProfile


class WebRemixAccepted(BaseModel):
    request_id: str
    stream_url: str


class TargetEnrichmentRequest(BaseModel):
    company_name: str | None = Field(default=None, max_length=200)
    company_url: str | None = Field(default=None, max_length=400)
    refresh: bool = False

    @model_validator(mode="after")
    def require_anchor(self):
        if not (self.company_name or self.company_url):
            raise ValueError("company_name_or_url_required")
        return self


class ProspectEnrichmentRequest(BaseModel):
    prospect_name: str = Field(min_length=1, max_length=200)
    prospect_title: str | None = Field(default=None, max_length=200)
    prospect_company: str | None = Field(default=None, max_length=200)
    prospect_linkedin_url: str | None = Field(default=None, max_length=500)
    target_company_name: str | None = Field(default=None, max_length=200)
    target_company_url: str | None = Field(default=None, max_length=400)
    refresh: bool = False


class SenderEnrichmentRequest(BaseModel):
    company_name: str | None = Field(default=None, max_length=200)
    current_product: str | None = Field(default=None, max_length=300)
    company_notes: str | None = Field(default=None, max_length=12000)
    other_products: str | None = Field(default=None, max_length=12000)
    refresh: bool = False


class EnrichmentAccepted(BaseModel):
    request_id: str
    stream_url: str


class PresetPreviewRequest(BaseModel):
    session_id: str | None = Field(default=None, min_length=1)
    preset_id: str = Field(min_length=1, max_length=120)
    prospect: WebProspectInput
    prospect_first_name: str | None = Field(default=None, max_length=60)
    research_text: str = Field(min_length=1, max_length=50000)
    offer_lock: str = Field(min_length=1, max_length=320)
    cta_offer_lock: str | None = Field(default=None, max_length=500)
    cta_type: Literal["question", "time_ask", "value_asset", "pilot", "referral", "event_invite"] | None = None
    style_profile: WebStyleProfile
    company_context: WebCompanyContext = Field(default_factory=WebCompanyContext)


class PresetPreviewResponse(BaseModel):
    preset_id: str
    subject: str
    body: str
    vibeLabel: str
    vibeTags: list[str]
    whyItWorks: list[str]
    sliderSummary: dict[str, int]
    validationWarning: str | None = None
    debug: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class PresetPreviewBatchGlobalSliders(BaseModel):
    formality: int = Field(ge=0, le=100)
    brevity: int = Field(ge=0, le=100)
    directness: int = Field(ge=0, le=100)
    personalization: int = Field(ge=0, le=100)


class PresetPreviewBatchProductContext(BaseModel):
    product_name: str = Field(min_length=1, max_length=300)
    one_line_value: str = Field(min_length=1, max_length=1200)
    proof_points: list[str] = Field(default_factory=list, max_length=12)
    target_outcome: str = Field(min_length=1, max_length=240)


class PresetPreviewBatchRawResearch(BaseModel):
    deep_research_paste: str = Field(min_length=1, max_length=50000)
    company_notes: str | None = Field(default=None, max_length=12000)
    extra_constraints: str | None = Field(default=None, max_length=4000)


class PresetPreviewBatchPreset(BaseModel):
    preset_id: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=200)
    slider_overrides: dict[str, int] = Field(default_factory=dict)


class PresetPreviewBatchRequest(BaseModel):
    prospect: WebProspectInput
    prospect_first_name: str | None = Field(default=None, max_length=60)
    product_context: PresetPreviewBatchProductContext
    raw_research: PresetPreviewBatchRawResearch
    global_sliders: PresetPreviewBatchGlobalSliders
    presets: list[PresetPreviewBatchPreset] = Field(default_factory=list, min_length=1, max_length=24)
    offer_lock: str = Field(min_length=1, max_length=320)
    cta_lock: str | None = Field(default=None, max_length=500)
    cta_lock_text: str | None = Field(default=None, max_length=500)
    cta_type: Literal["question", "time_ask", "value_asset", "pilot", "referral", "event_invite"] | None = None
    hook_strategy: Literal["research_anchored", "role_hypothesis", "domain_signal"] | None = None


class PresetPreviewBatchItem(BaseModel):
    preset_id: str
    label: str
    effective_sliders: dict[str, int]
    vibeLabel: str
    vibeTags: list[str]
    whyItWorks: list[str]
    subject: str
    body: str
    debug: dict[str, Any] = Field(default_factory=dict)


class PresetPreviewBatchResponse(BaseModel):
    previews: list[PresetPreviewBatchItem]
    meta: dict[str, Any] = Field(default_factory=dict)


class ResearchRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=200)
    domain: str | None = Field(default=None, max_length=400)
    company_name: str | None = Field(default=None, max_length=200)


class ResearchCreateResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "complete", "failed"]


class ResearchResult(BaseModel):
    domain: str = Field(default="Unknown")
    summary: str = Field(default="Unknown")
    products: list[str] = Field(default_factory=list)
    ICP: str = Field(default="Unknown")
    differentiators: list[str] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)
    news: list[NewsItem] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    result_text: str = Field(default="")


class ResearchStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "complete", "failed"]
    progress: str | None = None
    result: ResearchResult | str | None = None
    error: str | None = None


class WebFeedbackRequest(BaseModel):
    session_id: str = Field(min_length=1)
    draft_before: str = Field(min_length=1, max_length=80000)
    draft_after: str = Field(min_length=1, max_length=80000)
    style_profile: WebStyleProfile = Field(default_factory=WebStyleProfile)


class EmailIdentity(BaseModel):
    sender_name: str | None = None
    sender_company: str
    prospect_name: str
    prospect_title: str
    prospect_company: str


class EmailStructure(BaseModel):
    opener_hook: str
    why_you_why_now: str
    value_points: list[str] = Field(min_length=2, max_length=3)
    proof_line: str | None = None
    cta_line_locked: str


class EmailConstraints(BaseModel):
    forbidden_claims: list[str] = Field(default_factory=list)
    max_facts_allowed: int = Field(default=4, ge=1, le=12)
    target_word_count_range_by_length_slider: dict[str, list[int]]
    must_include_cta_lock: bool = True


class EmailBlueprint(BaseModel):
    identity: EmailIdentity
    angle: str
    personalization_facts_used: list[str] = Field(default_factory=list)
    structure: EmailStructure
    constraints: EmailConstraints


class ValidationResult(BaseModel):
    passed: bool
    violations: list[str] = Field(default_factory=list)
    validator_attempt_count: int = 1
    repair_attempt_count: int = 0
    repaired: bool = False


class DebugMeta(BaseModel):
    trace_id: str
    prompt_template_hash: str
    prompt_template_version: str
    validation: ValidationResult


class RenderResult(BaseModel):
    subject: str
    body: str
    sources: list[Citation] = Field(default_factory=list)
    debug: DebugMeta
