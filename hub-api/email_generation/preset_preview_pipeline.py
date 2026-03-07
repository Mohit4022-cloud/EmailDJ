"""Preset preview pipeline with a single low-latency generator stage."""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.schemas import (
    WebPresetPreviewBatchRequest,
    WebPresetPreviewBatchResponse,
    WebPreviewBatchMeta,
    WebPreviewEffectiveSliders,
    WebPreviewItem,
    WebPreviewPresetInput,
    WebSummaryPack,
)
from email_generation.claim_verifier import (
    extract_allowed_numeric_claims,
    find_unverified_claims,
    merge_claim_sources,
    rewrite_unverified_claims,
)
from email_generation.compliance_rules import (
    _CASH_CTA_PATTERN,
    _GUARANTEED_CLAIM_PATTERN,
    _ABSOLUTE_REVENUE_PATTERN,
    _STAT_CLAIM_PATTERN,
    _NO_LEAKAGE_TERMS,
    _collapse_ws,
    _contains_term,
)
from email_generation.cta_templates import resolve_cta_lock
from email_generation.model_defaults import (
    default_openai_model,
    openai_reasoning_effort,
    openai_supports_temperature_override,
)
from email_generation.output_enforcement import (
    _GENERIC_CLOSER_PATTERNS,
    compose_body_without_padding_loops,
    derive_first_name,
    enforce_first_name_greeting,
    long_mode_section_pool,
    remove_generic_closers,
    sanitize_generic_ai_opener,
    split_sentences,
)
from email_generation.offer_domain import infer_offer_domain, offer_keywords_from_lock
from email_generation.preset_strategies import get_preset_strategy
from email_generation.runtime_policies import quick_generate_mode, repair_loop_enabled
from infra.redis_client import get_redis

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "single-generator-v2"
_PREVIEW_ENFORCEMENT_LEVEL_ENV = "EMAILDJ_PREVIEW_ENFORCEMENT_LEVEL"
_PREVIEW_OPENAI_TIMEOUT_ENV = "EMAILDJ_PREVIEW_OPENAI_TIMEOUT_SECONDS"
_BANNED_POSITIONING_PHRASES = (
    "ai services",
    "ai consulting",
    "we build ai",
    "ai transformation services",
)
_GENERIC_AI_OPENER_PATTERN = re.compile(
    r"^(?:(?:hi|hello)\s+[^,\n]+,\s*)?as\s+[a-z0-9&.\- ]+\s+scales\s+(?:its|their)\s+(?:enterprise\s+)?ai\s+initiatives[, ]",
    re.IGNORECASE,
)
_EXEC_TITLES_RE = re.compile(
    r"\b(ceo|chief executive officer|founder|co-founder|president|chief of staff)\b",
    re.IGNORECASE,
)
# _OWNERSHIP_KEYWORDS removed — keywords are now derived from req.offer_lock at
# call time via offer_keywords_from_lock(). See _repair_prospect_offer_ownership().
_SOCIAL_PROOF_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bbrands like yours\b", "teams like yours"),
    (r"\bcompanies like yours\b", "teams like yours"),
    (r"\bbrands like\b", "teams at"),
    (r"\bcompanies like\b", "teams at"),
    (r"\btrusted by\b", "used with"),
    (r"\bused by\b", "used with"),
    (r"\bcustomers include\b", "customers in"),
    (r"\bclients include\b", "clients in"),
)
# Brand-protection-specific data-security → brand-protection term rewrites.
# These are only applied when the offer domain is brand_protection.
# For all other sellers this is a no-op (gated in _apply_category_mismatch_rewrites).
_CATEGORY_MISMATCH_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\bcybersecurity\b", "brand security"),
    (r"\bcyber security\b", "brand security"),
    (r"\bdata security\b", "brand security"),
    (r"\bdata breach\b", "brand abuse"),
    (r"\bransomware\b", "counterfeit risk"),
    (r"\bmalware\b", "brand abuse"),
    (r"\bphishing\b", "impersonation"),
    (r"\bendpoint protection\b", "brand monitoring"),
)
_PROOF_DUMP_TOKEN_RE = re.compile(r"\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,})*|[A-Z]{3,})\b")
_PROOF_DUMP_COMMON_CAPS = {
    "You", "Your", "We", "Our", "Their", "The", "This", "That", "These", "Those",
    "It", "If", "In", "On", "At", "For", "To", "And", "But", "Or", "A", "An",
    "Hi", "Dear", "Best", "Thanks", "Thank", "Hope", "Would", "Could", "Should",
    "Let", "Open", "Happy", "Glad", "Given", "Based", "When", "While", "Since",
    "With", "From", "By", "As", "Is", "Are", "Was", "Were", "Be", "Have",
    "Has", "Had", "Do", "Does", "Did", "Will", "Can", "May", "Might", "Must",
}
_WIKIPEDIA_TOKEN_RE = re.compile(r"\bwikipedia\b", re.IGNORECASE)
_WIKIPEDIA_TOKEN_LINE_RE = re.compile(r"^\s*wikipedia\s*$", re.IGNORECASE)
_WIKIPEDIA_SOURCE_INDEX_LINE_RE = re.compile(r"^\s*\+\d+\s*$")
_WIKI_BIO_OPENER_LINE_RE = re.compile(
    r"^\s*[A-Z][A-Za-z0-9&.,'’\- ]{1,120}\s+is an?\s+"
    r"(?:American|British|Canadian|German|French|global|international|leading)\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def preview_prompt_template_hashes() -> dict[str, str]:
    generator_material = _GENERATOR_SYSTEM_PROMPT + inspect.getsource(_generator_messages)
    generator_hash = hashlib.sha256(generator_material.encode("utf-8")).hexdigest()[:16]
    return {
        "extractor": "removed",
        "generator": generator_hash,
        "combined": "removed",
    }

# CTA-like sentence patterns — used to strip duplicate CTA lines from draft body
_CTA_LINE_PATTERN = re.compile(
    r"\b(worth a look|not a priority|open to|book|15[ -]?min|quick call|"
    r"quick chat|calendar|schedule|let me know|next step|reach out|happy to)\b",
    re.IGNORECASE,
)

_GENERATOR_SYSTEM_PROMPT = """You are EmailDJ’s Preview Batch Generator. Generate send-ready outbound emails with strict CTCO compliance and cost control.
Optimization priorities: (1) CTCO compliance, (2) lowest total tokens, (3) high-quality credible copy.

HARD COMPLIANCE RULES (violations trigger regeneration):
- OFFER LOCK: Pitch ONLY the product named in offer_lock. Never mention other products or services.
- CTA PRECEDENCE (apply per preset): (1) if cta_lock_text is non-empty, use it exactly; (2) else if cta_type is provided, use that CTA template; (3) else use preset default CTA type.
- LEAKAGE BAN: Never output these terms: emaildj, remix, mapping, template, templates, slider, sliders, prompt, prompts, llm, llms, openai, gemini, codex, generated, automation tooling.
- GROUNDING: Only assert specific facts from summary_pack.facts. Frame all else as soft hypothesis or general pattern.
- NO CASH CTAs: Never offer gift cards, Amazon cards, prepaid cards, cash rewards, or "$X gift".
- NO FAKE STATISTICS: Do not include percentage improvements, ROI claims, or "proven"/"guaranteed" performance claims unless the exact figure appears in summary_pack.facts.
- NEVER output placeholders like [Name], [Company], {variable}. Use clean fallbacks ('Hi there,') if a value is missing.
- Do not mention you are an AI.

HARD FORMAT LIMITS:
- subject: <= 8 words
- body: 55-130 words total (including cta_lock line); exec titles must stay <=90 words

STYLE RULES:
- No "hope you’re well"
- No exclamation marks
- Body must end with the resolved CTA line as its own line

Output MUST match the JSON schema (Structured Outputs / strict).
Return exactly this shape:
{
  "previews": [
    {"preset_id": "...", "subject": "...", "body": "..."}
  ]
}
Do not include extra fields."""

_GENERATOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "previews": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "preset_id": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["preset_id", "subject", "body"],
            },
        }
    },
    "required": ["previews"],
}

class _GeneratorPreviewOutputItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preset_id: str = Field(min_length=1)
    subject: str
    body: str


class _GeneratorPreviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    previews: list[_GeneratorPreviewOutputItem] = Field(min_length=1)


@dataclass
class PipelineResult:
    previews: list[WebPreviewItem]
    summary_pack: WebSummaryPack
    mode: str
    cache_hit: bool
    provider: str
    model_name: str
    provider_attempt_count: int
    validator_attempt_count: int
    repair_attempt_count: int
    repaired: bool
    initial_violation_count: int
    final_violation_count: int
    latency_ms: int
    violations: list[str] = None  # type: ignore[assignment]
    violation_codes: list[str] = None  # type: ignore[assignment]
    violation_count: int = 0
    enforcement_level: str = "repair"
    repair_loop_enabled: bool = True
    status: str = "success"
    degraded_reason: str | None = None

    def __post_init__(self) -> None:
        if self.violations is None:
            self.violations = []
        if self.violation_codes is None:
            self.violation_codes = []


def _compact(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _preprocess_research_text(value: str | None) -> str:
    lines = str(value or "").splitlines()
    cleaned: list[str] = []
    for line in lines:
        candidate = _compact(line)
        if not candidate:
            continue
        if _WIKIPEDIA_TOKEN_LINE_RE.match(candidate):
            continue
        if _WIKIPEDIA_SOURCE_INDEX_LINE_RE.match(candidate):
            continue
        if _WIKI_BIO_OPENER_LINE_RE.match(candidate):
            continue
        cleaned.append(candidate)
    text = "\n".join(cleaned).strip()
    if not text:
        return ""
    text = _WIKIPEDIA_TOKEN_RE.sub("", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.;!?])", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _preprocessed_raw_research(req: WebPresetPreviewBatchRequest) -> dict[str, Any]:
    return {
        "deep_research_paste": _preprocess_research_text(req.raw_research.deep_research_paste),
        "company_notes": _preprocess_research_text(req.raw_research.company_notes or ""),
        "extra_constraints": req.raw_research.extra_constraints,
    }


def _violation_codes(violations: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for entry in violations:
        code = entry.split(":", 1)[0].strip()
        if not code or code in seen:
            continue
        seen.add(code)
        output.append(code)
    return output


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _quick_mode() -> str:
    return quick_generate_mode()


def _generator_model() -> str:
    default_model = default_openai_model()
    return os.environ.get("EMAILDJ_PRESET_PREVIEW_MODEL_GENERATOR", default_model).strip() or default_model


def _fallback_model() -> str:
    default_model = default_openai_model()
    return os.environ.get("EMAILDJ_PRESET_PREVIEW_MODEL_FALLBACK", default_model).strip() or default_model


def _include_summary_pack() -> bool:
    return os.environ.get("EMAILDJ_PREVIEW_INCLUDE_SUMMARY_PACK", "0").strip() == "1"


def _summary_ttl() -> int:
    return _env_int("EMAILDJ_PRESET_PREVIEW_SUMMARY_CACHE_TTL_SEC", 900, 60, 3600)


def _openai_timeout_seconds(transform_type: str) -> float:
    _ = transform_type  # kept for call-site compatibility
    default_timeout = 30.0
    raw_default = os.environ.get(_PREVIEW_OPENAI_TIMEOUT_ENV, str(default_timeout)).strip()
    try:
        fallback_timeout = float(raw_default)
    except ValueError:
        fallback_timeout = default_timeout
    return max(10.0, min(30.0, fallback_timeout))


def _to_words(value: str) -> list[str]:
    return re.findall(r"\S+", value)


def _clamp_slider(value: Any) -> int:
    try:
        parsed = int(round(float(value)))
    except Exception:
        parsed = 50
    return max(0, min(100, parsed))


def _effective_sliders(req: WebPresetPreviewBatchRequest, preset: WebPreviewPresetInput) -> WebPreviewEffectiveSliders:
    base = req.global_sliders.model_dump()
    overrides = preset.slider_overrides.model_dump(exclude_none=True)
    base.update({key: _clamp_slider(value) for key, value in overrides.items()})
    return WebPreviewEffectiveSliders(**base)


def _resolve_preview_cta(
    req: WebPresetPreviewBatchRequest,
    preset: WebPreviewPresetInput,
    effective: WebPreviewEffectiveSliders,
) -> str:
    strategy = get_preset_strategy(preset.preset_id)
    cta_type = (req.cta_type or strategy.cta_type or "").strip() or None
    lock_text = _compact(req.cta_lock_text or req.cta_lock or "")
    risk_surface = _compact(req.offer_lock) or _compact(req.product_context.product_name) or "your highest-risk surface"
    return resolve_cta_lock(
        existing_lock=lock_text,
        cta_type=cta_type,
        risk_surface=risk_surface,
        directness=_clamp_slider(effective.directness),
        preset_id=str(preset.preset_id),
        prospect_title=req.prospect.title,
    )


def _first_sentence(value: str) -> str:
    text = _compact(value)
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return parts[0].strip() if parts else text


def _ensure_likely_prefix(items: list[str]) -> list[str]:
    output: list[str] = []
    for item in items[:3]:
        text = _compact(item)
        if not text:
            text = "reviewing reply quality and outbound consistency"
        if not text.lower().startswith("(likely)"):
            text = f"(likely) {text}"
        output.append(text)
    while len(output) < 3:
        output.append("(likely) improving reply quality from first-touch messaging")
    return output


def _trim_words(value: str, max_words: int) -> str:
    words = _to_words(_compact(value))
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words])


def _is_exec_title(title: str | None) -> bool:
    return bool(_EXEC_TITLES_RE.search(_compact(title)))


def _body_word_targets(req: WebPresetPreviewBatchRequest) -> tuple[int, int]:
    if _is_exec_title(req.prospect.title):
        return 55, 90
    return 90, 130


def _sentence_case_offer_lock(offer_lock: str) -> str:
    cleaned = _compact(offer_lock)
    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:].lower()


def _sentence_case_phrase(value: str) -> str:
    cleaned = _compact(value)
    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:].lower()


def _soften_offer_lock_mentions(text: str, offer_lock: str, *, force_lowercase: bool = False) -> str:
    body = _compact(text)
    lock = _compact(offer_lock)
    if not body or not lock:
        return body
    softened = lock.lower() if force_lowercase else _sentence_case_phrase(lock)
    return re.sub(re.escape(lock), softened, body, flags=re.IGNORECASE)


def _soften_company_mentions(text: str, company: str) -> str:
    body = _compact(text)
    company_clean = _compact(company)
    if not body or not company_clean:
        return body
    softened = _sentence_case_phrase(company_clean)
    return re.sub(re.escape(company_clean), softened, body, flags=re.IGNORECASE)


def _soften_proof_point_mentions(text: str, proof_points: list[str] | None) -> str:
    body = _compact(text)
    if not body:
        return body
    for point in proof_points or []:
        point_clean = _compact(point)
        if not point_clean:
            continue
        softened = point_clean.lower()
        body = re.sub(re.escape(point_clean), softened, body, flags=re.IGNORECASE)
    body = re.sub(r"\s{2,}", " ", body)
    body = re.sub(r"\s+([,.;!?])", r"\1", body)
    return body.strip()


def _repair_prospect_offer_ownership(
    text: str,
    *,
    company: str,
    offer_lock: str = "",
) -> str:
    """Repair ownership framing patterns like ‘<Co>’s <offer>’ or ‘your <offer>’.

    Keywords are derived from ``offer_lock`` at call time — no hardcoded domain
    vocabulary. Works for any seller (brand protection, HR tech, AI platform, etc.).
    """
    body = _compact(text)
    if not body:
        return body
    company_clean = _compact(company)
    keywords = offer_keywords_from_lock(offer_lock)

    for keyword in keywords:
        safe_keyword = re.escape(keyword.lower())
        if company_clean:
            company_safe = re.escape(company_clean)
            # "<Co>’s <offer>" → "<offer> for <Co>"
            body = re.sub(
                rf"\b{company_safe}[‘’]s\s+{safe_keyword}\b",
                f"{keyword} for {company_clean}",
                body,
                flags=re.IGNORECASE,
            )
            # "<Co> <offer>" → "<offer> for <Co>"
            body = re.sub(
                rf"\b{company_safe}\s+{safe_keyword}\b",
                f"{keyword} for {company_clean}",
                body,
                flags=re.IGNORECASE,
            )
            # Generic preposition patterns using primary keyword
            if keyword == keywords[0]:
                body = re.sub(
                    rf"\b{safe_keyword}\s+for\s+{company_safe}\b",
                    f"controls for {company_clean}",
                    body,
                    flags=re.IGNORECASE,
                )
                body = re.sub(
                    rf"\b{safe_keyword}\s+at\s+{company_safe}\b",
                    f"controls at {company_clean}",
                    body,
                    flags=re.IGNORECASE,
                )
                body = re.sub(
                    rf"\b{company_safe}\s+uses\s+{safe_keyword}\b",
                    f"{company_clean} manages controls",
                    body,
                    flags=re.IGNORECASE,
                )
        # Match singular and plural ("your trademark" and "your trademarks")
        body = re.sub(rf"\byour\s+{safe_keyword}s?\b", keyword, body, flags=re.IGNORECASE)

    body = re.sub(r"\s{2,}", " ", body)
    body = re.sub(r"\s+([,.;!?])", r"\1", body)
    return body.strip()


def _sanitize_social_proof_phrasing(text: str) -> str:
    body = _compact(text)
    if not body:
        return body
    for pattern, replacement in _SOCIAL_PROOF_PATTERNS:
        body = re.sub(pattern, replacement, body, flags=re.IGNORECASE)
    body = re.sub(r"\s{2,}", " ", body)
    body = re.sub(r"\s+([,.;!?])", r"\1", body)
    return body.strip()


def _sanitize_category_mismatch_terms(text: str, *, offer_domain: str | None = None) -> str:
    """Replace data-security vocabulary with brand-protection equivalents.

    This is a no-op for sellers outside the brand_protection domain — avoids
    false rewrites for HR tech, AI platform, retail, and other sellers.
    """
    body = _compact(text)
    if not body:
        return body
    if offer_domain != "brand_protection":
        return body
    for pattern, replacement in _CATEGORY_MISMATCH_REPLACEMENTS:
        body = re.sub(pattern, replacement, body, flags=re.IGNORECASE)
    body = re.sub(r"\s{2,}", " ", body)
    body = re.sub(r"\s+([,.;!?])", r"\1", body)
    return body.strip()


def _strip_post_greeting_name_fragment(text: str, *, prospect_name: str, first_name: str) -> str:
    body = _compact(text)
    if not body:
        return body
    full = _compact(prospect_name)
    parts = full.split()
    if len(parts) < 2:
        return body
    surname = parts[-1]
    if not surname:
        return body
    first = _compact(first_name)
    if not first:
        first = parts[0]
    return re.sub(
        rf"^(Hi|Hello)\s+{re.escape(first)}\s*,\s*{re.escape(surname)}\s*,\s*",
        rf"\1 {first}, ",
        body,
        flags=re.IGNORECASE,
    )


def _strip_double_greeting_prefix(text: str, *, first_name: str) -> str:
    body = _compact(text)
    if not body:
        return body
    first = _compact(first_name) or "there"
    return re.sub(
        rf"^(Hi|Hello|Hey)\s+{re.escape(first)}\s*,\s*(Hi|Hello|Hey)(?:\s+{re.escape(first)})?\s*,?\s*",
        rf"\1 {first}, ",
        body,
        flags=re.IGNORECASE,
    )


def _proof_dump_tokens(sentence: str) -> list[str]:
    tokens = _PROOF_DUMP_TOKEN_RE.findall(sentence)
    return [token for token in tokens if token not in _PROOF_DUMP_COMMON_CAPS and len(token) >= 3]


def _defuse_proof_dump_sentence(sentence: str, *, protected_tokens: set[str]) -> str:
    working = sentence
    for _ in range(8):
        tokens = _proof_dump_tokens(working)
        if len(tokens) <= 3:
            return working
        changed = False
        for token in reversed(tokens):
            if token.lower() in protected_tokens:
                continue
            replaced = re.sub(rf"\b{re.escape(token)}\b", token.lower(), working, count=1)
            if replaced != working:
                working = replaced
                changed = True
                break
        if not changed:
            break
    return working


def _sanitize_proof_dump_bursts(text: str, *, prospect_name: str, first_name: str) -> str:
    body = _compact(text)
    if not body:
        return body
    protected: set[str] = set()
    first = _compact(first_name)
    if first:
        protected.add(first.lower())
    full = _compact(prospect_name)
    if full:
        for part in full.split():
            protected.add(part.lower())
    out: list[str] = []
    for sentence in split_sentences(body):
        out.append(_defuse_proof_dump_sentence(sentence, protected_tokens=protected))
    sanitized = " ".join(_compact(item) for item in out if _compact(item))
    sanitized = re.sub(r"\s{2,}", " ", sanitized)
    sanitized = re.sub(r"\s+([,.;!?])", r"\1", sanitized)
    return sanitized.strip()


def _fit_body_range(
    main_text: str,
    cta_line: str,
    *,
    min_words: int,
    max_words: int,
    extra_sections: list[str] | None = None,
) -> str:
    return compose_body_without_padding_loops(
        base_sentences=split_sentences(main_text),
        extra_sections=extra_sections or [],
        cta_line=cta_line,
        min_words=min_words,
        max_words=max_words,
    )


def _extra_sections_for_brevity(section_pool: list[str], brevity: int) -> list[str]:
    if brevity <= 20:
        return section_pool[:4]
    if brevity <= 40:
        return section_pool[:3]
    if brevity <= 70:
        return section_pool[:2]
    return section_pool[:2]


def _ensure_preview_greeting(main_text: str, first_name: str) -> str:
    text = _compact(main_text)
    if not text:
        return text
    expected = first_name if first_name and first_name.lower() != "there" else "there"
    return enforce_first_name_greeting(text, expected)


def _remove_banned_positioning(text: str) -> str:
    output = text
    for phrase in _BANNED_POSITIONING_PHRASES:
        output = re.sub(re.escape(phrase), "", output, flags=re.IGNORECASE)
    output = re.sub(r"\s{2,}", " ", output)
    output = re.sub(r"\s+([,.;!?])", r"\1", output)
    return output.strip()


def _normalize_subject(subject: str, fallback: str, used: set[str]) -> str:
    base = _compact(subject) or fallback
    words = _to_words(base)
    if len(words) > 8:
        base = " ".join(words[:8])
    if not base:
        base = fallback
    canonical = base.lower()
    counter = 2
    while canonical in used:
        parts = _to_words(base)
        if len(parts) >= 8:
            parts = parts[:7]
        candidate = " ".join(parts + [str(counter)]).strip()
        base = candidate or f"{fallback} {counter}"
        canonical = base.lower()
        counter += 1
    used.add(canonical)
    return base


def _normalize_tags(raw: Any, effective: WebPreviewEffectiveSliders) -> list[str]:
    tags: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            text = _compact(item)
            if not text:
                continue
            tags.append(text[:18])
    if len(tags) < 2:
        tags.extend(
            [
                "Formal" if effective.formality > 60 else "Casual",
                "Direct" if effective.directness > 60 else "Diplomatic",
                "Brief" if effective.brevity > 60 else "Detailed",
                "Personalized" if effective.personalization > 60 else "General",
            ]
        )
    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(tag[:18])
        if len(deduped) == 4:
            break
    while len(deduped) < 2:
        deduped.append("Outbound")
    return deduped[:4]


def _normalize_why(raw: Any) -> list[str]:
    bullets: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            text = _trim_words(item, 12)
            if text:
                bullets.append(text)
            if len(bullets) == 3:
                break
    defaults = [
        "Uses stated facts without overstating certainty.",
        "Matches tone through clear slider controls.",
        "Ends with one specific, low-friction CTA.",
    ]
    while len(bullets) < 3:
        bullets.append(_trim_words(defaults[len(bullets)], 12))
    return bullets[:3]


def _mock_subject(company: str, preset: WebPreviewPresetInput, index: int) -> str:
    seed = _to_words(preset.label)
    label_word = seed[0] if seed else "Preset"
    return f"{company} {label_word} angle {index + 1}"


def _mock_body(
    req: WebPresetPreviewBatchRequest,
    summary_pack: WebSummaryPack,
    preset: WebPreviewPresetInput,
    index: int,
) -> str:
    effective = _effective_sliders(req, preset)
    hook = summary_pack.hooks[index % len(summary_pack.hooks)]
    fact = summary_pack.facts[index % len(summary_pack.facts)]
    likely = summary_pack.likely_priorities[index % len(summary_pack.likely_priorities)]
    likely_clean = re.sub(r"^\(likely\)\s*", "", likely, flags=re.IGNORECASE)
    prospect_name = derive_first_name(req.prospect_first_name or req.prospect.name or "")
    proof_points = [item for item in req.product_context.proof_points if _compact(item)]
    if proof_points:
        proof_line = f"From our side, teams usually start with {proof_points[0]}"
        if len(proof_points) > 1:
            proof_line += f" and {proof_points[1]}"
        proof_line += "."
    else:
        proof_line = (
            "From our side, this is usually implemented with a lightweight rollout so reps keep control while quality stays consistent."
        )
    main = (
        f"{hook}. "
        f"One fact that stood out: {fact}. "
        f"{req.product_context.product_name} is built to {req.product_context.one_line_value}. "
        f"{proof_line} "
        f"My read is that your team may be prioritizing {likely_clean}. "
        f"The practical win is tighter control over {req.offer_lock} execution and faster team alignment."
    )
    main = sanitize_generic_ai_opener(
        main,
        research_text=req.raw_research.deep_research_paste,
        hook_strategy=req.hook_strategy,
        company=req.prospect.company,
        risk_surface=req.offer_lock,
    )
    main = _ensure_preview_greeting(main, prospect_name)
    main = _strip_post_greeting_name_fragment(
        main,
        prospect_name=req.prospect.name,
        first_name=prospect_name,
    )
    main = _strip_double_greeting_prefix(main, first_name=prospect_name)
    exec_route = _is_exec_title(req.prospect.title)
    main = _soften_offer_lock_mentions(main, req.offer_lock, force_lowercase=exec_route)
    main = _soften_company_mentions(main, req.prospect.company)
    main = _soften_proof_point_mentions(main, req.product_context.proof_points)
    _offer_domain = infer_offer_domain(req.offer_lock)
    main = _repair_prospect_offer_ownership(main, company=req.prospect.company, offer_lock=req.offer_lock)
    main = _sanitize_social_proof_phrasing(main)
    main = _sanitize_category_mismatch_terms(main, offer_domain=_offer_domain)
    main = _sanitize_proof_dump_bursts(
        main,
        prospect_name=req.prospect.name,
        first_name=prospect_name,
    )
    cta = _resolve_preview_cta(req, preset, effective)
    section_pool = long_mode_section_pool(
        company_notes=req.raw_research.company_notes,
        allowed_facts=summary_pack.facts,
        offer_lock=req.offer_lock,
        company=req.prospect.company,
    )
    extras = _extra_sections_for_brevity(section_pool, effective.brevity)
    min_words, max_words = _body_word_targets(req)
    return _fit_body_range(
        main_text=main,
        cta_line=cta,
        min_words=min_words,
        max_words=max_words,
        extra_sections=extras,
    )


def _extract_sentences(*parts: str) -> list[str]:
    sentences: list[str] = []
    for part in parts:
        text = _compact(part)
        if not text:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            candidate = _compact(sentence)
            if candidate:
                sentences.append(candidate)
    return sentences


def _mock_summary_pack(req: WebPresetPreviewBatchRequest) -> WebSummaryPack:
    research = _preprocessed_raw_research(req)
    sentences = _extract_sentences(research["deep_research_paste"], research["company_notes"])
    facts: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        if len(_to_words(sentence)) < 4:
            continue
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        facts.append(sentence)
        if len(facts) == 4:
            break

    if len(facts) < 4:
        fallback = [
            f"The research input is focused on {req.prospect.company}.",
            f"The target persona is {req.prospect.title}.",
            f"Product context includes {req.product_context.product_name}.",
            f"The requested target outcome is {req.product_context.target_outcome}.",
        ]
        for item in fallback:
            if len(facts) == 4:
                break
            if item.lower() not in seen:
                seen.add(item.lower())
                facts.append(item)

    hooks = [
        _trim_words(f"Lead with this signal: {facts[0]}", 12),
        _trim_words(f"Tie value directly to {facts[1]}", 12),
        _trim_words(f"Use a low-friction step from {facts[2]}", 12),
    ]

    likely_priorities = _ensure_likely_prefix(
        [
            f"improving {req.prospect.title} team reply quality",
            "keeping outreach relevant while scaling activity",
            f"moving quickly toward a {req.product_context.target_outcome}",
        ]
    )

    keywords_pool = [
        req.prospect.company,
        req.prospect.title,
        req.product_context.product_name,
        req.product_context.target_outcome,
        "outbound quality",
        "reply lift",
        "personalization",
        "pipeline efficiency",
    ]
    keywords: list[str] = []
    for item in keywords_pool:
        text = _compact(item)
        if not text:
            continue
        if text.lower() in {k.lower() for k in keywords}:
            continue
        keywords.append(text)
        if len(keywords) == 6:
            break
    while len(keywords) < 6:
        keywords.append(f"keyword-{len(keywords) + 1}")

    return WebSummaryPack(
        facts=facts[:4],
        hooks=hooks[:3],
        likely_priorities=likely_priorities[:3],
        keywords=keywords[:6],
    )


def _summary_cache_key(req: WebPresetPreviewBatchRequest) -> str:
    preprocessed_research = _preprocessed_raw_research(req)
    identity = {
        "prospect": req.prospect.model_dump(),
        "prospect_first_name": req.prospect_first_name,
        "product_context": req.product_context.model_dump(),
        "raw_research": preprocessed_research,
        "offer_lock": req.offer_lock,
        "cta_lock": req.cta_lock,
        "cta_lock_text": req.cta_lock_text,
        "cta_type": req.cta_type,
        "hook_strategy": req.hook_strategy,
    }
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"web_mvp:preview_summary:{digest}"


async def _load_cached_summary(req: WebPresetPreviewBatchRequest) -> WebSummaryPack | None:
    redis = get_redis()
    key = _summary_cache_key(req)
    raw = await redis.get(key)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        return WebSummaryPack.model_validate(payload)
    except Exception:
        return None


async def _save_cached_summary(req: WebPresetPreviewBatchRequest, summary_pack: WebSummaryPack) -> None:
    redis = get_redis()
    key = _summary_cache_key(req)
    await redis.setex(key, _summary_ttl(), json.dumps(summary_pack.model_dump(), separators=(",", ":")))


def _generator_messages(
    req: WebPresetPreviewBatchRequest,
    summary_pack: WebSummaryPack,
    repair_notes: list[str] | None = None,
) -> list[dict[str, str]]:
    payload = {
        "prospect": req.prospect.model_dump(),
        "product_context": req.product_context.model_dump(),
        "summary_pack": summary_pack.model_dump(),
        "global_sliders": req.global_sliders.model_dump(),
        "presets": [item.model_dump() for item in req.presets],
        "offer_lock": req.offer_lock,
        "cta_lock_text": req.cta_lock_text or req.cta_lock or "",
        "cta_type": req.cta_type,
        "hook_strategy": req.hook_strategy,
    }
    extra = ""
    if repair_notes:
        joined = "\n".join(f"- {note}" for note in repair_notes)
        extra = (
            "\n\nRepair this output:\n"
            f"{joined}\n"
            "Keep the exact JSON schema and return only one preview per preset_id."
        )
    user_prompt = (
        "INPUTS:\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}\n\n"
        "TASK:\n"
        "Generate previews for ALL presets in one response.\n"
        "Use preset_id values exactly as provided.\n"
        "Write a unique email where opener references one hook or softened likely priority.\n"
        "Only state specific facts from summary_pack.facts.\n"
        "Include 1-2 proof points when available; otherwise use a soft credibility line.\n"
        "End with exactly one CTA line.\n"
        "Return ONLY strict JSON in this exact shape:\n"
        '{"previews":[{"preset_id":"...","subject":"...","body":"..."}]}'
        f"{extra}"
    )
    return [
        {"role": "system", "content": _GENERATOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _message_chars(messages: list[dict[str, str]]) -> int:
    return sum(len(str(item.get("content") or "")) for item in messages)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    lowered = str(exc).lower()
    return "timeout" in lowered or "timed out" in lowered


def _generator_output_token_budget(req: WebPresetPreviewBatchRequest) -> int:
    per_preset_budget = 220
    return max(600, min(5000, len(req.presets) * per_preset_budget))


def _validate_generator_output(raw: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        parsed = _GeneratorPreviewOutput.model_validate(raw)
    except ValidationError as exc:
        raise RuntimeError(f"preview_output_validation_failed:{exc}") from exc
    return [item.model_dump() for item in parsed.previews]


async def _openai_structured_json(
    *,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    schema_name: str,
    model_name: str,
    transform_type: str,
    max_output_tokens: int | None = None,
    reasoning_effort_override: str | None = None,
    timeout_seconds_override: float | None = None,
    temperature_override: float | None = None,
) -> dict[str, Any]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing")

    request_timeout = timeout_seconds_override or _openai_timeout_seconds(transform_type)
    request_timeout = max(10.0, min(30.0, request_timeout))
    reasoning_effort = reasoning_effort_override or openai_reasoning_effort(
        model_name=model_name,
        transform_type=transform_type,
    )
    request_body = {
        "model": model_name,
        "messages": messages,
        "reasoning_effort": reasoning_effort,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
    }
    if max_output_tokens is not None and max_output_tokens > 0:
        request_body["max_completion_tokens"] = int(max_output_tokens)
    chosen_temperature = 0.0 if temperature_override is None else temperature_override
    if openai_supports_temperature_override(model_name):
        request_body["temperature"] = chosen_temperature
    started = time.perf_counter()
    start_iso = _now_iso()
    prompt_chars = _message_chars(messages)
    logger.debug(
        "preview_openai_request_policy",
        extra={
            "schema_name": schema_name,
            "model": model_name,
            "transform_type": transform_type,
            "reasoning_effort": reasoning_effort,
            "temperature_override": "temperature" in request_body,
            "timeout_seconds": request_timeout,
            "max_output_tokens": request_body.get("max_completion_tokens"),
            "prompt_chars": prompt_chars,
            "started_at": start_iso,
        },
    )
    try:
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=request_body,
            )
    except Exception as exc:
        outcome = "timeout" if _is_timeout_error(exc) else "error"
        logger.warning(
            "preview_openai_step_end",
            extra={
                "schema_name": schema_name,
                "model": model_name,
                "transform_type": transform_type,
                "reasoning_effort": reasoning_effort,
                "prompt_chars": prompt_chars,
                "timeout_seconds": request_timeout,
                "max_output_tokens": request_body.get("max_completion_tokens"),
                "started_at": start_iso,
                "finished_at": _now_iso(),
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "outcome": outcome,
                "error": str(exc),
            },
        )
        raise
    try:
        if response.status_code >= 400:
            raise RuntimeError(f"openai_error_{response.status_code}:{response.text[:300]}")
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("openai_empty_choices")
        message = choices[0].get("message") or {}
        if message.get("refusal"):
            raise RuntimeError("openai_model_refused")
        content = message.get("content")
        if isinstance(content, list):
            text = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        else:
            text = str(content or "")
        if not text.strip():
            raise RuntimeError("openai_empty_content")
        try:
            parsed = json.loads(text)
        except Exception as exc:  # pragma: no cover - defensive for provider drift
            raise RuntimeError(f"openai_invalid_json:{exc}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("openai_json_not_object")
    except Exception as exc:
        logger.warning(
            "preview_openai_step_end",
            extra={
                "schema_name": schema_name,
                "model": model_name,
                "transform_type": transform_type,
                "reasoning_effort": reasoning_effort,
                "prompt_chars": prompt_chars,
                "timeout_seconds": request_timeout,
                "max_output_tokens": request_body.get("max_completion_tokens"),
                "started_at": start_iso,
                "finished_at": _now_iso(),
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "outcome": "error",
                "error": str(exc),
            },
        )
        raise
    logger.info(
        "preview_openai_step_end",
        extra={
            "schema_name": schema_name,
            "model": model_name,
            "transform_type": transform_type,
            "reasoning_effort": reasoning_effort,
            "prompt_chars": prompt_chars,
            "timeout_seconds": request_timeout,
            "max_output_tokens": request_body.get("max_completion_tokens"),
            "started_at": start_iso,
            "finished_at": _now_iso(),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "outcome": "success",
        },
    )
    return parsed


async def _openai_structured_json_with_fallback(
    *,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    schema_name: str,
    model_name: str,
    transform_type: str,
    max_output_tokens: int | None = None,
    reasoning_effort_override: str | None = None,
    timeout_seconds_override: float | None = None,
    temperature_override: float | None = None,
) -> tuple[dict[str, Any], str]:
    """Call with primary model; fall back on schema/refusal error."""
    try:
        result = await _openai_structured_json(
            messages=messages,
            schema=schema,
            schema_name=schema_name,
            model_name=model_name,
            transform_type=transform_type,
            max_output_tokens=max_output_tokens,
            reasoning_effort_override=reasoning_effort_override,
            timeout_seconds_override=timeout_seconds_override,
            temperature_override=temperature_override,
        )
        return result, model_name
    except RuntimeError as exc:
        if "openai_model_refused" in str(exc) or "openai_error_400" in str(exc):
            fallback = _fallback_model()
            logger.warning(
                "preview_model_fallback_triggered",
                extra={"primary_model": model_name, "fallback_model": fallback, "reason": str(exc)},
            )
            result = await _openai_structured_json(
                messages=messages,
                schema=schema,
                schema_name=schema_name,
                model_name=fallback,
                transform_type=transform_type,
                max_output_tokens=max_output_tokens,
                reasoning_effort_override=reasoning_effort_override,
                timeout_seconds_override=timeout_seconds_override,
                temperature_override=temperature_override,
            )
            return result, fallback
        raise


def _is_cta_like_sentence(sentence: str, canonical_cta: str) -> bool:
    text = _collapse_ws(sentence).lower()
    if not text:
        return False
    canonical = _collapse_ws(canonical_cta).lower()
    if canonical and text == canonical:
        return True
    if canonical:
        ratio = SequenceMatcher(None, canonical, text).ratio()
        if ratio >= 0.82 and ("?" in text or _CTA_LINE_PATTERN.search(text)):
            return True
    return _CTA_LINE_PATTERN.search(text) is not None


def _strip_cta_lines_from_draft(draft_body: str, canonical_cta: str) -> str:
    """Remove CTA-like sentences before appending the canonical CTA line."""
    kept: list[str] = []
    for sentence in split_sentences(draft_body):
        if _is_cta_like_sentence(sentence, canonical_cta):
            continue
        kept.append(_collapse_ws(sentence))
    return " ".join(item for item in kept if item).strip()


def _violation_messages(previews: list[WebPreviewItem], req: WebPresetPreviewBatchRequest) -> list[str]:
    violations: list[str] = []
    seen_subjects: set[str] = set()
    expected_first_name = derive_first_name(req.prospect_first_name or req.prospect.name or "")
    preset_by_id = {str(preset.preset_id): preset for preset in req.presets}
    min_words, max_words = _body_word_targets(req)

    offer_lock_lower = _collapse_ws(req.offer_lock).lower()
    approved_claim_source = merge_claim_sources(
        [
            req.raw_research.deep_research_paste,
            req.raw_research.company_notes or "",
            " ".join(req.product_context.proof_points),
            req.offer_lock,
            req.product_context.product_name,
        ]
    )
    allowed_numeric_claims = extract_allowed_numeric_claims(req.raw_research.company_notes)
    allowed_leakage_text = _collapse_ws(
        " ".join([req.offer_lock, req.product_context.product_name, req.prospect.company, req.prospect.name])
    ).lower()
    research_has_ai_phrase = (
        re.search(
            r"scales\s+(?:its|their)\s+(?:enterprise\s+)?ai\s+initiatives",
            req.raw_research.deep_research_paste,
            flags=re.IGNORECASE,
        )
        is not None
    )

    for item in previews:
        # --- Format / length checks (existing) ---
        subject_words = len(_to_words(item.subject))
        if subject_words > 8:
            violations.append(f"{item.preset_id}: subject exceeds 8 words")
        key = item.subject.lower()
        if key in seen_subjects:
            violations.append(f"{item.preset_id}: subject is not unique")
        seen_subjects.add(key)
        body_words = len(_to_words(item.body))
        if body_words < min_words or body_words > max_words:
            violations.append(f"{item.preset_id}: body word count outside {min_words}-{max_words}")
        if len(item.whyItWorks) != 3:
            violations.append(f"{item.preset_id}: whyItWorks count not equal to 3")
        for bullet in item.whyItWorks:
            if len(_to_words(bullet)) > 12:
                violations.append(f"{item.preset_id}: whyItWorks bullet exceeds 12 words")
                break
        if not (2 <= len(item.vibeTags) <= 4):
            violations.append(f"{item.preset_id}: vibeTags count outside 2-4")
        for tag in item.vibeTags:
            if len(tag) > 18:
                violations.append(f"{item.preset_id}: vibeTag exceeds 18 characters")
                break

        # --- CTCO-aligned checks (Batch 3 P2) ---
        body_lower = _collapse_ws(item.body).lower()
        body_lines = [_collapse_ws(line) for line in item.body.splitlines() if line.strip()]
        first_line = body_lines[0] if body_lines else ""

        if expected_first_name and expected_first_name.lower() != "there":
            greeting_match = re.match(r"^(Hi|Hello)\s+([^,\n]+),", first_line)
            if greeting_match is None:
                violations.append(f"{item.preset_id}: greeting_missing_or_invalid")
            else:
                greeted_name = _collapse_ws(greeting_match.group(2))
                if greeted_name.lower() != expected_first_name.lower():
                    violations.append(f"{item.preset_id}: greeting_first_name_mismatch")
                if " " in greeted_name:
                    violations.append(f"{item.preset_id}: greeting_not_first_name_only")

        # Offer lock must appear in body
        if offer_lock_lower and offer_lock_lower not in body_lower:
            violations.append(f"{item.preset_id}: offer_lock_missing")

        # CTA lock must appear exactly once as a standalone line
        preset = preset_by_id.get(str(item.preset_id))
        expected_cta = _collapse_ws(req.cta_lock_text or req.cta_lock or "")
        if preset is not None:
            expected_cta = _collapse_ws(_resolve_preview_cta(req, preset, item.effective_sliders))
        cta_matches = sum(1 for line in body_lines if line == expected_cta)
        if cta_matches != 1:
            violations.append(f"{item.preset_id}: cta_lock_not_used_exactly_once")

        # Leakage terms
        for term in _NO_LEAKAGE_TERMS:
            if term in allowed_leakage_text:
                continue
            if _contains_term(body_lower, term):
                violations.append(f"{item.preset_id}: internal_leakage_term:{term}")
                break

        for phrase in _BANNED_POSITIONING_PHRASES:
            if phrase in body_lower:
                violations.append(f"{item.preset_id}: banned_phrase:{phrase}")

        if _GENERIC_AI_OPENER_PATTERN.search(first_line) and not (
            research_has_ai_phrase and (req.hook_strategy or "").strip().lower() == "research_anchored"
        ):
            violations.append(f"{item.preset_id}: banned_generic_ai_opener")

        # Cash-equivalent CTA
        if _CASH_CTA_PATTERN.search(body_lower):
            violations.append(f"{item.preset_id}: cash_equivalent_cta_detected")

        claim_surfaces = {
            "subject": item.subject,
            "body": item.body,
            "why_it_works": " ".join(item.whyItWorks),
            "vibe": " ".join([item.vibeLabel, *item.vibeTags]),
        }
        for surface, surface_text in claim_surfaces.items():
            for claim in find_unverified_claims(
                surface_text,
                approved_claim_source,
                allowed_numeric_claims=allowed_numeric_claims,
            ):
                if re.search(r"\d|%|rate|marketplace|accuracy|compliance|x", claim, re.IGNORECASE):
                    violations.append(f"{item.preset_id}: unsubstantiated_statistical_claim:{surface}")
                else:
                    violations.append(f"{item.preset_id}: unsubstantiated_claim:{surface}:{claim[:60]}")

        # Unsubstantiated guaranteed/proven claims
        for match in _GUARANTEED_CLAIM_PATTERN.finditer(body_lower):
            claim = _collapse_ws(match.group(0))
            if claim and claim not in approved_claim_source:
                violations.append(f"{item.preset_id}: unsubstantiated_claim:{claim[:60]}")
                break

        # Unsubstantiated stat claims (%, Nx)
        for match in _STAT_CLAIM_PATTERN.finditer(body_lower):
            claim = _collapse_ws(match.group(0))
            if claim and claim not in approved_claim_source:
                violations.append(f"{item.preset_id}: unsubstantiated_claim:{claim[:60]}")
                break

        # Unsubstantiated absolute revenue claims
        for match in _ABSOLUTE_REVENUE_PATTERN.finditer(body_lower):
            claim = _collapse_ws(match.group(0))
            if claim and claim not in approved_claim_source:
                violations.append(f"{item.preset_id}: unsubstantiated_claim:{claim[:60]}")
                break

        # Signoff must not appear before the final CTA line
        body_sentences = split_sentences(item.body)
        for sent in body_sentences[:-1]:  # all except last (CTA)
            if any(p.search(sent) for p in _GENERIC_CLOSER_PATTERNS):
                violations.append(f"{item.preset_id}: signoff_before_cta")
                break

    return violations


def _normalize_preview_items(
    *,
    req: WebPresetPreviewBatchRequest,
    summary_pack: WebSummaryPack,
    raw_items: list[dict[str, Any]],
) -> list[WebPreviewItem]:
    by_id: dict[str, dict[str, Any]] = {}
    by_label: dict[str, dict[str, Any]] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        preset_id = _compact(item.get("preset_id"))
        label = _compact(item.get("label"))
        if preset_id and preset_id not in by_id:
            by_id[preset_id] = item
        if label and label.lower() not in by_label:
            by_label[label.lower()] = item

    used_subjects: set[str] = set()
    previews: list[WebPreviewItem] = []
    claim_source = merge_claim_sources(
        [
            req.raw_research.deep_research_paste,
            req.raw_research.company_notes or "",
            " ".join(req.product_context.proof_points),
            " ".join(summary_pack.facts),
            req.offer_lock,
        ]
    )
    allowed_numeric_claims = extract_allowed_numeric_claims(req.raw_research.company_notes)
    preview_first_name = derive_first_name(req.prospect_first_name or req.prospect.name or "")
    min_words, max_words = _body_word_targets(req)
    exec_route = _is_exec_title(req.prospect.title)
    for index, preset in enumerate(req.presets):
        source = by_id.get(str(preset.preset_id)) or by_label.get(preset.label.lower()) or {}
        effective = _effective_sliders(req, preset)
        fallback_subject = _mock_subject(req.prospect.company or "Account", preset, index)
        subject = _normalize_subject(_compact(source.get("subject")), fallback_subject, used_subjects)
        subject = rewrite_unverified_claims(
            subject,
            claim_source,
            allowed_numeric_claims=allowed_numeric_claims,
        )
        cta = _resolve_preview_cta(req, preset, effective)
        draft_body = _compact(source.get("body")) or _mock_body(req, summary_pack, preset, index)
        draft_body = _remove_banned_positioning(draft_body)
        draft_body = sanitize_generic_ai_opener(
            draft_body,
            research_text=req.raw_research.deep_research_paste,
            hook_strategy=req.hook_strategy,
            company=req.prospect.company,
            risk_surface=req.offer_lock,
        )
        draft_body = _ensure_preview_greeting(draft_body, preview_first_name)
        draft_body = _strip_post_greeting_name_fragment(
            draft_body,
            prospect_name=req.prospect.name,
            first_name=preview_first_name,
        )
        draft_body = _strip_double_greeting_prefix(draft_body, first_name=preview_first_name)
        draft_body = _soften_offer_lock_mentions(draft_body, req.offer_lock, force_lowercase=exec_route)
        draft_body = _soften_company_mentions(draft_body, req.prospect.company)
        draft_body = _soften_proof_point_mentions(draft_body, req.product_context.proof_points)
        _offer_domain = infer_offer_domain(req.offer_lock)
        draft_body = _repair_prospect_offer_ownership(draft_body, company=req.prospect.company, offer_lock=req.offer_lock)
        draft_body = _sanitize_social_proof_phrasing(draft_body)
        draft_body = _sanitize_category_mismatch_terms(draft_body, offer_domain=_offer_domain)
        draft_body = _sanitize_proof_dump_bursts(
            draft_body,
            prospect_name=req.prospect.name,
            first_name=preview_first_name,
        )
        draft_body = rewrite_unverified_claims(
            draft_body,
            claim_source,
            allowed_numeric_claims=allowed_numeric_claims,
        )
        draft_body = remove_generic_closers(draft_body)  # strip signoffs before CTA append
        draft_body = _strip_cta_lines_from_draft(draft_body, cta)  # prevent double CTA
        section_pool = long_mode_section_pool(
            company_notes=req.raw_research.company_notes,
            allowed_facts=summary_pack.facts,
            offer_lock=req.offer_lock,
            company=req.prospect.company,
        )
        extras = _extra_sections_for_brevity(section_pool, effective.brevity)
        extras = [
            rewrite_unverified_claims(
                section,
                claim_source,
                allowed_numeric_claims=allowed_numeric_claims,
            )
            for section in extras
        ]
        body = _fit_body_range(
            main_text=draft_body,
            cta_line=cta,
            min_words=min_words,
            max_words=max_words,
            extra_sections=extras,
        )
        vibe_label = rewrite_unverified_claims(
            _compact(source.get("vibeLabel")) or preset.label,
            claim_source,
            allowed_numeric_claims=allowed_numeric_claims,
        )
        vibe_tags = [
            rewrite_unverified_claims(tag, claim_source, allowed_numeric_claims=allowed_numeric_claims)
            for tag in _normalize_tags(source.get("vibeTags"), effective)
        ]
        why_items = [
            rewrite_unverified_claims(item, claim_source, allowed_numeric_claims=allowed_numeric_claims)
            for item in _normalize_why(source.get("whyItWorks"))
        ]

        preview = WebPreviewItem(
            preset_id=str(preset.preset_id),
            label=preset.label,
            effective_sliders=effective,
            vibeLabel=vibe_label,
            vibeTags=vibe_tags,
            whyItWorks=why_items,
            subject=subject,
            body=body,
        )
        previews.append(preview)
    return previews


def _mock_previews(req: WebPresetPreviewBatchRequest, summary_pack: WebSummaryPack) -> list[WebPreviewItem]:
    return _normalize_preview_items(req=req, summary_pack=summary_pack, raw_items=[])


async def _generate_raw_preview_items(
    *,
    req: WebPresetPreviewBatchRequest,
    summary_pack: WebSummaryPack,
    repair_enabled: bool,
    throttled: bool,
) -> tuple[list[dict[str, Any]], str, int, int, int, bool]:
    provider_attempt_count = 1
    validator_attempt_count = 1
    repair_attempt_count = 0
    repaired = False
    model_name = _generator_model()

    messages = _generator_messages(req, summary_pack)
    raw, model_name = await _openai_structured_json_with_fallback(
        messages=messages,
        schema=_GENERATOR_SCHEMA,
        schema_name="preset_preview_batch",
        model_name=model_name,
        transform_type="rendering",
        max_output_tokens=_generator_output_token_budget(req),
    )
    try:
        raw_items = _validate_generator_output(raw)
        return (
            raw_items,
            model_name,
            provider_attempt_count,
            validator_attempt_count,
            repair_attempt_count,
            repaired,
        )
    except RuntimeError as exc:
        if "preview_output_validation_failed" not in str(exc) or throttled or not repair_enabled:
            raise
        repair_attempt_count = 1
        repaired = True
        provider_attempt_count += 1
        validator_attempt_count += 1
        repair_notes = [
            "Schema validation failed. Return strict JSON only.",
            "Each item must include only preset_id, subject, and body.",
        ]
        repaired_raw, model_name = await _openai_structured_json_with_fallback(
            messages=_generator_messages(req, summary_pack, repair_notes=repair_notes),
            schema=_GENERATOR_SCHEMA,
            schema_name="preset_preview_batch_repair",
            model_name=model_name,
            transform_type="rewrite",
            max_output_tokens=400,
            reasoning_effort_override="low",
            timeout_seconds_override=30.0,
            temperature_override=0.0,
        )
        repaired_items = _validate_generator_output(repaired_raw)
        return (
            repaired_items,
            model_name,
            provider_attempt_count,
            validator_attempt_count,
            repair_attempt_count,
            repaired,
        )


async def run_preview_pipeline(req: WebPresetPreviewBatchRequest, throttled: bool = False) -> PipelineResult:
    started = time.perf_counter()
    mode = _quick_mode()
    enforcement_level = os.environ.get(_PREVIEW_ENFORCEMENT_LEVEL_ENV, "warn").strip().lower() or "warn"
    repair_enabled = repair_loop_enabled()
    cache_hit = False
    provider = "mock"
    model_name = "mock"
    provider_attempt_count = 0
    validator_attempt_count = 0
    repair_attempt_count = 0
    repaired = False
    initial_violation_count = 0
    final_violation_count = 0
    status = "success"
    degraded_reason: str | None = None

    summary_pack = await _load_cached_summary(req)
    if summary_pack is not None:
        cache_hit = True
    else:
        summary_pack = _mock_summary_pack(req)
        await _save_cached_summary(req, summary_pack)

    all_violations: list[str] = []
    previews: list[WebPreviewItem]
    final_violations: list[str]

    if mode == "real":
        provider = "openai"
        try:
            (
                raw_items,
                model_name,
                provider_attempt_count,
                validator_attempt_count,
                repair_attempt_count,
                repaired,
            ) = await _generate_raw_preview_items(
                req=req,
                summary_pack=summary_pack,
                repair_enabled=repair_enabled,
                throttled=throttled,
            )
            previews = _normalize_preview_items(
                req=req,
                summary_pack=summary_pack,
                raw_items=raw_items,
            )
        except Exception as exc:
            provider_attempt_count = max(provider_attempt_count, 1)
            validator_attempt_count = max(validator_attempt_count, 1)
            status = "degraded"
            degraded_reason = "timeout" if _is_timeout_error(exc) else "provider_error"
            logger.warning(
                "preview_generation_degraded",
                extra={
                    "reason": degraded_reason,
                    "error": str(exc),
                    "model": model_name,
                    "started_at": _now_iso(),
                },
            )
            previews = _mock_previews(req, summary_pack)
    else:
        previews = _mock_previews(req, summary_pack)

    violations = _violation_messages(previews, req)
    initial_violation_count = len(violations)
    all_violations.extend(violations)
    final_violations = violations

    if (
        violations
        and mode == "real"
        and status == "success"
        and enforcement_level == "repair"
        and repair_enabled
        and not throttled
    ):
        try:
            repair_attempt_count += 1
            repaired = True
            provider_attempt_count += 1
            validator_attempt_count += 1
            repaired_raw, model_name = await _openai_structured_json_with_fallback(
                messages=_generator_messages(req, summary_pack, repair_notes=violations[:10]),
                schema=_GENERATOR_SCHEMA,
                schema_name="preset_preview_batch_compliance_repair",
                model_name=model_name,
                transform_type="rewrite",
                max_output_tokens=400,
                reasoning_effort_override="low",
                timeout_seconds_override=30.0,
                temperature_override=0.0,
            )
            repaired_items = _validate_generator_output(repaired_raw)
            previews = _normalize_preview_items(
                req=req,
                summary_pack=summary_pack,
                raw_items=repaired_items,
            )
            final_violations = _violation_messages(previews, req)
            all_violations.extend(final_violations)
        except Exception as exc:
            status = "degraded"
            degraded_reason = "timeout" if _is_timeout_error(exc) else "repair_error"
            logger.warning(
                "preview_compliance_repair_degraded",
                extra={
                    "reason": degraded_reason,
                    "error": str(exc),
                    "model": model_name,
                },
            )
            previews = _mock_previews(req, summary_pack)
            final_violations = _violation_messages(previews, req)
            all_violations.extend(final_violations)

    if final_violations and enforcement_level in {"repair", "block"}:
        status = "degraded"
        degraded_reason = degraded_reason or "validation_failed"
        previews = _mock_previews(req, summary_pack)
        final_violations = _violation_messages(previews, req)
        all_violations.extend(final_violations)
        logger.warning(
            "preview_validation_degraded",
            extra={
                "reason": degraded_reason,
                "enforcement_level": enforcement_level,
                "violation_count": len(final_violations),
            },
        )

    final_violation_count = len(final_violations)

    latency_ms = int((time.perf_counter() - started) * 1000)
    return PipelineResult(
        previews=previews,
        summary_pack=summary_pack,
        mode=mode,
        cache_hit=cache_hit,
        provider=provider,
        model_name=model_name,
        provider_attempt_count=provider_attempt_count,
        validator_attempt_count=validator_attempt_count,
        repair_attempt_count=repair_attempt_count,
        repaired=repaired,
        initial_violation_count=initial_violation_count,
        final_violation_count=final_violation_count,
        latency_ms=latency_ms,
        violations=all_violations,
        violation_codes=_violation_codes(all_violations),
        violation_count=len(all_violations),
        enforcement_level=enforcement_level,
        repair_loop_enabled=repair_enabled,
        status=status,
        degraded_reason=degraded_reason,
    )


def make_response(
    result: PipelineResult,
    *,
    request_id: str | None = None,
    session_id: str | None = None,
    flags_effective: dict[str, bool] | None = None,
    prompt_template_versions: dict[str, Any] | None = None,
    execution_trace: dict[str, Any] | None = None,
) -> WebPresetPreviewBatchResponse:
    return WebPresetPreviewBatchResponse(
        previews=result.previews,
        meta=WebPreviewBatchMeta(
            request_id=request_id,
            session_id=session_id,
            pipeline_version=PIPELINE_VERSION,
            generation_mode=result.mode,
            provider=result.provider,
            model=result.model_name,
            provider_attempt_count=result.provider_attempt_count,
            validator_attempt_count=result.validator_attempt_count,
            repair_attempt_count=result.repair_attempt_count,
            repaired=result.repaired,
            initial_violation_count=result.initial_violation_count,
            final_violation_count=result.final_violation_count,
            violation_codes=result.violation_codes,
            violation_count=result.violation_count,
            enforcement_level=result.enforcement_level,
            repair_loop_enabled=result.repair_loop_enabled,
            status=result.status,
            degraded_reason=result.degraded_reason,
            cache_hit=result.cache_hit,
            latency_ms=result.latency_ms,
            flags_effective=flags_effective,
            prompt_template_versions=prompt_template_versions,
            execution_trace=execution_trace,
        ),
        summary_pack=result.summary_pack if _include_summary_pack() else None,
    )
