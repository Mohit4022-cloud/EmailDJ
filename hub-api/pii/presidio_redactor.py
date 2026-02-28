"""PII redaction service with Presidio-first and regex fallback behavior."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_SYNTHETIC_NAMES = [
    "Alex",
    "Jordan",
    "Morgan",
    "Casey",
    "Taylor",
    "Riley",
    "Quinn",
    "Sam",
    "Drew",
    "Blake",
]


@dataclass
class RedactionResult:
    redacted: str
    entities_found: list = field(default_factory=list)
    redaction_stats: dict = field(default_factory=dict)


try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import OperatorConfig

    _analyzer = AnalyzerEngine(supported_languages=["en"])
    _anonymizer = AnonymizerEngine()
    _presidio_ready = True
except Exception:
    _analyzer = None
    _anonymizer = None
    _presidio_ready = False

_warned_fallback = False

_REGEX_FALLBACK = {
    "EMAIL_ADDRESS": re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+"),
    "PHONE_NUMBER": re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
}


def _synthetic_name(seed: str) -> str:
    idx = abs(hash(seed)) % len(_SYNTHETIC_NAMES)
    return _SYNTHETIC_NAMES[idx]


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
        operators = {
            "DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"}),
            "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "anonymized@[DOMAIN_REDACTED].com"}),
            "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE_REDACTED]"}),
            "PERSON": OperatorConfig("replace", {"new_value": _synthetic_name(text)}),
        }
        result = _anonymizer.anonymize(text=text, analyzer_results=entities, operators=operators)
        stats: dict[str, int] = {}
        for entity in entities:
            stats[entity.entity_type] = stats.get(entity.entity_type, 0) + 1
        return RedactionResult(
            redacted=result.text,
            entities_found=[{"type": e.entity_type, "start": e.start, "end": e.end} for e in entities],
            redaction_stats=stats,
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
        replacement = "[EMAIL_REDACTED]" if etype == "EMAIL_ADDRESS" else "[PHONE_REDACTED]"
        redacted = pattern.sub(replacement, redacted)
    return RedactionResult(redacted=redacted, redaction_stats=stats)
