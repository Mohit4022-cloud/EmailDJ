"""Shared output-enforcement helpers for main and preset-preview pipelines."""

from __future__ import annotations

import re
from typing import Iterable


_GENERIC_AI_OPENER_PATTERN = re.compile(
    r"^(?:(?:hi|hello)\s+[^,\n]+,\s*)?as\s+[a-z0-9&.\- ]+\s+scales\s+(?:its|their)\s+(?:enterprise\s+)?ai\s+initiatives[, ]",
    re.IGNORECASE,
)
_GENERIC_AI_RESEARCH_PATTERN = re.compile(r"scales\s+(?:its|their)\s+(?:enterprise\s+)?ai\s+initiatives", re.IGNORECASE)
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


def compact(value: str | None) -> str:
    return " ".join(str(value or "").split())


def split_sentences(value: str | None) -> list[str]:
    text = compact(value)
    if not text:
        return []
    return [part.strip() for part in _SENTENCE_SPLIT_PATTERN.split(text) if part.strip()]


def sentence_key(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", compact(value).lower())


def derive_first_name(raw_name: str | None) -> str:
    tokens = [token.strip(",.!?:;") for token in compact(raw_name).split() if token.strip(",.!?:;")]
    while tokens and tokens[0].lower().rstrip(".") in {"mr", "mrs", "ms", "dr", "prof", "sir", "madam"}:
        tokens.pop(0)
    return tokens[0] if tokens else ""


def enforce_first_name_greeting(text: str, first_name: str | None) -> str:
    body = compact(text)
    if not body:
        return ""
    greeting = "Hi"
    greeting_match = re.match(r"^(hi|hello)\s+[^,\n]+,\s*", body, flags=re.IGNORECASE)
    if greeting_match:
        greeting = "Hello" if greeting_match.group(1).lower() == "hello" else "Hi"
    stripped = re.sub(r"^(?:hi|hello)\s+[^,\n]+,\s*", "", body, flags=re.IGNORECASE)
    name = derive_first_name(first_name) or "there"
    return f"{greeting} {name}, {stripped}".strip()


def dedupe_sentence_list(sentences: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        cleaned = compact(sentence)
        if not cleaned:
            continue
        key = sentence_key(cleaned)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output


def dedupe_sentences_text(text: str) -> str:
    return " ".join(dedupe_sentence_list(split_sentences(text))).strip()


def _sentence_ngrams(sentence: str, n: int) -> list[str]:
    words = re.findall(r"[a-z0-9']+", sentence.lower())
    if len(words) < n:
        return []
    return [" ".join(words[index : index + n]) for index in range(len(words) - n + 1)]


def cap_repeated_ngrams(sentences: list[str], max_count: int = 2, min_n: int = 3, max_n: int = 5) -> list[str]:
    counts: dict[str, int] = {}
    output: list[str] = []
    for sentence in sentences:
        reject = False
        sentence_counts: dict[str, int] = {}
        for n in range(min_n, max_n + 1):
            for ngram in _sentence_ngrams(sentence, n):
                sentence_counts[ngram] = sentence_counts.get(ngram, 0) + 1
                if counts.get(ngram, 0) + sentence_counts[ngram] > max_count:
                    reject = True
                    break
            if reject:
                break
        if reject:
            continue
        output.append(sentence)
        for ngram, value in sentence_counts.items():
            counts[ngram] = counts.get(ngram, 0) + value
    return output


def _stable_pick(values: list[str], seed: str) -> str:
    if not values:
        return ""
    if not seed:
        return values[0]
    index = sum(ord(ch) for ch in seed) % len(values)
    return values[index]


def sanitize_generic_ai_opener(
    text: str,
    *,
    research_text: str | None,
    hook_strategy: str | None,
    company: str | None,
    risk_surface: str | None,
) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return ""

    opener_index = -1
    for index, sentence in enumerate(sentences):
        if _GENERIC_AI_OPENER_PATTERN.search(sentence):
            opener_index = index
            break
    if opener_index < 0:
        return compact(text)

    research_ok = bool(_GENERIC_AI_RESEARCH_PATTERN.search(compact(research_text)))
    if research_ok and (hook_strategy or "").strip().lower() == "research_anchored":
        return " ".join(sentences).strip()

    account = compact(company) or "your team"
    surface = compact(risk_surface) or "your enforcement workflow"
    replacements = [
        f"Brand-risk exposure usually rises when counterfeit enforcement queues stall at {account}.",
        f"Counterfeit risk is hardest to contain when detection and action workflows drift apart in {surface}.",
        "The practical win is reducing counterfeit exposure while improving enforcement throughput.",
    ]
    sentences[opener_index] = _stable_pick(replacements, f"{account}|{surface}|{hook_strategy or ''}")
    return " ".join(sentences).strip()


def long_mode_section_pool(
    *,
    company_notes: str | None,
    allowed_facts: list[str] | None,
    offer_lock: str,
    company: str,
    forbidden_terms: list[str] | None = None,
) -> list[str]:
    note_sentences = split_sentences(company_notes)
    fact_sentences = split_sentences(" ".join(allowed_facts or []))
    proof_candidates = dedupe_sentence_list(note_sentences + fact_sentences)
    proof_line = ""
    if proof_candidates:
        proof_slice = proof_candidates[:2]
        if len(proof_slice) == 1:
            proof_line = f"One proof point from your notes: {proof_slice[0]}"
        else:
            proof_line = f"Two proof points from your notes: {proof_slice[0]}; {proof_slice[1]}"

    mechanism_line = (
        f"{offer_lock} helps teams detect risky patterns, prioritize high-impact cases, and route follow-up actions without losing context."
    )
    deliverable_line = (
        "In week one, we'd run a focused sweep and teardown, then hand over a prioritized enforcement workflow by risk tier."
    )
    risk_line = (
        f"That lowers counterfeit exposure, protects brand trust, and improves enforcement throughput for {company}."
    )

    pool = [
        proof_line,
        mechanism_line,
        deliverable_line,
        risk_line,
    ]
    filtered_terms: list[str] = []
    seen: set[str] = set()
    offer_key = compact(offer_lock).lower()
    for term in forbidden_terms or []:
        cleaned = compact(term)
        key = cleaned.lower()
        if not key or key == offer_key or key in seen:
            continue
        seen.add(key)
        filtered_terms.append(cleaned)

    sanitized: list[str] = []
    for line in pool:
        cleaned_line = compact(line)
        if not cleaned_line:
            continue
        for term in filtered_terms:
            if " " in term:
                cleaned_line = re.sub(re.escape(term), "", cleaned_line, flags=re.IGNORECASE)
            else:
                cleaned_line = re.sub(rf"\b{re.escape(term)}\b", "", cleaned_line, flags=re.IGNORECASE)
        cleaned_line = re.sub(r"\s{2,}", " ", cleaned_line)
        cleaned_line = re.sub(r"\s+([,.;!?])", r"\1", cleaned_line).strip(" ,;")
        if cleaned_line:
            sanitized.append(cleaned_line)
    return sanitized


def compose_body_without_padding_loops(
    *,
    base_sentences: list[str],
    extra_sections: list[str],
    cta_line: str,
    min_words: int,
    max_words: int,
) -> str:
    cta = compact(cta_line)
    cta_words = len(re.findall(r"[A-Za-z0-9']+", cta))
    min_main = max(20, min_words - cta_words)
    max_main = max(min_main, max_words - cta_words)

    ordered = dedupe_sentence_list([*base_sentences, *extra_sections])
    filtered = cap_repeated_ngrams(ordered, max_count=2, min_n=3, max_n=5)

    selected: list[str] = []
    selected_words = 0
    for sentence in filtered:
        count = len(re.findall(r"[A-Za-z0-9']+", sentence))
        if count == 0:
            continue
        if selected_words + count > max_main and selected:
            continue
        selected.append(sentence)
        selected_words += count

    if not selected:
        selected = [compact(cta)] if cta else []

    if selected_words > max_main:
        words = re.findall(r"\S+", " ".join(selected))[:max_main]
        main_text = " ".join(words)
    else:
        main_text = " ".join(selected)

    # Add finite unique sections only once (no loops) when below minimum.
    if len(re.findall(r"[A-Za-z0-9']+", main_text)) < min_main:
        existing = set(sentence_key(line) for line in split_sentences(main_text))
        additions: list[str] = []
        for section in extra_sections:
            key = sentence_key(section)
            if not key or key in existing:
                continue
            existing.add(key)
            additions.append(section)
            candidate = " ".join([main_text, *additions]).strip()
            if len(re.findall(r"[A-Za-z0-9']+", candidate)) >= min_main:
                main_text = candidate
                break
        else:
            if additions:
                main_text = " ".join([main_text, *additions]).strip()

    # Final trim to max in case additions pushed over.
    words = re.findall(r"\S+", main_text)
    if len(words) > max_main:
        main_text = " ".join(words[:max_main]).strip()

    return f"{main_text}\n\n{cta}".strip() if cta else main_text.strip()
