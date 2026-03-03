import os

import pytest

os.environ.setdefault("REDIS_FORCE_INMEMORY", "1")

import email_generation.preset_preview_pipeline as preview_pipeline
from api.schemas import WebPresetPreviewBatchRequest, WebPreviewEffectiveSliders, WebPreviewItem
from email_generation.preset_preview_pipeline import (
    _mock_summary_pack,
    _normalize_preview_items,
    _violation_messages,
    make_response,
    run_preview_pipeline,
)


def _request_payload(company_suffix: str = "Cache") -> WebPresetPreviewBatchRequest:
    return WebPresetPreviewBatchRequest.model_validate(
        {
            "prospect": {
                "name": "Alex Doe",
                "title": "SDR Manager",
                "company": f"Acme {company_suffix}",
                "company_url": "https://acme.example",
                "linkedin_url": "https://linkedin.com/in/alex-doe",
            },
            "product_context": {
                "product_name": "Remix Studio",
                "one_line_value": "improve SDR reply quality with controlled personalization",
                "proof_points": ["Prospect Enrichment", "Sequence QA"],
                "target_outcome": "15-minute meeting",
            },
            "raw_research": {
                "deep_research_paste": (
                    "Acme is scaling outbound AI programs and wants better reply quality in enterprise accounts."
                ),
                "company_notes": "We help SDR teams increase reply quality without extra process overhead.",
                "extra_constraints": None,
            },
            "global_sliders": {"formality": 40, "brevity": 65, "directness": 70, "personalization": 75},
            "presets": [
                {
                    "preset_id": "challenger",
                    "label": "The Challenger",
                    "slider_overrides": {"directness": 85, "brevity": 75},
                },
                {
                    "preset_id": "warm_intro",
                    "label": "The Warm Intro",
                    "slider_overrides": {"formality": 55, "personalization": 80},
                },
            ],
            "offer_lock": "Remix Studio",
            "cta_lock": "Open to a quick chat to see if this is relevant?",
            "cta_lock_text": "Open to a quick chat to see if this is relevant?",
            "cta_type": "question",
        }
    )


def _last_nonempty_line(value: str) -> str:
    lines = [line.strip() for line in (value or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


@pytest.mark.asyncio
async def test_mock_preview_pipeline_returns_valid_shapes_and_cache_hits():
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["USE_PROVIDER_STUB"] = "1"
    os.environ["EMAILDJ_PREVIEW_INCLUDE_SUMMARY_PACK"] = "0"

    req = _request_payload("MockCache")
    first = await run_preview_pipeline(req)
    second = await run_preview_pipeline(req)

    assert first.provider == "mock"
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert len(first.previews) == len(req.presets)
    assert first.enforcement_level in {"warn", "repair", "block"}
    assert isinstance(first.repair_loop_enabled, bool)
    assert isinstance(first.violation_codes, list)
    assert isinstance(first.violation_count, int)

    subjects = {preview.subject for preview in first.previews}
    assert len(subjects) == len(first.previews)
    for preview in first.previews:
        assert len(preview.whyItWorks) == 3
        assert 2 <= len(preview.vibeTags) <= 4
        assert 90 <= len(preview.body.split()) <= 130


@pytest.mark.asyncio
async def test_make_response_hides_or_shows_summary_pack_by_flag():
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["USE_PROVIDER_STUB"] = "1"

    req = _request_payload("SummaryToggle")
    result = await run_preview_pipeline(req)

    os.environ["EMAILDJ_PREVIEW_INCLUDE_SUMMARY_PACK"] = "0"
    hidden = make_response(result, request_id="preview-req-1", session_id=None)
    assert hidden.summary_pack is None
    assert hidden.meta.request_id == "preview-req-1"
    assert hidden.meta.session_id is None
    assert hidden.meta.enforcement_level in {"warn", "repair", "block"}

    os.environ["EMAILDJ_PREVIEW_INCLUDE_SUMMARY_PACK"] = "1"
    shown = make_response(result)
    assert shown.summary_pack is not None


@pytest.mark.asyncio
async def test_preview_pipeline_uses_cta_type_when_lock_blank():
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["USE_PROVIDER_STUB"] = "1"

    req = _request_payload("CtaType")
    req.cta_lock = None
    req.cta_lock_text = None
    req.cta_type = "event_invite"
    result = await run_preview_pipeline(req)

    for preview in result.previews:
        cta_line = _last_nonempty_line(preview.body)
        assert "Open to a" in cta_line
        assert "Worth a look / Not a priority?" in cta_line
        assert "quick chat to see if this is relevant" not in cta_line


@pytest.mark.asyncio
async def test_preview_pipeline_lock_text_overrides_cta_type():
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["USE_PROVIDER_STUB"] = "1"

    req = _request_payload("CtaLockWins")
    req.cta_type = "event_invite"
    req.cta_lock = None
    req.cta_lock_text = "Open to a 17-min call for a first-week counterfeit sweep + teardown? Worth a look / Not a priority?"
    result = await run_preview_pipeline(req)

    for preview in result.previews:
        assert _last_nonempty_line(preview.body) == req.cta_lock_text


@pytest.mark.asyncio
async def test_preview_pipeline_uses_first_name_for_greeting():
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["USE_PROVIDER_STUB"] = "1"

    req = _request_payload("Greeting")
    req.prospect.name = "Rohan Singh"
    req.prospect_first_name = "Rohan"
    result = await run_preview_pipeline(req)

    for preview in result.previews:
        first_line = next((line.strip() for line in preview.body.splitlines() if line.strip()), "")
        assert first_line.startswith("Hi Rohan,")


def test_preview_normalization_exec_caps_length_and_repairs_greeting_and_ownership():
    req = _request_payload("ExecLength")
    req.prospect.name = "Sarah Chen"
    req.prospect.title = "CEO"
    req.prospect.company = "Acme Consumer Brands"
    req.prospect_first_name = "Sarah"
    req.offer_lock = "Trademark Search, Screening, and Brand Protection"
    req.product_context.product_name = req.offer_lock
    req.cta_lock_text = "Open to a quick 15-minute chat next week?"
    req.cta_lock = req.cta_lock_text

    summary_pack = _mock_summary_pack(req)
    raw_items = [
        {
            "preset_id": "challenger",
            "label": "The Challenger",
            "subject": "Protect Your Brand Globally",
            "body": (
                "Hi Sarah, Sarah, as CEO of Acme Consumer Brands, your focus on brand integrity and risk management is key. "
                "Our Trademark Search, Screening, and Brand Protection service helps identify conflicts and safeguard your trademarks "
                "across markets. Our tools are proven to help brands like yours. "
                "With recent filings and European conflicts, proactive IP management is crucial. "
                "Acme consumer brands is a mid-size fmcg company headquartered in chicago with a portfolio of household cleaning, "
                "personal care, and food products sold across north america and europe.\n\n"
                f"{req.cta_lock_text}"
            ),
            "vibeLabel": "Risk-led",
            "vibeTags": ["Direct", "Specific"],
            "whyItWorks": ["Uses one hook", "Focuses risk", "Clear ask"],
        }
    ]

    normalized = _normalize_preview_items(req=req, summary_pack=summary_pack, raw_items=raw_items)
    body = normalized[0].body

    assert len(body.split()) <= 90
    assert "Hi Sarah, Sarah," not in body
    assert "your trademark" not in body.lower()
    assert "brands like" not in body.lower()
    assert "Acme Consumer Brands" not in body
    assert "Trademark Search, Screening, and Brand Protection" not in body
    assert body.splitlines()[-1].strip() == req.cta_lock_text


def test_preview_normalization_rewrites_disallowed_numeric_claims_across_surfaces():
    req = _request_payload("Claims")
    req.raw_research.company_notes = "Trusted by 80+ marketplaces for enforcement triage."
    req.cta_lock_text = "Open to a 15-min call for a quick teardown + first workflow recommendation? Worth a look / Not a priority?"
    req.cta_lock = req.cta_lock_text

    summary_pack = _mock_summary_pack(req)
    raw_items = [
        {
            "preset_id": "challenger",
            "label": "The Challenger",
            "subject": "73 Fortune 100 teams use this",
            "body": (
                "Hi Alex, We deliver 99.9% compliance and 30x ROI with 5,000+ customers.\n\n"
                f"{req.cta_lock_text}"
            ),
            "vibeLabel": "99.9% compliant challenger",
            "vibeTags": ["30x ROI", "80+ marketplaces"],
            "whyItWorks": ["Used by 5,000+ customers", "Strong proof", "Low friction CTA"],
        }
    ]
    normalized = _normalize_preview_items(req=req, summary_pack=summary_pack, raw_items=raw_items)
    first = normalized[0]

    assert "80+ marketplaces" in " ".join([first.body, first.vibeLabel, *first.vibeTags, *first.whyItWorks])
    assert "99.9%" not in first.subject + " " + first.body + " " + first.vibeLabel + " " + " ".join(first.whyItWorks)
    assert "30x" not in first.subject + " " + first.body + " " + first.vibeLabel + " " + " ".join(first.whyItWorks)
    assert "5,000+" not in first.subject + " " + first.body + " " + first.vibeLabel + " " + " ".join(first.whyItWorks)


def test_preview_normalization_blocks_generic_ai_opener_without_research_anchor():
    req = _request_payload("OpenersBlocked")
    req.hook_strategy = "domain_hook"
    req.raw_research.deep_research_paste = "The account is scaling enforcement workflows and triage throughput."
    summary_pack = _mock_summary_pack(req)
    raw_items = [
        {
            "preset_id": "challenger",
            "label": "The Challenger",
            "subject": "Quick angle",
            "body": (
                "As Palantir scales its enterprise AI initiatives, their team is balancing quality and speed.\n\n"
                f"{req.cta_lock_text}"
            ),
            "vibeLabel": "Risk-led",
            "vibeTags": ["Direct", "Specific"],
            "whyItWorks": ["Uses one hook", "Focuses risk", "Clear ask"],
        }
    ]
    normalized = _normalize_preview_items(req=req, summary_pack=summary_pack, raw_items=raw_items)
    assert "scales its enterprise ai initiatives" not in normalized[0].body.lower()


def test_preview_normalization_allows_generic_ai_opener_for_research_anchored_hook():
    req = _request_payload("OpenersAllowed")
    req.hook_strategy = "research_anchored"
    req.raw_research.deep_research_paste = (
        "As Palantir scales its enterprise AI initiatives, the team is modernizing enforcement routing."
    )
    summary_pack = _mock_summary_pack(req)
    raw_items = [
        {
            "preset_id": "challenger",
            "label": "The Challenger",
            "subject": "Quick angle",
            "body": (
                "As Palantir scales its enterprise AI initiatives, their team is balancing quality and speed.\n\n"
                f"{req.cta_lock_text}"
            ),
            "vibeLabel": "Risk-led",
            "vibeTags": ["Direct", "Specific"],
            "whyItWorks": ["Uses one hook", "Focuses risk", "Clear ask"],
        }
    ]
    normalized = _normalize_preview_items(req=req, summary_pack=summary_pack, raw_items=raw_items)
    assert "scales its enterprise ai initiatives" in normalized[0].body.lower()


def test_preview_normalization_sections_avoid_search_enrich_act_phrase():
    req = _request_payload("NoSearchEnrichAct")
    summary_pack = _mock_summary_pack(req)
    raw_items = [
        {
            "preset_id": "challenger",
            "label": "The Challenger",
            "subject": "Quick angle",
            "body": (
                "Hi Alex, Acme is tightening outbound controls while preserving rep workflow quality.\n\n"
                f"{req.cta_lock_text}"
            ),
            "vibeLabel": "Risk-led",
            "vibeTags": ["Direct", "Specific"],
            "whyItWorks": ["Uses one hook", "Focuses risk", "Clear ask"],
        }
    ]
    normalized = _normalize_preview_items(req=req, summary_pack=summary_pack, raw_items=raw_items)
    assert "search, enrich, act" not in normalized[0].body.lower()


def test_normalize_strips_signoff_before_cta():
    req = _request_payload("SignoffStrip")
    summary_pack = _mock_summary_pack(req)
    raw_items = [
        {
            "preset_id": "challenger",
            "label": "The Challenger",
            "subject": "Remix Studio for Acme",
            "body": (
                "Hi Alex, Acme is scaling outbound quality and wants stronger first-touch response rates. "
                "Remix Studio keeps outreach specific without adding manager review overhead. "
                "Best regards, Alex.\n\n"
                f"{req.cta_lock_text}"
            ),
            "vibeLabel": "Risk-led",
            "vibeTags": ["Direct", "Specific"],
            "whyItWorks": ["Uses one hook", "Focuses risk", "Clear ask"],
        }
    ]
    normalized = _normalize_preview_items(req=req, summary_pack=summary_pack, raw_items=raw_items)
    body = normalized[0].body
    assert "best regards" not in body.lower()
    assert _last_nonempty_line(body) == req.cta_lock_text


def test_violation_catches_signoff_before_cta():
    req = _request_payload("SignoffViolation")
    preview = WebPreviewItem(
        preset_id="challenger",
        label="The Challenger",
        effective_sliders=WebPreviewEffectiveSliders(formality=40, brevity=65, directness=70, personalization=75),
        vibeLabel="Risk-led",
        vibeTags=["Direct", "Specific"],
        whyItWorks=["Uses one hook", "Focuses risk", "Clear ask"],
        subject="Remix Studio for Acme",
        body=(
            "Hi Alex, Acme is scaling outbound quality across enterprise accounts and the team wants cleaner first-touch "
            "messages with less manual rewrite work. Remix Studio helps keep outreach specific while preserving rep control, "
            "and it reduces manager QA cycles across higher-volume sequences. That shift usually creates more consistency in "
            "qualification conversations and follow-up quality. Best regards, Alex.\n\n"
            f"{req.cta_lock_text}"
        ),
    )
    violations = _violation_messages([preview], req)
    assert any("signoff_before_cta" in item for item in violations)


def test_cta_canonicalization_strips_fuzzy_match():
    req = _request_payload("CtaCanonical")
    summary_pack = _mock_summary_pack(req)
    raw_items = [
        {
            "preset_id": "challenger",
            "label": "The Challenger",
            "subject": "Remix Studio for Acme",
            "body": (
                "Hi Alex, Acme is tightening outbound quality controls while preserving SDR workflow speed. "
                "Remix Studio keeps messaging specific and easier to review. "
                "Open to a quick chat to see if this is relevant? Worth a look? Not a priority?"
            ),
            "vibeLabel": "Risk-led",
            "vibeTags": ["Direct", "Specific"],
            "whyItWorks": ["Uses one hook", "Focuses risk", "Clear ask"],
        }
    ]
    normalized = _normalize_preview_items(req=req, summary_pack=summary_pack, raw_items=raw_items)
    body = normalized[0].body
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    assert sum(1 for line in lines if line == req.cta_lock_text) == 1
    assert "worth a look? not a priority?" not in body.lower()


@pytest.mark.asyncio
async def test_preview_pipeline_single_call_cache_miss(monkeypatch):
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["USE_PROVIDER_STUB"] = "0"
    os.environ["EMAILDJ_PREVIEW_ENFORCEMENT_LEVEL"] = "warn"

    req = _request_payload("SingleCall")
    summary_pack = _mock_summary_pack(req)
    call_names: list[str] = []

    async def fake_load_cached_summary(_req):
        return None

    async def fake_save_cached_summary(_req, _summary_pack):
        return None

    async def fake_openai_with_fallback(*, messages, schema, schema_name, model_name):  # noqa: ARG001
        call_names.append(schema_name)
        previews = []
        for preset in req.presets:
            previews.append(
                {
                    "preset_id": str(preset.preset_id),
                    "label": preset.label,
                    "effective_sliders": {
                        "formality": 40,
                        "brevity": 65,
                        "directness": 70,
                        "personalization": 75,
                    },
                    "vibeLabel": "Risk-led",
                    "vibeTags": ["Direct", "Specific"],
                    "whyItWorks": ["Uses one hook", "Focuses risk", "Clear ask"],
                    "subject": "Remix Studio for Acme",
                    "body": (
                        "Hi Alex, Acme is scaling outbound quality and the team wants cleaner first-touch messaging. "
                        "Remix Studio keeps outreach specific and reduces rewrite overhead for managers.\n\n"
                        f"{req.cta_lock_text}"
                    ),
                }
            )
        return {"summary_pack": summary_pack.model_dump(), "previews": previews}, "gpt-4.1-nano"

    monkeypatch.setattr(preview_pipeline, "_load_cached_summary", fake_load_cached_summary)
    monkeypatch.setattr(preview_pipeline, "_save_cached_summary", fake_save_cached_summary)
    monkeypatch.setattr(preview_pipeline, "_openai_structured_json_with_fallback", fake_openai_with_fallback)
    monkeypatch.setattr(preview_pipeline, "_violation_messages", lambda previews, request: [])  # noqa: ARG005

    result = await run_preview_pipeline(req)

    assert call_names == ["preset_preview_combined"]
    assert result.provider_attempt_count == 1
    assert result.model_name == "gpt-4.1-nano"
