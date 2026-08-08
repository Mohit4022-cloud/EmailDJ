"""PII redaction service with Presidio-first and regex fallback behavior."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from hashlib import sha256

logger = logging.getLogger(__name__)


@dataclass
class RedactionResult:
    redacted: str
    entities_found: list = field(default_factory=list)
    redaction_stats: dict = field(default_factory=dict)
    vault: dict[str, str] = field(default_factory=dict)


try:
    from presidio_analyzer import AnalyzerEngine

    _analyzer = AnalyzerEngine(supported_languages=["en"])
    _presidio_ready = True
except Exception:
    _analyzer = None
    _presidio_ready = False

_warned_fallback = False

_REGEX_FALLBACK = {
    "EMAIL_ADDRESS": re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+"),
    "PHONE_NUMBER": re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
}


def _token_for(entity_type: str, raw_value: str) -> str:
    digest = sha256(f"{entity_type}:{raw_value}".encode("utf-8")).hexdigest()[:12].upper()
    return f"[{entity_type}_{digest}]"


def _person_output_value(raw_value: str) -> str:
    tokens = [part.strip(",.!?:;") for part in str(raw_value or "").split() if part.strip(",.!?:;")]
    while tokens and tokens[0].lower().rstrip(".") in {"mr", "mrs", "ms", "dr", "prof", "sir", "madam"}:
        tokens.pop(0)
    return tokens[0] if tokens else raw_value


def _replace_entities(text: str, entities: list) -> tuple[str, dict[str, str]]:
    selected = []
    occupied: list[tuple[int, int]] = []
    for entity in sorted(entities, key=lambda item: (item.start, -(item.end - item.start), -float(getattr(item, "score", 0) or 0))):
        start, end = int(entity.start), int(entity.end)
        if start < 0 or end <= start or end > len(text):
            continue
        if any(not (end <= used_start or start >= used_end) for used_start, used_end in occupied):
            continue
        selected.append(entity)
        occupied.append((start, end))

    vault: dict[str, str] = {}
    redacted = text
    for entity in sorted(selected, key=lambda item: item.start, reverse=True):
        raw_value = text[int(entity.start) : int(entity.end)]
        entity_type = str(entity.entity_type)
        token = _token_for(entity_type, raw_value)
        vault[token] = _person_output_value(raw_value) if entity_type == "PERSON" else raw_value
        redacted = redacted[: int(entity.start)] + token + redacted[int(entity.end) :]
    return redacted, vault


def analyze_and_anonymize(text: str) -> RedactionResult:
    global _warned_fallback
    if not text:
        return RedactionResult(redacted=text)

    if _presidio_ready:
        entities = _analyzer.analyze(
            text=text,
            language="en",
            entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "ORGANIZATION"],
        )
        redacted, vault = _replace_entities(text, entities)
        stats: dict[str, int] = {}
        for entity in entities:
            stats[entity.entity_type] = stats.get(entity.entity_type, 0) + 1
        return RedactionResult(
            redacted=redacted,
            entities_found=[{"type": e.entity_type, "start": e.start, "end": e.end} for e in entities],
            redaction_stats=stats,
            vault=vault,
        )

    if not _warned_fallback:
        logger.warning("presidio_unavailable_regex_fallback_active")
        _warned_fallback = True

    redacted = text
    stats: dict[str, int] = {}
    for etype, pattern in _REGEX_FALLBACK.items():
        matches = list(pattern.finditer(redacted))
        if not matches:
            continue
        stats[etype] = len(matches)
        for match in reversed(matches):
            raw_value = match.group(0)
            token = _token_for(etype, raw_value)
            redacted = redacted[: match.start()] + token + redacted[match.end() :]
    vault = {}
    for etype, pattern in _REGEX_FALLBACK.items():
        for match in pattern.finditer(text):
            raw_value = match.group(0)
            vault[_token_for(etype, raw_value)] = raw_value
    return RedactionResult(redacted=redacted, redaction_stats=stats, vault=vault)
