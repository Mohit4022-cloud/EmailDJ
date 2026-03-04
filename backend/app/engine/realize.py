from __future__ import annotations

import re

from .types import EmailDraft, MessagePlan, NormalizedContext, ProductCategory


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def word_band_for_brevity(brevity: int) -> tuple[int, int]:
    if brevity <= 20:
        return (120, 220)
    if brevity <= 40:
        return (95, 170)
    if brevity <= 60:
        return (70, 130)
    if brevity <= 80:
        return (50, 95)
    return (40, 75)


def _trim_to_words(text: str, max_words: int) -> str:
    words = re.findall(r"\S+", text)
    if len(words) <= max_words:
        return text
    trimmed = " ".join(words[:max_words]).strip()
    if not trimmed.endswith((".", "!", "?")):
        trimmed = trimmed.rstrip(",;:") + "."
    return trimmed


def _length_tier(brevity: int) -> str:
    if brevity >= 67:
        return "short"
    if brevity >= 34:
        return "medium"
    return "long"


def _subject(ctx: NormalizedContext, plan: MessagePlan) -> str:
    company = ctx.prospect_company or "your team"
    title = ctx.prospect_title or "your role"
    offer = ctx.offer_lock or ctx.current_product or "Quick idea"

    preset = (ctx.preset_id or "").strip().lower()
    if plan.hook_type == "research_anchored":
        base = f"{offer} for {company}"
    elif plan.hook_type == "domain_signal":
        base = f"{title} + {offer}"
    else:
        base = f"Idea for {title}"

    if preset in {"challenger", "headliner"}:
        base = f"Priority idea for {company}"
    elif preset in {"warm_intro", "warm-intro"}:
        base = f"Quick thought for {title}"

    subject = re.sub(r"\s+", " ", base).strip()
    return subject[:70]


def _style_line(ctx: NormalizedContext) -> str:
    directness = int(ctx.sliders.get("directness", 50))
    personalization = int(ctx.sliders.get("personalization", 50))
    preset = (ctx.preset_id or "").strip().lower()

    if preset in {"warm_intro", "warm-intro"}:
        return "If this is off-base, ignore this note and I can recalibrate quickly."
    if preset in {"challenger", "headliner"}:
        return "Short version: small workflow gaps can compound faster than expected."

    if ctx.product_category == "brand_protection":
        if directness >= 70:
            return "Short version: this is a practical way to speed enforcement response and reduce delay."
        if personalization >= 70:
            return "I kept this focused on the outcomes your role usually owns in brand and IP workflows."
        return "This stays focused on practical enforcement and risk-control outcomes."

    if ctx.product_category == "sales_outbound":
        if directness >= 70:
            return "Short version: this can improve response consistency quickly with fewer manual edits."
        if personalization >= 70:
            return "I kept this focused on the outcomes your role usually owns in outreach execution."
        return "This stays focused on practical response-quality outcomes."

    if directness >= 70:
        return "Short version: this is a practical way to improve execution consistency quickly."
    if personalization >= 70:
        return "I kept this focused on the outcomes your role usually owns."
    return "This stays focused on practical execution outcomes."


def _extra_beats(category: ProductCategory, tier: str, plan: MessagePlan) -> list[tuple[str, str, str]]:
    # id, text, source_label
    medium_common = [
        ("how_it_works", "The workflow is intentionally simple: align priority signals, route action quickly, and keep handoffs clear.", "how_it_works"),
    ]
    long_common = [
        ("adoption_fit", "This can run alongside existing tooling, so teams can start with narrow scope and expand only where useful.", "adoption_fit"),
    ]

    if category == "brand_protection":
        medium_specific = [
            ("brand_risk_context", "Teams usually get better outcomes when high-risk trademark and infringement cases are escalated with consistent criteria.", "pain"),
        ]
        long_specific = [
            ("ops_clarity", "That structure tends to reduce queue churn and makes enforcement follow-through easier to govern.", "value"),
        ]
    elif category == "sales_outbound":
        medium_specific = [
            ("response_consistency", "Teams usually improve response quality when core messaging decisions are explicit and easier to reuse.", "pain"),
        ]
        long_specific = [
            ("workflow_adoption", "That approach tends to reduce message drift while still giving reps room to personalize when needed.", "value"),
        ]
    else:
        medium_specific = [
            ("workflow_clarity", "Teams usually see stronger outcomes when execution criteria are explicit and handoffs are easier to follow.", "pain"),
        ]
        long_specific = [
            ("rollout_fit", "That tends to make rollout smoother, especially when teams need consistency without adding overhead.", "value"),
        ]

    beats: list[tuple[str, str, str]] = []
    if tier in {"medium", "long"}:
        beats.extend(medium_specific)
        beats.extend(medium_common)
    if tier == "long":
        beats.extend(long_specific)
        beats.extend(long_common)
    return beats


def realize_email(plan: MessagePlan, ctx: NormalizedContext) -> EmailDraft:
    tier = _length_tier(int(ctx.sliders.get("brevity", 50)))

    greeting = f"Hi {ctx.prospect_first_name or 'there'},"
    lines_with_sources: list[tuple[str, str, str]] = [
        ("greeting", greeting, "hook"),
        ("hook", plan.hook_sentence, "hook"),
        ("value_prop", plan.value_prop, "value"),
    ]

    kpi_line = "Common priorities here are " + ", ".join(plan.persona_pains_kpis[:2]) + "."
    lines_with_sources.append(("kpis", kpi_line, "pain"))

    if plan.proof_point:
        lines_with_sources.append(("proof_point", f"For context, {plan.proof_point.rstrip('.') }.", "proof"))

    lines_with_sources.append(("style_line", _style_line(ctx), "how_it_works"))
    lines_with_sources.extend(_extra_beats(ctx.product_category, tier, plan))
    lines_with_sources.append(("cta", plan.cta_line_locked, "cta"))

    body = "\n\n".join([line.strip() for _, line, _ in lines_with_sources if line.strip()])

    # Soft length policy: only cap over-length output; do not force minimum filler.
    _, max_words = word_band_for_brevity(int(ctx.sliders.get("brevity", 50)))
    wc = _word_count(body)
    if wc > max_words:
        parts = body.split("\n\n")
        cta = parts[-1]
        narrative = "\n\n".join(parts[:-1])
        narrative = _trim_to_words(narrative, max_words - _word_count(cta) - 2)
        body = (narrative.strip() + "\n\n" + cta.strip()).strip()

    return EmailDraft(
        subject=_subject(ctx, plan),
        body=body,
        subject_source="subject_strategy",
        body_sources=[source for _, _, source in lines_with_sources],
        selected_beat_ids=[beat_id for beat_id, _, _ in lines_with_sources],
    )
