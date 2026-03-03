from __future__ import annotations

import re
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))


def _subject_body(draft: str) -> tuple[str, str]:
    from email_generation.remix_engine import _extract_subject_and_body

    return _extract_subject_and_body(draft)


def _narrative_without_cta(body: str, cta: str) -> str:
    lines = [line.strip() for line in (body or "").splitlines() if line.strip()]
    output: list[str] = []
    removed = False
    for line in lines:
        if line == cta and not removed:
            removed = True
            continue
        output.append(line)
    return " ".join(output).strip()


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


def _has_duplicate_sentence(text: str) -> bool:
    from email_generation.output_enforcement import split_sentences

    seen: set[str] = set()
    for sentence in split_sentences(text):
        key = re.sub(r"[^a-z0-9 ]", "", sentence.lower()).strip()
        if not key:
            continue
        if key in seen:
            return True
        seen.add(key)
    return False


def _max_ngram_count(text: str, n: int = 3) -> int:
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    if len(words) < n:
        return 0
    counts: dict[str, int] = {}
    for index in range(len(words) - n + 1):
        key = " ".join(words[index : index + n])
        counts[key] = counts.get(key, 0) + 1
    return max(counts.values(), default=0)


@pytest.mark.asyncio
async def test_quality_gate_noisy_fixture_20x(monkeypatch):
    import email_generation.remix_engine as remix_engine

    monkeypatch.setenv("REDIS_FORCE_INMEMORY", "1")
    monkeypatch.setenv("USE_PROVIDER_STUB", "1")
    monkeypatch.setenv("FEATURE_SENTENCE_SAFE_TRUNCATION", "1")
    monkeypatch.setenv("EMAILDJ_ALLOWED_FACTS_TARGET_COUNT", "10")

    noise_variants = [
        "Acme recently consolidated outbound playbooks.",
        "Acme is tracking weekly quality drift across SDR pods.",
        "Leadership is prioritizing repeatable message governance.",
        "The SDR org added enablement reviews for enterprise accounts.",
        "Managers are tightening proof requirements in outreach copy.",
        "Acme reported increased outreach volume in Q1.",
        "The team is emphasizing consistency across new hires.",
        "Acme is expanding enterprise account coverage this quarter.",
        "Quality reviews now include claim-grounding checks.",
        "The team added a stricter QA rubric for outbound emails.",
        "Acme is standardizing messaging standards for global teams.",
        "The SDR function is balancing volume and personalization.",
        "New leadership goals include higher response quality.",
        "Acme is improving manager visibility into outbound execution.",
        "The team is reducing variance in first-touch messaging.",
        "A recent initiative focused on reply-quality controls.",
        "Acme is improving consistency for high-volume outreach.",
        "The org is reinforcing measurable quality expectations.",
        "Managers want more predictable outbound performance.",
        "Acme is refining enterprise targeting and message clarity.",
    ]
    oversized_notes = (
        "Corsearch helps enterprise teams enforce outbound quality and keep messaging consistent under scale. "
        "This block is intentionally long so truncation behavior is exercised safely. "
    ) * 25
    base_research = (
        "Acme launched a new enterprise outbound initiative in January 2026 and expanded SDR hiring by 12 roles in Q1. "
        "Leadership is focused on response quality and repeatable message governance under higher send volume. "
    )

    for index, noise in enumerate(noise_variants):
        session = remix_engine.create_session_payload(
            prospect={
                "name": "Alex Doe",
                "title": "SDR Manager",
                "company": "Acme",
                "linkedin_url": "https://linkedin.com/in/alex-doe",
            },
            research_text=f"{base_research} {noise}",
            initial_style={"formality": 0.0, "orientation": 0.0, "length": 1.0, "assertiveness": 0.0},
            offer_lock="Remix Studio",
            cta_offer_lock="Open to a quick chat to see if this is relevant?",
            cta_type="question",
            company_context={
                "company_name": "Corsearch",
                "company_url": "https://corsearch.com",
                "current_product": "Remix Studio",
                "other_products": "Prospect Enrichment\nSequence QA",
                "company_notes": oversized_notes,
            },
        )
        result = await remix_engine.build_draft(
            session=session,
            style_profile={"formality": 0.0, "orientation": 0.0, "length": 1.0, "assertiveness": 0.0},
        )
        subject, body = _subject_body(result.draft)
        assert subject.strip(), f"case {index}: subject must be non-empty"
        assert body.strip(), f"case {index}: body must be non-empty"

        cta = str(session.get("cta_lock_effective") or "").strip()
        assert cta, f"case {index}: cta lock must be resolved"
        assert body.count(cta) == 1, f"case {index}: CTA must appear exactly once"

        narrative = _narrative_without_cta(body, cta)
        assert not _has_fragment_ending(narrative), f"case {index}: narrative ended mid-sentence"
        assert not _has_duplicate_sentence(narrative), f"case {index}: duplicated sentence detected"
        assert _max_ngram_count(narrative, n=3) <= 2, f"case {index}: trigram repetition threshold exceeded"

        rendered_lower = result.draft.lower()
        assert "alex" in rendered_lower, f"case {index}: missing prospect first name"
        assert "acme" in rendered_lower, f"case {index}: missing prospect company"
        assert "remix studio" in rendered_lower, f"case {index}: missing offer lock"
