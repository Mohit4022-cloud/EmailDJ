import os

import pytest

from api.schemas import WebPresetPreviewBatchRequest
from email_generation.preset_preview_pipeline import make_response, run_preview_pipeline


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
        }
    )


@pytest.mark.asyncio
async def test_mock_preview_pipeline_returns_valid_shapes_and_cache_hits():
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_QUICK_GENERATE_MODE"] = "mock"
    os.environ["EMAILDJ_PREVIEW_INCLUDE_SUMMARY_PACK"] = "0"

    req = _request_payload("MockCache")
    first = await run_preview_pipeline(req)
    second = await run_preview_pipeline(req)

    assert first.provider == "mock"
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert len(first.previews) == len(req.presets)

    subjects = {preview.subject for preview in first.previews}
    assert len(subjects) == len(first.previews)
    for preview in first.previews:
        assert len(preview.whyItWorks) == 3
        assert 2 <= len(preview.vibeTags) <= 4
        assert 90 <= len(preview.body.split()) <= 130


@pytest.mark.asyncio
async def test_make_response_hides_or_shows_summary_pack_by_flag():
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_QUICK_GENERATE_MODE"] = "mock"

    req = _request_payload("SummaryToggle")
    result = await run_preview_pipeline(req)

    os.environ["EMAILDJ_PREVIEW_INCLUDE_SUMMARY_PACK"] = "0"
    hidden = make_response(result)
    assert hidden.summary_pack is None

    os.environ["EMAILDJ_PREVIEW_INCLUDE_SUMMARY_PACK"] = "1"
    shown = make_response(result)
    assert shown.summary_pack is not None
