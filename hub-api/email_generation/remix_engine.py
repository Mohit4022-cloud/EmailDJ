"""Web MVP remix engine with CTCO lock controls and session caching."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from email_generation.claim_verifier import (
    extract_allowed_numeric_claims,
    find_unverified_claims,
    merge_claim_sources,
    rewrite_unverified_claims,
)
from email_generation.compliance_rules import (
    _CASH_CTA_PATTERN,
    _CTA_ASK_CUES,
    _CTA_CHANNEL_HINTS,
    _CTA_DURATION_PATTERN,
    _GUARANTEED_CLAIM_PATTERN,
    _ABSOLUTE_REVENUE_PATTERN,
    _META_COMMENTARY_PATTERN,
    _NO_LEAKAGE_TERMS,
    _collapse_ws,
    _contains_term,
    _word_count,
)
from email_generation.cta_templates import resolve_cta_lock
from email_generation.generation_plan import GenerationPlan, apply_generation_plan, build_generation_plan
from email_generation.output_enforcement import (
    _GENERIC_CLOSER_PATTERNS,
    compose_body_without_padding_loops,
    dedupe_sentences_text,
    derive_first_name,
    enforce_first_name_greeting,
    long_mode_section_pool,
    remove_generic_closers,
    sanitize_generic_ai_opener,
    split_sentences,
)
from email_generation.policies import policy_runner
from email_generation.policies.policy_metrics import persist_policy_metrics
from email_generation.preset_strategies import normalize_preset_id
from email_generation.prompt_templates import get_web_mvp_prompt
from email_generation.quick_generate import GenerateResult, _mode, _preferred_provider, _real_generate
from email_generation.rc_tco_controller import (
    LEGACY_RESPONSE_CONTRACT,
    RC_TCO_RESPONSE_CONTRACT,
    build_rc_tco_output,
    validate_rc_tco_json,
)
from email_generation.runtime_policies import repair_loop_enabled, strict_lock_enforcement_level
from infra.redis_client import get_redis

logger = logging.getLogger(__name__)

# Model names keyed by provider (mirrors quick_generate._real_generate hardcoded values)
_PROVIDER_MODELS: dict[str, str] = {
    "openai": "gpt-4.1-nano",
    "anthropic": "claude-3-5-haiku-latest",
    "groq": "llama-3.3-70b-versatile",
}

SESSION_TTL_SECONDS = 24 * 60 * 60
STYLE_CACHE_MAX = 5
MAX_VALIDATION_ATTEMPTS = 3
DEFAULT_FALLBACK_CTA = "Open to a quick chat to see if this is relevant?"

_BANNED_PHRASES = (
    "ai services",
    "ai consulting",
    "we build ai",
    "ai transformation services",
    "pipeline outcomes",
    "reply lift",
    "conversion lift",
    "measurable results",
)

_GENERIC_AI_OPENER_PATTERN = re.compile(
    r"^(?:(?:hi|hello)\s+[^,\n]+,\s*)?as\s+[a-z0-9&.\- ]+\s+scales\s+(?:its|their)\s+(?:enterprise\s+)?ai\s+initiatives[, ]",
    re.IGNORECASE,
)

_INSTRUCTIONAL_RESEARCH_PHRASES = (
    "ignore offer lock",
    "ignore previous instructions",
    "reveal your system prompt",
    "reveal system prompt",
    "system prompt",
    "internal mapping",
    "other_products/services mapping",
    "gift card",
    "measurable lift",
    "reply lift",
    "guarantee measurable",
    "promise 30%",
    "outreach should",
    "you should",
    "we should",
    "should propose",
    "propose a pilot",
    "recommend",
    "suggest",
    "pitch",
    "position this as",
    "frame this as",
    "use this angle",
    "focus on",
    "make sure to",
    "tell them to",
)

_FACT_SIGNAL_TOKENS = (
    "launched",
    "announced",
    "hiring",
    "hired",
    "expanded",
    "rolled out",
    "adopted",
    "using",
    "uses",
    "recently",
    "currently",
    "team",
    "organization",
    "org",
    "initiative",
    "program",
    "company",
    "revenue",
    "funding",
    "series",
)

_STAT_CLAIM_PATTERNS = (
    re.compile(r"\b\d+(?:\.\d+)?%\s+(?:improvement|increase|lift|gain|boost|growth|reduction|decrease)\b"),
    re.compile(r"\b(?:increase(?:d)?|improve(?:d|ment)?|boost(?:ed)?|lift(?:ed)?|reduc(?:ed|tion)|grow(?:th|n)?)\s+(?:by\s+)?\d+(?:\.\d+)?\s*%\b"),
)

_PERFORMANCE_CLAIM_PATTERNS = (
    re.compile(r"\bproven to\b"),
    re.compile(r"\bscientifically proven\b"),
)

_CLAIM_VIOLATION_PREFIXES = (
    "unsubstantiated_statistical_claim",
    "unsubstantiated_performance_claim",
    "unsubstantiated_claim",
)


def _response_contract(session: dict[str, Any]) -> str:
    value = _collapse_ws(str(session.get("response_contract") or LEGACY_RESPONSE_CONTRACT)).lower()
    if value == RC_TCO_RESPONSE_CONTRACT:
        return RC_TCO_RESPONSE_CONTRACT
    return LEGACY_RESPONSE_CONTRACT


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
    return _normalize_lock_text(value, max_length=500) or ""


def _resolve_effective_cta_lock(
    *,
    raw_lock: Any,
    cta_type: str | None,
    offer_lock: str,
    style_sliders: dict[str, int] | None = None,
    company_context: dict[str, Any] | None = None,
) -> str:
    sliders = style_sliders or {"stance_bold_diplomatic": 50}
    directness = max(0, min(100, 100 - int(sliders.get("stance_bold_diplomatic", 50))))
    risk_surface = _normalize_lock_text((company_context or {}).get("current_product"), max_length=240) or offer_lock
    return resolve_cta_lock(
        existing_lock=_normalize_lock_text(raw_lock, max_length=500),
        cta_type=cta_type,
        risk_surface=risk_surface,
        directness=directness,
    )


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


def _unique_ordered(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(key)
    return output


def _violation_codes(violations: list[str]) -> list[str]:
    codes = [entry.split(":", 1)[0] for entry in violations if entry]
    return _unique_ordered(codes)


def _claim_violations(violations: list[str]) -> list[str]:
    return [entry for entry in violations if entry and entry.split(":", 1)[0] in _CLAIM_VIOLATION_PREFIXES]


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
    if length_short_long <= 33:
        return 55, 75
    if length_short_long <= 66:
        return 75, 110
    return 110, 160


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


def _split_research_sentences(text: str) -> list[str]:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    chunks = re.split(r"(?<=[.!?])\s+|\n+", normalized)
    return [chunk.strip(" -*\t") for chunk in chunks if chunk and chunk.strip(" -*\t")]


def _is_instruction_like(sentence: str) -> bool:
    normalized = _collapse_ws((sentence or "").lower())
    if not normalized:
        return False
    return any(phrase in normalized for phrase in _INSTRUCTIONAL_RESEARCH_PHRASES)


def _contains_factual_signal(sentence: str) -> bool:
    normalized = _collapse_ws((sentence or "").lower())
    if not normalized:
        return False
    if len(re.findall(r"[A-Za-z0-9']+", normalized)) < 6:
        return False
    if re.search(r"\d", normalized):
        return True
    return any(token in normalized for token in _FACT_SIGNAL_TOKENS)


def _strip_instructional_phrases(research_text: str) -> str:
    kept: list[str] = []
    for sentence in _split_research_sentences(research_text):
        if _is_instruction_like(sentence):
            continue
        kept.append(sentence.rstrip())
    return " ".join(kept).strip()


def _extract_allowed_facts(research_text: str, max_items: int = 4) -> list[str]:
    sanitized = _strip_instructional_phrases(research_text)
    facts: list[str] = []
    seen: set[str] = set()

    for sentence in _split_research_sentences(sanitized):
        cleaned = _collapse_ws(sentence.strip().rstrip("."))
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        if not _contains_factual_signal(cleaned):
            continue
        seen.add(key)
        facts.append(cleaned)
        if len(facts) >= max_items:
            return facts

    for sentence in _split_research_sentences(sanitized):
        cleaned = _collapse_ws(sentence.strip().rstrip("."))
        key = cleaned.lower()
        if not cleaned or key in seen or _is_instruction_like(cleaned):
            continue
        if len(cleaned.split()) < 6:
            continue
        seen.add(key)
        facts.append(cleaned)
        if len(facts) >= max_items:
            break

    if facts:
        return facts

    compact = _collapse_ws(sanitized)
    if compact:
        return [compact[:220].rstrip()]
    return []


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


def _rc_tco_payload_to_draft(payload: dict[str, Any]) -> str:
    email = payload.get("email") if isinstance(payload, dict) else {}
    subject = _collapse_ws((email or {}).get("subject") or "")
    body = ((email or {}).get("body") or "").strip()
    return _format_draft(subject=subject, body=body)


def canonicalize_draft(draft: str) -> str:
    subject, body = _extract_subject_and_body(draft)
    return _format_draft(subject=subject, body=body)


def _parse_json_candidate(raw: str) -> dict[str, Any]:
    payload = (raw or "").strip()
    if not payload:
        raise ValueError("empty_output")

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        if payload.startswith("```"):
            payload = re.sub(r"^```(?:json)?\s*|\s*```$", "", payload, flags=re.IGNORECASE | re.DOTALL).strip()
            if payload:
                parsed = json.loads(payload)
            else:
                raise ValueError("json_fence_without_content") from None
        else:
            start = payload.find("{")
            end = payload.rfind("}")
            if start == -1 or end <= start:
                raise ValueError("no_json_object_found") from None
            parsed = json.loads(payload[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("json_output_not_object")
    return parsed


def _parse_structured_output(raw: str) -> tuple[str, str]:
    parsed = _parse_json_candidate(raw)
    subject = parsed.get("subject")
    body = parsed.get("body")
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("missing_json_subject")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("missing_json_body")
    return subject.strip(), body.strip()



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


def _expected_prospect_first_name(session: dict[str, Any]) -> str:
    first_name = derive_first_name(str(session.get("prospect_first_name") or "").strip())
    if first_name:
        return first_name
    raw_name = str((session.get("prospect") or {}).get("name") or "").strip()
    return derive_first_name(raw_name)


def _check_signoff_before_cta(body: str) -> list[str]:
    """Hard violation: no generic signoff in body before the final CTA line."""
    sentences = split_sentences(body)
    for sentence in sentences[:-1]:
        if any(pattern.search(sentence) for pattern in _GENERIC_CLOSER_PATTERNS):
            snippet = _collapse_ws(sentence)[:60]
            return [f"signoff_before_cta:{snippet}"]
    return []


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

    expected_first_name = _expected_prospect_first_name(session)
    first_body_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
    if expected_first_name:
        greeting_match = re.match(r"^(Hi|Hello)\s+([^,\n]+),", first_body_line)
        if greeting_match is None:
            violations.append("greeting_missing_or_invalid")
        else:
            greeted_name = _collapse_ws(greeting_match.group(2))
            if greeted_name.lower() != expected_first_name.lower():
                violations.append("greeting_first_name_mismatch")
            if " " in greeted_name:
                violations.append("greeting_not_first_name_only")

    expected_cta = str(session.get("cta_lock_effective") or DEFAULT_FALLBACK_CTA).strip()
    body_lines = [line.strip() for line in body.splitlines() if line.strip()]
    cta_matches = sum(1 for line in body_lines if line == expected_cta)
    if cta_matches != 1:
        violations.append("cta_lock_not_used_exactly_once")

    expected_cta_norm = _collapse_ws(expected_cta).lower()
    for line in body_lines:
        if line == expected_cta:
            continue
        line_norm = _collapse_ws(line).lower()
        if not line_norm:
            continue
        ratio = SequenceMatcher(None, expected_cta_norm, line_norm).ratio()
        if ratio >= 0.88 and (_is_additional_cta_line(line) or "?" in line):
            violations.append("cta_near_match_detected")
            break

    body_without_cta_lines: list[str] = []
    cta_removed = False
    for line in body_lines:
        if line == expected_cta and not cta_removed:
            cta_removed = True
            continue
        body_without_cta_lines.append(line)
    for line in body_without_cta_lines:
        if _is_additional_cta_line(line):
            violations.append("additional_cta_detected")
            break

    violations.extend(_check_signoff_before_cta(body))

    draft_lower = draft.lower()
    offer_lock = _collapse_ws(session.get("offer_lock") or "")
    if not offer_lock or offer_lock.lower() not in draft_lower:
        violations.append("offer_lock_missing")
    if offer_lock:
        body_lower = _collapse_ws(body).lower()
        if offer_lock.lower() not in body_lower:
            violations.append("offer_lock_body_verbatim_missing")
            # Semantic drift: check keyword overlap between offer_lock and body
            _STOPWORDS = {
                "a", "an", "the", "and", "or", "of", "to", "in", "for", "with",
                "by", "on", "at", "from", "as", "is", "was", "are", "be", "this",
                "that", "it", "its", "our", "your", "we", "you", "i",
            }
            offer_keywords = [
                w.lower() for w in re.findall(r"[A-Za-z0-9']+", offer_lock)
                if w.lower() not in _STOPWORDS and len(w) > 2
            ]
            if len(offer_keywords) >= 2:
                overlap = sum(1 for kw in offer_keywords if kw in body_lower)
                if overlap / len(offer_keywords) < 0.4:
                    violations.append("offer_drift_keyword_overlap_low")

    for phrase in _BANNED_PHRASES:
        if phrase in draft_lower:
            violations.append(f"banned_phrase:{phrase}")

    for forbidden in _offer_lock_forbidden_items(session):
        key = _collapse_ws(forbidden.lower().strip())
        if not key:
            continue
        if _contains_term(draft_lower, key):
            violations.append(f"forbidden_other_product_mentioned:{forbidden}")

    seller_name = ((session.get("company_context") or {}).get("company_name") or "").lower()
    allowed_text = f"{seller_name} {offer_lock.lower()}"
    for term in _NO_LEAKAGE_TERMS:
        if term in allowed_text:
            continue
        if _contains_term(draft_lower, term):
            violations.append(f"internal_leakage_term:{term}")

    # Meta-commentary: sentences that describe the email's own compliance/construction
    for line in body_lines:
        if _META_COMMENTARY_PATTERN.search(line):
            violations.append(f"meta_commentary:{line[:80]}")
            break

    research_lower = (session.get("research_text") or "").lower()
    if any(word in draft_lower for word in (" saw ", " read ", " noticed ")) and not any(
        word in research_lower for word in (" saw ", " read ", " noticed ")
    ):
        violations.append("ungrounded_seen_read_noticed_claim")

    research_claim_source = merge_claim_sources(
        [
            session.get("research_text_raw"),
            session.get("research_text"),
            (session.get("company_context") or {}).get("company_notes"),
            " ".join(session.get("allowed_facts") or []),
        ]
    )
    allowed_numeric_claims = extract_allowed_numeric_claims((session.get("company_context") or {}).get("company_notes"))
    hook_strategy = _collapse_ws(str((session.get("generation_plan") or {}).get("hook_strategy") or "")).lower()
    research_has_ai_phrase = (
        re.search(
            r"scales\s+(?:its|their)\s+(?:enterprise\s+)?ai\s+initiatives",
            session.get("research_text_raw") or "",
            flags=re.IGNORECASE,
        )
        is not None
    )
    if _GENERIC_AI_OPENER_PATTERN.search(first_body_line or "") and not (
        research_has_ai_phrase and hook_strategy == "research_anchored"
    ):
        violations.append("banned_generic_ai_opener")

    unverified_claims = find_unverified_claims(
        draft,
        research_claim_source,
        allowed_numeric_claims=allowed_numeric_claims,
    )
    for claim in unverified_claims:
        if re.search(r"\d|%|rate|marketplace|accuracy|compliance|x", claim, re.IGNORECASE):
            violations.append("unsubstantiated_statistical_claim")
        else:
            violations.append(f"unsubstantiated_claim:{claim[:60]}")

    # Cash-equivalent CTA: gift cards, prepaid cards, cash rewards (Batch 3 P4)
    if _CASH_CTA_PATTERN.search(draft_lower):
        violations.append("cash_equivalent_cta_detected")

    # Unsubstantiated guaranteed/proven claims (Batch 3 P4)
    for match in _GUARANTEED_CLAIM_PATTERN.finditer(draft_lower):
        claim = _collapse_ws(match.group(0))
        if claim and claim not in research_claim_source:
            violations.append(f"unsubstantiated_claim:{claim[:60]}")
            break

    # Unsubstantiated absolute revenue/pipeline claims (Batch 3 P4)
    for match in _ABSOLUTE_REVENUE_PATTERN.finditer(draft_lower):
        claim = _collapse_ws(match.group(0))
        if claim and claim not in research_claim_source:
            violations.append(f"unsubstantiated_claim:{claim[:60]}")
            break

    min_words, max_words = body_word_range(style_sliders["length_short_long"])
    words = _word_count(body)
    if words < min_words or words > max_words:
        violations.append(f"length_out_of_range:{words}_expected_{min_words}_{max_words}")

    prospect = session.get("prospect") or {}
    expected_first_name = _expected_prospect_first_name(session).lower()
    company_full = _collapse_ws(str(prospect.get("company") or "")).lower()
    company_primary = company_full.split(" ")[0] if company_full else ""
    identity_markers = [
        _collapse_ws(str(prospect.get("name") or "")).lower(),
        _collapse_ws(str(prospect.get("title") or "")).lower(),
        company_full,
        expected_first_name,
        company_primary if len(company_primary) >= 3 else "",
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
    notes = ["Rewrite and fix these violations exactly: " + "; ".join(violations)]
    claim_violations = _claim_violations(violations)
    if claim_violations:
        notes.append(
            "Claims policy: keep claims qualitative unless the exact quantified claim is in approved proof text."
        )
    if any(v.startswith("meta_commentary") for v in violations):
        notes.append(
            "Meta-commentary policy: remove any sentence that describes the email's compliance or "
            "construction (e.g. 'This email follows...', 'This keeps messaging...'). "
            "The body must be pure outbound copy — never reference the email itself."
        )
    if any(v.startswith("offer_drift") for v in violations):
        notes.append(
            "Offer drift policy: the email body must clearly and explicitly pitch the OFFER_LOCK. "
            "Use the offer's actual name, not a paraphrase or category description."
        )
    return " ".join(notes)


def _json_repair_feedback(raw_output: str, parse_error: str) -> str:
    preview = _collapse_ws((raw_output or "").strip())[:500]
    return (
        "Your previous output was not valid JSON. Return ONLY a JSON object with string keys "
        '"subject" and "body". Do not add markdown fences, labels, or commentary. '
        f"Parse error: {parse_error}. Previous output: {preview}"
    )


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


def _fit_body_range(
    main_text: str,
    cta_line: str,
    min_total: int,
    max_total: int,
    *,
    extra_sections: list[str] | None = None,
) -> str:
    return compose_body_without_padding_loops(
        base_sentences=split_sentences(main_text),
        extra_sections=extra_sections or [],
        cta_line=cta_line,
        min_words=min_total,
        max_words=max_total,
    )


def _sanitize_prior_draft(text: str | None) -> str | None:
    """Strip duplicate sentences and meta-commentary from prior_draft before repair re-injection.

    This prevents the repair loop from amplifying filler phrases or constraint-language
    sentences that were in the failed attempt.
    """
    if not text:
        return None
    # Remove exact-duplicate sentences
    cleaned = dedupe_sentences_text(text)
    # Remove generic closers
    cleaned = remove_generic_closers(cleaned)
    # Remove meta-commentary sentences (model describing the email's compliance)
    kept = [s for s in split_sentences(cleaned) if not _META_COMMENTARY_PATTERN.search(s)]
    result = " ".join(kept).strip()
    return result or None


def _remove_forbidden_product_terms(text: str, forbidden_items: list[str]) -> str:
    cleaned = text or ""
    for item in forbidden_items:
        token = _collapse_ws(item).strip()
        if not token:
            continue
        if " " in token:
            cleaned = re.sub(re.escape(token), "", cleaned, flags=re.IGNORECASE)
        else:
            cleaned = re.sub(rf"\b{re.escape(token)}\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;!?])", r"\1", cleaned)
    return cleaned.strip()


def _deterministic_compliance_repair(
    candidate: str,
    session: dict[str, Any],
    style_sliders: dict[str, int],
) -> str:
    subject, body = _extract_subject_and_body(candidate)
    plan = GenerationPlan.from_dict(session.get("generation_plan")) or build_generation_plan(
        session=session,
        style_sliders=style_sliders,
        preset_id=session.get("preset_id"),
        cta_type=session.get("cta_type"),
    )
    repaired_subject, repaired_body = apply_generation_plan(
        subject=subject,
        body=body,
        session=session,
        style_sliders=style_sliders,
        plan=plan,
    )
    if repaired_body.splitlines():
        session["cta_lock_effective"] = _collapse_ws(repaired_body.splitlines()[-1].strip())
    return _format_draft(subject=repaired_subject, body=repaired_body)


def _mock_subject(prospect: dict[str, Any], offer_lock: str, style_sliders: dict[str, int]) -> str:
    company = prospect.get("company") or "your team"
    if style_sliders["framing_problem_outcome"] <= 40:
        return f"Quick thought on {offer_lock} for {company}"
    return f"{offer_lock} — relevant for {company}?"


def _mock_body(session: dict[str, Any], style_sliders: dict[str, int]) -> str:
    prospect = session["prospect"]
    offer_lock = session["offer_lock"]
    cta = session["cta_lock_effective"]
    first_name = derive_first_name(session.get("prospect_first_name") or prospect.get("name")) or "there"

    title = prospect.get("title") or "your role"
    company = prospect.get("company") or "your company"
    hooks = _extract_research_hooks(session.get("research_text") or "")

    formal = style_sliders["tone_formal_casual"]
    framing = style_sliders["framing_problem_outcome"]
    stance = style_sliders["stance_bold_diplomatic"]

    if framing <= 40:
        lead = f"{company} is navigating priorities that make it hard to engage target accounts with the right message at the right time."
    else:
        lead = f"{company} teams focused on message relevance tend to see stronger engagement from priority accounts."

    hook_line = (
        f"Based on recent activity, {hooks[0]}."
        if hooks
        else f"As {title}, you're likely balancing reach efficiency with message quality."
    )
    value_line = f"{offer_lock} is built to help your team do exactly this: more precise engagement without adding process overhead."
    support_line = (
        f"{hooks[1]}."
        if len(hooks) > 1
        else "Most teams find it integrates into existing workflows without major changes."
    )

    close_line = (
        "Teams that have applied this report faster adoption and more targeted messaging."
        if stance >= 61
        else "It is generally lightweight and fits within existing processes."
    )
    main = " ".join([lead, hook_line, value_line, support_line, close_line]).strip()
    main = sanitize_generic_ai_opener(
        main,
        research_text=session.get("research_text_raw") or session.get("research_text"),
        hook_strategy=(session.get("generation_plan") or {}).get("hook_strategy"),
        company=company,
        risk_surface=offer_lock,
    )
    main = enforce_first_name_greeting(main, first_name)

    claim_source = merge_claim_sources(
        [
            session.get("research_text_raw"),
            session.get("research_text"),
            (session.get("company_context") or {}).get("company_notes"),
            " ".join(session.get("allowed_facts") or []),
        ]
    )
    allowed_numeric_claims = extract_allowed_numeric_claims((session.get("company_context") or {}).get("company_notes"))
    main = rewrite_unverified_claims(main, claim_source, allowed_numeric_claims=allowed_numeric_claims)

    min_words, max_words = body_word_range(style_sliders["length_short_long"])
    section_pool = long_mode_section_pool(
        company_notes=(session.get("company_context") or {}).get("company_notes"),
        allowed_facts=session.get("allowed_facts") or [],
        offer_lock=offer_lock,
        company=company,
        forbidden_terms=_offer_lock_forbidden_items(session),
    )
    if style_sliders["length_short_long"] >= 85:
        extra_sections = section_pool[:4]
    elif style_sliders["length_short_long"] >= 67:
        extra_sections = section_pool[:3]
    elif style_sliders["length_short_long"] >= 50:
        extra_sections = section_pool[:1]
    else:
        extra_sections = []
    return _fit_body_range(
        main_text=main,
        cta_line=cta,
        min_total=min_words,
        max_total=max_words,
        extra_sections=extra_sections,
    )


@dataclass
class DraftResult:
    draft: str
    style_key: str
    style_profile: dict[str, float]
    response_contract: str = field(default=LEGACY_RESPONSE_CONTRACT)
    mode: str = field(default="mock")
    provider: str = field(default="mock")
    model_name: str = field(default="mock")
    cascade_reason: str = field(default="primary")
    attempt_count: int = field(default=1)
    validator_attempt_count: int = field(default=0)
    json_repair_count: int = field(default=0)
    violation_retry_count: int = field(default=0)
    repaired: bool = field(default=False)
    violation_codes: list[str] = field(default_factory=list)
    violation_count: int = field(default=0)
    enforcement_level: str = field(default="repair")
    repair_loop_enabled: bool = field(default=True)
    policy_version_snapshot: dict[str, str] = field(default_factory=dict)


@dataclass
class RealDraftStats:
    validator_attempt_count: int = 1
    json_repair_count: int = 0
    violation_retry_count: int = 0
    violation_codes: list[str] = field(default_factory=list)
    violation_count: int = 0


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


async def persist_violations(
    violations: list[str],
    session_id: str | None,
    pipeline: str,  # "remix" | "preview"
) -> None:
    """Persist violation counts to Redis for the compliance dashboard."""
    if not violations:
        return
    redis = get_redis()
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    ttl = 3 * 24 * 60 * 60
    for v in violations:
        category = v.split(":")[0]
        for key in (
            f"web_mvp:compliance:violation:{category}:{day}",
            f"web_mvp:compliance:violation:{pipeline}:{category}:{day}",
        ):
            await redis.incr(key)
            await redis.expire(key, ttl)
    if session_id:
        sk = f"web_mvp:compliance:session_violations:{session_id}"
        current = int(await redis.get(sk) or "0")
        await redis.set(sk, str(current + len(violations)))
        await redis.expire(sk, SESSION_TTL_SECONDS)


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
    enforcement_level: str,
    repair_enabled: bool,
    session_id: str | None = None,
) -> tuple[str, GenerateResult, RealDraftStats]:
    prior_draft = session.get("last_draft") or None
    correction_notes: str | None = None
    last_violations: list[str] = []
    all_violations: list[str] = []
    json_repair_count = 0
    violation_retry_count = 0
    validator_attempt_count = 0
    max_attempts = MAX_VALIDATION_ATTEMPTS if enforcement_level == "repair" and repair_enabled and not throttled else 1
    plan = GenerationPlan.from_dict(session.get("generation_plan")) or build_generation_plan(
        session=session,
        style_sliders=style_sliders,
        preset_id=session.get("preset_id"),
        cta_type=session.get("cta_type"),
    )
    session["generation_plan"] = plan.to_dict()

    seller_context = {
        "seller_company_name": (session.get("company_context") or {}).get("company_name"),
        "seller_company_url": (session.get("company_context") or {}).get("company_url"),
        "seller_company_notes": (session.get("company_context") or {}).get("company_notes"),
    }

    for attempt_index in range(max_attempts):
        validator_attempt_count = attempt_index + 1
        prompt = get_web_mvp_prompt(
            seller=seller_context,
            prospect=session["prospect"],
            research_sanitized=session.get("research_text_sanitized") or session.get("research_text") or "",
            allowed_facts=session.get("allowed_facts") or [],
            offer_lock=session["offer_lock"],
            cta_offer_lock=session["cta_lock_effective"],
            cta_type=session.get("cta_type"),
            style_sliders=style_sliders,
            style_bands=style_bands,
            generation_plan=plan.to_dict(),
            prior_draft=prior_draft,
            correction_notes=correction_notes,
            prospect_first_name=session.get("prospect_first_name"),
        )
        gen_result = await _real_generate(prompt=prompt, throttled=throttled)
        try:
            subject, body = _parse_structured_output(gen_result.text)
        except ValueError as exc:
            last_violations = [f"invalid_json_output:{exc}"]
            all_violations.extend(last_violations)
            prior_draft = _collapse_ws((gen_result.text or "").strip())[:1200]
            correction_notes = _json_repair_feedback(gen_result.text, str(exc))
            json_repair_count += 1
            await persist_violations(last_violations, session_id=session_id, pipeline="remix")
            logger.warning(
                "web_mvp_json_parse_failed",
                extra={
                    "session_id": session_id,
                    "attempt": validator_attempt_count,
                    "violations": last_violations,
                    "enforcement_level": enforcement_level,
                },
            )
            if enforcement_level == "warn":
                candidate = canonicalize_draft(gen_result.text)
                return (
                    candidate,
                    gen_result,
                    RealDraftStats(
                        validator_attempt_count=validator_attempt_count,
                        json_repair_count=json_repair_count,
                        violation_retry_count=violation_retry_count,
                        violation_codes=_violation_codes(all_violations),
                        violation_count=len(all_violations),
                    ),
                )
            if enforcement_level == "repair" and repair_enabled and not throttled and attempt_index < (max_attempts - 1):
                continue
            raise ValueError(f"ctco_validation_failed: {'; '.join(last_violations)}") from exc

        subject, body = apply_generation_plan(
            subject=subject,
            body=body,
            session=session,
            style_sliders=style_sliders,
            plan=plan,
        )
        session["cta_lock_effective"] = _collapse_ws(body.splitlines()[-1].strip()) if body.splitlines() else session.get(
            "cta_lock_effective", DEFAULT_FALLBACK_CTA
        )
        candidate = _format_draft(subject=subject, body=body)
        violations = validate_ctco_output(candidate, session=session, style_sliders=style_sliders)
        if not violations:
            return (
                candidate,
                gen_result,
                RealDraftStats(
                    validator_attempt_count=validator_attempt_count,
                    json_repair_count=json_repair_count,
                    violation_retry_count=violation_retry_count,
                    violation_codes=_violation_codes(all_violations),
                    violation_count=len(all_violations),
                ),
            )

        last_violations = violations
        all_violations.extend(violations)
        prior_draft = _sanitize_prior_draft(candidate)
        correction_notes = _validation_feedback(violations)
        logger.warning(
            "web_mvp_validation_failed",
            extra={
                "session_id": session_id,
                "attempt": validator_attempt_count,
                "violations": violations,
                "enforcement_level": enforcement_level,
            },
        )
        await persist_violations(violations, session_id=session_id, pipeline="remix")

        if enforcement_level == "repair" and repair_enabled:
            repaired_candidate = _deterministic_compliance_repair(
                candidate,
                session=session,
                style_sliders=style_sliders,
            )
            if repaired_candidate != candidate:
                repaired_violations = validate_ctco_output(
                    repaired_candidate,
                    session=session,
                    style_sliders=style_sliders,
                )
                if not repaired_violations:
                    logger.info(
                        "web_mvp_validation_repaired_deterministically",
                        extra={
                            "session_id": session_id,
                            "attempt": validator_attempt_count,
                            "initial_violations": violations,
                        },
                    )
                    return (
                        repaired_candidate,
                        gen_result,
                        RealDraftStats(
                            validator_attempt_count=validator_attempt_count,
                            json_repair_count=json_repair_count,
                            violation_retry_count=violation_retry_count + 1,
                            violation_codes=_violation_codes(all_violations),
                            violation_count=len(all_violations),
                        ),
                    )

                all_violations.extend(repaired_violations)
                await persist_violations(repaired_violations, session_id=session_id, pipeline="remix")
                candidate = repaired_candidate
                last_violations = repaired_violations
                prior_draft = _sanitize_prior_draft(candidate)
                correction_notes = _validation_feedback(repaired_violations)
                logger.warning(
                    "web_mvp_validation_deterministic_repair_incomplete",
                    extra={
                        "session_id": session_id,
                        "attempt": validator_attempt_count,
                        "violations": repaired_violations,
                        "enforcement_level": enforcement_level,
                    },
                )

        if enforcement_level == "warn":
            return (
                candidate,
                gen_result,
                RealDraftStats(
                    validator_attempt_count=validator_attempt_count,
                    json_repair_count=json_repair_count,
                    violation_retry_count=violation_retry_count,
                    violation_codes=_violation_codes(all_violations),
                    violation_count=len(all_violations),
                ),
            )

        if enforcement_level == "repair" and repair_enabled and not throttled and attempt_index < (max_attempts - 1):
            violation_retry_count += 1
            continue

        raise ValueError(f"ctco_validation_failed: {'; '.join(last_violations)}")

    raise ValueError(f"ctco_validation_failed: {'; '.join(last_violations)}")


async def build_draft(
    session: dict[str, Any],
    style_profile: dict[str, Any],
    throttled: bool = False,
    session_id: str | None = None,
) -> DraftResult:
    normalized = normalize_style_profile(style_profile)
    style_sliders = style_profile_to_ctco_sliders(normalized)
    preset_id = normalize_preset_id(session.get("preset_id"))
    session["preset_id"] = preset_id
    response_contract = _response_contract(session)
    session["response_contract"] = response_contract
    plan = build_generation_plan(
        session=session,
        style_sliders=style_sliders,
        preset_id=preset_id,
        cta_type=session.get("cta_type"),
    )
    session["generation_plan"] = plan.to_dict()
    session["cta_lock_effective"] = _resolve_effective_cta_lock(
        raw_lock=session.get("cta_offer_lock"),
        cta_type=plan.cta_type,
        offer_lock=session.get("offer_lock") or "",
        style_sliders=style_sliders,
        company_context=session.get("company_context"),
    )
    style_key = f"c:{response_contract}|p:{preset_id}|{style_profile_key(normalized)}"
    style_cache = session.get("style_cache", {})
    mode = _mode()
    enforcement_level = strict_lock_enforcement_level()
    repair_enabled = repair_loop_enabled()
    style_bands = ctco_style_bands(style_sliders)
    validator_attempt_count = 0
    json_repair_count = 0
    violation_retry_count = 0
    violation_count = 0
    violation_codes: list[str] = []
    if style_key in style_cache:
        cached_draft = style_cache[style_key]
        if response_contract == RC_TCO_RESPONSE_CONTRACT:
            cached_violations = validate_rc_tco_json(cached_draft)
        else:
            cached_violations = validate_ctco_output(cached_draft, session=session, style_sliders=style_sliders)
        if cached_violations:
            style_cache.pop(style_key, None)
            session["style_cache"] = style_cache
            session["style_order"] = [k for k in session.get("style_order", []) if k != style_key]
        else:
            # Return cached draft with current mode metadata
            _provider = _preferred_provider() if mode == "real" else "mock"
            _model = _PROVIDER_MODELS.get(_provider, _provider) if mode == "real" else "mock"
            return DraftResult(
                draft=cached_draft,
                style_key=style_key,
                style_profile=normalized,
                response_contract=response_contract,
                mode=mode,
                provider=_provider,
                model_name=_model,
                cascade_reason="cached",
                attempt_count=0,
                validator_attempt_count=0,
                json_repair_count=0,
                violation_retry_count=0,
                repaired=False,
                violation_codes=[],
                violation_count=0,
                enforcement_level=enforcement_level,
                repair_loop_enabled=repair_enabled,
                policy_version_snapshot=policy_runner.aggregate_versions(),
            )

    result_cascade_reason = "primary"
    result_attempt_count = 0
    legacy_draft = ""
    if mode != "real":
        subject = _mock_subject(session["prospect"], session["offer_lock"], style_sliders)
        body = _mock_body(session=session, style_sliders=style_sliders)
        subject, body = apply_generation_plan(
            subject=subject,
            body=body,
            session=session,
            style_sliders=style_sliders,
            plan=plan,
        )
        if body.splitlines():
            session["cta_lock_effective"] = _collapse_ws(body.splitlines()[-1].strip())
        legacy_draft = _format_draft(subject=subject, body=body)
        result_provider = "mock"
        result_model = "mock"
    else:
        legacy_draft, gen_result, real_stats = await _build_real_draft(
            session=session,
            style_sliders=style_sliders,
            style_bands=style_bands,
            throttled=throttled,
            enforcement_level=enforcement_level,
            repair_enabled=repair_enabled,
            session_id=session_id,
        )
        result_provider = gen_result.provider
        result_model = gen_result.model_name
        result_cascade_reason = gen_result.cascade_reason
        result_attempt_count = gen_result.attempt_count
        validator_attempt_count = real_stats.validator_attempt_count
        json_repair_count = real_stats.json_repair_count
        violation_retry_count = real_stats.violation_retry_count
        violation_codes = list(real_stats.violation_codes)
        violation_count = real_stats.violation_count

    legacy_violations = validate_ctco_output(legacy_draft, session=session, style_sliders=style_sliders)
    if legacy_violations:
        await persist_violations(legacy_violations, session_id=session_id, pipeline="remix")
        violation_codes = _unique_ordered(violation_codes + _violation_codes(legacy_violations))
        violation_count += len(legacy_violations)
        if enforcement_level != "warn":
            raise ValueError(f"ctco_validation_failed: {'; '.join(legacy_violations)}")

    draft = legacy_draft
    policy_draft = legacy_draft
    if response_contract == RC_TCO_RESPONSE_CONTRACT:
        subject, body = _extract_subject_and_body(legacy_draft)
        payload = build_rc_tco_output(
            session=session,
            subject=subject,
            body=body,
            mode=mode,
            effective_model_used=result_model,
            pipeline_meta=session.get("pipeline_meta"),
        )
        draft = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
        policy_draft = _rc_tco_payload_to_draft(payload)
        contract_violations = validate_rc_tco_json(draft)
        if contract_violations:
            await persist_violations(contract_violations, session_id=session_id, pipeline="remix")
            violation_codes = _unique_ordered(violation_codes + _violation_codes(contract_violations))
            violation_count += len(contract_violations)
            if enforcement_level != "warn":
                raise ValueError(f"ctco_validation_failed: {'; '.join(contract_violations)}")

    # Run policy_runner in parallel for observability — does NOT affect repair loop.
    _policy_report = policy_runner.run(
        policy_draft,
        session,
        style_sliders,
        session_id=str(session_id) if session_id is not None else None,
        repair_count=violation_retry_count,
    )
    session["policy_version_snapshot"] = _policy_report.policy_version_snapshot
    await persist_policy_metrics(_policy_report, session_id=str(session_id) if session_id is not None else None)

    style_cache[style_key] = draft
    style_order = session.get("style_order", [])
    style_order = [k for k in style_order if k != style_key] + [style_key]
    style_cache, style_order = _trim_style_cache(style_cache, style_order)
    session["style_cache"] = style_cache
    session["style_order"] = style_order
    session["last_style_profile"] = normalized
    session["style_history"] = (session.get("style_history", []) + [normalized])[-20:]
    session["last_draft"] = policy_draft
    if response_contract == RC_TCO_RESPONSE_CONTRACT:
        session["last_structured_draft"] = draft
    else:
        session.pop("last_structured_draft", None)

    return DraftResult(
        draft=draft,
        style_key=style_key,
        style_profile=normalized,
        response_contract=response_contract,
        mode=mode,
        provider=result_provider,
        model_name=result_model,
        cascade_reason=result_cascade_reason,
        attempt_count=result_attempt_count,
        validator_attempt_count=validator_attempt_count,
        json_repair_count=json_repair_count,
        violation_retry_count=violation_retry_count,
        repaired=(json_repair_count + violation_retry_count) > 0,
        violation_codes=violation_codes,
        violation_count=violation_count,
        enforcement_level=enforcement_level,
        repair_loop_enabled=repair_enabled,
        policy_version_snapshot=_policy_report.policy_version_snapshot,
    )


def create_session_payload(
    prospect: dict[str, Any],
    research_text: str,
    initial_style: dict[str, Any],
    offer_lock: str,
    cta_offer_lock: str | None = None,
    cta_type: str | None = None,
    company_context: dict[str, Any] | None = None,
    prospect_first_name: str | None = None,
    preset_id: str | None = None,
    response_contract: str | None = None,
    pipeline_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_style = normalize_style_profile(initial_style)
    initial_sliders = style_profile_to_ctco_sliders(normalized_style)
    normalized_company = normalize_company_context(company_context)
    effective_offer_lock = _normalize_lock_text(offer_lock, max_length=240) or normalized_company.get("current_product") or ""
    research_text_raw = (research_text or "").strip()
    research_text_sanitized = _strip_instructional_phrases(research_text_raw)
    if not research_text_sanitized:
        research_text_sanitized = _collapse_ws(research_text_raw)
    allowed_facts = _extract_allowed_facts(research_text_raw, max_items=4)

    # Derive first name server-side if not provided by client.
    if not prospect_first_name:
        prospect_first_name = derive_first_name((prospect.get("name") or "").strip())
    else:
        prospect_first_name = derive_first_name(prospect_first_name)
    normalized_preset_id = normalize_preset_id(preset_id)
    normalized_contract = RC_TCO_RESPONSE_CONTRACT if _collapse_ws(str(response_contract or "")).lower() == RC_TCO_RESPONSE_CONTRACT else LEGACY_RESPONSE_CONTRACT
    seed_session = {
        "prospect": prospect,
        "prospect_first_name": prospect_first_name,
        "company_context": normalized_company,
        "allowed_facts": allowed_facts,
        "offer_lock": effective_offer_lock,
        "research_text_raw": research_text_raw,
        "research_text": research_text_sanitized,
        "preset_id": normalized_preset_id,
        "cta_type": cta_type,
        "response_contract": normalized_contract,
    }
    initial_plan = build_generation_plan(
        session=seed_session,
        style_sliders=initial_sliders,
        preset_id=normalized_preset_id,
        cta_type=cta_type,
    )
    effective_cta_lock = _normalize_cta_lock(cta_offer_lock)

    return {
        "prospect": prospect,
        "prospect_first_name": prospect_first_name,
        "preset_id": normalized_preset_id,
        "response_contract": normalized_contract,
        "pipeline_meta": pipeline_meta or {},
        "company_context": normalized_company,
        "company_context_brief": build_company_context_brief(normalized_company),
        "research_text_raw": research_text_raw,
        "research_text_sanitized": research_text_sanitized,
        "research_text": research_text_sanitized,
        "allowed_facts": allowed_facts,
        "factual_brief": build_factual_brief(prospect=prospect, research_text=research_text_sanitized),
        "offer_lock": effective_offer_lock,
        "cta_offer_lock": _normalize_lock_text(cta_offer_lock, max_length=500),
        "cta_lock_effective": effective_cta_lock,
        "cta_type": cta_type,
        "generation_plan": initial_plan.to_dict(),
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
