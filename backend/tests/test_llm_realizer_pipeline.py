from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.config import load_settings
from app.engine import normalize_generate_request, run_engine
from app.engine.llm_realizer import assemble_llm_prompt_messages
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


def test_llm_disabled_uses_existing_deterministic_path() -> None:
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

    result = run_engine(ctx, max_repairs=2, openai=openai, settings=settings)

    assert result.debug.draft_source == "deterministic"
    assert len(openai.calls) == 0


def test_malformed_json_then_repair_then_safe_fallback() -> None:
    req = _request()
    ctx = normalize_generate_request(req)
    openai = StubOpenAI([{}, {}])
    settings = replace(load_settings(), llm_drafting_enabled=True)

    result = run_engine(ctx, max_repairs=2, openai=openai, settings=settings)

    assert result.debug.draft_source == "fallback"
    assert result.debug.llm_attempt_count == 2
    assert result.debug.degraded is True
    assert result.draft.body.splitlines()[-1].strip() == req.cta_offer_lock


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

    assert result.debug.draft_source == "llm"
    assert result.draft.body.splitlines()[-1].strip() == req.cta_offer_lock
    assert result.draft.body.count(req.cta_offer_lock) == 1
