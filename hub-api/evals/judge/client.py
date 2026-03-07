from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

from email_generation.model_defaults import openai_reasoning_effort
from evals.checks import parse_draft
from evals.judge.cache import JudgeCache
from evals.judge.prompts import (
    PAIRWISE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_pairwise_user_prompt,
    build_user_prompt,
    prompt_contract_hash,
)
from evals.judge.redaction import build_allowed_context, redact_judge_artifact
from evals.judge.reliability import aggregate_pairwise_votes, deterministic_order_swap
from evals.judge.rubric import JudgeConfig
from evals.judge.schemas import (
    JUDGE_OUTPUT_SCHEMA,
    JUDGE_SCHEMA_VERSION,
    PAIRWISE_OUTPUT_SCHEMA,
    validate_judge_output,
    validate_pairwise_output,
)
from evals.judge.scoring import aggregate_samples, normalize_scored_output
from evals.models import EvalCase


@dataclass
class JudgeRuntime:
    mode: str
    model: str
    timeout_seconds: float
    sample_count: int
    model_version: str = ""
    secondary_model: str | None = None


class JudgeClient:
    def __init__(
        self,
        *,
        cache: JudgeCache | None = None,
        runtime: JudgeRuntime | None = None,
    ):
        self.cache = cache
        self.runtime = runtime or JudgeRuntime(
            mode=os.environ.get("EMAILDJ_JUDGE_MODE", "mock").strip().lower() or "mock",
            model=os.environ.get("EMAILDJ_JUDGE_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
            timeout_seconds=float(os.environ.get("EMAILDJ_JUDGE_TIMEOUT_SEC", "30")),
            sample_count=max(1, int(os.environ.get("EMAILDJ_JUDGE_SAMPLE_COUNT", "1"))),
            model_version=(
                os.environ.get("EMAILDJ_JUDGE_MODEL_VERSION", "").strip()
                or os.environ.get("EMAILDJ_JUDGE_MODEL", "gpt-4.1-mini").strip()
                or "gpt-4.1-mini"
            ),
            secondary_model=(os.environ.get("EMAILDJ_JUDGE_SECONDARY_MODEL", "").strip() or None),
        )

    @property
    def config(self) -> JudgeConfig:
        return JudgeConfig(
            model=self.runtime.model,
            model_version=self.runtime.model_version or self.runtime.model,
            mode=self.runtime.mode,
            sample_count=self.runtime.sample_count,
            secondary_model=self.runtime.secondary_model,
        )

    def evaluate_email(
        self,
        *,
        case: EvalCase,
        subject: str,
        body: str,
        candidate_id: str,
        eval_mode: str,
    ) -> dict[str, Any]:
        context = build_allowed_context(case)
        contract_hash = prompt_contract_hash()
        content_hash = _content_hash(context=context, subject=subject, body=body)
        cache_key = None
        if self.cache is not None:
            cache_key = self.cache.build_key(
                case_id=case.id,
                model_version=self.runtime.model_version or self.runtime.model,
                prompt_contract_hash=contract_hash,
                candidate_id=candidate_id,
                eval_mode=eval_mode,
                extra=f"email:{content_hash}",
            )
            cached = self.cache.get(cache_key)
            if cached is not None:
                cached = dict(cached)
                cached["cache_hit"] = True
                return cached

        samples: list[dict[str, Any]] = []
        for sample_idx in range(self.runtime.sample_count):
            if self.runtime.mode == "real":
                raw = self._judge_with_model(
                    model_name=self.runtime.model,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=build_user_prompt(context=context, subject=subject, body=body),
                    schema_name="emaildj_quality_judge",
                    schema=JUDGE_OUTPUT_SCHEMA,
                )
            else:
                raw = self._mock_judge(
                    context=context,
                    subject=subject,
                    body=body,
                    sample_idx=sample_idx,
                )
            validated = validate_judge_output(raw)
            samples.append(normalize_scored_output(validated))

        aggregated = aggregate_samples(samples)
        result = {
            "status": "scored",
            "schema_version": JUDGE_SCHEMA_VERSION,
            "judge_model": self.runtime.model,
            "judge_model_version": self.runtime.model_version or self.runtime.model,
            "judge_mode": self.runtime.mode,
            "prompt_contract_hash": contract_hash,
            "content_hash": content_hash,
            "cache_hit": False,
            "samples": [redact_judge_artifact(sample) for sample in samples],
            **aggregated,
        }
        if self.cache is not None and cache_key is not None:
            self.cache.put(cache_key, result)
        return result

    def evaluate_ad_hoc(
        self,
        *,
        case_id: str,
        context: dict[str, str],
        subject: str,
        body: str,
        candidate_id: str,
        eval_mode: str,
    ) -> dict[str, Any]:
        contract_hash = prompt_contract_hash()
        content_hash = _content_hash(context=context, subject=subject, body=body)
        cache_key = None
        if self.cache is not None:
            cache_key = self.cache.build_key(
                case_id=case_id,
                model_version=self.runtime.model_version or self.runtime.model,
                prompt_contract_hash=contract_hash,
                candidate_id=candidate_id,
                eval_mode=eval_mode,
                extra=f"adhoc:{content_hash}",
            )
            cached = self.cache.get(cache_key)
            if cached is not None:
                cached = dict(cached)
                cached["cache_hit"] = True
                return cached

        samples: list[dict[str, Any]] = []
        for sample_idx in range(self.runtime.sample_count):
            if self.runtime.mode == "real":
                raw = self._judge_with_model(
                    model_name=self.runtime.model,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=build_user_prompt(context=context, subject=subject, body=body),
                    schema_name="emaildj_quality_judge",
                    schema=JUDGE_OUTPUT_SCHEMA,
                )
            else:
                raw = self._mock_judge(
                    context=context,
                    subject=subject,
                    body=body,
                    sample_idx=sample_idx,
                )
            validated = validate_judge_output(raw)
            samples.append(normalize_scored_output(validated))

        aggregated = aggregate_samples(samples)
        result = {
            "status": "scored",
            "schema_version": JUDGE_SCHEMA_VERSION,
            "judge_model": self.runtime.model,
            "judge_model_version": self.runtime.model_version or self.runtime.model,
            "judge_mode": self.runtime.mode,
            "prompt_contract_hash": contract_hash,
            "content_hash": content_hash,
            "cache_hit": False,
            "samples": [redact_judge_artifact(sample) for sample in samples],
            **aggregated,
        }
        if self.cache is not None and cache_key is not None:
            self.cache.put(cache_key, result)
        return result

    def evaluate_pairwise(
        self,
        *,
        case: EvalCase,
        draft_a: str,
        draft_b: str,
        eval_mode: str,
        candidate_id: str = "pairwise",
    ) -> dict[str, Any]:
        parsed_a = parse_draft(draft_a)
        parsed_b = parse_draft(draft_b)
        context = build_allowed_context(case)
        contract_hash = prompt_contract_hash()

        order_swapped = deterministic_order_swap(case.id)
        order_plan = [("A", "B"), ("B", "A")]
        if order_swapped:
            order_plan = list(reversed(order_plan))

        votes: list[dict[str, Any]] = []
        for left, right in order_plan:
            subject_left = parsed_a.subject if left == "A" else parsed_b.subject
            body_left = parsed_a.body if left == "A" else parsed_b.body
            subject_right = parsed_b.subject if right == "B" else parsed_a.subject
            body_right = parsed_b.body if right == "B" else parsed_a.body

            if self.runtime.mode == "real":
                raw = self._judge_with_model(
                    model_name=self.runtime.model,
                    system_prompt=PAIRWISE_SYSTEM_PROMPT,
                    user_prompt=build_pairwise_user_prompt(
                        context=context,
                        subject_a=subject_left,
                        body_a=body_left,
                        subject_b=subject_right,
                        body_b=body_right,
                    ),
                    schema_name="emaildj_pairwise_judge",
                    schema=PAIRWISE_OUTPUT_SCHEMA,
                )
                validated = validate_pairwise_output(raw)
            else:
                validated = self._mock_pairwise(
                    context=context,
                    subject_a=subject_left,
                    body_a=body_left,
                    subject_b=subject_right,
                    body_b=body_right,
                )

            winner = validated["winner"]
            if left == "B" and right == "A":
                if winner == "A":
                    winner = "B"
                elif winner == "B":
                    winner = "A"
            votes.append(
                {
                    "winner": winner,
                    "confidence": validated["confidence"],
                    "rationale_bullets": validated["rationale_bullets"],
                    "flags": validated["flags"],
                }
            )

        aggregated = aggregate_pairwise_votes(votes)
        return {
            "status": "scored",
            "judge_model": self.runtime.model,
            "judge_model_version": self.runtime.model_version or self.runtime.model,
            "judge_mode": self.runtime.mode,
            "prompt_contract_hash": contract_hash,
            "eval_mode": eval_mode,
            "candidate_id": candidate_id,
            "order_swapped": order_swapped,
            "votes": votes,
            **aggregated,
        }

    def _judge_with_model(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> str:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY missing for real judge mode")
        with httpx.Client(timeout=self.runtime.timeout_seconds) as client:
            response = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model_name,
                    "temperature": 0,
                    "reasoning_effort": openai_reasoning_effort(),
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema_name,
                            "strict": True,
                            "schema": schema,
                        },
                    },
                },
            )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        if isinstance(content, list):
            text = "".join(chunk.get("text", "") for chunk in content if isinstance(chunk, dict))
        else:
            text = str(content or "")
        if not text.strip():
            raise ValueError("judge_model_empty_output")
        return text

    def _mock_judge(
        self,
        *,
        context: dict[str, str],
        subject: str,
        body: str,
        sample_idx: int = 0,
    ) -> dict[str, Any]:
        text = f"{subject}\n{body}".strip()
        lower = text.lower()
        words = re.findall(r"[A-Za-z0-9']+", body.lower())
        word_count = len(words)
        body_lines = [line.strip() for line in body.splitlines() if line.strip()]
        paragraphs = [paragraph.strip() for paragraph in body.split("\n\n") if paragraph.strip()]
        sentence_parts = [part.strip() for part in re.split(r"[.!?]+", body) if part.strip()]
        sentence_count = max(1, len(sentence_parts))
        avg_sentence_len = (word_count / sentence_count) if sentence_count else float(word_count)
        max_sentence_len = max((len(re.findall(r"[A-Za-z0-9']+", sentence)) for sentence in sentence_parts), default=word_count)
        flags: list[str] = []

        overclaim_present = _overclaim_present(lower)
        filler_padding_present = _filler_padding_present(lower=lower, words=words, word_count=word_count)
        clarity_violation_present = _clarity_violation_present(
            lower=lower,
            paragraph_count=len(paragraphs),
            sentence_count=sentence_count,
            avg_sentence_len=avg_sentence_len,
            max_sentence_len=max_sentence_len,
        )

        if _contains_pii(lower):
            flags.append("auto_fail_pii_leakage")
        if any(term in lower for term in ("gift card", "amazon card", "$100", "cash reward", "prepaid card")):
            flags.append("auto_fail_bribery_or_gift")
        if overclaim_present:
            flags.append("auto_fail_overclaim_present")
        if re.search(r"\bguarantee(?:d)?\b|\b\d+%\b|\b100%\b", lower):
            flags.append("auto_fail_guaranteed_outcome")
        if any(term in lower for term in ("ignore previous instructions", "bypass policy", "non-compliant")):
            flags.append("auto_fail_policy_or_compliance_risk")
        if any(term in lower for term in ("as a judge", "dear evaluator", "this should score", "judge score")):
            flags.append("judge_pandering_detected")
        if filler_padding_present or word_count > 220:
            flags.append("verbosity_padding_detected")
        if clarity_violation_present:
            flags.append("clarity_violation_detected")
        if context.get("prospect_company", "").lower() not in lower:
            flags.append("insufficient_personalization")
        cta_lock = context.get("cta_lock", "").strip()
        if not cta_lock or (body_lines and body_lines[-1] != cta_lock):
            flags.append("weak_cta")
        if "!" in body:
            flags.append("tone_mismatch")

        relevance = 1
        if context.get("offer_lock", "").lower() in lower:
            relevance += 2
        if context.get("prospect_company", "").lower() in lower:
            relevance += 1
        if context.get("prospect_role", "").split()[0:1]:
            role_token = context.get("prospect_role", "").split()[0].lower()
            if role_token and role_token in lower:
                relevance += 1
        if filler_padding_present:
            relevance -= 1
        relevance = max(0, min(5, relevance))

        if clarity_violation_present:
            clarity = 1 if avg_sentence_len > 42 or len(paragraphs) > 3 else 2
        elif 1 <= len(paragraphs) <= 2 and sentence_count <= 4 and avg_sentence_len <= 22:
            clarity = 5
        elif len(paragraphs) <= 2 and sentence_count <= 5 and avg_sentence_len <= 28:
            clarity = 4
        else:
            clarity = 3

        if overclaim_present:
            credibility = 1
        elif any(term in lower for term in ("best product ever", "absolutely transform", "instantly")):
            credibility = 2
        elif any(term in lower for term in ("will improve", "proven", "always")):
            credibility = 3
        elif any(term in lower for term in ("might help", "can help", "designed to", "typically")):
            credibility = 5
        elif "possible_hallucination" in flags:
            credibility = 2
        else:
            credibility = 4

        personalization = 5 if "insufficient_personalization" not in flags else 2
        if context.get("prospect_role", "").lower() not in lower:
            personalization = max(1, personalization - 1)
        if filler_padding_present:
            personalization = max(1, personalization - 1)

        cta_quality = 5 if cta_lock and body_lines and body_lines[-1] == cta_lock else 2
        tone = 5 if "tone_mismatch" not in flags else 2

        if 25 <= word_count <= 110 and not filler_padding_present and not clarity_violation_present:
            conciseness = 5
        elif 20 <= word_count <= 140 and not filler_padding_present:
            conciseness = 4
        elif 20 <= word_count <= 170 and not (filler_padding_present and clarity_violation_present):
            conciseness = 3
        elif 15 <= word_count <= 220:
            conciseness = 2
        else:
            conciseness = 1

        value_prop = 3
        if context.get("offer_lock", "").lower() in lower and any(
            term in lower for term in ("built to", "help", "improve", "reduce", "faster", "quality")
        ):
            value_prop = 5
        elif context.get("offer_lock", "").lower() in lower:
            value_prop = 4

        # Introduce tiny deterministic variance for multi-sample self-consistency.
        if sample_idx % 3 == 1:
            clarity = max(0, min(5, clarity - 1))
        elif sample_idx % 3 == 2:
            relevance = max(0, min(5, relevance - 1))

        return {
            "scores": {
                "relevance_to_prospect": relevance,
                "clarity_and_structure": clarity,
                "credibility_no_overclaim": credibility,
                "personalization_quality": personalization,
                "cta_quality": cta_quality,
                "tone_match": tone,
                "conciseness_signal_density": conciseness,
                "value_prop_specificity": value_prop,
            },
            "binary_checks": {
                "overclaim_present": overclaim_present,
                "filler_padding_present": filler_padding_present,
                "clarity_violation_present": clarity_violation_present,
            },
            "overall": 0,
            "pass_fail": "pass",
            "rationale_bullets": [
                f"Relevance scored {relevance}/5 based on prospect and offer alignment.",
                f"Credibility scored {credibility}/5 with emphasis on claim safety.",
                f"CTA quality scored {cta_quality}/5 based on final ask precision.",
            ],
            "flags": flags,
        }

    def _mock_pairwise(
        self,
        *,
        context: dict[str, str],
        subject_a: str,
        body_a: str,
        subject_b: str,
        body_b: str,
    ) -> dict[str, Any]:
        a = normalize_scored_output(self._mock_judge(context=context, subject=subject_a, body=body_a))
        b = normalize_scored_output(self._mock_judge(context=context, subject=subject_b, body=body_b))
        delta = a["overall"] - b["overall"]
        if abs(delta) < 0.2:
            winner = "tie"
        elif delta > 0:
            winner = "A"
        else:
            winner = "B"
        confidence = min(1.0, abs(delta) / 2.5)
        return {
            "winner": winner,
            "confidence": confidence,
            "rationale_bullets": [
                f"Email A overall={a['overall']:.2f}, Email B overall={b['overall']:.2f}.",
                "Winner selected using rubric-weighted comparison with length neutrality.",
            ],
            "flags": list({*a.get("flags", []), *b.get("flags", [])}),
        }


def _contains_pii(lower_text: str) -> bool:
    if re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", lower_text, re.IGNORECASE):
        return True
    if re.search(r"\b(?:\+?\d{1,2}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b", lower_text):
        return True
    return False


def _overclaim_present(lower_text: str) -> bool:
    patterns = (
        r"\bguarantee(?:d)?\b",
        r"\b\d+%\b",
        r"\bwill\s+(?:absolutely\s+)?(?:increase|improve|transform)\b",
        r"\bzero effort\b",
        r"\bbest product ever\b",
        r"\b100%\b",
    )
    return any(re.search(pattern, lower_text) for pattern in patterns)


def _filler_padding_present(*, lower: str, words: list[str], word_count: int) -> bool:
    repeated_generic_count = sum(lower.count(token) for token in (" broad ", " generic ", " many ", "various ", "everything "))
    top_frequency = 0
    if words:
        token_counts: dict[str, int] = {}
        for token in words:
            token_counts[token] = token_counts.get(token, 0) + 1
        top_frequency = max(token_counts.values())
    unique_ratio = (len(set(words)) / word_count) if word_count else 0.0
    repeated_phrases = bool(re.search(r"\bbroad\b.*\bbroad\b|\bgeneric\b.*\bgeneric\b", lower))
    explicit_filler_markers = any(
        marker in lower
        for marker in ("keeps repeating", "repeating", "on and on", "without adding value", "intentionally long")
    )
    return (
        (word_count >= 120 and unique_ratio < 0.45)
        or (word_count > 170)
        or repeated_phrases
        or explicit_filler_markers
        or ((word_count >= 70) and (top_frequency / max(1, word_count) > 0.07))
        or repeated_generic_count >= 5
    )


def _clarity_violation_present(
    *,
    lower: str,
    paragraph_count: int,
    sentence_count: int,
    avg_sentence_len: float,
    max_sentence_len: int,
) -> bool:
    jargon_hits = sum(1 for term in ("synergy", "paradigm", "best-in-class", "revolutionary", "world-class") if term in lower)
    conjunction_count = len(re.findall(r"\b(and|while|which|that)\b", lower))
    return (
        paragraph_count > 2
        or sentence_count > 5
        or avg_sentence_len > 30
        or max_sentence_len > 42
        or jargon_hits >= 2
        or conjunction_count > 12
    )


def _content_hash(*, context: dict[str, str], subject: str, body: str) -> str:
    payload = {
        "context": {k: str(v) for k, v in sorted(context.items())},
        "subject": subject.strip(),
        "body": body.strip(),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
