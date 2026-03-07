from __future__ import annotations

import re

from .types import MessagePlan, NormalizedContext, ProductCategory


SALES_ROLE_KPI_MAP: list[tuple[tuple[str, ...], list[str]]] = [
    (("sdr", "sales development", "bdr"), ["reply rate", "meeting quality", "pipeline coverage"]),
    (("revops", "revenue operations", "ops"), ["forecast reliability", "pipeline efficiency", "rep productivity"]),
    (("vp", "head", "director"), ["team output consistency", "pipeline conversion", "execution speed"]),
    (("marketing",), ["lead quality", "conversion efficiency", "campaign impact"]),
]

BRAND_ROLE_KPI_MAP: list[tuple[tuple[str, ...], list[str]]] = [
    (("legal", "counsel", "ip", "trademark"), ["enforcement consistency", "case resolution speed", "risk reduction"]),
    (("brand", "trust", "safety"), ["brand misuse coverage", "high-risk case prioritization", "takedown velocity"]),
    (("operations", "ops"), ["workflow reliability", "handoff clarity", "response turnaround"]),
]

GENERIC_ROLE_KPI_MAP: list[tuple[tuple[str, ...], list[str]]] = [
    (("director", "head", "vp"), ["execution consistency", "team throughput", "time-to-outcome"]),
    (("operations", "ops"), ["workflow reliability", "handoff quality", "cycle-time reduction"]),
]


def _text(value: str | None) -> str:
    return str(value or "").strip()


def _first_sentence(text: str, default: str) -> str:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", _text(text)) if p.strip()]
    if not parts:
        return default
    sentence = re.sub(r"^[#>*\-\s]+", "", parts[0])
    sentence = re.sub(r"\s+", " ", sentence).strip()
    if not sentence.endswith((".", "!", "?")):
        sentence += "."
    return sentence[:220]


def _kpis_for_role(title: str, mapping: list[tuple[tuple[str, ...], list[str]]], default: list[str]) -> list[str]:
    lowered = _text(title).lower()
    for needles, kpis in mapping:
        if any(token in lowered for token in needles):
            return kpis
    return default


def _persona_kpis(title: str, category: ProductCategory) -> list[str]:
    if category == "sales_outbound":
        return _kpis_for_role(title, SALES_ROLE_KPI_MAP, ["message consistency", "response quality", "faster iteration"])
    if category == "brand_protection":
        return _kpis_for_role(title, BRAND_ROLE_KPI_MAP, ["enforcement consistency", "case prioritization", "response speed"])
    return _kpis_for_role(title, GENERIC_ROLE_KPI_MAP, ["execution consistency", "handoff clarity", "time-to-outcome"])


def _proof_point(ctx: NormalizedContext) -> str:
    if ctx.proof_points:
        return ctx.proof_points[0]
    notes = _text(ctx.company_notes)
    if notes:
        return _first_sentence(notes, "")
    return ""


def _hook_type(ctx: NormalizedContext) -> str:
    if ctx.hook_strategy:
        return ctx.hook_strategy
    if ctx.signal_available and _text(ctx.usable_research_text):
        return "research_anchored"
    if ctx.prospect_company_url:
        return "domain_signal"
    return "role_hypothesis"


def _role_hypothesis_sentence(role_label: str, category: ProductCategory) -> str:
    if category == "brand_protection":
        return f"I may be off, but teams in {role_label} usually focus on enforcement speed, case prioritization, and risk control."
    if category == "sales_outbound":
        return f"I may be off, but teams in {role_label} usually care about response quality, meeting conversion, and consistency."
    return f"I may be off, but teams in {role_label} usually focus on workflow reliability and faster execution."


def _value_prop(ctx: NormalizedContext, role_anchor: str) -> str:
    offer = ctx.offer_lock or ctx.current_product or "our platform"
    if ctx.product_category == "brand_protection":
        return f"{offer} helps {role_anchor} reduce trademark and infringement response lag with clearer enforcement workflows."
    if ctx.product_category == "sales_outbound":
        return f"{offer} helps {role_anchor} improve outreach consistency and response quality with less manual rework."
    return f"{offer} helps {role_anchor} improve execution consistency without adding process overhead."


def build_message_plan(ctx: NormalizedContext) -> MessagePlan:
    hook_type = _hook_type(ctx)
    if hook_type == "research_anchored":
        hook_sentence = _first_sentence(
            ctx.usable_research_text,
            f"Saw a public signal related to {ctx.prospect_company} and thought this could be timely.",
        )
    elif hook_type == "domain_signal":
        domain_hint = ctx.prospect_company_url or ctx.prospect_company
        hook_sentence = f"I checked {domain_hint} and this seemed potentially relevant for your team."
    else:
        role_label = ctx.prospect_title or "your role"
        hook_sentence = _role_hypothesis_sentence(role_label, ctx.product_category)

    kpis = _persona_kpis(ctx.prospect_title, ctx.product_category)
    role_anchor = ctx.prospect_title or "the team"
    value_prop = _value_prop(ctx, role_anchor)

    proof_point = _proof_point(ctx)
    cta_lock = ctx.cta_lock or "Open to a quick chat to see if this is relevant?"

    beat_ids = ["hook", "value_prop", "kpis", "cta"]
    if proof_point:
        beat_ids.insert(3, "proof_point")

    return MessagePlan(
        hook_type=hook_type,
        hook_sentence=hook_sentence,
        persona_pains_kpis=kpis,
        value_prop=value_prop,
        proof_point=proof_point,
        cta_line_locked=cta_lock,
        constraints={
            "forbid_internal_rubric_text": True,
            "no_unsourced_claims": True,
        },
        selected_beat_ids=beat_ids,
    )
