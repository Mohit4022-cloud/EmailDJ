from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from app.config import load_settings
from app.engine import normalize_generate_request, run_engine
from app.engine.llm_realizer import assemble_llm_prompt_messages
from app.engine.postprocess import word_count
from app.engine.planning import build_message_plan
from app.schemas import WebCompanyContext, WebGenerateRequest, WebProspectInput, WebStyleProfile


class StubOpenAI:
    def __init__(self, responses: list[dict[str, Any]], *, enabled: bool = True):
        self._responses = list(responses)
        self._enabled = enabled
        self.calls: list[dict[str, Any]] = []

    def enabled(self) -> bool:
        return self._enabled

    async def chat_json(
        self,
        *,
        messages: list[dict[str, Any]],
        reasoning_effort: str,
        schema_name: str,
        schema: dict[str, Any],
        max_completion_tokens: int = 1000,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "messages": messages,
                "reasoning_effort": reasoning_effort,
                "schema_name": schema_name,
                "schema": schema,
                "max_completion_tokens": max_completion_tokens,
            }
        )
        if not self._responses:
            return {}
        return self._responses.pop(0)


def _request(cta: str = "Open to a quick chat to see if this is relevant?") -> WebGenerateRequest:
    return WebGenerateRequest(
        prospect=WebProspectInput(
            name="Alex Doe",
            title="Head of Brand Protection",
            company="Acme",
            company_url="https://acme.example",
            linkedin_url="https://linkedin.com/in/alex",
        ),
        prospect_first_name="Alex",
        research_text="Acme expanded trademark enforcement coverage in Q1 and added new takedown workflows.",
        offer_lock="Trademark Workflow Platform",
        cta_offer_lock=cta,
        response_contract="email_json_v1",
        preset_id="straight_shooter",
        style_profile=WebStyleProfile(formality=0.1, orientation=-0.2, length=-0.4, assertiveness=-0.1),
        company_context=WebCompanyContext(
            company_name="Example Seller",
            company_url="https://example-seller.test",
            current_product="Trademark Workflow Platform",
            seller_offerings="Trademark monitoring\nMarketplace takedowns",
            internal_modules="Prospect Enrichment\nSequence QA\nPersona Research",
            company_notes="Supports legal teams with consistent enforcement workflows.",
            cta_offer_lock=cta,
            cta_type="question",
        ),
    )


def test_llm_path_selected_when_enabled_and_provider_available() -> None:
    req = _request()
    ctx = normalize_generate_request(req)
    openai = StubOpenAI(
        [
            {
                "subject": "Acme trademark enforcement workflow",
                "body": (
                    "Hi Alex,\n\n"
                    "Saw Acme expanded trademark enforcement coverage in Q1.\n\n"
                    "Example Seller helps legal teams route high-risk cases with consistent workflows.\n\n"
                    f"{req.cta_offer_lock}"
                ),
            }
        ]
    )
    settings = replace(load_settings(), llm_drafting_enabled=True)

    result = run_engine(ctx, max_repairs=2, openai=openai, settings=settings)

    assert result.debug.draft_source == "llm"
    assert result.draft.subject == "Acme trademark enforcement workflow"
    assert result.draft.body.splitlines()[-1].strip() == req.cta_offer_lock
    assert len(openai.calls) == 1


def test_llm_disabled_fails_closed() -> None:
    req = _request()
    ctx = normalize_generate_request(req)
    openai = StubOpenAI(
        [
            {
                "subject": "Should never be used",
                "body": "Should never be used",
            }
        ]
    )
    settings = replace(load_settings(), llm_drafting_enabled=False)

    with pytest.raises(RuntimeError, match="ai_only_pipeline_requires_openai"):
        run_engine(ctx, max_repairs=2, openai=openai, settings=settings)
    assert len(openai.calls) == 0


def test_malformed_json_then_repair_fails_closed() -> None:
    req = _request()
    ctx = normalize_generate_request(req)
    openai = StubOpenAI([{}, {}])
    settings = replace(load_settings(), llm_drafting_enabled=True)

    with pytest.raises(RuntimeError, match="llm_realize_failed:llm_json_parse_failed"):
        run_engine(ctx, max_repairs=2, openai=openai, settings=settings)


def test_llm_prompt_payload_excludes_internal_modules_values() -> None:
    req = _request()
    ctx = normalize_generate_request(req)
    plan = build_message_plan(ctx)
    messages = assemble_llm_prompt_messages(ctx, plan)
    serialized = str(messages)

    assert "Prospect Enrichment" not in serialized
    assert "Sequence QA" not in serialized
    assert "Persona Research" not in serialized


def test_cta_lock_is_hard_enforced_for_llm_output() -> None:
    req = _request(cta="Would you be open to a 15-minute call next week?")
    ctx = normalize_generate_request(req)
    openai = StubOpenAI(
        [
            {
                "subject": "Acme outreach idea",
                "body": (
                    "Hi Alex,\n\n"
                    "Saw Acme expanded trademark enforcement coverage in Q1.\n\n"
                    "Example Seller helps legal teams route trademark work with fewer delays.\n\n"
                    "Can I share details?"
                ),
            }
        ]
    )
    settings = replace(load_settings(), llm_drafting_enabled=True)

    result = run_engine(ctx, max_repairs=2, openai=openai, settings=settings)

    assert result.debug.draft_source == "llm_postprocessed"
    assert result.draft.body.splitlines()[-1].strip() == req.cta_offer_lock
    assert result.draft.body.count(req.cta_offer_lock) == 1
    assert len(openai.calls) == 1


def test_length_only_violation_is_postprocessed_without_llm_repair_or_fallback() -> None:
    req = _request()
    ctx = normalize_generate_request(req)
    long_sentences = " ".join(
        [
            f"Sentence {idx} ties workflow reliability to trademark enforcement priorities."
            for idx in range(1, 25)
        ]
    )
    openai = StubOpenAI(
        [
            {
                "subject": "Acme workflow note",
                "body": (
                    "Hi Alex,\n\n"
                    f"{long_sentences}\n\n"
                    f"{req.cta_offer_lock}"
                ),
            }
        ]
    )
    settings = replace(load_settings(), llm_drafting_enabled=True)

    result = run_engine(ctx, max_repairs=2, openai=openai, settings=settings)

    assert result.debug.draft_source == "llm_postprocessed"
    assert result.debug.repair_attempt_count == 0
    assert result.debug.llm_attempt_count == 1
    assert len(openai.calls) == 1
    assert "trim_to_max_words" in result.debug.postprocess_applied
    assert "word_count_out_of_band" in result.debug.validation_error_codes_raw
    assert result.debug.validation_error_codes_final == []
    assert result.debug.word_count_final <= result.debug.word_band_max
    assert word_count(result.draft.body) <= result.debug.word_band_max
