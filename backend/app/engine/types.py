from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


HookType = Literal["research_anchored", "role_hypothesis", "domain_signal"]
ProductCategory = Literal["brand_protection", "sales_outbound", "generic_b2b"]


@dataclass(slots=True)
class NormalizedContext:
    source: Literal["generate", "preview"]
    prospect_name: str
    prospect_first_name: str
    prospect_title: str
    prospect_company: str
    prospect_company_url: str
    prospect_linkedin_url: str

    sender_company_name: str
    sender_company_url: str

    offer_lock: str
    current_product: str
    cta_lock: str
    cta_type: str

    research_text: str
    company_notes: str
    proof_points: list[str]
    seller_offerings: list[str]
    internal_modules: list[str]
    product_category: ProductCategory
    category_confidence: float

    preset_id: str
    preset_label: str
    hook_strategy: HookType | None

    sliders: dict[str, int]
    style_profile: dict[str, float]
    response_contract: str

    signal_available: bool


@dataclass(slots=True)
class MessagePlan:
    hook_type: HookType
    hook_sentence: str
    persona_pains_kpis: list[str]
    value_prop: str
    proof_point: str
    cta_line_locked: str
    constraints: dict[str, bool]
    selected_beat_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EmailDraft:
    subject: str
    body: str
    subject_source: str = "hook"
    body_sources: list[str] = field(default_factory=list)
    selected_beat_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ValidationDebug:
    violations: list[str] = field(default_factory=list)
    validator_attempt_count: int = 1
    repair_attempt_count: int = 0
    repaired: bool = False
    degraded: bool = False
    draft_source: str = "deterministic"
    llm_attempt_count: int = 0
    llm_used: bool = False
    stage_latency_ms: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class EngineResult:
    draft: EmailDraft
    debug: ValidationDebug
    plan: MessagePlan
