"""Deterministic generation-plan IR and rendering transforms."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from email_generation.claim_verifier import (
    extract_allowed_numeric_claims,
    merge_claim_sources,
    rewrite_unverified_claims,
)
from email_generation.cta_templates import render_cta
from email_generation.output_enforcement import (
    cap_repeated_ngrams,
    compose_body_without_padding_loops,
    dedupe_sentence_list,
    derive_first_name,
    enforce_first_name_greeting,
    long_mode_section_pool,
    sanitize_generic_ai_opener,
    split_sentences,
)
from email_generation.preset_strategies import PresetStrategy, get_preset_strategy, normalize_preset_id
from email_generation.text_postprocess import enforce_information_density


_CONTRACTIONS = {
    "do not": "don't",
    "does not": "doesn't",
    "cannot": "can't",
    "we are": "we're",
    "we will": "we'll",
    "you are": "you're",
    "it is": "it's",
}
_EXPANSIONS = {value: key for key, value in _CONTRACTIONS.items()}
_FORMAL_VOCAB = {
    "quick": "brief",
    "help": "support",
    "show": "share",
    "fix": "address",
}
_CASUAL_VOCAB = {
    "support": "help",
    "share": "show",
    "address": "fix",
    "brief": "quick",
}

_BANNED_POSITIONING_PHRASES = [
    "ai services",
    "ai consulting",
    "we build ai",
    "ai transformation services",
]

_ADDITIONAL_BANNED = [
    "pipeline outcomes",
    "reply lift",
    "conversion lift",
    "measurable results",
]

def _compact(value: str | None) -> str:
    return " ".join(str(value or "").split())


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def _split_lines_catalog(raw: str | None, limit: int = 3) -> list[str]:
    if not raw:
        return []
    values: list[str] = []
    seen: set[str] = set()
    for line in str(raw).splitlines():
        for item in re.split(r"[,;|]", line):
            cleaned = _compact(item.strip(" -*\t"))
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            values.append(cleaned)
            if len(values) >= limit:
                return values
    return values


def _forbidden_product_terms(session: dict[str, Any], offer_lock: str) -> list[str]:
    company_context = session.get("company_context") or {}
    terms = _split_lines_catalog(company_context.get("other_products"), limit=8)
    forbidden: list[str] = []
    for term in terms:
        key = _compact(term).lower()
        if not key or key == _compact(offer_lock).lower():
            continue
        forbidden.append(term)
    return forbidden


def _first_sentence(text: str) -> str:
    value = _compact(text)
    if not value:
        return ""
    chunks = re.split(r"(?<=[.!?])\s+", value)
    return chunks[0].strip().rstrip(".")


def _normalize_sentence(text: str) -> str:
    value = _compact(text).strip()
    if not value:
        return ""
    if value[-1] not in ".!?":
        value += "."
    return value


def _apply_vocab(sentence: str, mapping: dict[str, str]) -> str:
    output = sentence
    for src, dst in mapping.items():
        output = re.sub(rf"\b{re.escape(src)}\b", dst, output, flags=re.IGNORECASE)
    return output


def _apply_contractions(sentence: str, *, use_contractions: bool) -> str:
    mapping = _CONTRACTIONS if use_contractions else _EXPANSIONS
    output = sentence
    for src, dst in mapping.items():
        output = re.sub(rf"\b{re.escape(src)}\b", dst, output, flags=re.IGNORECASE)
    return output


def _length_target(length_slider: int) -> tuple[int, int, int]:
    if length_slider <= 33:
        return 55, 75, 2
    if length_slider <= 66:
        return 75, 110, 3
    return 110, 160, 5


def _subject_fallback(strategy: PresetStrategy, company: str, offer_lock: str) -> str:
    templates = {
        "straight_shooter": f"{offer_lock} for {company}",
        "headliner": f"{company}: one gap to close",
        "giver": f"Quick teardown for {company}",
        "challenger": f"Hidden cost in {company} outreach",
        "industry_insider": f"A pattern we see in {company}",
        "c_suite_sniper": f"{company} outbound risk brief",
    }
    return templates.get(strategy.preset_id, f"{offer_lock} for {company}")


def _trim_subject(subject: str, max_words: int = 8) -> str:
    words = re.findall(r"\S+", _compact(subject))
    if not words:
        return ""
    return " ".join(words[:max_words])


@dataclass
class GenerationPlan:
    greeting: str
    hook_type: str
    hook_strategy: str
    wedge_problem: str
    wedge_outcome: str
    proof_points_used: list[str]
    objection_guardrails: list[str]
    tone_style: dict[str, Any]
    length_target: dict[str, int]
    cta_type: str
    banned_phrases: list[str]
    problem_outcome_balance: str
    preset_id: str
    structure_template: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "GenerationPlan | None":
        if not isinstance(raw, dict):
            return None
        required = {
            "greeting",
            "hook_type",
            "hook_strategy",
            "wedge_problem",
            "wedge_outcome",
            "proof_points_used",
            "objection_guardrails",
            "tone_style",
            "length_target",
            "cta_type",
            "banned_phrases",
            "problem_outcome_balance",
            "preset_id",
            "structure_template",
        }
        if not required.issubset(raw.keys()):
            return None
        try:
            return cls(
                greeting=str(raw["greeting"]),
                hook_type=str(raw["hook_type"]),
                hook_strategy=str(raw["hook_strategy"]),
                wedge_problem=str(raw["wedge_problem"]),
                wedge_outcome=str(raw["wedge_outcome"]),
                proof_points_used=[str(item) for item in list(raw.get("proof_points_used") or [])][:3],
                objection_guardrails=[str(item) for item in list(raw.get("objection_guardrails") or [])][:4],
                tone_style=dict(raw.get("tone_style") or {}),
                length_target=dict(raw.get("length_target") or {}),
                cta_type=str(raw["cta_type"]),
                banned_phrases=[str(item).lower() for item in list(raw.get("banned_phrases") or [])],
                problem_outcome_balance=str(raw["problem_outcome_balance"]),
                preset_id=normalize_preset_id(str(raw["preset_id"])),
                structure_template=[str(item) for item in list(raw.get("structure_template") or []) if item][:6],
            )
        except Exception:
            return None


def build_generation_plan(
    *,
    session: dict[str, Any],
    style_sliders: dict[str, int],
    preset_id: str | None = None,
    cta_type: str | None = None,
) -> GenerationPlan:
    strategy = get_preset_strategy(preset_id or session.get("preset_id"))
    prospect = session.get("prospect") or {}
    company = _compact(prospect.get("company")) or "your team"
    first_name = derive_first_name(session.get("prospect_first_name") or prospect.get("name"))
    greeting_base = "Hello" if style_sliders.get("tone_formal_casual", 50) <= 33 else "Hi"
    greeting = f"{greeting_base} {first_name or 'there'},"

    allowed_facts = [item for item in (session.get("allowed_facts") or []) if _compact(item)]
    first_fact = _first_sentence(allowed_facts[0]) if allowed_facts else ""
    second_fact = _first_sentence(allowed_facts[1]) if len(allowed_facts) > 1 else ""
    offer_lock = _compact(session.get("offer_lock")) or "this approach"

    proof_points = _split_lines_catalog((session.get("company_context") or {}).get("company_notes"), limit=3)
    if not proof_points and second_fact:
        proof_points = [second_fact]

    wedge_problem = (
        first_fact
        or f"{company} teams often lose replies when first-touch messaging lacks clear enforcement discipline"
    )
    wedge_outcome = f"{offer_lock} helps teams keep outreach specific while raising quality from first touch"

    formality = style_sliders.get("tone_formal_casual", 50)
    stance = style_sliders.get("stance_bold_diplomatic", 50)
    framing = style_sliders.get("framing_problem_outcome", 50)
    min_words, max_words, sentence_budget = _length_target(style_sliders.get("length_short_long", 50))
    if strategy.preset_id == "c_suite_sniper":
        sentence_budget = 2

    tone_style = {
        "use_contractions": formality >= 67,
        "formality_band": "formal" if formality <= 33 else "casual" if formality >= 67 else "neutral",
        "directness_band": "bold" if stance <= 33 else "diplomatic" if stance >= 67 else "balanced",
        "sentence_budget": sentence_budget,
    }
    balance = "problem_first" if framing <= 33 else "outcome_first" if framing >= 67 else "balanced"

    selected_cta_type = cta_type or strategy.cta_type
    requested_hook_strategy = _compact(session.get("hook_strategy"))
    if requested_hook_strategy not in {"research_anchored", "risk_framed", "domain_hook", "outcome_hook"}:
        requested_hook_strategy = {
            "contrarian_risk": "risk_framed",
            "executive_brief": "risk_framed",
            "domain_pattern": "domain_hook",
            "value_first": "outcome_hook",
            "curiosity_headline": "outcome_hook",
        }.get(strategy.hook_type, "domain_hook")

    return GenerationPlan(
        greeting=greeting,
        hook_type=strategy.hook_type,
        hook_strategy=requested_hook_strategy,
        wedge_problem=_normalize_sentence(wedge_problem),
        wedge_outcome=_normalize_sentence(wedge_outcome),
        proof_points_used=[_normalize_sentence(item) for item in proof_points if _compact(item)][:3],
        objection_guardrails=[
            "No unverified metrics or absolute guarantees.",
            "Pitch only offer_lock and approved positioning.",
            "Use first-name greeting when available.",
        ],
        tone_style=tone_style,
        length_target={"min_words": min_words, "max_words": max_words},
        cta_type=(selected_cta_type or "time_ask"),
        banned_phrases=[*(_BANNED_POSITIONING_PHRASES + _ADDITIONAL_BANNED)],
        problem_outcome_balance=balance,
        preset_id=strategy.preset_id,
        structure_template=list(strategy.structure_template),
    )


def _hook_sentence(plan: GenerationPlan, company: str, fact_hint: str) -> str:
    hint = fact_hint or f"{company} is under pressure to keep outreach precise without slowing execution"
    templates = {
        "direct_wedge": f"Quick point from what we saw: {hint}.",
        "curiosity_headline": f"One pattern that stood out in {company}: {hint}.",
        "value_first": f"I put together a quick teardown based on {hint}.",
        "contrarian_risk": f"Contrarian take: {hint} can hide a costly quality gap.",
        "domain_pattern": f"Pattern we keep seeing in this segment: {hint}.",
        "executive_brief": f"Executive brief: {hint}.",
    }
    return _normalize_sentence(templates.get(plan.hook_type, hint))


def _apply_tone(sentence: str, tone_style: dict[str, Any]) -> str:
    text = sentence
    band = str(tone_style.get("formality_band") or "neutral")
    if band == "formal":
        text = _apply_contractions(text, use_contractions=False)
        text = _apply_vocab(text, _FORMAL_VOCAB)
    elif band == "casual":
        text = _apply_contractions(text, use_contractions=True)
        text = _apply_vocab(text, _CASUAL_VOCAB)
    return text


def _remove_banned_phrases(text: str, banned_phrases: list[str]) -> str:
    output = text
    for phrase in banned_phrases:
        token = _compact(phrase)
        if not token:
            continue
        output = re.sub(re.escape(token), "", output, flags=re.IGNORECASE)
    output = re.sub(r"\s{2,}", " ", output)
    output = re.sub(r"\s+([,.;!?])", r"\1", output)
    return output.strip()


def apply_generation_plan(
    *,
    subject: str,
    body: str,
    session: dict[str, Any],
    style_sliders: dict[str, int],
    plan: GenerationPlan,
) -> tuple[str, str]:
    prospect = session.get("prospect") or {}
    company = _compact(prospect.get("company")) or "your team"
    offer_lock = _compact(session.get("offer_lock")) or "this approach"
    stance = style_sliders.get("stance_bold_diplomatic", 50)
    directness = max(0, min(100, 100 - stance))
    risk_surface = _compact((session.get("company_context") or {}).get("current_product")) or offer_lock
    cta_override = _compact(session.get("cta_lock_effective") or session.get("cta_offer_lock"))
    cta_line = cta_override or render_cta(
        cta_type=plan.cta_type,
        risk_surface=risk_surface,
        directness=directness,
        minutes=20 if style_sliders.get("length_short_long", 50) >= 67 else 15,
    )

    fact_hint = ""
    allowed_facts = [item for item in (session.get("allowed_facts") or []) if _compact(item)]
    if allowed_facts:
        fact_hint = _first_sentence(allowed_facts[0])
    model_signal = _first_sentence(body)
    if model_signal and re.match(r"^(Hi|Hello)\s+[^,\n]+,", model_signal):
        model_signal = re.sub(r"^(Hi|Hello)\s+[^,\n]+,\s*", "", model_signal).strip()
    if model_signal and _word_count(model_signal) >= 6:
        fact_hint = model_signal

    blocks: dict[str, str] = {
        "hook": _hook_sentence(plan, company, fact_hint),
        "problem": _normalize_sentence(plan.wedge_problem),
        "outcome": _normalize_sentence(plan.wedge_outcome),
        "proof": _normalize_sentence(plan.proof_points_used[0]) if plan.proof_points_used else "",
    }

    sequence = [item for item in plan.structure_template if item != "cta"]
    if plan.problem_outcome_balance == "problem_first":
        sequence = sorted(sequence, key=lambda item: 0 if item == "problem" else 1 if item == "outcome" else 2)
    elif plan.problem_outcome_balance == "outcome_first":
        sequence = sorted(sequence, key=lambda item: 0 if item == "outcome" else 1 if item == "problem" else 2)

    sentence_budget = int(plan.tone_style.get("sentence_budget", 3))
    parts: list[str] = []
    for key in sequence:
        sentence = _compact(blocks.get(key))
        if not sentence:
            continue
        parts.append(_apply_tone(_normalize_sentence(sentence), plan.tone_style))
        if len(parts) >= sentence_budget:
            break
    if not parts:
        parts.append(_apply_tone(_normalize_sentence(plan.wedge_outcome), plan.tone_style))

    claim_source = merge_claim_sources(
        [
            session.get("research_text_raw"),
            session.get("research_text"),
            (session.get("company_context") or {}).get("company_notes"),
            " ".join(session.get("allowed_facts") or []),
            " ".join(plan.proof_points_used),
        ]
    )
    allowed_numeric_claims = extract_allowed_numeric_claims((session.get("company_context") or {}).get("company_notes"))

    main_text = " ".join(parts)
    main_text = _remove_banned_phrases(main_text, plan.banned_phrases)
    main_text = sanitize_generic_ai_opener(
        main_text,
        research_text=session.get("research_text_raw") or session.get("research_text"),
        hook_strategy=plan.hook_strategy,
        company=company,
        risk_surface=risk_surface,
    )
    main_text = f"{plan.greeting} {main_text}".strip()
    main_text = enforce_first_name_greeting(main_text, session.get("prospect_first_name") or prospect.get("name"))
    main_text = rewrite_unverified_claims(
        main_text,
        claim_source,
        allowed_numeric_claims=allowed_numeric_claims,
    )
    main_text = enforce_information_density(main_text)

    base_sentences = cap_repeated_ngrams(dedupe_sentence_list(split_sentences(main_text)), max_count=2, min_n=3, max_n=5)
    for index, sentence in enumerate(base_sentences):
        base_sentences[index] = rewrite_unverified_claims(
            sentence,
            claim_source,
            allowed_numeric_claims=allowed_numeric_claims,
        )

    length_slider = style_sliders.get("length_short_long", 50)
    section_pool = long_mode_section_pool(
        company_notes=(session.get("company_context") or {}).get("company_notes"),
        allowed_facts=session.get("allowed_facts") or [],
        offer_lock=offer_lock,
        company=company,
    )
    proof_block = section_pool[0:1]
    mechanism_block = section_pool[1:2]
    deliverable_block = section_pool[2:3]
    risk_block = section_pool[3:4]
    if length_slider >= 85:
        extra_sections = [*proof_block, *mechanism_block, *deliverable_block, *risk_block]
    elif length_slider >= 67:
        extra_sections = [*proof_block, *mechanism_block, *deliverable_block]
    elif length_slider >= 34:
        extra_sections = [*proof_block, *mechanism_block, *deliverable_block]
    else:
        extra_sections = [*mechanism_block]
    extra_sections = [
        rewrite_unverified_claims(
            section,
            claim_source,
            allowed_numeric_claims=allowed_numeric_claims,
        )
        for section in extra_sections
    ]

    rendered_body = compose_body_without_padding_loops(
        base_sentences=base_sentences,
        extra_sections=extra_sections,
        cta_line=cta_line,
        min_words=int(plan.length_target.get("min_words", 75)),
        max_words=int(plan.length_target.get("max_words", 110)),
    )

    strategy = get_preset_strategy(plan.preset_id)
    fallback_subject = _subject_fallback(strategy, company, offer_lock)
    next_subject = _trim_subject(subject) or _trim_subject(fallback_subject)
    for forbidden in _forbidden_product_terms(session, offer_lock):
        token = _compact(forbidden)
        if token:
            next_subject = re.sub(re.escape(token), "", next_subject, flags=re.IGNORECASE)
    next_subject = re.sub(r"\s{2,}", " ", next_subject).strip(" -")
    if not next_subject:
        next_subject = _trim_subject(fallback_subject)
    next_subject = rewrite_unverified_claims(
        next_subject,
        claim_source,
        allowed_numeric_claims=allowed_numeric_claims,
    )
    return next_subject, rendered_body
