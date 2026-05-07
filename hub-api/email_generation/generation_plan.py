"""Deterministic generation-plan IR and rendering transforms."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any

from email_generation.claim_verifier import (
    extract_allowed_numeric_claims,
    merge_claim_sources,
    rewrite_unverified_claims,
)
from email_generation.offer_domain import infer_offer_domain
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
from email_generation.policies.context_policy import sanitize_company_notes_for_generation
from email_generation.preset_strategies import PresetStrategy, get_preset_strategy, normalize_preset_id
from email_generation.runtime_policies import (
    feature_preset_true_rewrite_enabled,
)
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

_CTA_LINE_PATTERN = re.compile(
    r"\b(worth a look|not a priority|open to|book|15[ -]?min|quick call|"
    r"quick chat|calendar|schedule|let me know|next step|reach out|happy to)\b",
    re.IGNORECASE,
)
_EXEC_TITLE_RE = re.compile(r"\b(ceo|chief executive officer|founder|co-founder|president)\b", re.IGNORECASE)
_BRAND_PROTECTION_TERMS = (
    "brand protection",
    "trademark",
    "counterfeit",
    "ip enforcement",
    "brand integrity",
)
_DATA_SECURITY_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bcybersecurity\b", re.IGNORECASE), "brand protection"),
    (re.compile(r"\bcyber security\b", re.IGNORECASE), "brand protection"),
    (re.compile(r"\bdata security\b", re.IGNORECASE), "brand integrity"),
    (re.compile(r"\bdata governance\b", re.IGNORECASE), "brand governance"),
    (re.compile(r"\bdigital risk\b", re.IGNORECASE), "brand risk"),
    (re.compile(r"\bdata breach(?:es)?\b", re.IGNORECASE), "brand abuse incidents"),
    (re.compile(r"\bransomware\b", re.IGNORECASE), "counterfeit abuse"),
    (re.compile(r"\bmalware\b", re.IGNORECASE), "infringement abuse"),
    (re.compile(r"\bphishing\b", re.IGNORECASE), "impersonation abuse"),
    (re.compile(r"\bendpoint protection\b", re.IGNORECASE), "brand protection"),
)
_PRESET_STRUCTURE_REWRITE: dict[str, list[str]] = {
    "straight_shooter": ["problem", "outcome", "proof", "cta"],
    "headliner": ["hook", "problem", "proof", "cta"],
    "giver": ["hook", "outcome", "proof", "cta"],
    "challenger": ["problem", "hook", "outcome", "cta"],
    "industry_insider": ["hook", "proof", "outcome", "cta"],
    "c_suite_sniper": ["outcome", "problem", "cta"],
}
_PRESET_CTA_STANDARD: dict[str, str] = {
    "straight_shooter": "calendar",
    "headliner": "curiosity",
    "giver": "async_audit",
    "challenger": "objection_friendly",
    "industry_insider": "referral",
    "c_suite_sniper": "permission",
}
_PRESET_CTA_EXEC: dict[str, str] = {
    "straight_shooter": "permission",
    "headliner": "curiosity",
    "giver": "async_audit",
    "challenger": "permission",
    "industry_insider": "referral",
    "c_suite_sniper": "calendar",
}

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


def _stable_pick(values: list[str], seed: str) -> str:
    if not values:
        return ""
    if not seed:
        return values[0]
    index = sum(ord(ch) for ch in seed) % len(values)
    return values[index]


def _contains_forbidden_term(text: str, forbidden_terms: list[str]) -> bool:
    lowered = _compact(text).lower()
    if not lowered:
        return False
    for term in forbidden_terms:
        token = _compact(term).lower()
        if not token:
            continue
        if " " in token:
            if token in lowered:
                return True
            continue
        if re.search(rf"\b{re.escape(token)}\b", lowered):
            return True
    return False


def _rewrite_forbidden_sentence(
    sentence: str,
    *,
    offer_lock: str,
    context_key: str,
    forbidden_terms: list[str],
) -> str:
    text = _compact(sentence)
    if not text:
        return ""
    if not _contains_forbidden_term(text, forbidden_terms):
        return _normalize_sentence(text)
    candidates = [
        f"{offer_lock} helps keep outreach specific while reducing execution drag.",
        "The practical goal is improving message quality without adding process overhead.",
        "Most teams start by tightening consistency before scaling volume.",
    ]
    return _normalize_sentence(_stable_pick(candidates, f"{context_key}|{offer_lock}|{text}"))


def _first_sentence(text: str) -> str:
    value = _compact(text)
    if not value:
        return ""
    chunks = re.split(r"(?<=[.!?])\s+", value)
    return chunks[0].strip().rstrip(".")


def _sanitize_fact_hint(
    fact_hint: str,
    *,
    prospect_name: str,
    company: str,
    first_name: str,
    soften_company_reference: bool = True,
) -> str:
    text = _compact(fact_hint)
    if not text:
        return ""
    full_name = _compact(prospect_name)
    first_name_key = _compact(first_name).lower()
    if full_name:
        text = re.sub(re.escape(full_name), first_name or "you", text, flags=re.IGNORECASE)
    if company and soften_company_reference:
        text = re.sub(re.escape(company), "your team", text, flags=re.IGNORECASE)
    # Remove unrelated full names that can trigger proof-dump heuristics.
    def _replace_non_prospect_name(match: re.Match[str]) -> str:
        token = _compact(match.group(0))
        if not token:
            return ""
        if first_name_key and token.split(" ", 1)[0].lower() == first_name_key:
            return token
        return "leadership"

    text = re.sub(r"\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b", _replace_non_prospect_name, text)
    return _compact(text)


def _offer_lock_sentence_case(value: str) -> str:
    cleaned = _compact(value)
    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:].lower()


def _apply_offer_lock_sentence_case(value: str, offer_lock: str) -> str:
    text = _compact(value)
    lock = _compact(offer_lock)
    if not text or not lock:
        return text
    return re.sub(
        re.escape(lock),
        _offer_lock_sentence_case(lock),
        text,
        flags=re.IGNORECASE,
    )


def _normalize_offer_category_framing(
    text: str,
    offer_lock: str,
    offer_category: str | None = None,
) -> str:
    normalized = _compact(text)
    if not normalized:
        return normalized
    # Only apply brand-protection-specific rewrites when the offer is in that domain.
    # For other sellers (HR tech, AI platform, retail, etc.) this is a no-op.
    if infer_offer_domain(offer_lock, offer_category) != "brand_protection":
        return normalized
    for pattern, replacement in _DATA_SECURITY_REWRITES:
        normalized = pattern.sub(replacement, normalized)
    return _compact(normalized)


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


def _is_exec_title(title: str | None) -> bool:
    return _EXEC_TITLE_RE.search(_compact(title)) is not None


def _default_cta_type(preset_id: str, persona_route: str) -> str:
    if persona_route == "exec":
        return _PRESET_CTA_EXEC.get(preset_id, "permission")
    return _PRESET_CTA_STANDARD.get(preset_id, "calendar")


def _preset_wedge_copy(preset_id: str, company: str, offer_lock: str) -> tuple[str, str]:
    templates = {
        "straight_shooter": (
            f"{company} teams often lose replies when first-touch messaging sounds generic.",
            f"{offer_lock} helps enforce message relevance without adding manager overhead.",
        ),
        "headliner": (
            f"A hidden gap at {company}: strong outreach volume, inconsistent first-touch quality.",
            f"{offer_lock} gives reps a tighter opening angle that keeps responses qualified.",
        ),
        "giver": (
            f"{company} likely already has enough activity; the gap is clarity in first touches.",
            f"{offer_lock} lets us share a quick async teardown so your team can test improvements immediately.",
        ),
        "challenger": (
            f"The expensive risk at {company} is not volume, it's low-signal conversations entering pipeline.",
            f"{offer_lock} reframes outreach around disqualification discipline and higher-quality replies.",
        ),
        "industry_insider": (
            f"Across teams like {company}, reply rates dip when persona triggers are not operationalized.",
            f"{offer_lock} converts trigger signals into consistent messaging patterns reps can execute quickly.",
        ),
        "c_suite_sniper": (
            f"{company} carries execution risk when outbound quality drifts across teams.",
            f"{offer_lock} reduces that risk by tightening message quality while preserving sales velocity.",
        ),
    }
    return templates.get(
        preset_id,
        (
            f"{company} teams often lose replies when first-touch messaging lacks clear enforcement discipline.",
            f"{offer_lock} helps teams keep outreach specific while raising quality from first touch.",
        ),
    )


_EVIDENCE_BAND_ORDER = {
    "contextual_inference": 0,
    "weak_signal": 1,
    "strong_signal": 2,
    "direct_evidence": 3,
}


def _evidence_band_rank(value: str | None) -> int:
    return _EVIDENCE_BAND_ORDER.get(_compact(value), 0)


def _normalize_proof_points_meta(raw: list[dict[str, Any]] | None, proof_points: list[str]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in raw or []:
        text = _normalize_sentence(str(item.get("text") or ""))
        if not text:
            continue
        normalized.append(
            {
                "text": text,
                "proof_basis": _compact(item.get("proof_basis")) or "seller_note",
            }
        )
    if normalized:
        return normalized[:3]
    return [{"text": _normalize_sentence(item), "proof_basis": "seller_note"} for item in proof_points if _compact(item)][:3]


def _banded_problem_statement(
    *,
    company: str,
    evidence_band: str,
    source_text: str,
    fact_type: str,
    fallback: str,
) -> str:
    source = _normalize_sentence(source_text)
    band = _compact(evidence_band) or "contextual_inference"
    if band == "direct_evidence" and source:
        return source
    if band == "strong_signal":
        templates = {
            "hiring": "Team growth can make message consistency harder to maintain across first touches.",
            "initiative": "New rollout work can make message quality and manager review more important.",
            "ops": "There are signs message review and execution discipline matter more right now.",
            "timeline": "Current timing pressure can make first-touch consistency harder to keep tight.",
        }
        return templates.get(fact_type, f"There are signs consistent first-touch quality matters more at {company}.")
    if band == "weak_signal":
        templates = {
            "hiring": "It may be worth tightening first-touch quality before team growth adds more drift.",
            "initiative": "It may be worth pressure-testing how consistently first touches map to current priorities.",
            "ops": "It may be worth tightening message review before quality drift becomes harder to catch.",
            "timeline": "It may be worth tightening message quality before timing pressure adds more noise.",
        }
        return templates.get(fact_type, f"It may be worth tightening first-touch quality as execution scales at {company}.")
    return fallback


def _hook_hint_for_band(plan: "GenerationPlan", company: str, fallback_hint: str) -> str:
    source = _normalize_sentence(plan.hook_source_text or fallback_hint).rstrip(".")
    fact_type = str((plan.hook_lineage or {}).get("fact_type") or "")
    band = plan.hook_evidence_band or "contextual_inference"
    if band == "direct_evidence" and source:
        return source
    if band == "strong_signal":
        templates = {
            "hiring": "team expansion can make message consistency harder to keep tight",
            "initiative": "new rollout work can put more pressure on message quality",
            "ops": "the team appears to be tightening message review and execution discipline",
            "timeline": "timing pressure can make consistent first touches harder to maintain",
        }
        return templates.get(fact_type, "there are signs message quality matters more as execution scales")
    if band == "weak_signal":
        templates = {
            "hiring": "it may be worth tightening first-touch quality before team growth adds more drift",
            "initiative": "it may be worth pressure-testing how consistently first touches map to current priorities",
            "ops": "it may be worth pressure-testing message quality before review gaps widen",
            "timeline": "it may be worth tightening message quality before timing pressure adds more noise",
        }
        return templates.get(fact_type, f"it may be worth tightening first-touch quality as execution scales at {company}")
    return f"{company} likely needs message quality to stay tight as execution scales"


def _proof_points_from_company_notes(company_notes: str | None, *, allowed_text: str = "") -> list[dict[str, str]]:
    safe_notes = sanitize_company_notes_for_generation(company_notes, allowed_text=allowed_text)
    points = _split_lines_catalog(safe_notes, limit=3)
    return [
        {
            "text": _normalize_sentence(point),
            "proof_basis": "seller_note",
        }
        for point in points
        if _compact(point)
    ][:3]


def _fact_entries_for_plan(
    *,
    session: dict[str, Any],
    company: str,
    first_name: str,
    prospect_name: str,
    soften_company_reference: bool,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw in session.get("allowed_facts_structured") or []:
        source_text = _sanitize_fact_hint(
            _first_sentence(raw.get("text", "")),
            prospect_name=prospect_name,
            company=company,
            first_name=first_name,
            soften_company_reference=soften_company_reference,
        )
        if not source_text:
            continue
        evidence_band = _compact(raw.get("evidence_band")) or "contextual_inference"
        entries.append(
            {
                "text": source_text,
                "type": _compact(raw.get("type")) or "other",
                "confidence": _compact(raw.get("confidence")) or "low",
                "evidence_band": evidence_band,
                "assertable": bool(raw.get("assertable", False)),
            }
        )
    return entries


def _select_hook_fact(fact_entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not fact_entries:
        return None
    for band in ("direct_evidence", "strong_signal", "weak_signal", "contextual_inference"):
        for entry in fact_entries:
            if entry.get("evidence_band") == band:
                return entry
    return fact_entries[0]


def _hook_signal_equivalent(candidate: str, plan: "GenerationPlan") -> bool:
    normalized = _compact(candidate)
    if not normalized:
        return False
    anchors = [
        _compact(plan.hook_source_text),
        _compact(plan.wedge_problem),
    ]
    for anchor in anchors:
        if not anchor:
            continue
        if SequenceMatcher(None, normalized.lower(), anchor.lower()).ratio() >= 0.72:
            return True
    return False


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
    persona_route: str
    hook_evidence_band: str = "contextual_inference"
    hook_source_text: str = ""
    hook_lineage: dict[str, Any] = field(default_factory=dict)
    proof_points_meta: list[dict[str, str]] = field(default_factory=list)
    required_fields: list[str] = field(default_factory=list)
    minimum_body_sections: list[str] = field(default_factory=list)
    optional_style_sections: list[str] = field(default_factory=list)

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
            "persona_route",
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
                persona_route=str(raw.get("persona_route") or "standard"),
                hook_evidence_band=str(raw.get("hook_evidence_band") or "contextual_inference"),
                hook_source_text=str(raw.get("hook_source_text") or ""),
                hook_lineage=dict(raw.get("hook_lineage") or {}),
                proof_points_meta=_normalize_proof_points_meta(raw.get("proof_points_meta"), [str(item) for item in list(raw.get("proof_points_used") or [])]),
                required_fields=[str(item) for item in list(raw.get("required_fields") or []) if str(item).strip()],
                minimum_body_sections=[str(item) for item in list(raw.get("minimum_body_sections") or []) if str(item).strip()],
                optional_style_sections=[str(item) for item in list(raw.get("optional_style_sections") or []) if str(item).strip()],
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
    title = _compact(prospect.get("title"))
    first_name = derive_first_name(session.get("prospect_first_name") or prospect.get("name"))
    greeting_base = "Hello" if style_sliders.get("tone_formal_casual", 50) <= 33 else "Hi"
    greeting = f"{greeting_base} {first_name or 'there'},"
    persona_route = "exec" if _is_exec_title(title) else "standard"
    preset_true_rewrite = feature_preset_true_rewrite_enabled()

    allowed_facts = [item for item in (session.get("allowed_facts") or []) if _compact(item)]
    prospect_name = str(prospect.get("name") or "")
    fact_entries = _fact_entries_for_plan(
        session=session,
        company=company,
        first_name=first_name or "you",
        prospect_name=prospect_name,
        soften_company_reference=persona_route != "exec",
    )
    hook_fact = _select_hook_fact(fact_entries)
    high_conf_facts = [entry["text"] for entry in fact_entries if str(entry.get("confidence") or "").lower() == "high"]
    first_fact = (
        _sanitize_fact_hint(
            _first_sentence(allowed_facts[0]),
            prospect_name=prospect_name,
            company=company,
            first_name=first_name or "you",
            soften_company_reference=persona_route != "exec",
        )
        if allowed_facts
        else ""
    )
    second_fact = (
        _sanitize_fact_hint(
            _first_sentence(allowed_facts[1]),
            prospect_name=prospect_name,
            company=company,
            first_name=first_name or "you",
            soften_company_reference=persona_route != "exec",
        )
        if len(allowed_facts) > 1
        else ""
    )
    offer_lock = _compact(session.get("offer_lock")) or "this approach"

    company_context = session.get("company_context") or {}
    seller_name = _compact(company_context.get("company_name"))
    proof_points_meta = _proof_points_from_company_notes(
        company_context.get("company_notes"),
        allowed_text=f"{seller_name} {offer_lock}",
    )
    proof_points = [item["text"] for item in proof_points_meta]

    wedge_problem, wedge_outcome = _preset_wedge_copy(strategy.preset_id, company, offer_lock)
    if hook_fact:
        wedge_problem = _banded_problem_statement(
            company=company,
            evidence_band=str((hook_fact or {}).get("evidence_band") or "contextual_inference"),
            source_text=str((hook_fact or {}).get("text") or first_fact),
            fact_type=str((hook_fact or {}).get("type") or "other"),
            fallback=(
                wedge_problem
                if preset_true_rewrite
                else first_fact
                or f"{company} teams often lose replies when first-touch messaging lacks clear enforcement discipline"
            ),
        )
    if not preset_true_rewrite:
        wedge_outcome = f"{offer_lock} helps teams keep outreach specific while raising quality from first touch"

    wedge_outcome = _apply_offer_lock_sentence_case(wedge_outcome, offer_lock)

    formality = style_sliders.get("tone_formal_casual", 50)
    stance = style_sliders.get("stance_bold_diplomatic", 50)
    framing = style_sliders.get("framing_problem_outcome", 50)
    min_words, max_words, sentence_budget = _length_target(style_sliders.get("length_short_long", 50))
    if strategy.preset_id == "c_suite_sniper" or persona_route == "exec":
        sentence_budget = 3
    elif preset_true_rewrite and sentence_budget < 3:
        sentence_budget = 3
    if persona_route == "exec":
        min_words, max_words = 55, 90

    tone_style = {
        "use_contractions": formality >= 67,
        "formality_band": "formal" if formality <= 33 else "casual" if formality >= 67 else "neutral",
        "directness_band": "bold" if stance <= 33 else "diplomatic" if stance >= 67 else "balanced",
        "sentence_budget": sentence_budget,
    }
    balance = "problem_first" if framing <= 33 else "outcome_first" if framing >= 67 else "balanced"

    selected_cta_type = cta_type or (strategy.cta_type if not preset_true_rewrite else _default_cta_type(strategy.preset_id, persona_route))
    requested_hook_strategy = _compact(session.get("hook_strategy"))
    if requested_hook_strategy not in {"research_anchored", "risk_framed", "domain_hook", "outcome_hook"}:
        requested_hook_strategy = {
            "contrarian_risk": "risk_framed",
            "executive_brief": "risk_framed",
            "domain_pattern": "domain_hook",
            "value_first": "outcome_hook",
            "curiosity_headline": "outcome_hook",
        }.get(strategy.hook_type, "domain_hook")
    if persona_route == "exec":
        requested_hook_strategy = "risk_framed"
        wedge_problem = _banded_problem_statement(
            company=company,
            evidence_band=str((hook_fact or {}).get("evidence_band") or "contextual_inference"),
            source_text=str((hook_fact or {}).get("text") or ""),
            fact_type=str((hook_fact or {}).get("type") or "other"),
            fallback=f"{company} carries execution risk when outbound quality drifts across teams.",
        )
        proof_points_meta = proof_points_meta[:1]
        proof_points = [item["text"] for item in proof_points_meta]

    structure_template = list(strategy.structure_template)
    if preset_true_rewrite:
        structure_template = list(_PRESET_STRUCTURE_REWRITE.get(strategy.preset_id, structure_template))
    if persona_route == "exec":
        structure_template = ["outcome", "problem", "hook", "cta"]

    required_fields = ["prospect_first_name", "prospect_company", "offer_lock", "cta"]
    if persona_route == "exec":
        minimum_body_sections = ["outcome", "problem", "hook"]
        optional_style_sections = ["proof"]
    else:
        minimum_body_sections = ["problem", "outcome"]
        optional_style_sections = ["hook", "proof"]

    return GenerationPlan(
        greeting=greeting,
        hook_type=strategy.hook_type,
        hook_strategy=requested_hook_strategy,
        wedge_problem=_normalize_sentence(wedge_problem),
        wedge_outcome=_normalize_sentence(wedge_outcome),
        proof_points_used=[_normalize_sentence(item) for item in proof_points if _compact(item)][: (1 if persona_route == "exec" else 3)],
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
        structure_template=structure_template,
        persona_route=persona_route,
        hook_evidence_band=str((hook_fact or {}).get("evidence_band") or "contextual_inference"),
        hook_source_text=str((hook_fact or {}).get("text") or ""),
        hook_lineage={
            "source_text": str((hook_fact or {}).get("text") or ""),
            "fact_type": str((hook_fact or {}).get("type") or "other"),
            "assertable": bool((hook_fact or {}).get("assertable", False)),
            "evidence_band": str((hook_fact or {}).get("evidence_band") or "contextual_inference"),
        },
        proof_points_meta=proof_points_meta[: (1 if persona_route == "exec" else 3)],
        required_fields=required_fields,
        minimum_body_sections=minimum_body_sections,
        optional_style_sections=optional_style_sections,
    )


def _hook_sentence(plan: GenerationPlan, company: str, fact_hint: str) -> str:
    hint = _hook_hint_for_band(plan, company, fact_hint or f"{company} is under pressure to keep outreach precise without slowing execution")
    templates = {
        "direct_wedge": f"Quick point from what we saw: {hint}.",
        "curiosity_headline": (
            f"One concrete signal at {company}: {hint}."
            if plan.hook_evidence_band == "direct_evidence"
            else f"One signal worth noting at {company}: {hint}."
        ),
        "value_first": (
            f"I put together a quick teardown based on {hint}."
            if plan.hook_evidence_band == "direct_evidence"
            else f"I put together a quick teardown around one signal we noticed: {hint}."
        ),
        "contrarian_risk": (
            f"Contrarian take: {hint} can hide a costly quality gap."
            if _evidence_band_rank(plan.hook_evidence_band) >= _evidence_band_rank("strong_signal")
            else f"Contrarian take: {hint}."
        ),
        "domain_pattern": (
            f"Pattern we keep seeing in this segment: {hint}."
            if _evidence_band_rank(plan.hook_evidence_band) >= _evidence_band_rank("strong_signal")
            else f"One pattern worth pressure-testing in this segment: {hint}."
        ),
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


def _is_cta_like_sentence(sentence: str, canonical_cta: str) -> bool:
    line_norm = _compact(sentence).lower()
    if not line_norm:
        return False
    cta_norm = _compact(canonical_cta).lower()
    if cta_norm and line_norm == cta_norm:
        return True
    if cta_norm:
        ratio = SequenceMatcher(None, cta_norm, line_norm).ratio()
        if ratio >= 0.82 and ("?" in line_norm or _CTA_LINE_PATTERN.search(line_norm)):
            return True
    return _CTA_LINE_PATTERN.search(line_norm) is not None


def _contains_text(text: str, token: str) -> bool:
    token_key = _compact(token).lower()
    if not token_key:
        return False
    return token_key in _compact(text).lower()


def _append_exec_support_line(
    sentence_lines: list[str],
    candidate: str,
    *,
    cta_line: str,
    max_words: int,
) -> bool:
    normalized = _normalize_sentence(candidate)
    if not normalized:
        return False
    if normalized.lower() in {entry.lower() for entry in sentence_lines}:
        return False
    candidate_lines = [*sentence_lines, normalized]
    candidate_body = "\n".join(candidate_lines) + f"\n\n{cta_line}"
    if _word_count(candidate_body) > max_words:
        return False
    sentence_lines.append(normalized)
    return True


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
    offer_category: str | None = session.get("offer_category") or None
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
    forbidden_terms = _forbidden_product_terms(session, offer_lock)
    first_name = derive_first_name(session.get("prospect_first_name") or prospect.get("name")) or "you"

    fact_hint = _compact(plan.hook_source_text)
    if _contains_forbidden_term(fact_hint, forbidden_terms):
        fact_hint = ""
    model_signal = _first_sentence(body)
    if model_signal and re.match(r"^(Hi|Hello)\s+[^,\n]+,", model_signal):
        model_signal = re.sub(r"^(Hi|Hello)\s+[^,\n]+,\s*", "", model_signal).strip()
    if (
        model_signal
        and _word_count(model_signal) >= 6
        and not _contains_forbidden_term(model_signal, forbidden_terms)
        and _hook_signal_equivalent(model_signal, plan)
        and _evidence_band_rank(plan.hook_evidence_band) >= _evidence_band_rank("direct_evidence")
    ):
        fact_hint = model_signal
    fact_hint = _sanitize_fact_hint(
        fact_hint,
        prospect_name=str(prospect.get("name") or ""),
        company=company,
        first_name=first_name,
        soften_company_reference=plan.persona_route != "exec",
    )

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
        sentence = _normalize_offer_category_framing(sentence, offer_lock, offer_category)
        toned = _apply_tone(_normalize_sentence(sentence), plan.tone_style)
        parts.append(
            _rewrite_forbidden_sentence(
                toned,
                offer_lock=offer_lock,
                context_key=f"part:{key}",
                forbidden_terms=forbidden_terms,
            )
        )
        if len(parts) >= sentence_budget:
            break
    if not parts:
        parts.append(
            _rewrite_forbidden_sentence(
                _apply_tone(_normalize_sentence(plan.wedge_outcome), plan.tone_style),
                offer_lock=offer_lock,
                context_key="part:fallback",
                forbidden_terms=forbidden_terms,
            )
        )

    claim_source = merge_claim_sources(
        [
            session.get("research_text_raw"),
            session.get("research_text"),
            (session.get("company_context") or {}).get("company_notes"),
            " ".join(
                item["text"]
                for item in (plan.proof_points_meta or [])
                if (item.get("proof_basis") or "") == "seller_note"
            ),
            " ".join(plan.proof_points_used),
        ]
    )
    allowed_numeric_claims = extract_allowed_numeric_claims((session.get("company_context") or {}).get("company_notes"))

    main_text = " ".join(parts)
    main_text = _normalize_offer_category_framing(main_text, offer_lock, offer_category)
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
    main_text = " ".join(
        _rewrite_forbidden_sentence(
            sentence,
            offer_lock=offer_lock,
            context_key=f"main:{index}",
            forbidden_terms=forbidden_terms,
        )
        for index, sentence in enumerate(split_sentences(main_text))
    ).strip()

    base_sentences = cap_repeated_ngrams(dedupe_sentence_list(split_sentences(main_text)), max_count=2, min_n=3, max_n=5)
    for index, sentence in enumerate(base_sentences):
        rewritten = rewrite_unverified_claims(
            sentence,
            claim_source,
            allowed_numeric_claims=allowed_numeric_claims,
        )
        rewritten = _normalize_offer_category_framing(rewritten, offer_lock, offer_category)
        base_sentences[index] = _rewrite_forbidden_sentence(
            rewritten,
            offer_lock=offer_lock,
            context_key=f"base:{index}",
            forbidden_terms=forbidden_terms,
        )
    base_sentences = [sentence for sentence in base_sentences if not _is_cta_like_sentence(sentence, cta_line)]

    length_slider = style_sliders.get("length_short_long", 50)
    section_pool = long_mode_section_pool(
        company_notes=(session.get("company_context") or {}).get("company_notes"),
        allowed_facts=session.get("allowed_facts") or [],
        offer_lock=offer_lock,
        company=company,
        forbidden_terms=forbidden_terms,
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
    sanitized_sections: list[str] = []
    for index, section in enumerate(extra_sections):
        rewritten = rewrite_unverified_claims(
            section,
            claim_source,
            allowed_numeric_claims=allowed_numeric_claims,
        )
        sanitized_sections.append(
            _rewrite_forbidden_sentence(
                rewritten,
                offer_lock=offer_lock,
                context_key=f"extra:{index}",
                forbidden_terms=forbidden_terms,
            )
        )
    extra_sections = sanitized_sections

    min_words = int(plan.length_target.get("min_words", 75))
    max_words = int(plan.length_target.get("max_words", 110))
    rendered_body = compose_body_without_padding_loops(
        base_sentences=base_sentences,
        extra_sections=extra_sections,
        cta_line=cta_line,
        min_words=min_words,
        max_words=max_words,
    )
    if _word_count(rendered_body) < min_words:
        fallback_sections = [section for section in section_pool if section not in extra_sections]
        filler_seed = [
            "The goal is keeping outreach consistent without adding manager overhead.",
            "Teams usually start with one sequence, verify reply quality, then expand.",
            "That creates a cleaner handoff between rep activity, quality checks, and follow-up actions per account.",
        ]
        filler_sentences: list[str] = []
        for index, sentence in enumerate(filler_seed):
            rewritten = rewrite_unverified_claims(
                sentence,
                claim_source,
                allowed_numeric_claims=allowed_numeric_claims,
            )
            filler_sentences.append(
                _rewrite_forbidden_sentence(
                    rewritten,
                    offer_lock=offer_lock,
                    context_key=f"filler:{index}",
                    forbidden_terms=forbidden_terms,
                )
            )
        rendered_body = compose_body_without_padding_loops(
            base_sentences=[*base_sentences, *filler_sentences],
            extra_sections=[*extra_sections, *fallback_sections],
            cta_line=cta_line,
            min_words=min_words,
            max_words=max_words,
        )

    # True-rewrite mode formats narrative as explicit sentence lines so structure is visible:
    # opener, relevance, value, then CTA.
    if feature_preset_true_rewrite_enabled():
        lines = [line.strip() for line in rendered_body.splitlines() if line.strip()]
        if lines:
            cta_line = lines[-1]
            narrative = " ".join(lines[:-1]).strip() if len(lines) > 1 else ""
            sentence_lines = [
                _normalize_sentence(sentence)
                for sentence in split_sentences(narrative)
                if _compact(sentence)
            ]
            if plan.persona_route != "exec":
                for section in extra_sections:
                    if len(sentence_lines) >= 4:
                        break
                    normalized = _normalize_sentence(section)
                    if normalized and normalized.lower() not in {entry.lower() for entry in sentence_lines}:
                        sentence_lines.append(normalized)
                if len(sentence_lines) < 3:
                    for sentence in base_sentences:
                        normalized = _normalize_sentence(sentence)
                        if normalized and normalized.lower() not in {entry.lower() for entry in sentence_lines}:
                            sentence_lines.append(normalized)
                        if len(sentence_lines) >= 3:
                            break
            if sentence_lines:
                if plan.persona_route == "exec":
                    support_candidates: list[str] = []
                    for key in ("hook", "proof", "problem", "outcome"):
                        candidate = _normalize_sentence(blocks.get(key))
                        if candidate:
                            support_candidates.append(candidate)
                    support_candidates.extend(_normalize_sentence(section) for section in extra_sections if _compact(section))
                    support_candidates.extend(_normalize_sentence(sentence) for sentence in base_sentences if _compact(sentence))
                    if company and not any(_contains_text(line, company) for line in sentence_lines):
                        for candidate in support_candidates:
                            if _contains_text(candidate, company):
                                _append_exec_support_line(
                                    sentence_lines,
                                    candidate,
                                    cta_line=cta_line,
                                    max_words=max_words,
                                )
                                break
                    while _word_count("\n".join(sentence_lines) + f"\n\n{cta_line}") < min_words and len(sentence_lines) < 4:
                        appended = False
                        for candidate in support_candidates:
                            if _append_exec_support_line(
                                sentence_lines,
                                candidate,
                                cta_line=cta_line,
                                max_words=max_words,
                            ):
                                appended = True
                                break
                        if not appended:
                            break
                    sentence_lines = sentence_lines[:4]
                rendered_body = "\n".join(sentence_lines) + f"\n\n{cta_line}"

    strategy = get_preset_strategy(plan.preset_id)
    fallback_subject = _subject_fallback(strategy, company, offer_lock)
    next_subject = _trim_subject(subject) or _trim_subject(fallback_subject)
    if _contains_forbidden_term(next_subject, forbidden_terms):
        next_subject = _trim_subject(f"{offer_lock} for your team")
    if not next_subject:
        next_subject = _trim_subject(fallback_subject)
    next_subject = rewrite_unverified_claims(
        next_subject,
        claim_source,
        allowed_numeric_claims=allowed_numeric_claims,
    )
    if _contains_forbidden_term(next_subject, forbidden_terms):
        next_subject = _trim_subject(f"{offer_lock} for your team")

    lines = [line.strip() for line in rendered_body.splitlines() if line.strip()]
    if lines:
        cta_tail = lines[-1]
        if feature_preset_true_rewrite_enabled():
            narrative_lines = [
                _apply_offer_lock_sentence_case(line, offer_lock)
                for line in lines[:-1]
                if _compact(line)
            ]
            rendered_body = "\n".join(narrative_lines) + f"\n\n{cta_tail}" if narrative_lines else cta_tail
        else:
            narrative = " ".join(lines[:-1]).strip() if len(lines) > 1 else ""
            if narrative:
                narrative = _apply_offer_lock_sentence_case(narrative, offer_lock)
                rendered_body = f"{narrative}\n\n{cta_tail}"
    return next_subject, rendered_body
