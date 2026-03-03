"""Web MVP remix engine with CTCO lock controls and session caching."""

from __future__ import annotations

import hashlib
import json
import logging
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
from email_generation.prompt_templates import get_web_mvp_prompt, web_mvp_prompt_template_hash
from email_generation.quick_generate import GenerateResult, _mode, _preferred_provider, _real_generate
from email_generation.rc_tco_controller import (
    LEGACY_RESPONSE_CONTRACT,
    RC_TCO_RESPONSE_CONTRACT,
    build_rc_tco_output,
    validate_rc_tco_json,
)
from email_generation.runtime_policies import (
    allowed_facts_target_count,
    feature_fluency_repair_enabled,
    feature_no_prospect_owns_guardrail_enabled,
    feature_preset_true_rewrite_enabled,
    feature_shadow_mode_enabled,
    feature_structured_output_enabled,
    feature_sentence_safe_truncation_enabled,
    repair_loop_enabled,
    strict_lock_enforcement_level,
    web_mvp_output_token_budget_default,
    web_mvp_output_token_budget_long,
)
from email_generation.truncation import truncate_sentence_safe
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
_QUALITY_METRIC_TTL_SECONDS = 3 * 24 * 60 * 60

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
_GENERIC_RESEARCH_PATTERNS = (
    re.compile(r"^\s*wikipedia\s*$", re.IGNORECASE),
    re.compile(r"^\s*\+?\d+\s*$"),
    re.compile(r"\bis an? (?:american|global|leading)\s+(?:software|technology)\s+company\b", re.IGNORECASE),
    re.compile(r"\bcore platforms?\b", re.IGNORECASE),
)
_RESEARCH_TRIGGER_TOKENS = (
    "announced",
    "launched",
    "hiring",
    "hired",
    "roles",
    "contract",
    "filing",
    "earnings",
    "press release",
    "headcount",
    "partnership",
    "pilot",
    "rollout",
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
_FACT_ENTITY_RE = re.compile(r"\b(?:[A-Z][a-z]+|[A-Z]{2,})\b")

_INCOMPLETE_SENTENCE_END_CHARS = (",", ";", ":", "-", "/", "(")
_TRAILING_FRAGMENT_RE = re.compile(
    r"(?:\b(?:and|or|to|with|for|of|from|that|which|while|because|so)\b)\s*$",
    flags=re.IGNORECASE,
)
_HANGING_CONNECTOR_END_RE = re.compile(r"(?:\b(?:and|to|with)\b)\s*$", flags=re.IGNORECASE)


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


def _legacy_truncate(value: str, max_chars: int) -> tuple[str, dict[str, Any]]:
    compact = " ".join((value or "").split())
    if len(compact) <= max_chars:
        return compact, {
            "was_truncated": False,
            "boundary_used": "none",
            "cut_mid_sentence": False,
            "original_length": len(compact),
            "final_length": len(compact),
        }
    truncated = compact[:max_chars].rstrip() + "..."
    return truncated, {
        "was_truncated": True,
        "boundary_used": "legacy_hard_cut",
        "cut_mid_sentence": True,
        "original_length": len(compact),
        "final_length": len(truncated),
    }


def _truncate_context_text(value: str, max_chars: int) -> tuple[str, dict[str, Any]]:
    compact = " ".join((value or "").split())
    if feature_sentence_safe_truncation_enabled():
        result = truncate_sentence_safe(compact, max_chars=max_chars)
        return result.text, {
            "was_truncated": result.was_truncated,
            "boundary_used": result.boundary_used,
            "cut_mid_sentence": result.cut_mid_sentence,
            "original_length": result.original_length,
            "final_length": result.final_length,
        }
    return _legacy_truncate(compact, max_chars=max_chars)


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
        compact_notes, _truncation_meta = _truncate_context_text(notes, max_chars=800)
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
    compact, _truncation_meta = _truncate_context_text(research_text, max_chars=1600)
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


def _is_generic_biography_sentence(sentence: str) -> bool:
    normalized = _collapse_ws(sentence)
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in _GENERIC_RESEARCH_PATTERNS)


def _contains_research_trigger(sentence: str) -> bool:
    normalized = _collapse_ws((sentence or "").lower())
    if not normalized:
        return False
    if re.search(r"\b(?:q[1-4]|20\d{2}|19\d{2})\b", normalized):
        return True
    return any(token in normalized for token in _RESEARCH_TRIGGER_TOKENS)


def _strip_instructional_phrases(research_text: str) -> str:
    kept: list[str] = []
    for sentence in _split_research_sentences(research_text):
        if _is_instruction_like(sentence):
            continue
        if _is_generic_biography_sentence(sentence) and not _contains_research_trigger(sentence):
            continue
        kept.append(sentence.rstrip())
    return " ".join(kept).strip()


def _fact_type(sentence: str) -> str:
    lower = _collapse_ws(sentence.lower())
    if any(token in lower for token in ("hiring", "hired", "headcount", "roles", "recruiting")):
        return "hiring"
    if any(token in lower for token in ("launched", "initiative", "program", "rolled out", "adopted")):
        return "initiative"
    if any(token in lower for token in ("january", "february", "march", "april", "may", "june", "q1", "q2", "q3", "q4", "202")):
        return "timeline"
    if any(token in lower for token in ("team", "workflow", "playbook", "process", "governance", "qa", "quality")):
        return "ops"
    if any(token in lower for token in ("company", "organization", "org")):
        return "company"
    return "other"


def _fact_confidence(sentence: str) -> str:
    lower = _collapse_ws(sentence.lower())
    has_numeric_or_date = bool(re.search(r"\b(?:\d{1,4}|q[1-4]|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", lower))
    has_signal = _contains_factual_signal(sentence)
    has_hedge = any(token in lower for token in ("likely", "may", "might", "could", "appears", "seems"))
    if has_signal and not has_hedge and has_numeric_or_date:
        return "high"
    if has_signal and not has_hedge:
        return "high"
    if len(re.findall(r"[A-Za-z0-9']+", lower)) >= 8:
        return "medium"
    return "low"


def _extract_allowed_facts_structured(research_text: str, target_items: int = 8) -> list[dict[str, str]]:
    sanitized = _strip_instructional_phrases(research_text)
    facts: list[dict[str, str]] = []
    seen: set[str] = set()

    for sentence in _split_research_sentences(sanitized):
        cleaned = _collapse_ws(sentence.strip().rstrip("."))
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        if len(re.findall(r"[A-Za-z0-9']+", cleaned)) < 6:
            continue
        seen.add(key)
        facts.append(
            {
                "text": cleaned,
                "type": _fact_type(cleaned),
                "confidence": _fact_confidence(cleaned),
            }
        )
        if len(facts) >= target_items:
            break

    if len(facts) < min(8, target_items):
        for sentence in _split_research_sentences(sanitized):
            cleaned = _collapse_ws(sentence.strip().rstrip("."))
            key = cleaned.lower()
            if not cleaned or key in seen or _is_instruction_like(cleaned):
                continue
            clause_parts = [part.strip() for part in re.split(r";|, and |, but ", cleaned) if part.strip()]
            for part in clause_parts:
                part_key = part.lower()
                if part_key in seen:
                    continue
                if len(re.findall(r"[A-Za-z0-9']+", part)) < 6:
                    continue
                seen.add(part_key)
                facts.append(
                    {
                        "text": part,
                        "type": _fact_type(part),
                        "confidence": _fact_confidence(part),
                    }
                )
                if len(facts) >= target_items:
                    break
            if len(facts) >= target_items:
                break

    if len(facts) < min(8, target_items):
        for sentence in _split_research_sentences(sanitized):
            cleaned = _collapse_ws(sentence.strip().rstrip("."))
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            facts.append({"text": cleaned, "type": _fact_type(cleaned), "confidence": "low"})
            if len(facts) >= target_items:
                break

    if facts:
        return facts[: min(12, max(8, target_items))]

    compact = _collapse_ws(sanitized)
    if compact:
        return [{"text": compact[:220].rstrip(), "type": "other", "confidence": "low"}]
    return []


def _extract_allowed_facts(research_text: str, max_items: int = 8) -> list[str]:
    structured = _extract_allowed_facts_structured(research_text, target_items=max_items)
    if structured:
        return [entry.get("text", "").strip() for entry in structured if entry.get("text", "").strip()]
    compact = _collapse_ws(_strip_instructional_phrases(research_text))
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


def _prompt_checksum(prompt: list[dict[str, str]]) -> str:
    payload = json.dumps(prompt, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _redact_prompt_for_trace(prompt: list[dict[str, str]], *, session: dict[str, Any]) -> list[dict[str, str]]:
    prospect = session.get("prospect") or {}
    company_ctx = session.get("company_context") or {}
    pii_tokens = [
        str(prospect.get("name") or "").strip(),
        str(prospect.get("company") or "").strip(),
        str(prospect.get("linkedin_url") or "").strip(),
        str(company_ctx.get("company_name") or "").strip(),
        str(company_ctx.get("company_url") or "").strip(),
    ]
    pii_tokens = [token for token in pii_tokens if token]
    output: list[dict[str, str]] = []
    for message in prompt:
        role = str(message.get("role") or "user")
        content = str(message.get("content") or "")
        content = re.sub(r"https?://\S+", "<redacted_url>", content)
        for token in pii_tokens:
            content = content.replace(token, "<redacted>")
        if len(content) > 5000:
            content = f"{content[:5000]}...[truncated]"
        output.append({"role": role, "content": content})
    return output


def _prospect_owns_offer_lock_violations(draft: str, session: dict[str, Any]) -> list[str]:
    offer_lock = _collapse_ws(str(session.get("offer_lock") or ""))
    company = _collapse_ws(str((session.get("prospect") or {}).get("company") or ""))
    if not offer_lock or not company:
        return []
    patterns = [
        re.compile(rf"\b{re.escape(company)}['’]s\s+{re.escape(offer_lock)}\b", re.IGNORECASE),
        re.compile(rf"\byour\s+{re.escape(offer_lock)}\b", re.IGNORECASE),
    ]
    violations: list[str] = []
    for pattern in patterns:
        match = pattern.search(draft or "")
        if match:
            snippet = _collapse_ws(match.group(0))[:80]
            violations.append(f"prospect_owns_offer_lock:{snippet}")
    return violations


def _repair_prospect_owns_offer_lock(draft: str, session: dict[str, Any]) -> tuple[str, bool, list[str]]:
    offer_lock = _collapse_ws(str(session.get("offer_lock") or ""))
    company = _collapse_ws(str((session.get("prospect") or {}).get("company") or ""))
    if not offer_lock or not company:
        return draft, False, []
    subject, body = _extract_subject_and_body(draft)
    rewritten = False
    snippets: list[str] = []
    replacements = [
        (
            re.compile(rf"\b{re.escape(company)}['’]s\s+{re.escape(offer_lock)}\b", re.IGNORECASE),
            f"{offer_lock} for {company}",
        ),
        (
            re.compile(rf"\byour\s+{re.escape(offer_lock)}\b", re.IGNORECASE),
            f"{offer_lock}",
        ),
    ]
    for pattern, replacement in replacements:
        while True:
            match = pattern.search(body)
            if not match:
                break
            snippets.append(_collapse_ws(match.group(0))[:80])
            body = f"{body[:match.start()]}{replacement}{body[match.end():]}"
            rewritten = True
    if not rewritten:
        return draft, False, []
    return _format_draft(subject=subject, body=body), True, snippets


def _rc_tco_payload_to_draft(payload: dict[str, Any]) -> str:
    email = payload.get("email") if isinstance(payload, dict) else {}
    subject = _collapse_ws((email or {}).get("subject") or "")
    body = ((email or {}).get("body") or "").strip()
    return _format_draft(subject=subject, body=body)


def canonicalize_draft(draft: str) -> str:
    subject, body = _extract_subject_and_body(draft)
    return _format_draft(subject=subject, body=body)


def _parse_json_candidate(raw: str, *, allow_salvage: bool = True) -> tuple[dict[str, Any], str]:
    payload = (raw or "").strip()
    if not payload:
        raise ValueError("empty_output")

    parse_method = "strict"
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        if payload.startswith("```"):
            payload = re.sub(r"^```(?:json)?\s*|\s*```$", "", payload, flags=re.IGNORECASE | re.DOTALL).strip()
            if payload:
                try:
                    parsed = json.loads(payload)
                    parse_method = "markdown_fence"
                except json.JSONDecodeError as exc:
                    raise ValueError("json_fence_invalid") from exc
            else:
                raise ValueError("json_fence_without_content") from None
        elif allow_salvage:
            start = payload.find("{")
            end = payload.rfind("}")
            if start == -1 or end <= start:
                raise ValueError("no_json_object_found") from None
            parsed = json.loads(payload[start : end + 1])
            parse_method = "salvage_substring"
        else:
            raise ValueError("non_json_output") from None

    if not isinstance(parsed, dict):
        raise ValueError("json_output_not_object")
    return parsed, parse_method


def _parse_structured_output(raw: str, *, allow_salvage: bool = True) -> tuple[str, str, str]:
    parsed, parse_method = _parse_json_candidate(raw, allow_salvage=allow_salvage)
    subject = parsed.get("subject")
    body = parsed.get("body")
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("missing_json_subject")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("missing_json_body")
    return subject.strip(), body.strip(), parse_method


def _parse_openai_structured_output(raw: str) -> tuple[str, str, str]:
    payload = (raw or "").strip()
    if not payload:
        raise ValueError("openai_structured_empty_output")
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("openai_structured_invalid_json") from exc
    if not isinstance(parsed, dict):
        raise ValueError("openai_structured_not_object")
    subject = parsed.get("subject")
    body = parsed.get("body")
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("openai_structured_missing_subject")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("openai_structured_missing_body")
    return subject.strip(), body.strip(), "strict_openai"



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


def _body_without_cta(body: str, expected_cta: str) -> str:
    lines = [line.strip() for line in (body or "").splitlines() if line.strip()]
    kept: list[str] = []
    removed = False
    for line in lines:
        if line == expected_cta and not removed:
            removed = True
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _trim_hanging_connectors(text: str) -> str:
    current = (text or "").rstrip(" ,;:-")
    while _HANGING_CONNECTOR_END_RE.search(current):
        current = _HANGING_CONNECTOR_END_RE.sub("", current).rstrip(" ,;:-")
    return current


def _high_confidence_fact_text(session: dict[str, Any]) -> str:
    entries = session.get("allowed_facts_structured") or []
    high = [entry.get("text", "") for entry in entries if str(entry.get("confidence", "")).lower() == "high"]
    return " ".join([_collapse_ws(text) for text in high if _collapse_ws(text)])


def _extract_entities(text: str) -> set[str]:
    return {match.group(0) for match in _FACT_ENTITY_RE.finditer(text or "")}


def _fact_preserving_change_ok(before: str, after: str, session: dict[str, Any]) -> bool:
    before_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", before or ""))
    after_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", after or ""))
    if not after_numbers.issubset(before_numbers):
        return False

    allowed_entities = _extract_entities(before) | _extract_entities(_high_confidence_fact_text(session))
    after_entities = _extract_entities(after)
    if not after_entities.issubset(allowed_entities):
        return False

    return True


def _fact_preserving_fluency_repair(candidate: str, session: dict[str, Any]) -> tuple[str, bool]:
    subject, body = _extract_subject_and_body(candidate)
    if not body:
        return candidate, False

    expected_cta = str(session.get("cta_lock_effective") or DEFAULT_FALLBACK_CTA).strip()
    body_lines = [line.strip() for line in body.splitlines() if line.strip()]
    main_lines: list[str] = []
    cta_line = expected_cta
    cta_removed = False
    for line in body_lines:
        if not cta_removed and line == expected_cta:
            cta_removed = True
            cta_line = line
            continue
        main_lines.append(line)

    narrative = " ".join(main_lines).strip()
    if not narrative:
        return candidate, False

    repaired = narrative.replace("(", "").replace(")", "")
    repaired = repaired.replace('"', "")
    repaired = _trim_hanging_connectors(repaired)
    repaired = repaired.rstrip(" ,;:-")
    if repaired and repaired[-1] not in ".!?":
        repaired = repaired + "."
    repaired = dedupe_sentences_text(repaired)
    repaired = _collapse_ws(repaired)
    if not repaired:
        return candidate, False

    if not _fact_preserving_change_ok(narrative, repaired, session=session):
        return candidate, False

    repaired_body = f"{repaired}\n\n{cta_line}".strip()
    repaired_draft = _format_draft(subject=subject, body=repaired_body)
    return repaired_draft, repaired_draft != candidate


def _fluency_completeness_violations(draft: str, session: dict[str, Any]) -> list[str]:
    subject, body = _extract_subject_and_body(draft)
    if not subject or not body:
        return []

    expected_cta = str(session.get("cta_lock_effective") or DEFAULT_FALLBACK_CTA).strip()
    body_lines = [line.strip() for line in body.splitlines() if line.strip()]
    draft_lower = _collapse_ws(draft).lower()
    body_without_cta = _body_without_cta(body, expected_cta)
    narrative = _collapse_ws(body_without_cta)
    violations: list[str] = []

    if narrative:
        if narrative.endswith("..."):
            violations.append("fluency_abrupt_truncation_detected")
        if narrative.endswith(_INCOMPLETE_SENTENCE_END_CHARS) or _TRAILING_FRAGMENT_RE.search(narrative):
            violations.append("fluency_incomplete_sentence_ending")
        if narrative.count("(") != narrative.count(")"):
            violations.append("fluency_unmatched_parentheses")
        if narrative.count('"') % 2 == 1:
            violations.append("fluency_unmatched_quotes")
        sentence_keys: set[str] = set()
        for sentence in split_sentences(narrative):
            key = re.sub(r"[^a-z0-9 ]", "", sentence.lower()).strip()
            if not key:
                continue
            if key in sentence_keys:
                violations.append("fluency_duplicate_sentence")
                break
            sentence_keys.add(key)

    expected_first_name = _expected_prospect_first_name(session).lower()
    if expected_first_name and expected_first_name not in draft_lower:
        violations.append("missing_required_field:prospect_first_name")

    prospect_company = _collapse_ws(str((session.get("prospect") or {}).get("company") or "")).lower()
    if prospect_company and prospect_company not in draft_lower:
        violations.append("missing_required_field:prospect_company")

    offer_lock = _collapse_ws(str(session.get("offer_lock") or "")).lower()
    if offer_lock and offer_lock not in _collapse_ws(body).lower():
        violations.append("missing_required_field:offer_lock")

    if expected_cta and sum(1 for line in body_lines if line == expected_cta) != 1:
        violations.append("missing_required_field:cta")

    return _unique_ordered(violations)


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
    if feature_no_prospect_owns_guardrail_enabled():
        violations.extend(_prospect_owns_offer_lock_violations(draft, session=session))

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
    if any(v.startswith("fluency_") for v in violations):
        notes.append(
            "Fluency policy: produce complete grammatical sentences, no abrupt endings, no unmatched punctuation, "
            "and no duplicated sentence."
        )
    if any(v.startswith("missing_required_field:") for v in violations):
        notes.append(
            "Required fields policy: keep prospect first name, prospect company, offer lock, and exact CTA present."
        )
    if any(v.startswith("meta_commentary") for v in violations):
        notes.append(
            "Meta-commentary policy: remove any sentence that describes the email's compliance or "
            "construction (e.g. 'This email follows...', 'This keeps messaging...'). "
            "The body must be pure outbound copy — never reference the email itself."
        )
    if any(v.startswith("prospect_owns_offer_lock") for v in violations):
        notes.append(
            "Ownership policy: OFFER_LOCK is our offering. Never phrase it as the prospect's product "
            "(forbidden: '<Prospect>'s OFFER_LOCK' or 'your OFFER_LOCK')."
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


def _parse_ctco_violation_codes(value: str) -> list[str]:
    marker = "ctco_validation_failed:"
    if marker not in value:
        return []
    payload = value.split(marker, 1)[1].strip()
    if not payload:
        return []
    codes = [item.strip() for item in payload.split(";") if item.strip()]
    return _unique_ordered(codes)


def _build_validation_fallback_draft(
    *,
    session: dict[str, Any],
    style_sliders: dict[str, int],
) -> str:
    plan = GenerationPlan.from_dict(session.get("generation_plan")) or build_generation_plan(
        session=session,
        style_sliders=style_sliders,
        preset_id=session.get("preset_id"),
        cta_type=session.get("cta_type"),
    )
    subject_seed = _mock_subject(session["prospect"], session["offer_lock"], style_sliders)
    body_seed = f"{plan.greeting} {plan.wedge_outcome} {plan.wedge_problem}".strip()
    draft_seed = _format_draft(subject=subject_seed, body=body_seed)
    repaired = _deterministic_compliance_repair(
        draft_seed,
        session=session,
        style_sliders=style_sliders,
    )
    violations = validate_ctco_output(repaired, session=session, style_sliders=style_sliders)
    if not violations:
        return repaired

    # Second deterministic pass with richer seed text if the terse fallback misses constraints.
    fallback_body = _mock_body(session=session, style_sliders=style_sliders)
    fallback_seed = _format_draft(subject=subject_seed, body=fallback_body)
    repaired = _deterministic_compliance_repair(
        fallback_seed,
        session=session,
        style_sliders=style_sliders,
    )
    violations = validate_ctco_output(repaired, session=session, style_sliders=style_sliders)
    if violations:
        raise ValueError(f"ctco_validation_failed: {'; '.join(violations)}")
    return repaired


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
        extra_sections = section_pool[:6]
    elif style_sliders["length_short_long"] >= 67:
        extra_sections = section_pool[:4]
    elif style_sliders["length_short_long"] >= 50:
        extra_sections = section_pool[:1]
    else:
        extra_sections = []
    body = _fit_body_range(
        main_text=main,
        cta_line=cta,
        min_total=min_words,
        max_total=max_words,
        extra_sections=extra_sections,
    )
    if _word_count(body) < min_words:
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        cta_line = lines[-1] if lines else cta
        main_lines = [line for line in lines if line != cta_line]
        base_main = " ".join(main_lines).strip()
        supplements = [
            f"{offer_lock} keeps message quality consistent across reps without adding extra process burden.",
            "Managers get clearer control over tone and relevance as outreach volume grows.",
            f"{company} teams keep a predictable quality bar while scaling outbound volume.",
        ]
        expanded = base_main
        for sentence in supplements:
            candidate_main = f"{expanded} {sentence}".strip()
            candidate_body = f"{candidate_main}\n\n{cta_line}".strip()
            if _word_count(candidate_body) > max_words:
                continue
            expanded = candidate_main
            if _word_count(candidate_body) >= min_words:
                break
        body = f"{expanded}\n\n{cta_line}".strip()
    return body


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
    generation_status: str = field(default="ok")
    fallback_reason: str | None = field(default=None)


@dataclass
class RealDraftStats:
    validator_attempt_count: int = 1
    json_repair_count: int = 0
    violation_retry_count: int = 0
    violation_codes: list[str] = field(default_factory=list)
    violation_count: int = 0


def _quality_metric_key(name: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"web_mvp:quality:{day}:{name}"


async def emit_quality_metric(name: str, amount: int = 1) -> None:
    if amount <= 0:
        return
    redis = get_redis()
    key = _quality_metric_key(name)
    if amount == 1:
        await redis.incr(key)
    else:
        await redis.incrby(key, amount)
    await redis.expire(key, _QUALITY_METRIC_TTL_SECONDS)


def _output_token_budget(style_sliders: dict[str, int]) -> int:
    # Keeps medium/short behavior conservative while giving long-band outputs headroom.
    if style_sliders.get("length_short_long", 50) >= 67:
        return web_mvp_output_token_budget_long()
    return web_mvp_output_token_budget_default()


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


def _estimate_prompt_tokens(prompt: list[dict[str, str]]) -> int:
    text_len = 0
    for message in prompt:
        text_len += len(str(message.get("content") or ""))
        text_len += len(str(message.get("role") or "")) + 4
    return max(1, int(round(text_len / 4)))


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
    output_budget = _output_token_budget(style_sliders)
    attempt_trace: list[dict[str, Any]] = []
    structured_output_enabled = feature_structured_output_enabled()
    fluency_repair_enabled = feature_fluency_repair_enabled()
    shadow_mode_enabled = feature_shadow_mode_enabled()
    parse_invalid_retries = 0

    for attempt_index in range(max_attempts):
        validator_attempt_count = attempt_index + 1
        prompt = get_web_mvp_prompt(
            seller=seller_context,
            prospect=session["prospect"],
            research_sanitized=session.get("research_text_sanitized") or session.get("research_text") or "",
            allowed_facts=session.get("allowed_facts") or [],
            allowed_facts_structured=session.get("allowed_facts_structured") or [],
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
        prompt_token_estimate = _estimate_prompt_tokens(prompt)
        logger.info(
            "web_mvp_provider_request",
            extra={
                "session_id": session_id,
                "attempt": validator_attempt_count,
                "provider_preference": _preferred_provider(),
                "prompt_token_estimate": prompt_token_estimate,
                "output_token_budget": output_budget,
                "throttled": throttled,
            },
        )
        try:
            gen_result = await _real_generate(
                prompt=prompt,
                task="web_mvp",
                throttled=throttled,
                output_token_budget=output_budget,
            )
        except TypeError:
            # Backwards compatibility for tests monkeypatching legacy _real_generate signature.
            gen_result = await _real_generate(prompt=prompt, throttled=throttled)

        logger.info(
            "web_mvp_provider_response",
            extra={
                "session_id": session_id,
                "attempt": validator_attempt_count,
                "provider": gen_result.provider,
                "model": gen_result.model_name,
                "raw_length": len(gen_result.text or ""),
                "finish_reason": getattr(gen_result, "finish_reason", None),
                "cascade_reason": gen_result.cascade_reason,
                "provider_attempt_count": gen_result.attempt_count,
            },
        )
        trace_row: dict[str, Any] = {
            "attempt": validator_attempt_count,
            "provider": gen_result.provider,
            "model": gen_result.model_name,
            "prompt_token_estimate": prompt_token_estimate,
            "output_token_budget": output_budget,
            "raw_length": len(gen_result.text or ""),
            "finish_reason": getattr(gen_result, "finish_reason", None),
            "prompt_template_hash": web_mvp_prompt_template_hash(),
            "prompt_checksum": _prompt_checksum(prompt),
            "prompt_redacted": _redact_prompt_for_trace(prompt, session=session),
        }
        try:
            await emit_quality_metric("parse_attempt_count")
            strict_openai_response = structured_output_enabled and gen_result.provider == "openai"
            allow_salvage = (not strict_openai_response) and parse_invalid_retries >= 2
            if strict_openai_response:
                subject, body, parse_method = _parse_openai_structured_output(gen_result.text)
            else:
                subject, body, parse_method = _parse_structured_output(
                    gen_result.text,
                    allow_salvage=allow_salvage,
                )
            trace_row["parse_method"] = parse_method
            trace_row["allow_salvage"] = allow_salvage
            trace_row["parse_invalid_retries"] = parse_invalid_retries
            trace_row["parsed_json"] = {"subject": subject, "body": body}
            trace_row["subject_length"] = len(subject)
            trace_row["body_length"] = len(body)
            if parse_method == "salvage_substring":
                await emit_quality_metric("parse_salvage_used_count")
            logger.info(
                "web_mvp_parse_complete",
                extra={
                    "session_id": session_id,
                    "attempt": validator_attempt_count,
                    "parse_method": parse_method,
                    "subject_length": len(subject),
                    "body_length": len(body),
                },
            )
        except ValueError as exc:
            await emit_quality_metric("parse_invalid_json_count")
            last_violations = [f"invalid_json_output:{exc}"]
            all_violations.extend(last_violations)
            prior_draft = _collapse_ws((gen_result.text or "").strip())[:1200]
            correction_notes = _json_repair_feedback(gen_result.text, str(exc))
            json_repair_count += 1
            parse_invalid_retries += 1
            trace_row["parse_error"] = str(exc)
            trace_row["violations"] = list(last_violations)
            attempt_trace.append(trace_row)
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
                if feature_no_prospect_owns_guardrail_enabled():
                    candidate, rewritten, snippets = _repair_prospect_owns_offer_lock(candidate, session=session)
                    trace_row["prospect_owns_offer_lock_rewritten"] = rewritten
                    if snippets:
                        trace_row["prospect_owns_offer_lock_snippets"] = snippets[:2]
                session["last_generation_trace"] = {
                    "attempts": attempt_trace,
                    "last_raw_model_output": gen_result.text,
                    "status": "warn_parse_fallback",
                }
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
        if feature_no_prospect_owns_guardrail_enabled():
            candidate, rewritten, snippets = _repair_prospect_owns_offer_lock(candidate, session=session)
            trace_row["prospect_owns_offer_lock_rewritten"] = rewritten
            if snippets:
                trace_row["prospect_owns_offer_lock_snippets"] = snippets[:2]
        violations = validate_ctco_output(candidate, session=session, style_sliders=style_sliders)
        fluency_violations: list[str] = []
        if fluency_repair_enabled:
            fluency_violations = _fluency_completeness_violations(candidate, session=session)
            if fluency_violations:
                await emit_quality_metric("fluency_violation_count")
                violations = _unique_ordered(violations + fluency_violations)
        if not violations:
            trace_row["violations"] = []
            trace_row["repaired"] = False
            attempt_trace.append(trace_row)
            session["last_generation_trace"] = {
                "attempts": attempt_trace,
                "last_raw_model_output": gen_result.text,
                "final_candidate": candidate,
                "status": "ok",
            }
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
        trace_row["violations"] = list(violations)
        trace_row["repaired"] = False
        attempt_trace.append(trace_row)
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

        fluency_violation_present = any(
            code.startswith("fluency_") or code.startswith("missing_required_field:")
            for code in violations
        )
        if fluency_repair_enabled and fluency_violation_present:
            await emit_quality_metric("fluency_repair_attempt_count")
            repaired_candidate, fluency_repaired = _fact_preserving_fluency_repair(candidate, session=session)
            if fluency_repaired:
                repaired_violations = validate_ctco_output(
                    repaired_candidate,
                    session=session,
                    style_sliders=style_sliders,
                )
                repaired_fluency = _fluency_completeness_violations(repaired_candidate, session=session)
                if repaired_fluency:
                    repaired_violations = _unique_ordered(repaired_violations + repaired_fluency)
                if not repaired_violations:
                    await emit_quality_metric("fluency_repair_success_count")
                    session["last_generation_trace"] = {
                        "attempts": attempt_trace,
                        "last_raw_model_output": gen_result.text,
                        "final_candidate": repaired_candidate,
                        "status": "ok_fluency_repair",
                        "shadow_mode": shadow_mode_enabled,
                    }
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
                prior_draft = _sanitize_prior_draft(repaired_candidate)
                correction_notes = _validation_feedback(repaired_violations)
                attempt_trace[-1]["fluency_repaired"] = True
                attempt_trace[-1]["fluency_repaired_violations"] = list(repaired_violations)
            else:
                await emit_quality_metric("fluency_repair_rejected_new_claim_count")

        if (
            enforcement_level == "repair"
            and repair_enabled
            and not (fluency_repair_enabled and fluency_violation_present)
        ):
            repaired_candidate = _deterministic_compliance_repair(
                candidate,
                session=session,
                style_sliders=style_sliders,
            )
            if repaired_candidate != candidate:
                await emit_quality_metric("ngram_repetition_repair_count")
                repaired_violations = validate_ctco_output(
                    repaired_candidate,
                    session=session,
                    style_sliders=style_sliders,
                )
                if fluency_repair_enabled:
                    repaired_fluency = _fluency_completeness_violations(repaired_candidate, session=session)
                    if repaired_fluency:
                        repaired_violations = _unique_ordered(repaired_violations + repaired_fluency)
                if not repaired_violations:
                    logger.info(
                        "web_mvp_validation_repaired_deterministically",
                        extra={
                            "session_id": session_id,
                            "attempt": validator_attempt_count,
                            "initial_violations": violations,
                        },
                    )
                    attempt_trace[-1]["repaired"] = True
                    attempt_trace[-1]["repaired_violations"] = []
                    session["last_generation_trace"] = {
                        "attempts": attempt_trace,
                        "last_raw_model_output": gen_result.text,
                        "final_candidate": repaired_candidate,
                        "status": "ok_deterministic_repair",
                    }
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
                attempt_trace[-1]["repaired"] = True
                attempt_trace[-1]["repaired_violations"] = list(repaired_violations)
                logger.warning(
                    "web_mvp_validation_deterministic_repair_incomplete",
                    extra={
                        "session_id": session_id,
                        "attempt": validator_attempt_count,
                        "violations": repaired_violations,
                        "enforcement_level": enforcement_level,
                    },
                )
        elif fluency_repair_enabled and fluency_violation_present:
            attempt_trace[-1]["deterministic_repair_skipped"] = "fluency_repair_path"

        if enforcement_level == "warn":
            session["last_generation_trace"] = {
                "attempts": attempt_trace,
                "last_raw_model_output": gen_result.text,
                "final_candidate": candidate,
                "status": "warn_with_violations",
            }
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

        session["last_generation_trace"] = {
            "attempts": attempt_trace,
            "last_raw_model_output": gen_result.text,
            "status": "failed_validation",
            "last_violations": list(last_violations),
        }
        raise ValueError(f"ctco_validation_failed: {'; '.join(last_violations)}")

    session["last_generation_trace"] = {
        "attempts": attempt_trace,
        "status": "failed_exhausted",
        "last_violations": list(last_violations),
    }
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
    quality_flags = session.get("quality_flags") or {}
    if quality_flags.get("truncation_mid_sentence") and not quality_flags.get("_reported_truncation_mid_sentence"):
        await emit_quality_metric("truncation_mid_sentence_count")
        quality_flags["_reported_truncation_mid_sentence"] = True
        session["quality_flags"] = quality_flags
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
    generation_status = "ok"
    fallback_reason: str | None = None
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
        if plan.persona_route == "exec" or feature_preset_true_rewrite_enabled():
            min_words = int(plan.length_target.get("min_words", 75))
            max_words = int(plan.length_target.get("max_words", 110))
        else:
            min_words, max_words = body_word_range(style_sliders["length_short_long"])
        if _word_count(body) < min_words:
            body_lines = [line.strip() for line in body.splitlines() if line.strip()]
            cta_line = body_lines[-1] if body_lines else session.get("cta_lock_effective", DEFAULT_FALLBACK_CTA)
            main_lines = body_lines[:-1] if len(body_lines) > 1 else body_lines
            main_text = " ".join(main_lines).strip()
            supplemental_sections = long_mode_section_pool(
                company_notes=(session.get("company_context") or {}).get("company_notes"),
                allowed_facts=session.get("allowed_facts") or [],
                offer_lock=session.get("offer_lock") or "",
                company=(session.get("prospect") or {}).get("company") or "your company",
                forbidden_terms=_offer_lock_forbidden_items(session),
            )
            body = _fit_body_range(
                main_text=main_text,
                cta_line=cta_line,
                min_total=min_words,
                max_total=max_words,
                extra_sections=supplemental_sections[:8],
            )
        if _word_count(body) < min_words:
            body_lines = [line.strip() for line in body.splitlines() if line.strip()]
            cta_line = body_lines[-1] if body_lines else session.get("cta_lock_effective", DEFAULT_FALLBACK_CTA)
            main_lines = body_lines[:-1] if len(body_lines) > 1 else body_lines
            base_main = " ".join(main_lines).strip()
            supplements = [
                "Teams maintain consistent outbound quality as volume increases.",
                "Managers get clearer control over message relevance without extra workflow burden.",
                "Execution stays practical for organizations that need repeatable weekly output.",
            ]
            for sentence in supplements:
                if sentence.lower() in base_main.lower():
                    continue
                candidate_main = f"{base_main} {sentence}".strip()
                candidate_body = f"{candidate_main}\n\n{cta_line}".strip()
                if _word_count(candidate_body) > max_words:
                    break
                base_main = candidate_main
                body = candidate_body
                if _word_count(body) >= min_words:
                    break
        if body.splitlines():
            session["cta_lock_effective"] = _collapse_ws(body.splitlines()[-1].strip())
        legacy_draft = _format_draft(subject=subject, body=body)
        result_provider = "mock"
        result_model = "mock"
    else:
        try:
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
        except ValueError as exc:
            raw_error = str(exc)
            if "ctco_validation_failed:" not in raw_error:
                raise
            fallback_codes = _parse_ctco_violation_codes(raw_error)
            if any(code.startswith("invalid_json_output") for code in fallback_codes):
                raise
            fallback_reason = raw_error
            generation_status = "fallback_after_validation_failure"
            legacy_draft = _build_validation_fallback_draft(
                session=session,
                style_sliders=style_sliders,
            )
            result_provider = "deterministic_fallback"
            result_model = "deterministic_fallback"
            result_cascade_reason = "fallback_after_validation_failure"
            result_attempt_count = 0
            validator_attempt_count = max(validator_attempt_count, 1)
            violation_retry_count = max(violation_retry_count, 1)
            violation_codes = _unique_ordered([*violation_codes, *fallback_codes])
            violation_count += len(fallback_codes)
            logger.warning(
                "web_mvp_validation_fallback_applied",
                extra={
                    "session_id": session_id,
                    "fallback_reason": raw_error,
                    "violation_codes": fallback_codes,
                    "enforcement_level": enforcement_level,
                },
            )

    if feature_no_prospect_owns_guardrail_enabled():
        legacy_draft, ownership_rewritten, ownership_snippets = _repair_prospect_owns_offer_lock(legacy_draft, session=session)
        quality_flags = session.get("quality_flags") or {}
        quality_flags["prospect_owns_offer_lock_rewritten"] = ownership_rewritten
        if ownership_snippets:
            quality_flags["prospect_owns_offer_lock_snippets"] = ownership_snippets[:2]
        session["quality_flags"] = quality_flags

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
        repaired=(json_repair_count + violation_retry_count) > 0 or generation_status != "ok",
        violation_codes=violation_codes,
        violation_count=violation_count,
        enforcement_level=enforcement_level,
        repair_loop_enabled=repair_enabled,
        policy_version_snapshot=_policy_report.policy_version_snapshot,
        generation_status=generation_status,
        fallback_reason=fallback_reason,
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
    facts_target = allowed_facts_target_count()
    allowed_facts_structured = _extract_allowed_facts_structured(research_text_raw, target_items=facts_target)
    allowed_facts = [entry.get("text", "").strip() for entry in allowed_facts_structured if entry.get("text", "").strip()]

    company_notes_source = normalized_company.get("company_notes") or ""
    _company_notes_preview, company_notes_trunc = _truncate_context_text(company_notes_source, max_chars=800)
    _research_preview, research_trunc = _truncate_context_text(research_text_sanitized, max_chars=1600)
    truncation_mid_sentence = bool(company_notes_trunc["cut_mid_sentence"] or research_trunc["cut_mid_sentence"])

    shadow_trace: dict[str, Any] = {}
    if feature_shadow_mode_enabled() and not feature_sentence_safe_truncation_enabled():
        shadow_company = truncate_sentence_safe(company_notes_source, max_chars=800)
        shadow_research = truncate_sentence_safe(research_text_sanitized, max_chars=1600)
        shadow_trace["sentence_safe_truncation"] = {
            "company_notes": {
                "was_truncated": shadow_company.was_truncated,
                "boundary_used": shadow_company.boundary_used,
                "cut_mid_sentence": shadow_company.cut_mid_sentence,
                "original_length": shadow_company.original_length,
                "final_length": shadow_company.final_length,
            },
            "research_excerpt": {
                "was_truncated": shadow_research.was_truncated,
                "boundary_used": shadow_research.boundary_used,
                "cut_mid_sentence": shadow_research.cut_mid_sentence,
                "original_length": shadow_research.original_length,
                "final_length": shadow_research.final_length,
            },
        }

    logger.info(
        "web_mvp_input_normalized",
        extra={
            "prospect_company": (prospect.get("company") or ""),
            "offer_lock_length": len(effective_offer_lock or ""),
            "company_notes_length": len(company_notes_source),
            "research_raw_length": len(research_text_raw),
            "research_sanitized_length": len(research_text_sanitized),
            "facts_target": facts_target,
        },
    )
    logger.info(
        "web_mvp_truncation_checkpoint",
        extra={
            "company_notes": company_notes_trunc,
            "research_excerpt": research_trunc,
            "company_notes_tail": company_notes_source[-120:],
            "research_tail": research_text_sanitized[-120:],
        },
    )
    logger.info(
        "web_mvp_allowed_facts_extracted",
        extra={
            "count": len(allowed_facts),
            "fact_lengths": [len(fact) for fact in allowed_facts],
            "fact_types": [entry.get("type", "other") for entry in allowed_facts_structured],
            "fact_confidence": [entry.get("confidence", "low") for entry in allowed_facts_structured],
        },
    )

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
        "allowed_facts_structured": allowed_facts_structured,
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
        "allowed_facts_structured": allowed_facts_structured,
        "allowed_facts_target_count": facts_target,
        "truncation_metadata": {
            "company_notes": company_notes_trunc,
            "research_excerpt": research_trunc,
        },
        "quality_flags": {
            "truncation_mid_sentence": truncation_mid_sentence,
        },
        "shadow_trace": shadow_trace,
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
        "draft_id_counter": 0,
        "metrics": {"generate_count": 0, "remix_count": 0},
    }


def mode_is_real() -> bool:
    return _mode() == "real"
