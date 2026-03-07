"""RC-TCO structured output composer for web generate flow."""

from __future__ import annotations

import json
import re
from typing import Any

from email_generation.output_enforcement import (
    compact,
    derive_first_name,
    enforce_cta_last_line,
    split_sentences,
)

LEGACY_RESPONSE_CONTRACT = "legacy_text"
RC_TCO_RESPONSE_CONTRACT = "rc_tco_json_v1"
DEFAULT_CTA_LINE = "Open to a 15-min chat to sanity-check fit? Worth a look / Not a priority?"

_SIGNOFF_PATTERN = re.compile(r"\b(?:best regards|regards|sincerely|thanks|thank you|cheers)\b", re.IGNORECASE)
_GREETING_PATTERN = re.compile(r"^(?:Hi|Hello)\s+[^,\n]+,\s*$", re.IGNORECASE)
_WIKI_PHRASES = (
    "is an american software company",
    "develops data integration",
)
_WORD_PATTERN = re.compile(r"\S+")


def _word_count(text: str) -> int:
    return len(_WORD_PATTERN.findall(text or ""))


def _trim_words(text: str, max_words: int) -> str:
    words = _WORD_PATTERN.findall(compact(text))
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words])


def _non_empty_lines(text: str) -> list[str]:
    return [compact(line) for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n") if compact(line)]


def _dedupe_lines(lines: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for line in lines:
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(line)
    return deduped


def _extract_proof_points(session: dict[str, Any], max_items: int = 2) -> list[str]:
    company_notes = compact((session.get("company_context") or {}).get("company_notes"))
    allowed_facts = [compact(item) for item in (session.get("allowed_facts") or []) if compact(item)]
    candidates: list[str] = []
    if company_notes:
        candidates.extend(split_sentences(company_notes))
    candidates.extend(allowed_facts)

    selected: list[str] = []
    for sentence in candidates:
        sentence_l = sentence.lower()
        if "wikipedia" in sentence_l:
            continue
        if any(phrase in sentence_l for phrase in _WIKI_PHRASES):
            continue
        if len(_WORD_PATTERN.findall(sentence)) < 6:
            continue
        selected.append(_trim_words(sentence, 16))
        if len(selected) >= max_items:
            break
    return selected[:max_items]


def _resolve_cta_line(session: dict[str, Any]) -> str:
    explicit = compact(session.get("cta_offer_lock"))
    if explicit:
        return explicit
    return DEFAULT_CTA_LINE


def build_user_company_intel(session: dict[str, Any]) -> dict[str, Any]:
    company_context = session.get("company_context") or {}
    company_name = compact(company_context.get("company_name")) or compact((session.get("prospect") or {}).get("company")) or "unknown"
    offer_lock = compact(session.get("offer_lock")) or "the current offer"
    prospect_title = compact((session.get("prospect") or {}).get("title")) or "revenue leaders"
    company_notes = compact(company_context.get("company_notes"))
    proof_points = _extract_proof_points(session, max_items=2)
    differentiation = _trim_words(split_sentences(company_notes)[0], 20) if company_notes else "unknown"

    forbidden_positioning = ["AI consulting/services"]
    for term in session.get("forbidden_terms") or []:
        normalized = compact(term)
        if normalized and normalized not in forbidden_positioning:
            forbidden_positioning.append(normalized)

    return {
        "company_name": company_name,
        "what_we_do": f"{company_name} helps teams execute {offer_lock} without adding workflow friction.",
        "who_we_help": f"We support teams led by {prospect_title} roles focused on outbound quality.",
        "outcomes": [
            "Raise outbound message relevance for priority accounts.",
            "Keep rep-written copy consistent across higher send volume.",
            "Reduce manual rewrite time before outbound goes live.",
        ],
        "proof_points": proof_points,
        "differentiation": differentiation,
        "forbidden_positioning": forbidden_positioning,
    }


def _extract_signals(session: dict[str, Any]) -> list[str]:
    candidates = [compact(item) for item in (session.get("allowed_facts") or []) if compact(item)]
    if not candidates:
        candidates = split_sentences(compact(session.get("research_text_raw") or session.get("research_text")))

    signals: list[str] = []
    for sentence in candidates:
        lowered = sentence.lower()
        if "wikipedia" in lowered:
            continue
        if any(phrase in lowered for phrase in _WIKI_PHRASES):
            continue
        if len(_WORD_PATTERN.findall(sentence)) < 5:
            continue
        signals.append(_trim_words(sentence, 16))
        if len(signals) >= 2:
            break

    while len(signals) < 2:
        signals.append("No specific verified trigger was provided in the research text.")
    return signals[:2]


def build_prospect_intel(session: dict[str, Any]) -> dict[str, Any]:
    prospect = session.get("prospect") or {}
    first_name = derive_first_name(session.get("prospect_first_name") or prospect.get("name")) or "there"
    title = compact(prospect.get("title")) or "unknown"
    company_name = compact(prospect.get("company")) or "unknown"
    signals = _extract_signals(session)
    signal_known = all("no specific verified trigger" not in signal.lower() for signal in signals)

    if signal_known:
        why_it_matters = (
            f"These signals suggest {title} ownership of reply quality and messaging consistency may be an active priority."
        )
    else:
        why_it_matters = f"{title} teams are typically measured on quality and conversion consistency in outbound."

    return {
        "prospect_first_name": first_name,
        "title": title,
        "company_name": company_name,
        "2_signals": signals,
        "why_it_matters": why_it_matters,
        "risk_or_cost_of_inaction": (
            "Without tighter outbound quality control, teams usually absorb lower reply efficiency and more rewrite overhead."
        ),
        "personalization_angle": _trim_words(signals[0], 14),
    }


def build_message_plan(
    *,
    session: dict[str, Any],
    user_company_intel: dict[str, Any],
    prospect_intel: dict[str, Any],
    subject: str,
    body: str,
    cta_line: str,
) -> dict[str, Any]:
    offer_lock = compact(session.get("offer_lock")) or "the offer"
    body_sentences = [
        re.sub(r"^(?:Hi|Hello)\s+[^,\n]+,\s*", "", sentence, flags=re.IGNORECASE).strip()
        for sentence in [
            sentence
        for sentence in split_sentences(compact(body))
        if sentence and not _SIGNOFF_PATTERN.search(sentence) and compact(sentence) != compact(cta_line)
        ]
    ]
    body_sentences = [sentence for sentence in body_sentences if sentence]
    hook_sentence = _trim_words(body_sentences[0] if body_sentences else prospect_intel["personalization_angle"], 16)
    value_sentence_1 = _trim_words(f"{offer_lock} keeps outbound quality controlled while reps move fast.", 16)
    value_sentence_2 = _trim_words(user_company_intel["outcomes"][0], 16)
    proof_points = user_company_intel.get("proof_points") or []

    plan: dict[str, Any] = {
        "chosen_hook_type": "trigger"
        if "no specific verified trigger" not in prospect_intel["2_signals"][0].lower()
        else "role-based",
        "hook_sentence": hook_sentence,
        "value_sentence_1": value_sentence_1,
        "value_sentence_2": value_sentence_2,
        "cta_line": cta_line,
    }
    if proof_points:
        plan["proof_sentence"] = _trim_words(proof_points[0], 18)
    return plan


def _content_lines_from_body(body: str, cta_line: str) -> list[str]:
    lines = _non_empty_lines(body)
    payload = " ".join(line for line in lines if not _GREETING_PATTERN.match(line) and compact(line) != compact(cta_line))
    candidates = [compact(sentence) for sentence in split_sentences(payload) if compact(sentence)]
    filtered: list[str] = []
    for line in candidates:
        line = re.sub(r"^(?:Hi|Hello)\s+[^,\n]+,\s*", "", line, flags=re.IGNORECASE).strip()
        if not line:
            continue
        lowered = line.lower()
        if _SIGNOFF_PATTERN.search(line):
            continue
        if any(phrase in lowered for phrase in _WIKI_PHRASES):
            continue
        filtered.append(_trim_words(line, 24))
    return _dedupe_lines(filtered)


def _fit_word_budget(body: str, *, cta_line: str, first_name: str) -> str:
    lines = _non_empty_lines(body)
    if not lines:
        return f"Hi {first_name},\n{cta_line}"

    greeting = f"Hi {first_name},"
    content = [line for line in lines if not _GREETING_PATTERN.match(line) and compact(line) != compact(cta_line)]
    if _word_count("\n".join([greeting, *content, cta_line])) < 80:
        fillers = [
            "That keeps quality consistent when send volume spikes and account context shifts across campaigns.",
            "The practical upside is cleaner messaging, faster approvals, and less manual rewrite work for reps.",
            "Teams usually adopt it in one motion so reps keep control while standards and compliance stay tight.",
            "It also reduces back-and-forth edits before send, which protects pacing and keeps outbound experiments moving.",
            "Managers get a cleaner QA baseline, so coaching time goes to strategy instead of line edits.",
        ]
        for filler in fillers:
            if filler.lower() in {item.lower() for item in content}:
                continue
            content.append(filler)
            if _word_count("\n".join([greeting, *content, cta_line])) >= 80:
                break

    while _word_count("\n".join([greeting, *content, cta_line])) > 130 and len(content) > 3:
        content.pop()

    while _word_count("\n".join([greeting, *content, cta_line])) > 130:
        longest_idx = max(range(len(content)), key=lambda idx: _word_count(content[idx])) if content else -1
        if longest_idx < 0 or _word_count(content[longest_idx]) <= 8:
            break
        content[longest_idx] = _trim_words(content[longest_idx], max(8, _word_count(content[longest_idx]) - 3))

    return "\n".join([greeting, *content, cta_line]).strip()


def _compose_email_body(
    *,
    first_name: str,
    source_body: str,
    message_plan: dict[str, Any],
    cta_line: str,
) -> str:
    lines = _content_lines_from_body(source_body, cta_line)
    if not lines:
        lines = [
            message_plan["hook_sentence"],
            message_plan["value_sentence_1"],
            message_plan["value_sentence_2"],
        ]
    else:
        required = [message_plan["hook_sentence"], message_plan["value_sentence_1"], message_plan["value_sentence_2"]]
        for sentence in required:
            if sentence.lower() not in {item.lower() for item in lines}:
                lines.append(sentence)

    lines = _dedupe_lines([_trim_words(item, 24) for item in lines if compact(item)])
    if message_plan.get("proof_sentence"):
        proof = _trim_words(message_plan["proof_sentence"], 18)
        if proof.lower() not in {item.lower() for item in lines}:
            lines.append(proof)

    composed = "\n".join([f"Hi {first_name},", *lines[:4], cta_line]).strip()
    repaired = enforce_cta_last_line(composed, cta_line=cta_line)
    repaired_lines = _non_empty_lines(repaired)
    filtered_lines: list[str] = []
    greeting = f"Hi {first_name},"
    greeting_seen = False
    for line in repaired_lines:
        if _GREETING_PATTERN.match(line):
            if greeting_seen:
                continue
            filtered_lines.append(greeting)
            greeting_seen = True
            continue
        filtered_lines.append(line)
    if not greeting_seen:
        filtered_lines.insert(0, greeting)
    if filtered_lines[-1] != cta_line:
        filtered_lines = [line for line in filtered_lines if compact(line) != compact(cta_line)]
        filtered_lines.append(cta_line)
    return _fit_word_budget("\n".join(filtered_lines), cta_line=cta_line, first_name=first_name)


def _has_repetition(body: str, *, cta_line: str) -> bool:
    lines = _non_empty_lines(body)
    cta = compact(cta_line)
    content_lines = [line for line in lines if not _GREETING_PATTERN.match(line) and line != cta]
    sentence_keys: set[str] = set()
    sentences = [compact(sentence) for sentence in split_sentences(" ".join(content_lines)) if compact(sentence)]
    for sentence in sentences:
        key = compact(sentence).lower()
        if not key:
            continue
        if key in sentence_keys:
            return True
        sentence_keys.add(key)

    phrase_to_sentence: dict[str, int] = {}
    for sentence_index, sentence in enumerate(sentences):
        tokens = re.findall(r"[a-z0-9']+", sentence.lower())
        sentence_phrases = {" ".join(tokens[idx : idx + 5]) for idx in range(0, max(0, len(tokens) - 4))}
        for phrase in sentence_phrases:
            prior = phrase_to_sentence.get(phrase)
            if prior is not None and prior != sentence_index:
                return True
            phrase_to_sentence[phrase] = sentence_index

    # Additional safety: repeated full lines (case-insensitive) across body lines.
    seen_ngrams: set[str] = set()
    for line in content_lines:
        key = line.lower()
        if key in seen_ngrams:
            return True
        seen_ngrams.add(key)
    return False


def run_self_check(body: str, *, cta_line: str) -> dict[str, Any]:
    lines = _non_empty_lines(body)
    cta = compact(cta_line)
    cta_count = sum(1 for line in lines if line == cta)
    last_non_empty = lines[-1] if lines else ""
    greeting_count = sum(1 for line in lines if _GREETING_PATTERN.match(line))
    body_lower = compact(body).lower()
    no_signoff_present = _SIGNOFF_PATTERN.search(body_lower) is None
    no_wikipedia_opener = not any(phrase in body_lower for phrase in _WIKI_PHRASES)

    return {
        "cta_is_last_line": bool(lines) and last_non_empty == cta,
        "cta_count": cta_count,
        "no_signoff_present": no_signoff_present,
        "no_double_greeting": greeting_count == 1 and "hello hi" not in body_lower and "hi hello" not in body_lower,
        "no_wikipedia_opener": no_wikipedia_opener,
        "repetition_detected": _has_repetition(body, cta_line=cta_line),
        "word_count": _word_count(body),
    }


def _check_failed(self_check: dict[str, Any]) -> bool:
    return not (
        self_check["cta_is_last_line"]
        and self_check["cta_count"] == 1
        and self_check["no_signoff_present"]
        and self_check["no_double_greeting"]
        and self_check["no_wikipedia_opener"]
        and (self_check["repetition_detected"] is False)
    )


def _repair_body(body: str, *, cta_line: str, first_name: str) -> str:
    lines = _non_empty_lines(body)
    cleaned: list[str] = []
    greeting = f"Hi {first_name},"
    greeting_added = False
    for line in lines:
        lowered = line.lower()
        if _SIGNOFF_PATTERN.search(lowered):
            continue
        if any(phrase in lowered for phrase in _WIKI_PHRASES):
            continue
        if _GREETING_PATTERN.match(line):
            if greeting_added:
                continue
            cleaned.append(greeting)
            greeting_added = True
            continue
        cleaned.append(line)

    cleaned = _dedupe_lines(cleaned)
    if not greeting_added:
        cleaned.insert(0, greeting)
    repaired = enforce_cta_last_line("\n".join(cleaned), cta_line=cta_line)
    return _fit_word_budget(repaired, cta_line=cta_line, first_name=first_name)


def _infer_failure_source(
    *,
    self_check: dict[str, Any],
    effective_model_used: str,
    pipeline_meta: dict[str, Any] | None,
    repair_passes: int,
) -> str:
    if not self_check["no_signoff_present"]:
        return "normalization"
    if self_check["cta_count"] != 1 or not self_check["cta_is_last_line"]:
        return "validator"
    if self_check["repetition_detected"]:
        return "UI_append"
    model_hint = compact((pipeline_meta or {}).get("model_hint")).lower()
    effective = compact(effective_model_used).lower()
    if model_hint and effective and model_hint != effective:
        return "cache_mix"
    if repair_passes > 0:
        return "prompt"
    return "unknown"


def _debug_mode(mode: str, pipeline_meta: dict[str, Any] | None) -> str:
    explicit = compact((pipeline_meta or {}).get("mode")).lower()
    if explicit in {"preview", "generate"}:
        return explicit
    return "generate" if mode else "unknown"


def build_rc_tco_output(
    *,
    session: dict[str, Any],
    subject: str,
    body: str,
    mode: str,
    effective_model_used: str,
    pipeline_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cta_line = _resolve_cta_line(session)
    user_company_intel = build_user_company_intel(session)
    prospect_intel = build_prospect_intel(session)
    message_plan = build_message_plan(
        session=session,
        user_company_intel=user_company_intel,
        prospect_intel=prospect_intel,
        subject=subject,
        body=body,
        cta_line=cta_line,
    )

    first_name = prospect_intel["prospect_first_name"] or "there"
    subject_text = _trim_words(compact(subject) or compact(session.get("offer_lock")) or "Quick question", 7)
    email_body = _compose_email_body(
        first_name=first_name,
        source_body=body,
        message_plan=message_plan,
        cta_line=cta_line,
    )

    self_check = run_self_check(email_body, cta_line=cta_line)
    repair_passes = 0
    while _check_failed(self_check) and repair_passes < 2:
        repair_passes += 1
        email_body = _repair_body(email_body, cta_line=cta_line, first_name=first_name)
        self_check = run_self_check(email_body, cta_line=cta_line)

    failure_source = _infer_failure_source(
        self_check=self_check,
        effective_model_used=effective_model_used,
        pipeline_meta=pipeline_meta,
        repair_passes=repair_passes,
    )

    debug_notes: list[str] = []
    if not self_check["no_signoff_present"]:
        debug_notes.append("Signoff phrase detected before final CTA and removed by normalization.")
    if self_check["cta_count"] != 1:
        debug_notes.append("CTA cardinality violation detected; enforced a single canonical CTA line.")
    if self_check["repetition_detected"]:
        debug_notes.append("Repeated sentence or 5-gram pattern remained after repair pass budget.")
    if repair_passes > 0:
        debug_notes.append(f"Deterministic repair passes applied: {repair_passes}.")
    debug_notes = debug_notes[:4]

    backend_guardrails = [
        "Run enforce_cta_last_line as mandatory post-processor before streaming output.",
        "Reject payload when self_check cta_count != 1 or CTA is not last line.",
        "Cap deterministic repair loop to 2 passes and emit structured failure metric.",
        "Log effective_model_used and fallback_reason on every non-primary model response.",
    ][:4]
    frontend_guardrails = [
        "When response_contract=rc_tco_json_v1, parse full stream JSON before rendering body text.",
        "Warn if token stream contains duplicate sequence or repeated CTA-like line.",
        "Display preview violations as non-blocking warnings; do not trigger auto-regeneration in warn mode.",
    ][:3]

    return {
        "user_company_intel": user_company_intel,
        "prospect_intel": prospect_intel,
        "message_plan": message_plan,
        "email": {
            "subject": subject_text,
            "body": email_body,
        },
        "self_check": self_check,
        "debug": {
            "effective_model_used": compact(effective_model_used) or "unknown",
            "mode": _debug_mode(mode, pipeline_meta),
            "suspected_failure_source": failure_source,
            "notes": debug_notes,
            "suggested_backend_guardrails": backend_guardrails,
            "suggested_frontend_guardrails": frontend_guardrails,
        },
    }


def validate_rc_tco_payload(payload: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    required_top = {"user_company_intel", "prospect_intel", "message_plan", "email", "self_check", "debug"}
    missing = sorted(required_top - set(payload.keys()))
    for item in missing:
        violations.append(f"missing_top_level_key:{item}")

    email = payload.get("email")
    if not isinstance(email, dict):
        violations.append("email_not_object")
        return violations
    body = compact(email.get("body"))
    if not isinstance(email.get("subject"), str) or not compact(email.get("subject")):
        violations.append("missing_email_subject")
    if not body:
        violations.append("missing_email_body")

    self_check = payload.get("self_check")
    if not isinstance(self_check, dict):
        violations.append("missing_self_check")
    else:
        expected = {"cta_is_last_line", "cta_count", "no_signoff_present", "no_double_greeting", "no_wikipedia_opener", "repetition_detected", "word_count"}
        for key in sorted(expected):
            if key not in self_check:
                violations.append(f"missing_self_check_key:{key}")

    debug = payload.get("debug")
    if not isinstance(debug, dict):
        violations.append("missing_debug")
    else:
        if not isinstance(debug.get("effective_model_used"), str):
            violations.append("debug_missing_effective_model")
        if not isinstance(debug.get("mode"), str):
            violations.append("debug_missing_mode")
        if not isinstance(debug.get("suspected_failure_source"), str):
            violations.append("debug_missing_failure_source")
    return violations


def validate_rc_tco_json(raw: str) -> list[str]:
    try:
        payload = json.loads(raw or "")
    except Exception:
        return ["invalid_rc_tco_json"]
    if not isinstance(payload, dict):
        return ["invalid_rc_tco_json_object"]
    return validate_rc_tco_payload(payload)
