"""Web MVP remix engine with style-vector controls and session caching."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from email_generation.prompt_templates import get_web_mvp_prompt
from email_generation.quick_generate import _mode, _real_generate
from infra.redis_client import get_redis

SESSION_TTL_SECONDS = 24 * 60 * 60
STYLE_CACHE_MAX = 5


def _session_key(session_id: str) -> str:
    return f"web_mvp:session:{session_id}"


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def _normalize_optional_text(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_length:
        return text[:max_length].rstrip() + "..."
    return text


def _catalog_items(raw: str | None) -> list[str]:
    if not raw:
        return []
    items: list[str] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        for part in line.replace(";", ",").split(","):
            candidate = part.strip(" -*\t")
            if not candidate:
                continue
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(candidate)
            if len(items) >= 8:
                return items
    return items


def normalize_company_context(company_context: dict[str, Any] | None) -> dict[str, str]:
    source = company_context or {}
    normalized: dict[str, str] = {}
    for key, max_length in (
        ("company_name", 160),
        ("company_url", 400),
        ("current_product", 240),
        ("other_products", 8000),
        ("company_notes", 8000),
    ):
        value = _normalize_optional_text(source.get(key), max_length=max_length)
        if value:
            normalized[key] = value
    return normalized


def build_company_context_brief(company_context: dict[str, Any] | None) -> str:
    normalized = normalize_company_context(company_context)
    if not normalized:
        return "No sender company context provided."

    lines: list[str] = []
    company_name = normalized.get("company_name")
    company_url = normalized.get("company_url")
    current_product = normalized.get("current_product")
    other_products = _catalog_items(normalized.get("other_products"))
    notes = normalized.get("company_notes")

    if company_name:
        lines.append(f"Sender company: {company_name}.")
    if company_url:
        lines.append(f"Website: {company_url}.")
    if current_product:
        lines.append(f"Primary offering: {current_product}.")
    if other_products:
        lines.append(f"Adjacent offerings: {', '.join(other_products[:4])}.")
    if notes:
        compact_notes = " ".join(notes.split())
        if len(compact_notes) > 800:
            compact_notes = compact_notes[:800].rstrip() + "..."
        lines.append(f"Context notes: {compact_notes}")
    return " ".join(lines)


def normalize_style_profile(style_profile: dict[str, Any]) -> dict[str, float]:
    return {
        "formality": _clamp(style_profile.get("formality", 0.0)),
        "orientation": _clamp(style_profile.get("orientation", 0.0)),
        "length": _clamp(style_profile.get("length", 0.0)),
        "assertiveness": _clamp(style_profile.get("assertiveness", 0.0)),
    }


def style_profile_key(style_profile: dict[str, float]) -> str:
    return (
        f"f:{style_profile['formality']:.2f}|"
        f"o:{style_profile['orientation']:.2f}|"
        f"l:{style_profile['length']:.2f}|"
        f"a:{style_profile['assertiveness']:.2f}"
    )


def build_factual_brief(prospect: dict[str, Any], research_text: str) -> str:
    compact = " ".join(research_text.split())
    if len(compact) > 1600:
        compact = compact[:1600].rstrip() + "..."
    linkedin = prospect.get("linkedin_url") or "not provided"
    return (
        f"Prospect: {prospect.get('name')} ({prospect.get('title')}) at {prospect.get('company')}. "
        f"LinkedIn URL: {linkedin}. "
        f"Research excerpt: {compact}"
    )


def build_anchors(prospect: dict[str, Any], company_context: dict[str, Any] | None = None) -> dict[str, str]:
    normalized = normalize_company_context(company_context)
    focus = normalized.get("current_product")
    seller = normalized.get("company_name") or "your company"
    mapping_anchor = (
        f"Map {focus} from {seller} to {prospect.get('company')}'s current outbound priorities with one concrete value bridge."
        if focus
        else f"Map the most relevant capability from {seller} to {prospect.get('company')}'s current outbound priorities with one concrete value bridge."
    )
    return {
        "intent": f"Help {prospect.get('company')} improve SDR response quality and throughput.",
        "cta": "Offer a low-friction 15-minute walkthrough next week.",
        "constraint": "One clear ask, no fabricated claims, and explicit relevance to current initiatives.",
        "service_mapping": mapping_anchor,
    }


def style_directives(style_profile: dict[str, float]) -> dict[str, str]:
    formality = style_profile["formality"]
    orientation = style_profile["orientation"]
    length = style_profile["length"]
    assertiveness = style_profile["assertiveness"]

    return {
        "formality": (
            "formal and executive" if formality > 0.35 else "conversational and plainspoken" if formality < -0.35 else "professional-neutral"
        ),
        "orientation": (
            "lead with pain/problem framing" if orientation < -0.25 else "lead with outcomes and upside framing" if orientation > 0.25 else "balanced pain/outcome framing"
        ),
        "length": (
            "very short (60-90 words)" if length < -0.5 else "compact (90-120 words)" if length < 0.2 else "expanded (120-170 words)"
        ),
        "assertiveness": (
            "bold ask with direct next step" if assertiveness > 0.45 else "diplomatic ask with softer tone" if assertiveness < -0.45 else "confident but measured ask"
        ),
    }


def _mock_subject(directives: dict[str, str], company: str, company_context: dict[str, Any] | None = None) -> str:
    normalized = normalize_company_context(company_context)
    focus = normalized.get("current_product")
    if focus:
        return f"Subject: {focus} fit for {company}'s outbound goals"
    if "pain/problem" in directives["orientation"]:
        return f"Subject: Quick fix for {company}'s outbound bottleneck"
    if "outcomes and upside" in directives["orientation"]:
        return f"Subject: Outcome lift idea for {company}'s SDR team"
    return f"Subject: A practical outbound idea for {company}"


def _mock_body(
    prospect: dict[str, Any],
    anchors: dict[str, str],
    directives: dict[str, str],
    company_context: dict[str, Any] | None = None,
) -> str:
    normalized = normalize_company_context(company_context)
    focus = normalized.get("current_product")
    seller = normalized.get("company_name") or "our team"
    catalog = _catalog_items(normalized.get("other_products"))
    notes = normalized.get("company_notes")

    opener = (
        f"Hi {prospect.get('name')}, I noticed teams like {prospect.get('company')} often lose replies when messaging sounds generic."
        if "pain/problem" in directives["orientation"]
        else f"Hi {prospect.get('name')}, teams like {prospect.get('company')} usually unlock more qualified replies with tighter, context-first messaging."
    )
    tone_line = (
        "I can show a concise way to remix outbound copy in real time with clear control over voice and emphasis."
        if "conversational" in directives["formality"]
        else "I can share a structured approach to real-time outbound remixing with explicit control over voice and message emphasis."
    )
    ask = (
        "If useful, open to a quick 15-minute walkthrough next week?"
        if "diplomatic" in directives["assertiveness"]
        else "Can we lock a 15-minute walkthrough next week to test this on one live sequence?"
    )
    mapping_line = (
        f"Given {prospect.get('company')}'s push on outbound quality, {seller}'s {focus} maps directly to higher reply quality through prospect-specific messaging."
        if focus
        else "I can map the most relevant parts of our offering to your active outbound initiatives without adding process drag."
    )
    adjacent_line = ""
    if focus and catalog:
        adjacent = [item for item in catalog if item.lower() != focus.lower()]
        if adjacent:
            adjacent_line = f"If helpful, related offerings include {', '.join(adjacent[:2])}."
    notes_line = ""
    if notes:
        compact_notes = " ".join(notes.split())
        if len(compact_notes) > 180:
            compact_notes = compact_notes[:180].rstrip() + "..."
        notes_line = f"Context from our side: {compact_notes}"

    if "very short" in directives["length"]:
        return f"{opener} {mapping_line} {ask}"
    if "expanded" in directives["length"]:
        return (
            f"{opener} {tone_line} "
            f"{mapping_line} "
            f"The goal is simple: preserve factual relevance while letting reps shape tone, structure, and persuasion instantly. "
            f"This aligns with your role as {prospect.get('title')} and the current outbound pressure teams are facing. "
            f"{adjacent_line} {notes_line} {anchors['cta']} {ask}"
        )
    return f"{opener} {tone_line} {mapping_line} {adjacent_line} {ask}"


@dataclass
class DraftResult:
    draft: str
    style_key: str
    style_profile: dict[str, float]


async def save_session(session_id: str, session: dict[str, Any]) -> None:
    redis = get_redis()
    key = _session_key(session_id)
    await redis.hset(key, mapping={"data": json.dumps(session)})
    await redis.expire(key, SESSION_TTL_SECONDS)


async def load_session(session_id: str) -> dict[str, Any] | None:
    redis = get_redis()
    raw = await redis.hget(_session_key(session_id), "data")
    if not raw:
        return None
    return json.loads(raw)


def _trim_style_cache(style_cache: dict[str, str], style_order: list[str]) -> tuple[dict[str, str], list[str]]:
    if len(style_order) <= STYLE_CACHE_MAX:
        return style_cache, style_order
    while len(style_order) > STYLE_CACHE_MAX:
        stale = style_order.pop(0)
        style_cache.pop(stale, None)
    return style_cache, style_order


def _compose_prompt_style(style_profile: dict[str, float], directives: dict[str, str]) -> dict[str, Any]:
    return {
        "vector": style_profile,
        "directives": directives,
        "lexical_constraints": [
            "keep explicit business relevance",
            "avoid buzzword-heavy filler",
            "retain CTA intent while restyling",
        ],
    }


async def build_draft(
    session: dict[str, Any],
    style_profile: dict[str, Any],
    throttled: bool = False,
) -> DraftResult:
    normalized = normalize_style_profile(style_profile)
    style_key = style_profile_key(normalized)
    style_cache = session.get("style_cache", {})
    if style_key in style_cache:
        return DraftResult(draft=style_cache[style_key], style_key=style_key, style_profile=normalized)

    directives = style_directives(normalized)
    mode = _mode()

    if mode != "real":
        subject = _mock_subject(directives, session["prospect"]["company"], session.get("company_context"))
        body = _mock_body(session["prospect"], session["anchors"], directives, session.get("company_context"))
        draft = f"{subject}\n\n{body}"
    else:
        prompt = get_web_mvp_prompt(
            prospect=session["prospect"],
            factual_brief=session["factual_brief"],
            anchors=session["anchors"],
            style_profile=_compose_prompt_style(normalized, directives),
            company_context_brief=session.get("company_context_brief", "No sender company context provided."),
            product_focus=(session.get("company_context") or {}).get("current_product"),
            prior_draft=session.get("last_draft"),
        )
        draft = await _real_generate(prompt=prompt, throttled=throttled)

    style_cache[style_key] = draft
    style_order = session.get("style_order", [])
    style_order = [k for k in style_order if k != style_key] + [style_key]
    style_cache, style_order = _trim_style_cache(style_cache, style_order)
    session["style_cache"] = style_cache
    session["style_order"] = style_order
    session["last_style_profile"] = normalized
    session["style_history"] = (session.get("style_history", []) + [normalized])[-20:]
    session["last_draft"] = draft

    return DraftResult(draft=draft, style_key=style_key, style_profile=normalized)


def create_session_payload(
    prospect: dict[str, Any],
    research_text: str,
    initial_style: dict[str, Any],
    company_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_style_profile(initial_style)
    normalized_company = normalize_company_context(company_context)
    return {
        "prospect": prospect,
        "company_context": normalized_company,
        "company_context_brief": build_company_context_brief(normalized_company),
        "research_text": research_text,
        "factual_brief": build_factual_brief(prospect=prospect, research_text=research_text),
        "anchors": build_anchors(prospect=prospect, company_context=normalized_company),
        "last_draft": "",
        "last_style_profile": normalized,
        "style_history": [normalized],
        "style_cache": {},
        "style_order": [],
        "metrics": {"generate_count": 0, "remix_count": 0},
    }


def mode_is_real() -> bool:
    return os.environ.get("EMAILDJ_QUICK_GENERATE_MODE", "mock").strip().lower() == "real"
