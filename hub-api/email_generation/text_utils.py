"""Shared text infrastructure used by policy modules and email generation helpers."""

from __future__ import annotations

import re
from typing import Iterable


_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


# ---------------------------------------------------------------------------
# Core text primitives
# ---------------------------------------------------------------------------


def compact(value: str | None) -> str:
    """Collapse all whitespace to single spaces and strip."""
    return " ".join(str(value or "").split())


def split_sentences(value: str | None) -> list[str]:
    """Split text into sentences on [.!?] boundaries."""
    text = compact(value)
    if not text:
        return []
    return [part.strip() for part in _SENTENCE_SPLIT_PATTERN.split(text) if part.strip()]


def sentence_key(value: str) -> str:
    """Normalized lowercase alphanumeric key for deduplication."""
    return re.sub(r"[^a-z0-9 ]", "", compact(value).lower())


def dedupe_sentence_list(sentences: Iterable[str]) -> list[str]:
    """Remove duplicate sentences by normalized key, preserving order."""
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
    """Deduplicate sentences in a text block, returning joined result."""
    return " ".join(dedupe_sentence_list(split_sentences(text))).strip()


def _sentence_ngrams(sentence: str, n: int) -> list[str]:
    """Extract all n-grams from a sentence."""
    words = re.findall(r"[a-z0-9']+", sentence.lower())
    if len(words) < n:
        return []
    return [" ".join(words[index : index + n]) for index in range(len(words) - n + 1)]


def cap_repeated_ngrams(sentences: list[str], max_count: int = 2, min_n: int = 3, max_n: int = 5) -> list[str]:
    """Drop sentences that push any n-gram count above max_count."""
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
    """Deterministic selection from list based on seed string."""
    if not values:
        return ""
    if not seed:
        return values[0]
    index = sum(ord(ch) for ch in seed) % len(values)
    return values[index]


# ---------------------------------------------------------------------------
# Whole-word matching and counting helpers (moved from compliance_rules)
# ---------------------------------------------------------------------------


def contains_term(text_lower: str, term: str) -> bool:
    """Check if a term appears as a whole word (or phrase) in lowercase text."""
    if " " in term:
        return term in text_lower
    return re.search(rf"\b{re.escape(term)}\b", text_lower) is not None


def word_count(text: str) -> int:
    """Count word tokens (alphanumeric + apostrophes)."""
    return len(re.findall(r"[A-Za-z0-9']+", text))


def collapse_ws(value: str) -> str:
    """Collapse all whitespace to single spaces and strip."""
    return " ".join(value.split())
