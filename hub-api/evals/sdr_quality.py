"""Deterministic SDR quality scoring harness for web_mvp drafts."""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from statistics import mean
from typing import Any

from email_generation.claim_verifier import extract_allowed_numeric_claims, find_unverified_claims, merge_claim_sources
from email_generation.output_enforcement import split_sentences
from email_generation.remix_engine import (
    _extract_subject_and_body,
    _prospect_owns_offer_lock_violations,
    create_session_payload,
    build_draft,
)
from email_generation.runtime_policies import rollout_context

_ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = _ROOT / "evals" / "sdr_quality_pack.v1.json"
LATEST_REPORT_PATH = _ROOT / "reports" / "sdr_quality" / "latest.json"

_EXEC_TITLE_RE = re.compile(r"\b(ceo|chief executive officer|founder|co-founder|president)\b", re.IGNORECASE)
_FUNCTIONAL_TITLE_RE = re.compile(r"\b(vp|vice president|director|head|brand|legal|ip)\b", re.IGNORECASE)
_RISK_OUTCOME_RE = re.compile(r"\b(risk|exposure|pipeline|revenue|outcome|priority|cost|efficiency|quality)\b", re.IGNORECASE)
_TACTICAL_DUMP_RE = re.compile(
    r"\b(workflow|feature|dashboard|integration|platform|tooling|template|automation|module)\b",
    re.IGNORECASE,
)
_CTA_VAGUE_RE = re.compile(r"\b(worth a look|not a priority)\b", re.IGNORECASE)

_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "your",
    "their",
    "have",
    "has",
    "into",
    "across",
    "teams",
    "team",
}


@contextmanager
def _temporary_env(overrides: dict[str, str]):
    prior = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def _max_ngram_repetition(text: str, n: int = 3) -> int:
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    if len(words) < n:
        return 0
    counts = Counter(" ".join(words[index : index + n]) for index in range(len(words) - n + 1))
    return max(counts.values(), default=0)


def _has_fragment_ending(text: str) -> bool:
    compact = " ".join((text or "").split())
    if not compact:
        return True
    if compact.endswith(("...", ",", ";", ":", "-", "/", "(")):
        return True
    return (
        re.search(
            r"(?:\b(?:and|or|to|with|for|of|from|that|which|while|because|so)\b)\s*$",
            compact,
            flags=re.IGNORECASE,
        )
        is not None
    )


def _fact_matches(body: str, high_conf_facts: list[str]) -> int:
    lowered = (body or "").lower()
    matches = 0
    for fact in high_conf_facts:
        words = [w for w in re.findall(r"[a-z0-9']+", fact.lower()) if len(w) >= 4 and w not in _STOPWORDS]
        if not words:
            continue
        overlap = sum(1 for word in set(words) if word in lowered)
        if overlap >= 2:
            matches += 1
    return matches


def _persona_fit_score(title: str, body: str, high_conf_facts: list[str]) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 100
    words = _word_count(body)
    title_lower = (title or "").lower()
    is_exec = _EXEC_TITLE_RE.search(title_lower) is not None
    tactical_hits = len(_TACTICAL_DUMP_RE.findall(body or ""))
    risk_hits = len(_RISK_OUTCOME_RE.findall(body or ""))
    fact_hits = _fact_matches(body, high_conf_facts)

    if is_exec:
        if words > 90:
            score -= 40
            reasons.append("exec_over_90_words")
        if tactical_hits >= 3:
            score -= 25
            reasons.append("exec_feature_dump")
        if risk_hits < 2:
            score -= 20
            reasons.append("exec_missing_risk_outcome_framing")
        if fact_hits > 1:
            score -= 15
            reasons.append("exec_uses_more_than_one_fact")
    elif _FUNCTIONAL_TITLE_RE.search(title_lower):
        if risk_hits < 1 and tactical_hits < 1:
            score -= 20
            reasons.append("functional_role_lacks_operational_value")
        if words < 55 or words > 165:
            score -= 10
            reasons.append("functional_role_length_outside_expected_range")
    else:
        if words < 50 or words > 165:
            score -= 10
            reasons.append("generic_role_length_outside_expected_range")

    return max(0, min(100, score)), reasons


def _structure_score(body: str, expected_cta: str | None, *, allow_vague_cta: bool) -> tuple[int, list[str]]:
    lines = [line.strip() for line in (body or "").splitlines() if line.strip()]
    reasons: list[str] = []
    score = 100
    if len(lines) < 3:
        score -= 35
        reasons.append("too_few_body_lines")
    cta_line = lines[-1] if lines else ""
    if expected_cta and cta_line != expected_cta.strip():
        score -= 25
        reasons.append("cta_not_last_or_not_exact")
    if "?" not in cta_line and not re.search(r"\b(send|call|chat|meeting|review|audit|brief)\b", cta_line, re.IGNORECASE):
        score -= 20
        reasons.append("cta_not_specific")
    if (not allow_vague_cta) and _CTA_VAGUE_RE.search(cta_line):
        score -= 20
        reasons.append("vague_cta_phrase")
    narrative = " ".join(lines[:-1]).strip() if len(lines) > 1 else ""
    sentence_count = len(split_sentences(narrative))
    if sentence_count < 3 or sentence_count > 5:
        score -= 20
        reasons.append("narrative_sentence_count_outside_3_to_5")
    return max(0, min(100, score)), reasons


def _specificity_score(body: str, offer_lock: str, high_conf_facts: list[str]) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 100
    fact_hits = _fact_matches(body, high_conf_facts)
    if fact_hits == 0:
        score -= 60
        reasons.append("no_high_conf_fact_used")
    elif fact_hits > 2:
        score -= 15
        reasons.append("uses_too_many_facts")
    if offer_lock.lower() not in (body or "").lower():
        score -= 25
        reasons.append("offer_lock_not_connected")
    return max(0, min(100, score)), reasons


def _readability_score(body: str) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 100
    narrative = " ".join(line.strip() for line in (body or "").splitlines() if line.strip())
    if _max_ngram_repetition(narrative, n=3) > 2:
        score -= 30
        reasons.append("trigram_repetition_gt_2")
    if _has_fragment_ending(narrative):
        score -= 20
        reasons.append("fragment_ending_detected")
    sentences = split_sentences(narrative)
    if sentences:
        avg_len = mean(max(1, _word_count(sentence)) for sentence in sentences)
        if avg_len > 28:
            score -= 20
            reasons.append("average_sentence_too_long")
    return max(0, min(100, score)), reasons


def _hallucination_check(
    draft: str,
    session: dict[str, Any],
    *,
    allowed_claim_source: str,
    allowed_numeric_claims: set[str],
) -> tuple[int, list[str]]:
    reasons: list[str] = []
    ownership = _prospect_owns_offer_lock_violations(draft, session=session)
    if ownership:
        reasons.extend(ownership)
    for claim in find_unverified_claims(draft, allowed_claim_source, allowed_numeric_claims=allowed_numeric_claims):
        reasons.append(f"unverified_claim:{claim[:80]}")
    trusted_by = re.findall(r"\btrusted by [^,.!?]+", draft, flags=re.IGNORECASE)
    for phrase in trusted_by:
        if phrase.lower() not in allowed_claim_source.lower():
            reasons.append(f"unsupported_trusted_by:{phrase[:80]}")
    return (1 if reasons else 0), reasons


def _score_case(
    *,
    case: dict[str, Any],
    session: dict[str, Any],
    draft: str,
) -> dict[str, Any]:
    subject, body = _extract_subject_and_body(draft)
    high_conf_facts = [
        str(entry.get("text") or "").strip()
        for entry in (session.get("allowed_facts_structured") or [])
        if str(entry.get("confidence") or "").lower() == "high" and str(entry.get("text") or "").strip()
    ]
    claim_source = merge_claim_sources(
        [
            session.get("research_text_raw"),
            session.get("research_text"),
            (session.get("company_context") or {}).get("company_notes"),
            " ".join(session.get("allowed_facts") or []),
        ]
    )
    allowed_numeric_claims = extract_allowed_numeric_claims((session.get("company_context") or {}).get("company_notes"))
    hallucination_fail, hallucination_reasons = _hallucination_check(
        draft,
        session=session,
        allowed_claim_source=claim_source,
        allowed_numeric_claims=allowed_numeric_claims,
    )
    persona_score, persona_reasons = _persona_fit_score(
        title=str((case.get("prospect") or {}).get("title") or ""),
        body=body,
        high_conf_facts=high_conf_facts,
    )
    allow_vague_cta = bool(case.get("preset_id") == "challenger" and not _EXEC_TITLE_RE.search(str((case.get("prospect") or {}).get("title") or "")))
    structure_score, structure_reasons = _structure_score(
        body=body,
        expected_cta=session.get("cta_lock_effective"),
        allow_vague_cta=allow_vague_cta,
    )
    specificity_score, specificity_reasons = _specificity_score(
        body=body,
        offer_lock=str(case.get("offer_lock") or ""),
        high_conf_facts=high_conf_facts,
    )
    readability_score, readability_reasons = _readability_score(body)

    credibility_score = 0 if hallucination_fail else 100
    sdr_score = round(
        (0.30 * credibility_score)
        + (0.20 * persona_score)
        + (0.20 * structure_score)
        + (0.20 * specificity_score)
        + (0.10 * readability_score),
        2,
    )
    return {
        "case_id": case["id"],
        "title": (case.get("prospect") or {}).get("title"),
        "preset_id": case.get("preset_id"),
        "subject": subject,
        "body": body,
        "hallucination": {
            "FAIL_HALLUCINATION": hallucination_fail,
            "reasons": hallucination_reasons,
        },
        "persona_fit_score": persona_score,
        "structure_score": structure_score,
        "specificity_score": specificity_score,
        "readability_score": readability_score,
        "sdr_score": sdr_score,
        "reason_codes": [
            *hallucination_reasons,
            *persona_reasons,
            *structure_reasons,
            *specificity_reasons,
            *readability_reasons,
        ],
    }


async def _run_single_case(case: dict[str, Any]) -> dict[str, Any]:
    style = case.get("style_profile") or {"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0}
    with rollout_context(endpoint="generate", bucket_key=case["id"]):
        session = create_session_payload(
            prospect=case["prospect"],
            research_text=case["research_text"],
            initial_style=style,
            offer_lock=case["offer_lock"],
            cta_offer_lock=case.get("cta_offer_lock"),
            cta_type=case.get("cta_type"),
            company_context=case.get("company_context") or {},
            preset_id=case.get("preset_id"),
        )
        result = await build_draft(session=session, style_profile=style)
    return _score_case(case=case, session=session, draft=result.draft)


def load_case_pack(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or PACK_PATH
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) != 20:
        raise ValueError(f"Expected 20 scenarios in {target}")
    return payload


def _summarize(case_reports: list[dict[str, Any]]) -> dict[str, Any]:
    reason_counter: Counter[str] = Counter()
    for report in case_reports:
        reason_counter.update(report.get("reason_codes") or [])
    avg_score = round(mean(item["sdr_score"] for item in case_reports), 2)
    hallucination_failures = sum(1 for item in case_reports if item["hallucination"]["FAIL_HALLUCINATION"] == 1)
    return {
        "case_count": len(case_reports),
        "average_sdr_score": avg_score,
        "hallucination_fail_count": hallucination_failures,
        "top_failure_reasons": reason_counter.most_common(10),
    }


async def run_profile(profile: str, *, pack_path: Path | None = None) -> dict[str, Any]:
    profile_normalized = profile.strip().lower()
    if profile_normalized not in {"baseline", "candidate"}:
        raise ValueError("profile must be baseline or candidate")
    base_env = {
        "REDIS_FORCE_INMEMORY": "1",
        "USE_PROVIDER_STUB": "1",
        "EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL": "warn",
        "FEATURE_PERSONA_ROUTER_GLOBAL": "0",
        "FEATURE_NO_PROSPECT_OWNS_GUARDRAIL_GLOBAL": "0",
        "FEATURE_PRESET_TRUE_REWRITE_GLOBAL": "0",
        "FEATURE_PERSONA_ROUTER_ROLLOUT_PERCENT": "0",
        "FEATURE_NO_PROSPECT_OWNS_GUARDRAIL_ROLLOUT_PERCENT": "0",
        "FEATURE_PRESET_TRUE_REWRITE_ROLLOUT_PERCENT": "0",
    }
    if profile_normalized == "candidate":
        base_env.update(
            {
                "FEATURE_PERSONA_ROUTER_GLOBAL": "1",
                "FEATURE_NO_PROSPECT_OWNS_GUARDRAIL_GLOBAL": "1",
                "FEATURE_PRESET_TRUE_REWRITE_GLOBAL": "1",
                "FEATURE_PERSONA_ROUTER_ROLLOUT_PERCENT": "100",
                "FEATURE_NO_PROSPECT_OWNS_GUARDRAIL_ROLLOUT_PERCENT": "100",
                "FEATURE_PRESET_TRUE_REWRITE_ROLLOUT_PERCENT": "100",
            }
        )
    cases = load_case_pack(pack_path)
    with _temporary_env(base_env):
        reports = await asyncio.gather(*[_run_single_case(case) for case in cases])
    return {
        "profile": profile_normalized,
        "summary": _summarize(reports),
        "cases": reports,
    }


async def run_baseline_and_candidate(*, pack_path: Path | None = None) -> dict[str, Any]:
    baseline = await run_profile("baseline", pack_path=pack_path)
    candidate = await run_profile("candidate", pack_path=pack_path)
    delta = round(candidate["summary"]["average_sdr_score"] - baseline["summary"]["average_sdr_score"], 2)
    return {
        "pack_path": str((pack_path or PACK_PATH).resolve()),
        "baseline": baseline,
        "candidate": candidate,
        "delta": {"average_sdr_score": delta},
    }


def write_latest_report(report: dict[str, Any], *, output_path: Path | None = None) -> Path:
    target = output_path or LATEST_REPORT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return target
