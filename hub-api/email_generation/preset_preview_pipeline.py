"""Two-call preset preview pipeline: extractor -> summary pack -> generator batch."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from api.schemas import (
    WebPresetPreviewBatchRequest,
    WebPresetPreviewBatchResponse,
    WebPreviewBatchMeta,
    WebPreviewEffectiveSliders,
    WebPreviewItem,
    WebPreviewPresetInput,
    WebSummaryPack,
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
from infra.redis_client import get_redis

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "extractor-generator-v1"

_EXTRACTOR_SYSTEM_PROMPT = """You are EmailDJ’s Research Extractor. Your job is to compress raw research into a small, high-signal summary_pack for downstream email generation.
Optimization priorities: (1) lowest tokens, (2) factual accuracy, (3) usefulness for outbound emails.
Rules:
- Only include facts that are explicitly supported by the raw research text provided.
- If something is uncertain, omit it (do not guess).
- Do not use placeholder tokens like [Name] or {Company}.
- Output MUST match the JSON schema provided (Structured Outputs / strict)."""

_GENERATOR_SYSTEM_PROMPT = """You are EmailDJ’s Preview Batch Generator. Generate send-ready outbound emails with strict CTCO compliance and cost control.
Optimization priorities: (1) CTCO compliance, (2) lowest total tokens, (3) high-quality credible copy.

HARD COMPLIANCE RULES (violations trigger regeneration):
- OFFER LOCK: Pitch ONLY the product named in offer_lock. Never mention other products or services.
- CTA LOCK: End EVERY email body with the exact text from cta_lock, used exactly once as its own line. No alternate asks.
- LEAKAGE BAN: Never output these terms: emaildj, remix, mapping, template, templates, slider, sliders, prompt, prompts, llm, llms, openai, gemini, codex, generated, automation tooling.
- GROUNDING: Only assert specific facts from summary_pack.facts. Frame all else as soft hypothesis or general pattern.
- NO CASH CTAs: Never offer gift cards, Amazon cards, prepaid cards, cash rewards, or "$X gift".
- NO FAKE STATISTICS: Do not include percentage improvements, ROI claims, or "proven"/"guaranteed" performance claims unless the exact figure appears in summary_pack.facts.
- NEVER output placeholders like [Name], [Company], {variable}. Use clean fallbacks ('Hi there,') if a value is missing.
- Do not mention you are an AI.

HARD FORMAT LIMITS:
- subject: <= 8 words
- body: 90-130 words total (including cta_lock line)
- whyItWorks: exactly 3 bullets, each <= 12 words
- vibeTags: 2-4 tags, each <= 18 characters

STYLE RULES:
- No "hope you’re well"
- No exclamation marks
- Body must end with cta_lock as its own line

Output MUST match the JSON schema (Structured Outputs / strict)."""

_EXTRACTOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary_pack": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "facts": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "string"}},
                "hooks": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "string"}},
                "likely_priorities": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "string"}},
                "keywords": {"type": "array", "minItems": 6, "maxItems": 6, "items": {"type": "string"}},
            },
            "required": ["facts", "hooks", "likely_priorities", "keywords"],
        }
    },
    "required": ["summary_pack"],
}

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
                    "label": {"type": "string"},
                    "effective_sliders": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "formality": {"type": "integer"},
                            "brevity": {"type": "integer"},
                            "directness": {"type": "integer"},
                            "personalization": {"type": "integer"},
                        },
                        "required": ["formality", "brevity", "directness", "personalization"],
                    },
                    "vibeLabel": {"type": "string"},
                    "vibeTags": {"type": "array", "minItems": 2, "maxItems": 4, "items": {"type": "string"}},
                    "whyItWorks": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "string"}},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": [
                    "preset_id",
                    "label",
                    "effective_sliders",
                    "vibeLabel",
                    "vibeTags",
                    "whyItWorks",
                    "subject",
                    "body",
                ],
            },
        }
    },
    "required": ["previews"],
}


@dataclass
class PipelineResult:
    previews: list[WebPreviewItem]
    summary_pack: WebSummaryPack
    cache_hit: bool
    provider: str
    latency_ms: int
    violations: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.violations is None:
            self.violations = []


def _compact(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _quick_mode() -> str:
    return os.environ.get("EMAILDJ_QUICK_GENERATE_MODE", "mock").strip().lower() or "mock"


def _extractor_model() -> str:
    return os.environ.get("EMAILDJ_PRESET_PREVIEW_MODEL_EXTRACTOR", "gpt-4o-mini").strip() or "gpt-4o-mini"


def _generator_model() -> str:
    return os.environ.get("EMAILDJ_PRESET_PREVIEW_MODEL_GENERATOR", "gpt-4o-mini").strip() or "gpt-4o-mini"


def _include_summary_pack() -> bool:
    return os.environ.get("EMAILDJ_PREVIEW_INCLUDE_SUMMARY_PACK", "0").strip() == "1"


def _summary_ttl() -> int:
    return _env_int("EMAILDJ_PRESET_PREVIEW_SUMMARY_CACHE_TTL_SEC", 900, 60, 3600)


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


def _fit_body_range(main_text: str, cta_line: str) -> str:
    filler = "This keeps messaging specific, credible, and easy for reps to use at scale."
    min_total = 90
    max_total = 130
    cta_words = len(_to_words(cta_line))
    main_words = _to_words(main_text)
    min_main = max(40, min_total - cta_words)
    max_main = max(80, max_total - cta_words)

    while len(main_words) < min_main:
        main_words.extend(_to_words(filler))
    if len(main_words) > max_main:
        main_words = main_words[:max_main]

    return f"{' '.join(main_words).strip()}\n\n{cta_line}".strip()


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
    hook = summary_pack.hooks[index % len(summary_pack.hooks)]
    fact = summary_pack.facts[index % len(summary_pack.facts)]
    likely = summary_pack.likely_priorities[index % len(summary_pack.likely_priorities)]
    likely_clean = re.sub(r"^\(likely\)\s*", "", likely, flags=re.IGNORECASE)
    prospect_name = req.prospect.name or "there"
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
        f"Hi {prospect_name}, {hook}. "
        f"One fact that stood out: {fact}. "
        f"{req.product_context.product_name} is built to {req.product_context.one_line_value}. "
        f"{proof_line} "
        f"My read is that your team may be prioritizing {likely_clean}. "
        f"The practical win is improving first-touch relevance without slowing execution across active sequences. "
        f"If useful, I can walk through how this maps to your current outbound motion in a concrete, low-lift way."
    )
    cta = req.cta_lock
    return _fit_body_range(main_text=main, cta_line=cta)


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
    sentences = _extract_sentences(req.raw_research.deep_research_paste, req.raw_research.company_notes or "")
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
    identity = {
        "prospect": req.prospect.model_dump(),
        "product_context": req.product_context.model_dump(),
        "raw_research": req.raw_research.model_dump(),
        "offer_lock": req.offer_lock,
        "cta_lock": req.cta_lock,
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


def _extractor_messages(req: WebPresetPreviewBatchRequest) -> list[dict[str, str]]:
    payload = {
        "prospect": req.prospect.model_dump(),
        "product_context": req.product_context.model_dump(),
        "raw_research": req.raw_research.model_dump(),
    }
    user_prompt = (
        "INPUTS (use exactly; do not invent facts):\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}\n\n"
        "TASK:\n"
        "Create a compact summary_pack for email generation:\n"
        "- facts: exactly 4 bullets, each must be directly supported by raw_research\n"
        "- hooks: exactly 3 short angles (derived from facts; no invention)\n"
        '- likely_priorities: exactly 3 bullets; may be reasonable inferences BUT must be labeled with "(likely)"\n'
        "- keywords: exactly 6 tags/phrases\n"
        "Return ONLY valid JSON."
    )
    return [
        {"role": "system", "content": _EXTRACTOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


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
        "cta_lock": req.cta_lock,
    }
    extra = ""
    if repair_notes:
        joined = "\n".join(f"- {note}" for note in repair_notes)
        extra = (
            "\n\nFix these violations in this attempt:\n"
            f"{joined}\n"
            "Do not change schema. Keep all hard limits satisfied."
        )
    user_prompt = (
        "INPUTS:\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}\n\n"
        "TASK:\n"
        "Generate previews for ALL presets in one response.\n"
        "For each preset compute effective_sliders with preset overrides applied.\n"
        "Write a unique email where opener references one hook or softened likely priority.\n"
        "Only state specific facts from summary_pack.facts.\n"
        "Include 1-2 proof points when available; otherwise use a soft credibility line.\n"
        "End with exactly one CTA line.\n"
        "Return ONLY valid JSON."
        f"{extra}"
    )
    return [
        {"role": "system", "content": _GENERATOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


async def _openai_structured_json(
    *,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    schema_name: str,
    model_name: str,
) -> dict[str, Any]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing")

    request_body = {
        "model": model_name,
        "messages": messages,
        "temperature": 0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=request_body,
        )
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
    return parsed


def _sanitize_summary_pack(raw: dict[str, Any], req: WebPresetPreviewBatchRequest) -> WebSummaryPack:
    data = raw.get("summary_pack", {}) if isinstance(raw, dict) else {}
    try:
        pack = WebSummaryPack.model_validate(data)
    except Exception:
        pack = _mock_summary_pack(req)
    pack.likely_priorities = _ensure_likely_prefix(pack.likely_priorities)
    return pack


def _violation_messages(previews: list[WebPreviewItem], req: WebPresetPreviewBatchRequest) -> list[str]:
    violations: list[str] = []
    seen_subjects: set[str] = set()

    offer_lock_lower = _collapse_ws(req.offer_lock).lower()
    cta_lock = _collapse_ws(req.cta_lock)
    research_lower = _collapse_ws(
        " ".join([req.raw_research.deep_research_paste, req.raw_research.company_notes or ""])
    ).lower()

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
        if body_words < 90 or body_words > 130:
            violations.append(f"{item.preset_id}: body word count outside 90-130")
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

        # Offer lock must appear in body
        if offer_lock_lower and offer_lock_lower not in body_lower:
            violations.append(f"{item.preset_id}: offer_lock_missing")

        # CTA lock must appear exactly once as a standalone line
        cta_matches = sum(1 for line in body_lines if line == cta_lock)
        if cta_matches != 1:
            violations.append(f"{item.preset_id}: cta_lock_not_used_exactly_once")

        # Leakage terms
        for term in _NO_LEAKAGE_TERMS:
            if _contains_term(body_lower, term):
                violations.append(f"{item.preset_id}: internal_leakage_term:{term}")
                break

        # Cash-equivalent CTA
        if _CASH_CTA_PATTERN.search(body_lower):
            violations.append(f"{item.preset_id}: cash_equivalent_cta_detected")

        # Unsubstantiated guaranteed/proven claims
        for match in _GUARANTEED_CLAIM_PATTERN.finditer(body_lower):
            claim = _collapse_ws(match.group(0))
            if claim and claim not in research_lower:
                violations.append(f"{item.preset_id}: unsubstantiated_claim:{claim[:60]}")
                break

        # Unsubstantiated stat claims (%, Nx)
        for match in _STAT_CLAIM_PATTERN.finditer(body_lower):
            claim = _collapse_ws(match.group(0))
            if claim and claim not in research_lower:
                violations.append(f"{item.preset_id}: unsubstantiated_claim:{claim[:60]}")
                break

        # Unsubstantiated absolute revenue claims
        for match in _ABSOLUTE_REVENUE_PATTERN.finditer(body_lower):
            claim = _collapse_ws(match.group(0))
            if claim and claim not in research_lower:
                violations.append(f"{item.preset_id}: unsubstantiated_claim:{claim[:60]}")
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
    for index, preset in enumerate(req.presets):
        source = by_id.get(str(preset.preset_id)) or by_label.get(preset.label.lower()) or {}
        effective = _effective_sliders(req, preset)
        fallback_subject = _mock_subject(req.prospect.company or "Account", preset, index)
        subject = _normalize_subject(_compact(source.get("subject")), fallback_subject, used_subjects)
        cta = req.cta_lock
        draft_body = _compact(source.get("body")) or _mock_body(req, summary_pack, preset, index)
        body = _fit_body_range(main_text=draft_body.replace("?", "."), cta_line=cta)

        preview = WebPreviewItem(
            preset_id=str(preset.preset_id),
            label=preset.label,
            effective_sliders=effective,
            vibeLabel=_compact(source.get("vibeLabel")) or preset.label,
            vibeTags=_normalize_tags(source.get("vibeTags"), effective),
            whyItWorks=_normalize_why(source.get("whyItWorks")),
            subject=subject,
            body=body,
        )
        previews.append(preview)
    return previews


def _mock_previews(req: WebPresetPreviewBatchRequest, summary_pack: WebSummaryPack) -> list[WebPreviewItem]:
    previews: list[WebPreviewItem] = []
    used_subjects: set[str] = set()
    for index, preset in enumerate(req.presets):
        effective = _effective_sliders(req, preset)
        subject = _normalize_subject(_mock_subject(req.prospect.company or "Account", preset, index), "Quick outbound idea", used_subjects)
        previews.append(
            WebPreviewItem(
                preset_id=str(preset.preset_id),
                label=preset.label,
                effective_sliders=effective,
                vibeLabel=preset.label,
                vibeTags=_normalize_tags([], effective),
                whyItWorks=_normalize_why([]),
                subject=subject,
                body=_mock_body(req, summary_pack, preset, index),
            )
        )
    return previews


async def run_preview_pipeline(req: WebPresetPreviewBatchRequest, throttled: bool = False) -> PipelineResult:
    started = time.perf_counter()
    cache_hit = False
    provider = "mock"

    summary_pack = await _load_cached_summary(req)
    if summary_pack is not None:
        cache_hit = True
    else:
        if _quick_mode() == "real":
            provider = "openai"
            raw = await _openai_structured_json(
                messages=_extractor_messages(req),
                schema=_EXTRACTOR_SCHEMA,
                schema_name="summary_pack_extractor",
                model_name=_extractor_model(),
            )
            summary_pack = _sanitize_summary_pack(raw, req)
        else:
            summary_pack = _mock_summary_pack(req)
        await _save_cached_summary(req, summary_pack)

    all_violations: list[str] = []

    if _quick_mode() == "real":
        provider = "openai"
        raw = await _openai_structured_json(
            messages=_generator_messages(req, summary_pack),
            schema=_GENERATOR_SCHEMA,
            schema_name="preset_preview_batch",
            model_name=_generator_model(),
        )
        raw_items = raw.get("previews", []) if isinstance(raw, dict) else []
        previews = _normalize_preview_items(req=req, summary_pack=summary_pack, raw_items=raw_items if isinstance(raw_items, list) else [])
        violations = _violation_messages(previews, req)
        all_violations.extend(violations)
        if violations and not throttled:
            repaired_raw = await _openai_structured_json(
                messages=_generator_messages(req, summary_pack, repair_notes=violations[:10]),
                schema=_GENERATOR_SCHEMA,
                schema_name="preset_preview_batch_repair",
                model_name=_generator_model(),
            )
            repaired_items = repaired_raw.get("previews", []) if isinstance(repaired_raw, dict) else []
            previews = _normalize_preview_items(
                req=req,
                summary_pack=summary_pack,
                raw_items=repaired_items if isinstance(repaired_items, list) else [],
            )
            final_violations = _violation_messages(previews, req)
            all_violations.extend(final_violations)
    else:
        previews = _mock_previews(req, summary_pack)

    latency_ms = int((time.perf_counter() - started) * 1000)
    return PipelineResult(
        previews=previews,
        summary_pack=summary_pack,
        cache_hit=cache_hit,
        provider=provider,
        latency_ms=latency_ms,
        violations=all_violations,
    )


def make_response(result: PipelineResult) -> WebPresetPreviewBatchResponse:
    return WebPresetPreviewBatchResponse(
        previews=result.previews,
        meta=WebPreviewBatchMeta(
            pipeline_version=PIPELINE_VERSION,
            provider=result.provider,
            cache_hit=result.cache_hit,
            latency_ms=result.latency_ms,
        ),
        summary_pack=result.summary_pack if _include_summary_pack() else None,
    )
