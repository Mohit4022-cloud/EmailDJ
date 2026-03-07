from __future__ import annotations

import re
from typing import Iterable

from app.schemas import PresetPreviewBatchPreset, PresetPreviewBatchRequest, PresetPreviewRequest, WebGenerateRequest

from .research_state import classify_research_state, has_grounded_research_signal, usable_research_text
from .types import NormalizedContext, ProductCategory


INTERNAL_MODULE_KEYWORDS = {
    "prospect enrichment",
    "sequence qa",
    "persona research",
    "messaging logic",
    "sequence analytics",
    "reply scorer",
    "first-touch optimizer",
}

CATEGORY_KEYWORDS: dict[ProductCategory, tuple[str, ...]] = {
    "brand_protection": (
        "brand protection",
        "trademark",
        "counterfeit",
        "infringement",
        "ip",
        "enforcement",
        "takedown",
        "rights management",
    ),
    "sales_outbound": (
        "outbound",
        "sdr",
        "bdr",
        "sequence",
        "reply",
        "meeting",
        "pipeline",
        "prospecting",
        "cold email",
    ),
    "generic_b2b": (),
}


def clamp_int(value: int, minimum: int = 0, maximum: int = 100) -> int:
    return max(minimum, min(maximum, int(value)))


def clamp_float(value: float, minimum: float = -1.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def axis_to_slider(value: float) -> int:
    return clamp_int(int(round((clamp_float(value) + 1.0) * 50.0)))


def slider_to_axis(value: int) -> float:
    return round(((clamp_int(value) - 50) / 50.0), 3)


def style_to_global_sliders(style: dict[str, float]) -> dict[str, int]:
    return {
        "formality": clamp_int(100 - axis_to_slider(float(style.get("formality", 0.0)))),
        "brevity": clamp_int(100 - axis_to_slider(float(style.get("length", 0.0)))),
        "directness": clamp_int(100 - axis_to_slider(float(style.get("assertiveness", 0.0)))),
        "personalization": clamp_int(axis_to_slider(float(style.get("orientation", 0.0)))),
    }


def global_sliders_to_style(sliders: dict[str, int]) -> dict[str, float]:
    return {
        "formality": slider_to_axis(100 - clamp_int(int(sliders.get("formality", 50)))),
        "orientation": slider_to_axis(clamp_int(int(sliders.get("personalization", 50)))),
        "length": slider_to_axis(100 - clamp_int(int(sliders.get("brevity", 50)))),
        "assertiveness": slider_to_axis(100 - clamp_int(int(sliders.get("directness", 50)))),
    }


def _text(value: str | None) -> str:
    return str(value or "").strip()


def _first_name(name: str) -> str:
    parts = [p for p in re.split(r"\s+", _text(name)) if p]
    return parts[0] if parts else "there"


def _parse_items(value: str | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"\n|,|;|\|", _text(value)):
        item = re.sub(r"\s+", " ", raw.strip(" -*\t\r"))
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _parse_mixed_items(value: str | list[str] | None) -> list[str]:
    if isinstance(value, list):
        return _proof_points(value)
    return _parse_items(value)


def _first_sentences(value: str, limit: int = 3) -> list[str]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", _text(value)) if s.strip()]
    return sentences[:limit]


def _proof_points(*groups: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for raw in group:
            item = _text(raw)
            if not item:
                continue
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
            if len(out) >= 8:
                return out
    return out


def _prospect_notes_from_generate_request(req: WebGenerateRequest) -> str:
    lines: list[str] = []

    target = req.target_profile_override
    if target is not None:
        for item in _first_sentences(_text(target.summary), limit=2):
            lines.append(item)
        lines.extend(_proof_points(target.proof_points))
        for news in list(target.recent_news or [])[:2]:
            headline = _text(getattr(news, "headline", ""))
            why_it_matters = _text(getattr(news, "why_it_matters", ""))
            if headline and why_it_matters:
                lines.append(f"{headline} {why_it_matters}")
            elif headline:
                lines.append(headline)

    contact = req.contact_profile_override
    if contact is not None:
        for item in _first_sentences(_text(contact.role_summary), limit=2):
            lines.append(item)
        lines.extend(_proof_points(contact.talking_points, contact.inferred_kpis_or_priorities))
        for news in list(contact.related_news or [])[:2]:
            headline = _text(getattr(news, "headline", ""))
            why_it_matters = _text(getattr(news, "why_it_matters", ""))
            if headline and why_it_matters:
                lines.append(f"{headline} {why_it_matters}")
            elif headline:
                lines.append(headline)

    return "\n".join(_proof_points(lines))


def _detect_signal(research_text: str) -> bool:
    return has_grounded_research_signal(research_text)


def _looks_internal_module(item: str) -> bool:
    key = _text(item).lower()
    return any(marker in key for marker in INTERNAL_MODULE_KEYWORDS)


def _split_offerings_and_modules(
    *,
    other_products: str | None,
    seller_offerings: str | list[str] | None,
    internal_modules: str | list[str] | None,
) -> tuple[list[str], list[str]]:
    explicit_seller = _parse_mixed_items(seller_offerings)
    explicit_internal = _parse_mixed_items(internal_modules)
    legacy_other = _parse_items(other_products)

    if explicit_internal:
        internal_set = {item.lower() for item in explicit_internal}
        seller_pool = _proof_points(explicit_seller, legacy_other)
        seller_clean = [item for item in seller_pool if item.lower() not in internal_set]
        return seller_clean, explicit_internal

    candidate_pool = _proof_points(explicit_seller, legacy_other)
    seller_clean: list[str] = []
    internal_guess: list[str] = []
    for item in candidate_pool:
        if _looks_internal_module(item):
            internal_guess.append(item)
        else:
            seller_clean.append(item)
    return seller_clean, internal_guess


def _score_hits(text: str, keywords: tuple[str, ...]) -> float:
    if not text:
        return 0.0
    hits = sum(1 for token in keywords if token in text)
    if hits <= 0:
        return 0.0
    return min(1.0, hits / 3.0)


def _infer_product_category(*, current_product: str, company_notes: str, research_text: str) -> tuple[ProductCategory, float]:
    scores: dict[ProductCategory, float] = {
        "brand_protection": 0.0,
        "sales_outbound": 0.0,
        "generic_b2b": 0.05,
    }

    weighted_fields: list[tuple[float, str]] = [
        (0.60, _text(current_product).lower()),
        (0.30, _text(company_notes).lower()),
        (0.10, _text(research_text).lower()),
    ]
    for weight, text in weighted_fields:
        if not text:
            continue
        for category in ("brand_protection", "sales_outbound"):
            scores[category] += weight * _score_hits(text, CATEGORY_KEYWORDS[category])

    winner: ProductCategory = "brand_protection" if scores["brand_protection"] >= scores["sales_outbound"] else "sales_outbound"
    confidence = round(scores[winner], 3)
    if confidence < 0.40:
        return "generic_b2b", confidence
    return winner, confidence


def normalize_generate_request(req: WebGenerateRequest, *, preset_id: str | None = None) -> NormalizedContext:
    style_payload = req.style_profile.model_dump(mode="json")
    global_sliders = style_to_global_sliders(style_payload)
    company_context = req.company_context
    company_notes = _text(company_context.company_notes)
    raw_research_text = _text(req.research_text)
    cleaned_research_text = usable_research_text(raw_research_text)
    research_state = classify_research_state(raw_research_text)
    seller_offerings, internal_modules = _split_offerings_and_modules(
        other_products=company_context.other_products,
        seller_offerings=company_context.seller_offerings,
        internal_modules=company_context.internal_modules,
    )
    note_points = _first_sentences(company_notes, limit=3)
    sender_override_points = list((req.sender_profile_override.proof_points if req.sender_profile_override else []) or [])
    seller_proof_points = _proof_points(sender_override_points)
    seller_context_points = _proof_points(seller_offerings, note_points)
    proof_points = _proof_points(seller_context_points, seller_proof_points)
    prospect_notes = _prospect_notes_from_generate_request(req)

    cta_lock = _text(req.cta_offer_lock) or _text(company_context.cta_offer_lock) or "Open to a quick chat to see if this is relevant?"

    prospect_name = _text(req.prospect.name)
    current_product = _text(company_context.current_product) or _text(req.offer_lock)
    category, category_confidence = _infer_product_category(
        current_product=current_product,
        company_notes=company_notes,
        research_text=cleaned_research_text,
    )
    return NormalizedContext(
        source="generate",
        prospect_name=prospect_name,
        prospect_first_name=_text(req.prospect_first_name) or _first_name(prospect_name),
        prospect_title=_text(req.prospect.title),
        prospect_company=_text(req.prospect.company),
        prospect_company_url=_text(req.prospect.company_url),
        prospect_linkedin_url=_text(req.prospect.linkedin_url),
        sender_company_name=_text(company_context.company_name),
        sender_company_url=_text(company_context.company_url),
        offer_lock=_text(req.offer_lock),
        current_product=current_product,
        cta_lock=cta_lock,
        cta_type=_text(req.cta_type) or _text(company_context.cta_type),
        research_text=raw_research_text,
        usable_research_text=cleaned_research_text,
        research_state=research_state,
        prospect_notes=prospect_notes,
        company_notes=company_notes,
        proof_points=proof_points,
        seller_proof_points=seller_proof_points,
        seller_context_points=seller_context_points,
        seller_offerings=seller_offerings,
        internal_modules=internal_modules,
        product_category=category,
        category_confidence=category_confidence,
        preset_id=_text(preset_id) or _text(req.preset_id) or "straight_shooter",
        preset_label="",
        hook_strategy=None,
        sliders=global_sliders,
        style_profile={k: float(v) for k, v in style_payload.items()},
        response_contract=_text(req.response_contract) or "legacy_text",
        signal_available=_detect_signal(raw_research_text),
    )


def normalize_single_preview_request(req: PresetPreviewRequest) -> NormalizedContext:
    style_payload = req.style_profile.model_dump(mode="json")
    global_sliders = style_to_global_sliders(style_payload)
    company_notes = _text(req.company_context.company_notes)
    raw_research_text = _text(req.research_text)
    cleaned_research_text = usable_research_text(raw_research_text)
    research_state = classify_research_state(raw_research_text)
    seller_offerings, internal_modules = _split_offerings_and_modules(
        other_products=req.company_context.other_products,
        seller_offerings=req.company_context.seller_offerings,
        internal_modules=req.company_context.internal_modules,
    )
    seller_proof_points: list[str] = []
    seller_context_points = _proof_points(seller_offerings, _first_sentences(company_notes, limit=3))
    proof_points = _proof_points(seller_context_points, seller_proof_points)

    prospect_name = _text(req.prospect.name)
    cta_lock = _text(req.cta_offer_lock) or _text(req.company_context.cta_offer_lock) or "Open to a quick chat to see if this is relevant?"
    current_product = _text(req.company_context.current_product) or _text(req.offer_lock)
    category, category_confidence = _infer_product_category(
        current_product=current_product,
        company_notes=company_notes,
        research_text=cleaned_research_text,
    )

    return NormalizedContext(
        source="preview",
        prospect_name=prospect_name,
        prospect_first_name=_text(req.prospect_first_name) or _first_name(prospect_name),
        prospect_title=_text(req.prospect.title),
        prospect_company=_text(req.prospect.company),
        prospect_company_url=_text(req.prospect.company_url),
        prospect_linkedin_url=_text(req.prospect.linkedin_url),
        sender_company_name=_text(req.company_context.company_name),
        sender_company_url=_text(req.company_context.company_url),
        offer_lock=_text(req.offer_lock),
        current_product=current_product,
        cta_lock=cta_lock,
        cta_type=_text(req.cta_type) or _text(req.company_context.cta_type),
        research_text=raw_research_text,
        usable_research_text=cleaned_research_text,
        research_state=research_state,
        prospect_notes="",
        company_notes=company_notes,
        proof_points=proof_points,
        seller_proof_points=seller_proof_points,
        seller_context_points=seller_context_points,
        seller_offerings=seller_offerings,
        internal_modules=internal_modules,
        product_category=category,
        category_confidence=category_confidence,
        preset_id=_text(req.preset_id),
        preset_label=_text(req.preset_id).replace("_", " ").title(),
        hook_strategy=None,
        sliders=global_sliders,
        style_profile={k: float(v) for k, v in style_payload.items()},
        response_contract="email_json_v1",
        signal_available=_detect_signal(raw_research_text),
    )


def _apply_slider_overrides(global_sliders: dict[str, int], preset: PresetPreviewBatchPreset) -> dict[str, int]:
    merged = {k: clamp_int(v) for k, v in global_sliders.items()}
    for key in ("formality", "brevity", "directness", "personalization"):
        if key in preset.slider_overrides:
            merged[key] = clamp_int(int(preset.slider_overrides[key]))
    return merged


def normalize_batch_preview_request(req: PresetPreviewBatchRequest, preset: PresetPreviewBatchPreset) -> NormalizedContext:
    global_sliders = _apply_slider_overrides(req.global_sliders.model_dump(mode="json"), preset)
    style_profile = global_sliders_to_style(global_sliders)
    raw_research_text = _text(req.raw_research.deep_research_paste)
    cleaned_research_text = usable_research_text(raw_research_text)
    research_state = classify_research_state(raw_research_text)
    company_notes = _text(req.raw_research.company_notes)

    seller_offerings = _proof_points(req.product_context.proof_points)
    seller_proof_points = _proof_points(req.product_context.proof_points)
    seller_context_points = _proof_points(_parse_items(company_notes), _first_sentences(company_notes, limit=2))
    proof_points = _proof_points(seller_context_points, seller_proof_points)
    cta_lock = _text(req.cta_lock) or _text(req.cta_lock_text) or "Open to a quick chat to see if this is relevant?"
    prospect_name = _text(req.prospect.name)
    current_product = _text(req.product_context.product_name)
    category, category_confidence = _infer_product_category(
        current_product=current_product,
        company_notes=company_notes,
        research_text=cleaned_research_text,
    )

    return NormalizedContext(
        source="preview",
        prospect_name=prospect_name,
        prospect_first_name=_text(req.prospect_first_name) or _first_name(prospect_name),
        prospect_title=_text(req.prospect.title),
        prospect_company=_text(req.prospect.company),
        prospect_company_url=_text(req.prospect.company_url),
        prospect_linkedin_url=_text(req.prospect.linkedin_url),
        sender_company_name="",
        sender_company_url="",
        offer_lock=_text(req.offer_lock) or current_product,
        current_product=current_product,
        cta_lock=cta_lock,
        cta_type=_text(req.cta_type),
        research_text=raw_research_text,
        usable_research_text=cleaned_research_text,
        research_state=research_state,
        prospect_notes="",
        company_notes=company_notes,
        proof_points=proof_points,
        seller_proof_points=seller_proof_points,
        seller_context_points=seller_context_points,
        seller_offerings=seller_offerings,
        internal_modules=[],
        product_category=category,
        category_confidence=category_confidence,
        preset_id=_text(preset.preset_id),
        preset_label=_text(preset.label) or _text(preset.preset_id),
        hook_strategy=req.hook_strategy,
        sliders=global_sliders,
        style_profile=style_profile,
        response_contract="email_json_v1",
        signal_available=_detect_signal(raw_research_text),
    )
