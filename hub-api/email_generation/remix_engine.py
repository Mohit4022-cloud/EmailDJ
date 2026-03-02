"""Web MVP remix engine with CTCO lock controls and session caching."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from email_generation.prompt_templates import get_web_mvp_prompt
from email_generation.quick_generate import _mode, _real_generate
from infra.redis_client import get_redis

SESSION_TTL_SECONDS = 24 * 60 * 60
STYLE_CACHE_MAX = 5
MAX_VALIDATION_ATTEMPTS = 3
DEFAULT_FALLBACK_CTA = "Open to a quick chat to see if this is relevant?"

_NO_LEAKAGE_TERMS = (
    "emaildj",
    "remix",
    "mapping",
    "template",
    "templates",
    "slider",
    "sliders",
    "prompt",
    "prompts",
    "llm",
    "llms",
    "openai",
    "gemini",
    "codex",
    "generated",
    "automation tooling",
)

_CTA_DURATION_PATTERN = re.compile(r"\b\d+\s*(?:-|to)?\s*\d*\s*(?:min|minute|minutes)\b")
_CTA_CHANNEL_HINTS = (
    "virtual coffee",
    "call",
    "quick call",
    "meeting",
    "demo",
    "walkthrough",
    "pilot",
    "book time",
    "chat",
    "deck",
    "next week",
)
_CTA_ASK_CUES = (
    "open to",
    "are you open",
    "would you",
    "could we",
    "can we",
    "worth",
    "if useful",
    "if helpful",
    "want me to send",
    "can i send",
    "should i send",
    "happy to share",
    "happy to hop",
    "if this is on your radar",
    "if this is relevant",
)


def _session_key(session_id: str) -> str:
    return f"web_mvp:session:{session_id}"


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def _collapse_ws(value: str) -> str:
    return " ".join(value.split())


def _normalize_optional_text(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_length:
        return text[:max_length].rstrip() + "..."
    return text


def _normalize_lock_text(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    text = _collapse_ws(str(value).strip())
    if not text:
        return None
    if len(text) > max_length:
        return text[:max_length].rstrip()
    return text


def _normalize_cta_lock(value: Any) -> str:
    return _normalize_lock_text(value, max_length=500) or DEFAULT_FALLBACK_CTA


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
    notes = normalized.get("company_notes")

    if company_name:
        lines.append(f"Sender company: {company_name}.")
    if company_url:
        lines.append(f"Website: {company_url}.")
    if current_product:
        lines.append(f"Primary offering: {current_product}.")
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


def _to_percent(value: float) -> int:
    return max(0, min(100, int(round(((value + 1.0) / 2.0) * 100))))


def style_profile_to_ctco_sliders(style_profile: dict[str, float]) -> dict[str, int]:
    return {
        "tone_formal_casual": _to_percent(style_profile["formality"]),
        "framing_problem_outcome": _to_percent(style_profile["orientation"]),
        "length_short_long": _to_percent(style_profile["length"]),
        "stance_bold_diplomatic": _to_percent(style_profile["assertiveness"]),
    }


def _band(value: int, labels: tuple[str, str, str, str, str]) -> str:
    if value <= 20:
        return labels[0]
    if value <= 40:
        return labels[1]
    if value <= 60:
        return labels[2]
    if value <= 80:
        return labels[3]
    return labels[4]


def ctco_style_bands(style_sliders: dict[str, int]) -> dict[str, str]:
    return {
        "formal_casual": _band(
            style_sliders["tone_formal_casual"],
            (
                "very formal, no contractions",
                "formal professional",
                "modern neutral",
                "casual professional",
                "very casual but respectful",
            ),
        ),
        "problem_outcome": _band(
            style_sliders["framing_problem_outcome"],
            (
                "problem-first",
                "problem then outcome",
                "balanced problem and outcome",
                "outcome-first",
                "strongly outcome-first",
            ),
        ),
        "short_long": _band(
            style_sliders["length_short_long"],
            (
                "45-70 words",
                "70-110 words",
                "110-160 words",
                "160-220 words",
                "220-300 words",
            ),
        ),
        "bold_diplomatic": _band(
            style_sliders["stance_bold_diplomatic"],
            (
                "bold and direct",
                "confident",
                "balanced confidence",
                "diplomatic",
                "very diplomatic",
            ),
        ),
    }


def body_word_range(length_short_long: int) -> tuple[int, int]:
    if length_short_long <= 20:
        return 45, 70
    if length_short_long <= 40:
        return 70, 110
    if length_short_long <= 60:
        return 110, 160
    if length_short_long <= 80:
        return 160, 220
    return 220, 300


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


def build_anchors(
    prospect: dict[str, Any],
    offer_lock: str,
    cta_lock: str,
    company_context: dict[str, Any] | None = None,
) -> dict[str, str]:
    normalized = normalize_company_context(company_context)
    seller = normalized.get("company_name") or "your company"
    return {
        "intent": f"Help {prospect.get('company')} improve SDR response quality and throughput.",
        "offer_lock": offer_lock,
        "cta_lock": cta_lock,
        "constraint": f"Pitch only {offer_lock} from {seller}; use only one CTA.",
    }


def style_directives(style_profile: dict[str, float]) -> dict[str, str]:
    formality = style_profile["formality"]
    orientation = style_profile["orientation"]
    length = style_profile["length"]
    assertiveness = style_profile["assertiveness"]

    return {
        "formality": (
            "formal and executive"
            if formality > 0.35
            else "conversational and plainspoken"
            if formality < -0.35
            else "professional-neutral"
        ),
        "orientation": (
            "lead with pain/problem framing"
            if orientation < -0.25
            else "lead with outcomes and upside framing"
            if orientation > 0.25
            else "balanced pain/outcome framing"
        ),
        "length": (
            "very short (60-90 words)"
            if length < -0.5
            else "compact (90-120 words)"
            if length < 0.2
            else "expanded (120-170 words)"
        ),
        "assertiveness": (
            "bold ask with direct next step"
            if assertiveness > 0.45
            else "diplomatic ask with softer tone"
            if assertiveness < -0.45
            else "confident but measured ask"
        ),
    }


def _extract_subject_and_body(draft: str) -> tuple[str, str]:
    text = (draft or "").replace("\r\n", "\n").strip()
    if not text:
        return "", ""

    lines = text.split("\n")
    first_non_empty = next((idx for idx, line in enumerate(lines) if line.strip()), 0)
    first_line = lines[first_non_empty].strip() if lines else ""

    subject = ""
    if first_line.lower().startswith("subject:"):
        subject = first_line.split(":", 1)[1].strip()
    else:
        subject = first_line

    body = ""
    body_marker_index = next(
        (idx for idx, line in enumerate(lines) if line.strip().lower().startswith("body:")),
        None,
    )
    if body_marker_index is not None:
        marker_line = lines[body_marker_index].strip()
        inline_body = marker_line.split(":", 1)[1].strip() if ":" in marker_line else ""
        body_lines = []
        if inline_body:
            body_lines.append(inline_body)
        body_lines.extend(lines[body_marker_index + 1 :])
        body = "\n".join(body_lines).strip()
    else:
        remainder = lines[first_non_empty + 1 :]
        body = "\n".join(remainder).strip()

    return subject, body


def _format_draft(subject: str, body: str) -> str:
    return f"Subject: {subject.strip()}\nBody:\n{body.strip()}".strip()


def canonicalize_draft(draft: str) -> str:
    subject, body = _extract_subject_and_body(draft)
    return _format_draft(subject=subject, body=body)


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def _contains_term(text_lower: str, term: str) -> bool:
    if " " in term:
        return term in text_lower
    return re.search(rf"\b{re.escape(term)}\b", text_lower) is not None


def _is_additional_cta_line(line: str) -> bool:
    normalized = _collapse_ws((line or "").lower())
    if not normalized:
        return False

    has_channel_hint = _CTA_DURATION_PATTERN.search(normalized) is not None or any(
        hint in normalized for hint in _CTA_CHANNEL_HINTS
    )
    if not has_channel_hint:
        return False

    has_ask_cue = any(cue in normalized for cue in _CTA_ASK_CUES)
    is_question = "?" in normalized
    return has_ask_cue or is_question


def _offer_lock_forbidden_items(session: dict[str, Any]) -> list[str]:
    offer_lock = _collapse_ws((session.get("offer_lock") or "").lower())
    company_context = session.get("company_context") or {}
    other_products = _catalog_items(company_context.get("other_products"))
    forbidden: list[str] = []
    for item in other_products:
        key = _collapse_ws(item.lower())
        if not key or key == offer_lock:
            continue
        forbidden.append(item)
    return forbidden


def validate_ctco_output(draft: str, session: dict[str, Any], style_sliders: dict[str, int]) -> list[str]:
    violations: list[str] = []

    subject, body = _extract_subject_and_body(draft)
    if not subject:
        violations.append("missing_subject")
    if not body:
        violations.append("missing_body")

    if not draft.startswith("Subject:") or "\nBody:\n" not in draft:
        violations.append("invalid_output_format")

    if "{{" in draft or "}}" in draft:
        violations.append("template_placeholders_present")

    expected_cta = _collapse_ws(session.get("cta_lock_effective") or DEFAULT_FALLBACK_CTA)
    body_lines = [line.strip() for line in body.splitlines() if line.strip()]
    normalized_lines = [_collapse_ws(line) for line in body_lines]
    cta_matches = sum(1 for line in normalized_lines if line == expected_cta)
    if cta_matches != 1:
        violations.append("cta_lock_not_used_exactly_once")

    body_without_cta_lines: list[str] = []
    cta_removed = False
    for line in body_lines:
        normalized = _collapse_ws(line)
        if normalized == expected_cta and not cta_removed:
            cta_removed = True
            continue
        body_without_cta_lines.append(line)
    for line in body_without_cta_lines:
        if _is_additional_cta_line(line):
            violations.append("additional_cta_detected")
            break

    draft_lower = draft.lower()
    offer_lock = _collapse_ws(session.get("offer_lock") or "")
    if not offer_lock or offer_lock.lower() not in draft_lower:
        violations.append("offer_lock_missing")

    for forbidden in _offer_lock_forbidden_items(session):
        key = forbidden.lower().strip()
        if not key:
            continue
        if key in draft_lower:
            violations.append(f"forbidden_other_product_mentioned:{forbidden}")

    seller_name = ((session.get("company_context") or {}).get("company_name") or "").lower()
    allowed_text = f"{seller_name} {offer_lock.lower()}"
    for term in _NO_LEAKAGE_TERMS:
        if term in allowed_text:
            continue
        if _contains_term(draft_lower, term):
            violations.append(f"internal_leakage_term:{term}")

    research_lower = (session.get("research_text") or "").lower()
    if any(word in draft_lower for word in (" saw ", " read ", " noticed ")) and not any(
        word in research_lower for word in (" saw ", " read ", " noticed ")
    ):
        violations.append("ungrounded_seen_read_noticed_claim")

    min_words, max_words = body_word_range(style_sliders["length_short_long"])
    words = _word_count(body)
    if words < min_words or words > max_words:
        violations.append(f"length_out_of_range:{words}_expected_{min_words}_{max_words}")

    prospect = session.get("prospect") or {}
    identity_markers = [
        _collapse_ws(str(prospect.get("name") or "")).lower(),
        _collapse_ws(str(prospect.get("title") or "")).lower(),
        _collapse_ws(str(prospect.get("company") or "")).lower(),
    ]
    if not any(marker and marker in draft_lower for marker in identity_markers):
        violations.append("prospect_reference_missing")

    unique: list[str] = []
    seen: set[str] = set()
    for violation in violations:
        if violation in seen:
            continue
        seen.add(violation)
        unique.append(violation)
    return unique


def _validation_feedback(violations: list[str]) -> str:
    return "Rewrite and fix these violations exactly: " + "; ".join(violations)


def _extract_research_hooks(research_text: str, max_items: int = 2) -> list[str]:
    compact = " ".join((research_text or "").split())
    if not compact:
        return []
    raw_sentences = re.split(r"(?<=[.!?])\s+", compact)
    hooks: list[str] = []
    for sentence in raw_sentences:
        sentence = sentence.strip()
        if len(sentence.split()) < 6:
            continue
        hooks.append(sentence.rstrip("."))
        if len(hooks) >= max_items:
            break
    return hooks


def _fit_body_range(main_text: str, cta_line: str, min_total: int, max_total: int) -> str:
    main_words = main_text.split()
    cta_words = _word_count(cta_line)
    min_main = max(25, min_total - cta_words)
    max_main = max(min_main, max_total - cta_words)

    if len(main_words) > max_main:
        main_words = main_words[:max_main]
    elif len(main_words) < min_main:
        pad_words = "This keeps messaging relevant, credible, and easy for your team to action.".split()
        idx = 0
        while len(main_words) < min_main:
            main_words.append(pad_words[idx % len(pad_words)])
            idx += 1

    return f"{' '.join(main_words).strip()}\n\n{cta_line}".strip()


def _mock_subject(prospect: dict[str, Any], offer_lock: str, style_sliders: dict[str, int]) -> str:
    company = prospect.get("company") or "your team"
    if style_sliders["framing_problem_outcome"] <= 40:
        return f"Reducing generic outbound risk at {company}"
    return f"{offer_lock} for {company}'s outbound outcomes"


def _mock_body(session: dict[str, Any], style_sliders: dict[str, int]) -> str:
    prospect = session["prospect"]
    offer_lock = session["offer_lock"]
    cta = session["cta_lock_effective"]

    name = prospect.get("name") or "there"
    title = prospect.get("title") or "your role"
    company = prospect.get("company") or "your company"
    hooks = _extract_research_hooks(session.get("research_text") or "")

    formal = style_sliders["tone_formal_casual"]
    framing = style_sliders["framing_problem_outcome"]
    stance = style_sliders["stance_bold_diplomatic"]

    greeting = f"Hello {name}," if formal <= 20 else f"Hi {name},"
    if framing <= 40:
        lead = f"{company} teams often lose replies when outbound messages are generic or poorly timed."
    else:
        lead = f"{company} teams can improve qualified replies when outbound messages are tailored to current priorities."

    hook_line = (
        f"From your current initiatives, {hooks[0]}." if hooks else f"As {title}, you likely need better reply quality without adding process overhead."
    )
    value_line = f"{offer_lock} helps reps send context-specific outreach with consistent quality controls."
    support_line = (
        f"{hooks[1]}."
        if len(hooks) > 1
        else "This typically improves message relevance while keeping execution practical for the team."
    )

    close_line = (
        "If this aligns, I can share how teams usually apply it in production workflows."
        if stance >= 61
        else "This can be applied quickly with minimal workflow disruption."
    )

    main = f"{greeting} {lead} {hook_line} {value_line} {support_line} {close_line}"
    min_words, max_words = body_word_range(style_sliders["length_short_long"])
    return _fit_body_range(main_text=main, cta_line=cta, min_total=min_words, max_total=max_words)


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


async def _build_real_draft(
    session: dict[str, Any],
    style_sliders: dict[str, int],
    style_bands: dict[str, str],
    throttled: bool,
) -> str:
    prior_draft = session.get("last_draft") or None
    correction_notes: str | None = None
    last_violations: list[str] = []

    seller_context = {
        "seller_company_name": (session.get("company_context") or {}).get("company_name"),
        "seller_company_url": (session.get("company_context") or {}).get("company_url"),
        "seller_company_notes": (session.get("company_context") or {}).get("company_notes"),
        "other_products_services_mapping": (session.get("company_context") or {}).get("other_products"),
    }

    for _attempt in range(MAX_VALIDATION_ATTEMPTS):
        prompt = get_web_mvp_prompt(
            seller=seller_context,
            prospect=session["prospect"],
            deep_research=session["research_text"],
            offer_lock=session["offer_lock"],
            cta_offer_lock=session["cta_lock_effective"],
            cta_type=session.get("cta_type"),
            style_sliders=style_sliders,
            style_bands=style_bands,
            prior_draft=prior_draft,
            correction_notes=correction_notes,
        )
        candidate = canonicalize_draft(await _real_generate(prompt=prompt, throttled=throttled))
        violations = validate_ctco_output(candidate, session=session, style_sliders=style_sliders)
        if not violations:
            return candidate

        last_violations = violations
        prior_draft = candidate
        correction_notes = _validation_feedback(violations)

    raise ValueError(f"ctco_validation_failed: {'; '.join(last_violations)}")


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

    style_sliders = style_profile_to_ctco_sliders(normalized)
    style_bands = ctco_style_bands(style_sliders)
    mode = _mode()

    if mode != "real":
        subject = _mock_subject(session["prospect"], session["offer_lock"], style_sliders)
        body = _mock_body(session=session, style_sliders=style_sliders)
        draft = _format_draft(subject=subject, body=body)
    else:
        draft = await _build_real_draft(
            session=session,
            style_sliders=style_sliders,
            style_bands=style_bands,
            throttled=throttled,
        )

    violations = validate_ctco_output(draft, session=session, style_sliders=style_sliders)
    if violations:
        raise ValueError(f"ctco_validation_failed: {'; '.join(violations)}")

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
    offer_lock: str,
    cta_offer_lock: str | None = None,
    cta_type: str | None = None,
    company_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_style = normalize_style_profile(initial_style)
    normalized_company = normalize_company_context(company_context)
    effective_offer_lock = _normalize_lock_text(offer_lock, max_length=240) or normalized_company.get("current_product") or ""
    effective_cta_lock = _normalize_cta_lock(cta_offer_lock)

    return {
        "prospect": prospect,
        "company_context": normalized_company,
        "company_context_brief": build_company_context_brief(normalized_company),
        "research_text": research_text,
        "factual_brief": build_factual_brief(prospect=prospect, research_text=research_text),
        "offer_lock": effective_offer_lock,
        "cta_offer_lock": _normalize_lock_text(cta_offer_lock, max_length=500),
        "cta_lock_effective": effective_cta_lock,
        "cta_type": cta_type,
        "anchors": build_anchors(
            prospect=prospect,
            offer_lock=effective_offer_lock,
            cta_lock=effective_cta_lock,
            company_context=normalized_company,
        ),
        "ctco_rules_version": "ctco_v1",
        "last_draft": "",
        "last_style_profile": normalized_style,
        "style_history": [normalized_style],
        "style_cache": {},
        "style_order": [],
        "metrics": {"generate_count": 0, "remix_count": 0},
    }


def mode_is_real() -> bool:
    return os.environ.get("EMAILDJ_QUICK_GENERATE_MODE", "mock").strip().lower() == "real"
