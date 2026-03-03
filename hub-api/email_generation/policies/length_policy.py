"""Email body length and composition policy."""

from __future__ import annotations

import re

from email_generation.text_utils import (
    cap_repeated_ngrams,
    compact,
    dedupe_sentence_list,
    sentence_key,
    split_sentences,
    word_count,
)

POLICY_VERSION = "1.0.0"
_TRUSTED_BY_PATTERN = re.compile(
    r"\b(trusted by|used by|customers include|clients include|brands like|companies like)\b",
    re.IGNORECASE,
)


def _offer_lock_sentence_case(value: str) -> str:
    cleaned = compact(value)
    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:].lower()


def _sanitize_proof_candidate(value: str) -> str:
    text = compact(value)
    if not text:
        return ""
    if _TRUSTED_BY_PATTERN.search(text):
        return ""
    # Reduce title-case token bursts in one sentence while preserving gist.
    normalized = text.lower().strip(" ,;")
    if not normalized:
        return ""
    if normalized[-1] not in ".!?":
        normalized += "."
    return normalized[0].upper() + normalized[1:]


def body_word_range(length_short_long: int) -> tuple[int, int]:
    """Return (min_words, max_words) for the given length slider value (0–100)."""
    if length_short_long <= 33:
        return 55, 75
    if length_short_long <= 66:
        return 75, 110
    return 110, 160


def check_length_violation(body: str, length_short_long: int) -> str | None:
    """Return a violation code string if the body word count is out of range, else None."""
    min_words, max_words = body_word_range(length_short_long)
    words = word_count(body)
    if words < min_words or words > max_words:
        return f"length_out_of_range:{words}_expected_{min_words}_{max_words}"
    return None


def long_mode_section_pool(
    *,
    company_notes: str | None,
    allowed_facts: list[str] | None,
    offer_lock: str,
    company: str,
    forbidden_terms: list[str] | None = None,
) -> list[str]:
    """Build proof lines, mechanism, deliverable, and risk statements for long-mode bodies."""
    note_sentences = split_sentences(company_notes)
    fact_sentences = split_sentences(" ".join(allowed_facts or []))
    proof_candidates = [
        _sanitize_proof_candidate(sentence)
        for sentence in dedupe_sentence_list(note_sentences + fact_sentences)
    ]
    proof_candidates = [sentence for sentence in proof_candidates if sentence]
    proof_line = ""
    if proof_candidates:
        proof_line = proof_candidates[0]

    offer_lock_phrase = _offer_lock_sentence_case(offer_lock)
    mechanism_line = (
        f"{offer_lock_phrase} helps teams detect risky patterns, prioritize high-impact cases, and route follow-up actions without losing context."
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
    # Keep a richer pool; downstream composition/dedupe already suppresses repetition.
    return sanitized[:4]


def compose_body_without_padding_loops(
    *,
    base_sentences: list[str],
    extra_sections: list[str],
    cta_line: str,
    min_words: int,
    max_words: int,
) -> str:
    """Compose email body with deduplication and word limits, without padding loops."""
    def _count_words(value: str) -> int:
        return len(re.findall(r"[A-Za-z0-9']+", value))

    cta = compact(cta_line)
    cta_words = _count_words(cta)
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
    if _count_words(main_text) < min_main:
        existing = set(sentence_key(line) for line in split_sentences(main_text))
        additions: list[str] = []
        for section in extra_sections:
            key = sentence_key(section)
            if not key or key in existing:
                continue
            existing.add(key)
            additions.append(section)
            candidate = " ".join([main_text, *additions]).strip()
            if _count_words(candidate) >= min_main:
                main_text = candidate
                break
        else:
            if additions:
                main_text = " ".join([main_text, *additions]).strip()

    # Final trim to max in case additions pushed over.
    words_list = re.findall(r"\S+", main_text)
    if len(words_list) > max_main:
        main_text = " ".join(words_list[:max_main]).strip()

    # Post-composition dedup: remove sentence-level duplicates and re-cap n-grams
    post_sentences = dedupe_sentence_list(split_sentences(main_text))
    capped_post_sentences = cap_repeated_ngrams(post_sentences, max_count=1, min_n=3, max_n=5)
    capped_text = " ".join(capped_post_sentences).strip()
    if _count_words(capped_text) >= min_main:
        main_text = capped_text
    else:
        # Preserve min-length guarantees when n-gram capping trims too aggressively.
        main_text = " ".join(post_sentences).strip()

    if _count_words(main_text) < min_main:
        existing = set(sentence_key(line) for line in split_sentences(main_text))
        for section in dedupe_sentence_list([*extra_sections, *base_sentences]):
            key = sentence_key(section)
            if not key or key in existing:
                continue
            candidate = " ".join([main_text, section]).strip() if main_text else section
            if _count_words(candidate) > max_main:
                continue
            main_text = candidate
            existing.add(key)
            if _count_words(main_text) >= min_main:
                break
        if _count_words(main_text) < min_main:
            filler_sentences = [
                "The approach stays practical for weekly execution across teams.",
                "It keeps quality controls clear without adding extra workflow burden.",
                "That helps maintain consistent outbound standards as volume grows.",
            ]
            for filler in filler_sentences:
                key = sentence_key(filler)
                if key in existing:
                    continue
                candidate = " ".join([main_text, filler]).strip() if main_text else filler
                if _count_words(candidate) > max_main:
                    continue
                main_text = candidate
                existing.add(key)
                if _count_words(main_text) >= min_main:
                    break

    return f"{main_text}\n\n{cta}".strip() if cta else main_text.strip()
