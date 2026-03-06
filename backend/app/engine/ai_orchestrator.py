from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.openai_client import ENFORCED_OPENAI_MODEL, OpenAIClient
from app.schemas import WebGenerateRequest

from .brief_cache import BriefCache, compute_brief_cache_key
from .normalize import normalize_generate_request
from .postprocess import deterministic_postprocess_draft
from .preset_contract import resolve_output_contract, sentence_count as preset_sentence_count, word_count as preset_word_count
from .presets.registry import load_all_presets, load_preset
from .prompts import stage_a, stage_b, stage_b0, stage_c, stage_c0, stage_d, stage_e
from .schemas import (
    RF_ANGLE_SET,
    RF_EMAIL_DRAFT,
    RF_FIT_MAP,
    RF_MESSAGING_BRIEF,
    RF_MESSAGE_ATOMS,
    RF_QA_REPORT,
    STAGES,
)
from .stage_a_sanitizer import sanitize_stage_a_brief
from .stage_runner import StageConfig, StageError, run_stage
from .tracer import Trace, hash_json
from .types import EmailDraft as LegacyEmailDraft
from .validators import (
    ValidationIssue,
    dominant_validation_code,
    normalize_qa_report,
    salvage_eligible_validation_codes,
    validate_angle_set,
    validate_email_draft,
    validate_fit_map,
    validate_message_atoms,
    validate_messaging_brief,
)


DEFAULT_CTA = "Open to a quick chat to see if this is relevant?"
TOTAL_PIPELINE_TIMEOUT_SECONDS = 90.0
STAGE_TIMEOUT_SECONDS = 25.0
SALVAGE_STAGE = "EMAIL_REWRITE_SALVAGE"


@dataclass(slots=True)
class PipelineResult:
    ok: bool
    trace_id: str
    stage_stats: list[dict[str, Any]]
    subject: str | None = None
    body: str | None = None
    variants: list[dict[str, Any]] | None = None
    provenance: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    def to_done_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "trace_id": self.trace_id,
            "stage_stats": self.stage_stats,
        }
        if self.ok:
            if self.variants is not None:
                payload["variants"] = self.variants
            else:
                payload["subject"] = self.subject or ""
                payload["body"] = self.body or ""
                payload["provenance"] = self.provenance or {}
        else:
            payload["error"] = self.error or {
                "code": "UNKNOWN",
                "message": "pipeline_error",
                "stage": "UNKNOWN",
                "details": {},
            }
        return payload


class AIOrchestrator:
    def __init__(self, *, openai: OpenAIClient, settings: Settings, brief_cache: BriefCache | None = None):
        self.openai = openai
        self.settings = settings
        self.brief_cache = brief_cache or BriefCache(max_size=200, ttl_seconds=30 * 60)

    async def run_pipeline_single(
        self,
        *,
        request: WebGenerateRequest,
        trace: Trace,
        preset_id: str | None = None,
        sliders: dict[str, Any] | None = None,
    ) -> PipelineResult:
        try:
            return await asyncio.wait_for(
                self._run_pipeline_single(request=request, trace=trace, preset_id=preset_id, sliders=sliders),
                timeout=TOTAL_PIPELINE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return self._error_result(
                trace=trace,
                code="PIPELINE_TIMEOUT",
                message="Pipeline timed out",
                stage="UNKNOWN",
                details={},
            )

    async def run_pipeline_presets(
        self,
        *,
        request: WebGenerateRequest,
        trace: Trace,
        preset_ids: list[str],
        sliders: dict[str, Any] | None = None,
        preset_sliders: dict[str, dict[str, Any]] | None = None,
    ) -> PipelineResult:
        try:
            return await asyncio.wait_for(
                self._run_pipeline_presets(
                    request=request,
                    trace=trace,
                    preset_ids=preset_ids,
                    sliders=sliders,
                    preset_sliders=preset_sliders,
                ),
                timeout=TOTAL_PIPELINE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return self._error_result(
                trace=trace,
                code="PIPELINE_TIMEOUT",
                message="Pipeline timed out",
                stage="UNKNOWN",
                details={},
            )

    def _build_slider_params(self, request: WebGenerateRequest, ctx: Any, provided: dict[str, Any] | None) -> dict[str, Any]:
        if provided:
            tone = float(provided.get("tone", 0.4))
            framing = float(provided.get("framing", 0.5))
            stance = float(provided.get("stance", 0.5))
            length = str(provided.get("length", "medium"))
            return {
                "tone": max(0.0, min(1.0, tone)),
                "framing": max(0.0, min(1.0, framing)),
                "length": length if length in {"short", "medium", "long"} else "medium",
                "stance": max(0.0, min(1.0, stance)),
            }

        formality = int(ctx.sliders.get("formality", 50))
        personalization = int(ctx.sliders.get("personalization", 50))
        directness = int(ctx.sliders.get("directness", 50))
        brevity = int(ctx.sliders.get("brevity", 50))
        if brevity >= 67:
            length = "short"
        elif brevity <= 33:
            length = "long"
        else:
            length = "medium"
        return {
            "tone": max(0.0, min(1.0, 1.0 - (formality / 100.0))),
            "framing": max(0.0, min(1.0, personalization / 100.0)),
            "length": length,
            "stance": max(0.0, min(1.0, directness / 100.0)),
        }

    def _cta_lock(self, request: WebGenerateRequest, ctx: Any) -> str:
        return str(request.cta_offer_lock or request.company_context.cta_offer_lock or ctx.cta_lock or DEFAULT_CTA).strip()

    def _trace_stage_name(self, stage: str, *, preset_id: str | None = None) -> str:
        preset_key = str(preset_id or "").strip()
        if not preset_key:
            return stage
        return f"{stage}:{preset_key}"

    def _stage_a_input(self, *, request: WebGenerateRequest, ctx: Any, cta_line: str) -> dict[str, Any]:
        icp_description = str(
            (
                (request.sender_profile_override.structured_icp if request.sender_profile_override else "")
                or ""
            )
        ).strip()
        return {
            "user_company": {
                "name": ctx.sender_company_name,
                "product_summary": ctx.current_product or ctx.offer_lock,
                "icp_description": icp_description,
                "differentiators": list(ctx.seller_offerings[:6]),
                "proof_points": list(ctx.seller_proof_points[:8]),
                "do_not_say": list(BANNED_DO_NOT_SAY_DEFAULT),
                "company_notes": ctx.company_notes,
            },
            "prospect": {
                "name": ctx.prospect_name,
                "title": ctx.prospect_title,
                "company": ctx.prospect_company,
                "industry": "",
                "notes": ctx.prospect_notes,
                "research_text": ctx.usable_research_text,
            },
            "cta": {
                "cta_type": ctx.cta_type or request.cta_type or "question",
                "cta_final_line": cta_line,
            },
        }

    def _cache_context(self, *, ctx: Any, cta_line: str) -> dict[str, Any]:
        return {
            "user_company": {
                "name": ctx.sender_company_name,
                "product_summary": ctx.current_product,
                "icp": ctx.company_notes,
                "differentiators": list(ctx.seller_offerings),
                "proof_points": list(ctx.seller_proof_points),
            },
            "prospect": {
                "name": ctx.prospect_name,
                "title": ctx.prospect_title,
                "company": ctx.prospect_company,
                "industry": "",
                "notes": ctx.prospect_notes,
                "research_text": ctx.usable_research_text,
            },
            "cta": {"cta_final_line": cta_line},
        }

    def _normalize_message_atoms(self, atoms: dict[str, Any], *, cta_line: str, trace: Trace) -> dict[str, Any]:
        out = dict(atoms)

        if str(out.get("cta_line") or "").strip() != cta_line:
            out["cta_line"] = cta_line
            trace.add_postprocess_step("force_atoms_cta_lock")

        raw_proof = out.get("proof_line")
        proof_line = str(raw_proof or "").strip()
        if proof_line:
            if proof_line != str(raw_proof or ""):
                trace.add_postprocess_step("normalize_atoms_proof_line_whitespace")
            out["proof_line"] = proof_line
            out["proof_gap"] = False
            trace.add_postprocess_step("set_atoms_proof_gap_false")
        else:
            if str(raw_proof or "") != "":
                trace.add_postprocess_step("normalize_atoms_proof_line_empty")
            out["proof_line"] = ""
            out["proof_gap"] = True
            trace.add_postprocess_step("set_atoms_proof_gap_true")
        return out

    def _split_failed_stage_details(self, details: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
        raw_details = dict(details or {})
        trace_details = dict(raw_details)
        for key in (
            "first_raw",
            "repair_raw",
            "first_payload",
            "repair_payload",
            "first_processed_payload",
            "repair_processed_payload",
            "first_artifact_metadata",
            "repair_artifact_metadata",
        ):
            trace_details.pop(key, None)

        artifact_payload = raw_details.get("first_processed_payload")
        if artifact_payload is None:
            artifact_payload = raw_details.get("repair_processed_payload")
        if artifact_payload is None:
            artifact_payload = raw_details.get("first_payload")
        if artifact_payload is None:
            artifact_payload = raw_details.get("repair_payload")
        raw_output_artifact = raw_details.get("first_payload")
        if raw_output_artifact is None:
            raw_output_artifact = raw_details.get("repair_payload")
        artifact_views = raw_details.get("first_artifact_metadata")
        if artifact_views is None:
            artifact_views = raw_details.get("repair_artifact_metadata")
        if isinstance(artifact_views, dict):
            sanitation_report = dict(artifact_views.get("sanitation_report") or {})
            raw_artifact_quality = dict(artifact_views.get("raw_artifact_quality") or {})
            if raw_artifact_quality:
                trace_details["raw_hygiene_issue_count"] = int(raw_artifact_quality.get("issue_count") or 0)
                trace_details["raw_artifact_quality"] = raw_artifact_quality
            if sanitation_report:
                trace_details["sanitation_action_counts"] = dict(sanitation_report.get("sanitation_action_counts") or {})
                trace_details["sanitation_changed_semantic_eligibility"] = bool(
                    sanitation_report.get("sanitation_changed_semantic_eligibility")
                )
        artifact_raw = str(raw_details.get("first_raw") or raw_details.get("repair_raw") or "").strip() or None
        artifact_status = str(raw_details.get("artifact_status") or "").strip()
        if not artifact_status:
            artifact_status = "failed_artifact_present" if (artifact_payload is not None or artifact_raw) else "artifact_missing"
        return trace_details, {
            "artifact_payload": artifact_payload,
            "artifact_raw": artifact_raw,
            "artifact_status": artifact_status,
            "attempt_count": int(raw_details.get("attempt_count") or 0),
            "raw_output_artifact": raw_output_artifact,
            "artifact_views": artifact_views if isinstance(artifact_views, dict) else {},
        }

    def _sanitize_stage_a_payload(
        self,
        payload: dict[str, Any],
        *,
        source_text: str,
        source_payload: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        raw_artifact = dict(payload)
        sanitized_brief, sanitation_report, raw_hygiene_flags = sanitize_stage_a_brief(
            payload,
            source_text=source_text,
            source_payload=source_payload,
        )
        artifact_views = {
            "raw_stage_a_artifact": raw_artifact,
            "sanitized_stage_a_artifact": sanitized_brief,
            "sanitation_report": sanitation_report,
            **raw_hygiene_flags,
        }
        return sanitized_brief, artifact_views

    async def _run_stage(
        self,
        *,
        trace: Trace,
        config: StageConfig,
        messages: list[dict[str, str]],
        validator,
        postprocess=None,
        trace_stage: str | None = None,
    ) -> dict[str, Any]:
        trace_name = str(trace_stage or config.stage)
        trace.start_stage(stage=trace_name, model=ENFORCED_OPENAI_MODEL)
        try:
            result = await run_stage(
                openai=self.openai,
                config=config,
                messages=messages,
                validator=validator,
                postprocess=postprocess,
                timeout_seconds=STAGE_TIMEOUT_SECONDS,
            )
            artifact_views = dict(result.artifact_metadata or {})
            details = {"usage": result.usage}
            if artifact_views:
                sanitation_report = dict(artifact_views.get("sanitation_report") or {})
                raw_artifact_quality = dict(artifact_views.get("raw_artifact_quality") or {})
                details["raw_hygiene_issue_count"] = int(raw_artifact_quality.get("issue_count") or 0)
                details["raw_artifact_quality"] = raw_artifact_quality
                details["sanitation_action_counts"] = dict(sanitation_report.get("sanitation_action_counts") or {})
                details["sanitation_changed_semantic_eligibility"] = bool(
                    sanitation_report.get("sanitation_changed_semantic_eligibility")
                )
            if result.raw_payload is not None:
                trace.put_hash(f"raw_output:{trace_name}", result.raw_payload)
            if artifact_views.get("sanitized_stage_a_artifact") is not None:
                trace.put_hash(f"sanitized_output:{trace_name}", artifact_views.get("sanitized_stage_a_artifact"))
            trace.end_stage(
                stage=trace_name,
                model=ENFORCED_OPENAI_MODEL,
                schema_ok=True,
                output=result.payload,
                attempt_count=result.attempts,
                details=details,
                raw_output=result.raw_text,
                raw_output_artifact=result.raw_payload,
                artifact_views=artifact_views,
                raw_validation_status=result.raw_validation_status,
                final_validation_status=result.final_validation_status,
                error_codes=result.validation_codes,
            )
            return result.payload
        except StageError as exc:
            validation_codes = list((exc.details or {}).get("codes") or [])
            validation_details = list((exc.details or {}).get("validation_details") or (exc.details or {}).get("rejected_facts") or [])
            if validation_codes:
                trace.add_validation_error(
                    stage=trace_name,
                    codes=validation_codes,
                    details={
                        "validation_details": validation_details,
                        "overreach_claims": [
                            str(item.get("claim_type") or "").strip()
                            for item in validation_details
                            if isinstance(item, dict) and str(item.get("claim_type") or "").strip()
                        ],
                    },
                )
            trace_details, artifact = self._split_failed_stage_details(exc.details)
            if artifact["raw_output_artifact"] is not None:
                trace.put_hash(f"raw_output:{trace_name}", artifact["raw_output_artifact"])
            if artifact["artifact_payload"] is not None:
                trace.put_hash(f"sanitized_output:{trace_name}", artifact["artifact_payload"])
            trace.fail_stage_with_artifact(
                stage=trace_name,
                model=ENFORCED_OPENAI_MODEL,
                error_code=exc.code,
                details=trace_details,
                artifact_status=str(artifact["artifact_status"] or ""),
                output=artifact["artifact_payload"],
                raw_output=artifact["artifact_raw"],
                attempt_count=int(artifact["attempt_count"] or 0),
                raw_output_artifact=artifact["raw_output_artifact"],
                artifact_views=artifact["artifact_views"],
                raw_validation_status=str((exc.details or {}).get("raw_validation_status") or "failed"),
                final_validation_status=str((exc.details or {}).get("final_validation_status") or "failed"),
                error_codes=validation_codes,
            )
            raise
        except ValidationIssue as exc:
            validation_details = list(getattr(exc, "details", []) or [])
            trace.add_validation_error(
                stage=trace_name,
                codes=exc.codes,
                details={
                    "validation_details": validation_details,
                    "overreach_claims": [
                        str(item.get("claim_type") or "").strip()
                        for item in validation_details
                        if isinstance(item, dict) and str(item.get("claim_type") or "").strip()
                    ],
                },
            )
            trace.fail_stage(
                stage=trace_name,
                model=ENFORCED_OPENAI_MODEL,
                error_code="VALIDATION_FAILED",
                details={
                    "codes": exc.codes,
                    "validation_details": validation_details,
                    "rejected_facts": validation_details,
                },
            )
            raise StageError(
                stage=config.stage,
                code="VALIDATION_FAILED",
                message="Stage deterministic validation failed",
                details={
                    "codes": exc.codes,
                    "validation_details": validation_details,
                    "rejected_facts": validation_details,
                },
            ) from exc

    def _annotate_draft_stage(
        self,
        *,
        trace: Trace,
        stage_name: str,
        draft: dict[str, Any],
        validation_codes: list[str],
        mechanical_steps: list[str],
        final_validation_status: str,
        preset_contract: dict[str, Any] | None = None,
        stage_details: dict[str, Any] | None = None,
    ) -> None:
        body = str(draft.get("body") or "").strip()
        details = dict(stage_details or {})
        details.setdefault("preset_id", str(draft.get("preset_id") or "").strip())
        details.setdefault("body_word_count", preset_word_count(body))
        details.setdefault("body_sentence_count", preset_sentence_count(body))
        if preset_contract:
            details.setdefault("preset_contract", dict(preset_contract))
            details.setdefault("preset_contract_hash", hash_json(preset_contract))
        trace.annotate_stage(
            stage=stage_name,
            final_validation_status=final_validation_status,
            error_codes=list(validation_codes),
            mechanical_postprocess_applied=list(mechanical_steps),
            details=details,
            output={
                "subject": str(draft.get("subject") or "").strip(),
                "body": str(draft.get("body") or "").strip(),
                "preset_id": str(draft.get("preset_id") or "").strip(),
                "selected_angle_id": str(draft.get("selected_angle_id") or "").strip(),
                "used_hook_ids": list(draft.get("used_hook_ids") or []),
            },
        )

    def _resolved_preset_contract(self, *, preset: dict[str, Any], sliders: dict[str, Any]) -> dict[str, Any]:
        return resolve_output_contract(preset, length=str(sliders.get("length") or "medium"))

    def _remember_preset_contract(self, *, trace: Trace, preset_id: str, preset_contract: dict[str, Any]) -> None:
        contracts = dict(trace.meta.get("preset_contracts") or {})
        contracts[str(preset_id)] = {
            "hash": hash_json(preset_contract),
            "contract": dict(preset_contract),
        }
        trace.set_meta(preset_contracts=contracts)

    def _annotate_qa_stage(
        self,
        *,
        trace: Trace,
        stage_name: str,
        preset_id: str,
        preset_contract: dict[str, Any],
        draft: dict[str, Any],
        qa_report: dict[str, Any],
        generation_validation_codes: list[str],
    ) -> None:
        issues = [item for item in qa_report.get("issues") or [] if isinstance(item, dict)]
        dominant_issue = next((str(item.get("type") or "").strip() for item in issues if str(item.get("type") or "").strip()), None)
        trace.annotate_stage(
            stage=stage_name,
            details={
                "preset_id": str(preset_id or ""),
                "preset_contract": dict(preset_contract),
                "preset_contract_hash": hash_json(preset_contract),
                "pre_rewrite_word_count": preset_word_count(str(draft.get("body") or "").strip()),
                "pre_rewrite_sentence_count": preset_sentence_count(str(draft.get("body") or "").strip()),
                "dominant_failing_rule": dominant_issue or dominant_validation_code(generation_validation_codes),
                "salvage_applied": False,
                "salvage_result": "not_run",
            },
        )

    async def _maybe_salvage_rewrite(
        self,
        *,
        trace: Trace,
        preset_id: str,
        draft: dict[str, Any],
        atoms: dict[str, Any],
        messaging_brief: dict[str, Any],
        cta_line: str,
        slider_params: dict[str, Any],
        preset_contract: dict[str, Any],
        final_codes: list[str],
    ) -> tuple[dict[str, Any], list[str], bool, str]:
        if not salvage_eligible_validation_codes(final_codes):
            return draft, final_codes, False, "not_run"

        salvage_stage = self._trace_stage_name(SALVAGE_STAGE, preset_id=preset_id)
        salvage_draft = await self._run_stage(
            trace=trace,
            config=StageConfig(
                stage=STAGES["E"],
                max_tokens=500,
                reasoning_effort=self.settings.openai_reasoning_low,
                response_format=RF_EMAIL_DRAFT,
            ),
            messages=stage_e.build_salvage_messages(
                email_draft=draft,
                message_atoms=atoms,
                messaging_brief=messaging_brief,
                cta_final_line=cta_line,
                preset_contract=preset_contract,
                failure_code=dominant_validation_code(final_codes) or "word_count_out_of_band",
            ),
            validator=None,
            trace_stage=salvage_stage,
        )
        salvage_draft["preset_id"] = str(preset_id)
        salvage_draft["selected_angle_id"] = str(draft.get("selected_angle_id") or atoms.get("selected_angle_id") or "")
        salvage_draft["used_hook_ids"] = list(draft.get("used_hook_ids") or atoms.get("used_hook_ids") or [])
        salvage_draft, salvage_steps = self._mechanical_postprocess(salvage_draft, slider_params, cta_line, trace)
        salvage_codes = validate_email_draft(
            salvage_draft,
            brief=messaging_brief,
            cta_final_line=cta_line,
            sliders=slider_params,
            preset_contract=preset_contract,
        )
        self._annotate_draft_stage(
            trace=trace,
            stage_name=salvage_stage,
            draft=salvage_draft,
            validation_codes=salvage_codes,
            mechanical_steps=salvage_steps,
            final_validation_status="failed" if salvage_codes else "passed",
            preset_contract=preset_contract,
            stage_details={
                "dominant_failing_rule": dominant_validation_code(final_codes) or "word_count_out_of_band",
                "salvage_applied": True,
                "salvage_result": "failed" if salvage_codes else "passed",
                "post_salvage_word_count": preset_word_count(str(salvage_draft.get("body") or "").strip()),
            },
        )
        if salvage_codes:
            trace.add_validation_error(stage=salvage_stage, codes=salvage_codes)
            return salvage_draft, salvage_codes, True, "failed"
        return salvage_draft, salvage_codes, True, "passed"

    async def _run_pipeline_single(
        self,
        *,
        request: WebGenerateRequest,
        trace: Trace,
        preset_id: str | None,
        sliders: dict[str, Any] | None,
    ) -> PipelineResult:
        if not self.openai.enabled():
            return self._error_result(
                trace=trace,
                code="OPENAI_UNAVAILABLE",
                message="OpenAI provider is unavailable",
                stage="TRANSPORT",
                details={},
            )

        ctx = normalize_generate_request(request, preset_id=preset_id)
        slider_params = self._build_slider_params(request, ctx, sliders)
        cta_line = self._cta_lock(request, ctx)

        trace.put_hash("request:normalized", self._cache_context(ctx=ctx, cta_line=cta_line))
        trace.set_meta(mode="single", preset_id=ctx.preset_id, sliders=slider_params, research_state=ctx.research_state)

        try:
            messaging_brief, fit_map, angle_set = await self._build_or_load_brief_stack(
                request=request,
                ctx=ctx,
                trace=trace,
                cta_line=cta_line,
            )

            selected_angle_id = str((angle_set.get("angles") or [{}])[0].get("angle_id") or "")
            if not selected_angle_id:
                raise StageError(
                    stage=STAGES["B0"],
                    code="ANGLE_SELECTION_FAILED",
                    message="No angle available",
                    details={},
                )

            atoms = await self._run_stage(
                trace=trace,
                config=StageConfig(
                    stage=STAGES["C0"],
                    max_tokens=400,
                    reasoning_effort=self.settings.openai_reasoning_low,
                    response_format=RF_MESSAGE_ATOMS,
                ),
                messages=stage_c0.build_messages(
                    messaging_brief,
                    fit_map,
                    angle_set,
                    selected_angle_id,
                    slider_params,
                    cta_line,
                ),
                validator=lambda payload: validate_message_atoms(
                    payload,
                    cta_final_line=cta_line,
                    forbidden_patterns=list(messaging_brief.get("forbidden_claim_patterns") or []),
                ),
            )
            atoms = self._normalize_message_atoms(atoms, cta_line=cta_line, trace=trace)

            preset = load_preset(ctx.preset_id)
            preset_contract = self._resolved_preset_contract(preset=preset, sliders=slider_params)
            self._remember_preset_contract(trace=trace, preset_id=ctx.preset_id, preset_contract=preset_contract)
            generation_stage = self._trace_stage_name(STAGES["C"])
            draft = await self._run_stage(
                trace=trace,
                config=StageConfig(
                    stage=STAGES["C"],
                    max_tokens=800,
                    reasoning_effort=self.settings.openai_reasoning_low,
                    response_format=RF_EMAIL_DRAFT,
                ),
                messages=stage_c.build_single_messages(
                    messaging_brief=messaging_brief,
                    fit_map=fit_map,
                    angle_set=angle_set,
                    message_atoms=atoms,
                    preset=preset,
                    sliders=slider_params,
                    cta_final_line=cta_line,
                ),
                validator=None,
                trace_stage=generation_stage,
            )
            draft.setdefault("preset_id", ctx.preset_id)
            draft.setdefault("selected_angle_id", selected_angle_id)
            draft.setdefault("used_hook_ids", list(atoms.get("used_hook_ids") or []))

            draft, generation_steps = self._mechanical_postprocess(draft, slider_params, cta_line, trace)

            validation_codes = validate_email_draft(
                draft,
                brief=messaging_brief,
                cta_final_line=cta_line,
                sliders=slider_params,
                preset_contract=preset_contract,
            )
            if validation_codes:
                trace.add_validation_error(stage=STAGES["C"], codes=validation_codes)
            self._annotate_draft_stage(
                trace=trace,
                stage_name=generation_stage,
                draft=draft,
                validation_codes=validation_codes,
                mechanical_steps=generation_steps,
                final_validation_status="rewrite_required" if validation_codes else "passed",
                preset_contract=preset_contract,
                stage_details={
                    "pre_rewrite_word_count": preset_word_count(str(draft.get("body") or "").strip()),
                    "salvage_applied": False,
                    "salvage_result": "not_run",
                },
            )

            qa_stage = self._trace_stage_name(STAGES["D"])
            qa = await self._run_stage(
                trace=trace,
                config=StageConfig(
                    stage=STAGES["D"],
                    max_tokens=800,
                    reasoning_effort=self.settings.openai_reasoning_high,
                    response_format=RF_QA_REPORT,
                ),
                messages=stage_d.build_messages(draft, messaging_brief, atoms, cta_line, preset_contract),
                validator=None,
                trace_stage=qa_stage,
            )
            qa = normalize_qa_report(qa)
            self._annotate_qa_stage(
                trace=trace,
                stage_name=qa_stage,
                preset_id=ctx.preset_id,
                preset_contract=preset_contract,
                draft=draft,
                qa_report=qa,
                generation_validation_codes=validation_codes,
            )
            self._annotate_draft_stage(
                trace=trace,
                stage_name=generation_stage,
                draft=draft,
                validation_codes=validation_codes,
                mechanical_steps=generation_steps,
                final_validation_status="rewrite_required" if (validation_codes or qa.get("pass_rewrite_needed")) else "passed",
                preset_contract=preset_contract,
                stage_details={
                    "dominant_failing_rule": dominant_validation_code(validation_codes)
                    or next(
                        (str(item.get("type") or "").strip() for item in qa.get("issues") or [] if str(item.get("type") or "").strip()),
                        None,
                    ),
                },
            )

            rewrite_applied = False
            if qa.get("pass_rewrite_needed") or validation_codes:
                rewrite_applied = True
                rewrite_stage = self._trace_stage_name(STAGES["E"])
                draft = await self._run_stage(
                    trace=trace,
                    config=StageConfig(
                        stage=STAGES["E"],
                        max_tokens=800,
                        reasoning_effort=self.settings.openai_reasoning_low,
                        response_format=RF_EMAIL_DRAFT,
                    ),
                    messages=stage_e.build_messages(
                        email_draft=draft,
                        qa_report=qa,
                        messaging_brief=messaging_brief,
                        message_atoms=atoms,
                        cta_final_line=cta_line,
                        preset_contract=preset_contract,
                        sliders=slider_params,
                    ),
                    validator=None,
                    trace_stage=rewrite_stage,
                )
                draft.setdefault("preset_id", ctx.preset_id)
                draft.setdefault("selected_angle_id", selected_angle_id)
                draft.setdefault("used_hook_ids", list(atoms.get("used_hook_ids") or []))
                draft, rewrite_steps = self._mechanical_postprocess(draft, slider_params, cta_line, trace)
                final_codes = validate_email_draft(
                    draft,
                    brief=messaging_brief,
                    cta_final_line=cta_line,
                    sliders=slider_params,
                    preset_contract=preset_contract,
                )
                self._annotate_draft_stage(
                    trace=trace,
                    stage_name=rewrite_stage,
                    draft=draft,
                    validation_codes=final_codes,
                    mechanical_steps=rewrite_steps,
                    final_validation_status="failed" if final_codes else "passed",
                    preset_contract=preset_contract,
                    stage_details={
                        "post_rewrite_word_count": preset_word_count(str(draft.get("body") or "").strip()),
                        "dominant_failing_rule": dominant_validation_code(final_codes),
                        "salvage_applied": False,
                        "salvage_result": "not_run",
                    },
                )
                if final_codes:
                    draft, final_codes, salvage_applied, salvage_result = await self._maybe_salvage_rewrite(
                        trace=trace,
                        preset_id=ctx.preset_id,
                        draft=draft,
                        atoms=atoms,
                        messaging_brief=messaging_brief,
                        cta_line=cta_line,
                        slider_params=slider_params,
                        preset_contract=preset_contract,
                        final_codes=final_codes,
                    )
                    trace.annotate_stage(
                        stage=rewrite_stage,
                        details={
                            "salvage_applied": salvage_applied,
                            "salvage_result": salvage_result,
                            "post_salvage_word_count": preset_word_count(str(draft.get("body") or "").strip())
                            if salvage_applied
                            else None,
                        },
                    )
                    if final_codes:
                        trace.add_validation_error(stage=STAGES["E"], codes=final_codes)
                        return self._error_result(
                            trace=trace,
                            code="VALIDATION_FAILED",
                            message="Final validation failed",
                            stage="VALIDATION",
                            details={"codes": final_codes},
                        )
            elif validation_codes:
                return self._error_result(
                    trace=trace,
                    code="VALIDATION_FAILED",
                    message="Email validation failed",
                    stage="VALIDATION",
                    details={"codes": validation_codes},
                )

            provenance = {
                "preset_id": str(draft.get("preset_id") or ctx.preset_id),
                "selected_angle_id": str(draft.get("selected_angle_id") or selected_angle_id),
                "used_hook_ids": list(draft.get("used_hook_ids") or []),
                "rewrite_applied": rewrite_applied,
            }
            outcome = {
                "ok": True,
                "subject_hash": trace.hashes.get("output:EMAIL_REWRITE") or trace.hashes.get("output:EMAIL_GENERATION"),
            }
            trace.finalize(outcome=outcome, write_debug=self.settings.app_env in {"local", "dev"})
            return PipelineResult(
                ok=True,
                trace_id=trace.trace_id,
                stage_stats=list(trace.stage_stats),
                subject=str(draft.get("subject") or "").strip(),
                body=str(draft.get("body") or "").strip(),
                provenance=provenance,
            )
        except StageError as exc:
            return self._error_result(
                trace=trace,
                code=exc.code,
                message=exc.message,
                stage=exc.stage,
                details=exc.details,
            )
        except Exception as exc:  # noqa: BLE001
            return self._error_result(
                trace=trace,
                code="UNKNOWN",
                message="Unhandled pipeline error",
                stage="UNKNOWN",
                details={"error": str(exc)},
            )

    async def _build_or_load_brief_stack(self, *, request: WebGenerateRequest, ctx: Any, trace: Trace, cta_line: str):
        cache_context = self._cache_context(ctx=ctx, cta_line=cta_line)
        cache_key = compute_brief_cache_key(cache_context)
        cached = self.brief_cache.get(cache_key)
        if cached is not None:
            trace.set_meta(cache_hit=True, brief_cache_key=cache_key)
            return cached["messaging_brief"], cached["fit_map"], cached["angle_set"]

        trace.set_meta(cache_hit=False, brief_cache_key=cache_key)

        stage_a_input = self._stage_a_input(request=request, ctx=ctx, cta_line=cta_line)
        messaging_brief = await self._run_stage(
            trace=trace,
            config=StageConfig(
                stage=STAGES["A"],
                max_tokens=1800,
                reasoning_effort=self.settings.openai_reasoning_low,
                response_format=RF_MESSAGING_BRIEF,
            ),
            messages=stage_a.build_messages(stage_a_input, research_state=ctx.research_state),
            validator=lambda payload: validate_messaging_brief(
                payload,
                source_text=ctx.research_text,
                source_payload=stage_a_input,
            ),
            postprocess=lambda payload: self._sanitize_stage_a_payload(
                payload,
                source_text=ctx.research_text,
                source_payload=stage_a_input,
            ),
        )

        fit_map = await self._run_stage(
            trace=trace,
            config=StageConfig(
                stage=STAGES["B"],
                max_tokens=1200,
                reasoning_effort=self.settings.openai_reasoning_high,
                response_format=RF_FIT_MAP,
            ),
            messages=stage_b.build_messages(messaging_brief),
            validator=lambda payload: validate_fit_map(payload, messaging_brief),
        )

        angle_set = await self._run_stage(
            trace=trace,
            config=StageConfig(
                stage=STAGES["B0"],
                max_tokens=1000,
                reasoning_effort=self.settings.openai_reasoning_high,
                response_format=RF_ANGLE_SET,
            ),
            messages=stage_b0.build_messages(messaging_brief, fit_map),
            validator=lambda payload: validate_angle_set(payload, messaging_brief, fit_map),
        )

        self.brief_cache.set(
            cache_key,
            {
                "messaging_brief": messaging_brief,
                "fit_map": fit_map,
                "angle_set": angle_set,
            },
        )
        return messaging_brief, fit_map, angle_set

    async def _run_pipeline_presets(
        self,
        *,
        request: WebGenerateRequest,
        trace: Trace,
        preset_ids: list[str],
        sliders: dict[str, Any] | None,
        preset_sliders: dict[str, dict[str, Any]] | None,
    ) -> PipelineResult:
        if not self.openai.enabled():
            return self._error_result(
                trace=trace,
                code="OPENAI_UNAVAILABLE",
                message="OpenAI provider is unavailable",
                stage="TRANSPORT",
                details={},
            )

        active_preset = str((preset_ids or [request.preset_id or "direct"])[0] or "direct")
        ctx = normalize_generate_request(request, preset_id=active_preset)
        slider_params = self._build_slider_params(request, ctx, sliders)
        cta_line = self._cta_lock(request, ctx)

        trace.set_meta(
            mode="preset_browse",
            preset_ids=list(preset_ids),
            sliders=slider_params,
            research_state=ctx.research_state,
            preset_slider_overrides=sorted(list((preset_sliders or {}).keys())),
        )

        try:
            messaging_brief, fit_map, angle_set = await self._build_or_load_brief_stack(
                request=request,
                ctx=ctx,
                trace=trace,
                cta_line=cta_line,
            )
            selected_angle_id = str((angle_set.get("angles") or [{}])[0].get("angle_id") or "")
            if not selected_angle_id:
                raise StageError(stage=STAGES["B0"], code="ANGLE_SELECTION_FAILED", message="No angle available", details={})

            atoms = await self._run_stage(
                trace=trace,
                config=StageConfig(
                    stage=STAGES["C0"],
                    max_tokens=400,
                    reasoning_effort=self.settings.openai_reasoning_low,
                    response_format=RF_MESSAGE_ATOMS,
                ),
                messages=stage_c0.build_messages(
                    messaging_brief,
                    fit_map,
                    angle_set,
                    selected_angle_id,
                    slider_params,
                    cta_line,
                ),
                validator=lambda payload: validate_message_atoms(
                    payload,
                    cta_final_line=cta_line,
                    forbidden_patterns=list(messaging_brief.get("forbidden_claim_patterns") or []),
                ),
            )
            atoms = self._normalize_message_atoms(atoms, cta_line=cta_line, trace=trace)

            output_variants: list[dict[str, Any]] = []
            for requested_id in preset_ids:
                try:
                    preset = load_preset(requested_id)
                    variant_sliders = self._build_slider_params(
                        request,
                        ctx,
                        (preset_sliders or {}).get(str(requested_id)),
                    )
                    preset_contract = self._resolved_preset_contract(preset=preset, sliders=variant_sliders)
                    self._remember_preset_contract(trace=trace, preset_id=str(requested_id), preset_contract=preset_contract)
                    generation_stage = self._trace_stage_name(STAGES["C"], preset_id=requested_id)
                    qa_stage = self._trace_stage_name(STAGES["D"], preset_id=requested_id)
                    rewrite_stage = self._trace_stage_name(STAGES["E"], preset_id=requested_id)

                    draft = await self._run_stage(
                        trace=trace,
                        config=StageConfig(
                            stage=STAGES["C"],
                            max_tokens=800,
                            reasoning_effort=self.settings.openai_reasoning_low,
                            response_format=RF_EMAIL_DRAFT,
                        ),
                        messages=stage_c.build_single_messages(
                            messaging_brief=messaging_brief,
                            fit_map=fit_map,
                            angle_set=angle_set,
                            message_atoms=atoms,
                            preset=preset,
                            sliders=variant_sliders,
                            cta_final_line=cta_line,
                        ),
                        validator=None,
                        trace_stage=generation_stage,
                    )
                    draft.setdefault("preset_id", str(requested_id))
                    draft.setdefault("selected_angle_id", selected_angle_id)
                    draft.setdefault("used_hook_ids", list(atoms.get("used_hook_ids") or []))
                    draft, generation_steps = self._mechanical_postprocess(draft, variant_sliders, cta_line, trace)

                    validation_codes = validate_email_draft(
                        draft,
                        brief=messaging_brief,
                        cta_final_line=cta_line,
                        sliders=variant_sliders,
                        preset_contract=preset_contract,
                    )
                    if validation_codes:
                        trace.add_validation_error(stage=generation_stage, codes=validation_codes)
                    self._annotate_draft_stage(
                        trace=trace,
                        stage_name=generation_stage,
                        draft=draft,
                        validation_codes=validation_codes,
                        mechanical_steps=generation_steps,
                        final_validation_status="rewrite_required" if validation_codes else "passed",
                        preset_contract=preset_contract,
                        stage_details={
                            "pre_rewrite_word_count": preset_word_count(str(draft.get("body") or "").strip()),
                            "salvage_applied": False,
                            "salvage_result": "not_run",
                        },
                    )

                    qa = await self._run_stage(
                        trace=trace,
                        config=StageConfig(
                            stage=STAGES["D"],
                            max_tokens=800,
                            reasoning_effort=self.settings.openai_reasoning_high,
                            response_format=RF_QA_REPORT,
                        ),
                        messages=stage_d.build_messages(draft, messaging_brief, atoms, cta_line, preset_contract),
                        validator=None,
                        trace_stage=qa_stage,
                    )
                    qa = normalize_qa_report(qa)
                    self._annotate_qa_stage(
                        trace=trace,
                        stage_name=qa_stage,
                        preset_id=str(requested_id),
                        preset_contract=preset_contract,
                        draft=draft,
                        qa_report=qa,
                        generation_validation_codes=validation_codes,
                    )
                    self._annotate_draft_stage(
                        trace=trace,
                        stage_name=generation_stage,
                        draft=draft,
                        validation_codes=validation_codes,
                        mechanical_steps=generation_steps,
                        final_validation_status="rewrite_required" if (validation_codes or qa.get("pass_rewrite_needed")) else "passed",
                        preset_contract=preset_contract,
                        stage_details={
                            "dominant_failing_rule": dominant_validation_code(validation_codes)
                            or next(
                                (str(item.get("type") or "").strip() for item in qa.get("issues") or [] if str(item.get("type") or "").strip()),
                                None,
                            ),
                        },
                    )

                    rewrite_applied = False
                    if qa.get("pass_rewrite_needed") or validation_codes:
                        rewrite_applied = True
                        draft = await self._run_stage(
                            trace=trace,
                            config=StageConfig(
                                stage=STAGES["E"],
                                max_tokens=800,
                                reasoning_effort=self.settings.openai_reasoning_low,
                                response_format=RF_EMAIL_DRAFT,
                            ),
                            messages=stage_e.build_messages(
                                email_draft=draft,
                                qa_report=qa,
                                messaging_brief=messaging_brief,
                                message_atoms=atoms,
                                cta_final_line=cta_line,
                                preset_contract=preset_contract,
                                sliders=variant_sliders,
                            ),
                            validator=None,
                            trace_stage=rewrite_stage,
                        )
                        draft["preset_id"] = str(requested_id)
                        draft["selected_angle_id"] = selected_angle_id
                        draft.setdefault("used_hook_ids", list(atoms.get("used_hook_ids") or []))
                        draft, rewrite_steps = self._mechanical_postprocess(draft, variant_sliders, cta_line, trace)

                        final_codes = validate_email_draft(
                            draft,
                            brief=messaging_brief,
                            cta_final_line=cta_line,
                            sliders=variant_sliders,
                            preset_contract=preset_contract,
                        )
                        self._annotate_draft_stage(
                            trace=trace,
                            stage_name=rewrite_stage,
                            draft=draft,
                            validation_codes=final_codes,
                            mechanical_steps=rewrite_steps,
                            final_validation_status="failed" if final_codes else "passed",
                            preset_contract=preset_contract,
                            stage_details={
                                "post_rewrite_word_count": preset_word_count(str(draft.get("body") or "").strip()),
                                "dominant_failing_rule": dominant_validation_code(final_codes),
                                "salvage_applied": False,
                                "salvage_result": "not_run",
                            },
                        )
                        if final_codes:
                            draft, final_codes, salvage_applied, salvage_result = await self._maybe_salvage_rewrite(
                                trace=trace,
                                preset_id=str(requested_id),
                                draft=draft,
                                atoms=atoms,
                                messaging_brief=messaging_brief,
                                cta_line=cta_line,
                                slider_params=variant_sliders,
                                preset_contract=preset_contract,
                                final_codes=final_codes,
                            )
                            trace.annotate_stage(
                                stage=rewrite_stage,
                                details={
                                    "salvage_applied": salvage_applied,
                                    "salvage_result": salvage_result,
                                    "post_salvage_word_count": preset_word_count(str(draft.get("body") or "").strip())
                                    if salvage_applied
                                    else None,
                                },
                            )
                            if final_codes:
                                trace.add_validation_error(stage=rewrite_stage, codes=final_codes)
                                output_variants.append(
                                    {
                                        "preset_id": str(requested_id),
                                        "error": {
                                            "code": "VALIDATION_FAILED",
                                            "message": f"Variant failed validation: {', '.join(final_codes)}",
                                        },
                                    }
                                )
                                continue

                    final_codes = validate_email_draft(
                        draft,
                        brief=messaging_brief,
                        cta_final_line=cta_line,
                        sliders=variant_sliders,
                        preset_contract=preset_contract,
                    )
                    if final_codes:
                        output_variants.append(
                            {
                                "preset_id": str(requested_id),
                                "error": {
                                    "code": "VALIDATION_FAILED",
                                    "message": f"Variant failed validation: {', '.join(final_codes)}",
                                },
                            }
                        )
                        continue

                    output_variants.append(
                        {
                            "preset_id": str(requested_id),
                            "subject": str(draft.get("subject") or "").strip(),
                            "body": str(draft.get("body") or "").strip(),
                            "used_hook_ids": list(draft.get("used_hook_ids") or []),
                            "selected_angle_id": selected_angle_id,
                            "rewrite_applied": rewrite_applied,
                        }
                    )
                except StageError as exc:
                    output_variants.append(
                        {
                            "preset_id": str(requested_id),
                            "error": {
                                "code": exc.code,
                                "message": exc.message,
                            },
                        }
                    )

            success_count = sum(1 for item in output_variants if "subject" in item and "body" in item)
            if success_count == 0:
                return self._error_result(
                    trace=trace,
                    code="ALL_VARIANTS_FAILED",
                    message="All preset variants failed",
                    stage="EMAIL_GENERATION",
                    details={"variants": output_variants},
                )

            trace.finalize(
                outcome={"ok": True, "success_variants": success_count, "total_variants": len(output_variants)},
                write_debug=self.settings.app_env in {"local", "dev"},
            )
            return PipelineResult(
                ok=True,
                trace_id=trace.trace_id,
                stage_stats=list(trace.stage_stats),
                variants=output_variants,
            )
        except StageError as exc:
            return self._error_result(
                trace=trace,
                code=exc.code,
                message=exc.message,
                stage=exc.stage,
                details=exc.details,
            )
        except Exception as exc:  # noqa: BLE001
            return self._error_result(
                trace=trace,
                code="UNKNOWN",
                message="Unhandled pipeline error",
                stage="UNKNOWN",
                details={"error": str(exc)},
            )

    def _mechanical_postprocess(
        self,
        draft: dict[str, Any],
        sliders: dict[str, Any],
        cta_line: str,
        trace: Trace,
    ) -> tuple[dict[str, Any], list[str]]:
        min_words, max_words = _length_band(str(sliders.get("length") or "medium"))
        del min_words
        legacy = LegacyEmailDraft(subject=str(draft.get("subject") or ""), body=str(draft.get("body") or ""))
        result = deterministic_postprocess_draft(
            legacy,
            max_words=max_words,
            cta_line=cta_line,
            subject_limit=70,
        )
        for step in result.applied:
            trace.add_postprocess_step(step)
        out = dict(draft)
        out["subject"] = result.draft.subject.strip()
        out["body"] = result.draft.body.strip()
        return out, list(result.applied)

    def _error_result(
        self,
        *,
        trace: Trace,
        code: str,
        message: str,
        stage: str,
        details: dict[str, Any],
    ) -> PipelineResult:
        if not any(str(item.get("stage") or "") == stage for item in trace.stage_stats):
            trace.stage_stats.append(
                {
                    "stage": stage,
                    "status": "failed",
                    "model": ENFORCED_OPENAI_MODEL,
                    "elapsed_ms": 0,
                    "error_code": code,
                    "details": details,
                    "raw_validation_status": "failed",
                    "final_validation_status": "failed",
                    "error_codes": list((details or {}).get("codes") or []),
                    "mechanical_postprocess_applied": [],
                }
            )
        trace.finalize(
            outcome={"ok": False, "code": code, "message": message, "stage": stage},
            write_debug=self.settings.app_env in {"local", "dev"},
        )
        return PipelineResult(
            ok=False,
            trace_id=trace.trace_id,
            stage_stats=list(trace.stage_stats),
            error={
                "code": code,
                "message": message,
                "stage": stage,
                "details": details,
            },
        )


def _length_band(length: str) -> tuple[int, int]:
    key = str(length or "medium").strip().lower()
    if key == "short":
        return (40, 80)
    if key == "long":
        return (140, 220)
    return (80, 140)


BANNED_DO_NOT_SAY_DEFAULT = [
    "touch base",
    "circle back",
    "synergy",
    "leverage",
    "game-changer",
    "revolutionary",
    "I hope this email finds you",
    "I wanted to reach out",
    "just checking in",
]


def available_presets() -> list[str]:
    return sorted(load_all_presets().keys())
