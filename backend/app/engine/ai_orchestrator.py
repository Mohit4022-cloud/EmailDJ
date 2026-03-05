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
from .presets.registry import load_all_presets, load_preset
from .prompts import stage_a, stage_b, stage_b0, stage_c, stage_c0, stage_d, stage_e
from .schemas import (
    RF_ANGLE_SET,
    RF_BATCH_VARIANTS,
    RF_EMAIL_DRAFT,
    RF_FIT_MAP,
    RF_MESSAGING_BRIEF,
    RF_MESSAGE_ATOMS,
    RF_QA_REPORT,
    STAGES,
)
from .stage_runner import StageConfig, StageError, run_stage
from .tracer import Trace
from .types import EmailDraft as LegacyEmailDraft
from .validators import (
    ValidationIssue,
    normalize_qa_report,
    validate_angle_set,
    validate_email_draft,
    validate_fit_map,
    validate_message_atoms,
    validate_messaging_brief,
)


DEFAULT_CTA = "Open to a quick chat to see if this is relevant?"
TOTAL_PIPELINE_TIMEOUT_SECONDS = 90.0
STAGE_TIMEOUT_SECONDS = 25.0


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
    ) -> PipelineResult:
        try:
            return await asyncio.wait_for(
                self._run_pipeline_presets(request=request, trace=trace, preset_ids=preset_ids, sliders=sliders),
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

    def _stage_a_input(self, *, request: WebGenerateRequest, ctx: Any, cta_line: str) -> dict[str, Any]:
        preset = load_preset(ctx.preset_id)
        return {
            "user_company": {
                "name": ctx.sender_company_name,
                "product_summary": ctx.current_product or ctx.offer_lock,
                "icp_description": ctx.company_notes,
                "differentiators": list(ctx.seller_offerings[:6]),
                "proof_points": list(ctx.proof_points[:8]),
                "do_not_say": list(dict.fromkeys([*preset.get("banned_phrases_additions", []), *BANNED_DO_NOT_SAY_DEFAULT])),
                "company_notes": ctx.company_notes,
            },
            "prospect": {
                "name": ctx.prospect_name,
                "title": ctx.prospect_title,
                "company": ctx.prospect_company,
                "industry": "",
                "notes": "",
                "research_text": ctx.research_text,
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
                "proof_points": list(ctx.proof_points),
            },
            "prospect": {
                "name": ctx.prospect_name,
                "title": ctx.prospect_title,
                "company": ctx.prospect_company,
                "industry": "",
                "notes": "",
                "research_text": ctx.research_text,
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

    async def _run_stage(
        self,
        *,
        trace: Trace,
        config: StageConfig,
        messages: list[dict[str, str]],
        validator,
    ) -> dict[str, Any]:
        trace.start_stage(stage=config.stage, model=ENFORCED_OPENAI_MODEL)
        try:
            result = await run_stage(
                openai=self.openai,
                config=config,
                messages=messages,
                validator=validator,
                timeout_seconds=STAGE_TIMEOUT_SECONDS,
            )
            trace.end_stage(
                stage=config.stage,
                model=ENFORCED_OPENAI_MODEL,
                schema_ok=True,
                output=result.payload,
                attempt_count=result.attempts,
                details={"usage": result.usage},
            )
            return result.payload
        except StageError as exc:
            trace.fail_stage(stage=config.stage, model=ENFORCED_OPENAI_MODEL, error_code=exc.code, details=exc.details)
            raise
        except ValidationIssue as exc:
            trace.add_validation_error(stage=config.stage, codes=exc.codes)
            trace.fail_stage(
                stage=config.stage,
                model=ENFORCED_OPENAI_MODEL,
                error_code="VALIDATION_FAILED",
                details={"codes": exc.codes},
            )
            raise StageError(
                stage=config.stage,
                code="VALIDATION_FAILED",
                message="Stage deterministic validation failed",
                details={"codes": exc.codes},
            ) from exc

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
        trace.set_meta(mode="single", preset_id=ctx.preset_id, sliders=slider_params)

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
            )
            draft.setdefault("preset_id", ctx.preset_id)
            draft.setdefault("selected_angle_id", selected_angle_id)
            draft.setdefault("used_hook_ids", list(atoms.get("used_hook_ids") or []))

            draft = self._mechanical_postprocess(draft, slider_params, cta_line, trace)

            validation_codes = validate_email_draft(draft, brief=messaging_brief, cta_final_line=cta_line, sliders=slider_params)
            if validation_codes:
                trace.add_validation_error(stage=STAGES["C"], codes=validation_codes)

            qa = await self._run_stage(
                trace=trace,
                config=StageConfig(
                    stage=STAGES["D"],
                    max_tokens=800,
                    reasoning_effort=self.settings.openai_reasoning_high,
                    response_format=RF_QA_REPORT,
                ),
                messages=stage_d.build_messages(draft, messaging_brief, atoms, cta_line),
                validator=None,
            )
            qa = normalize_qa_report(qa)

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
                        sliders=slider_params,
                    ),
                    validator=None,
                )
                draft.setdefault("preset_id", ctx.preset_id)
                draft.setdefault("selected_angle_id", selected_angle_id)
                draft.setdefault("used_hook_ids", list(atoms.get("used_hook_ids") or []))
                draft = self._mechanical_postprocess(draft, slider_params, cta_line, trace)
                final_codes = validate_email_draft(
                    draft,
                    brief=messaging_brief,
                    cta_final_line=cta_line,
                    sliders=slider_params,
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
            messages=stage_a.build_messages(stage_a_input),
            validator=lambda payload: validate_messaging_brief(payload, source_text=ctx.research_text),
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

        trace.set_meta(mode="preset_browse", preset_ids=list(preset_ids), sliders=slider_params)

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

            presets = [load_preset(pid) for pid in preset_ids]
            batch = await self._run_stage(
                trace=trace,
                config=StageConfig(
                    stage=STAGES["C"],
                    max_tokens=2400,
                    reasoning_effort=self.settings.openai_reasoning_low,
                    response_format=RF_BATCH_VARIANTS,
                ),
                messages=stage_c.build_batch_messages(
                    messaging_brief=messaging_brief,
                    fit_map=fit_map,
                    angle_set=angle_set,
                    message_atoms=atoms,
                    presets=presets,
                    sliders=slider_params,
                    cta_final_line=cta_line,
                ),
                validator=None,
            )

            output_variants: list[dict[str, Any]] = []
            for requested_id in preset_ids:
                matched = next(
                    (item for item in (batch.get("variants") or []) if str(item.get("preset_id") or "") == str(requested_id)),
                    None,
                )
                if matched is None:
                    output_variants.append(
                        {
                            "preset_id": str(requested_id),
                            "error": {"code": "VARIANT_MISSING", "message": "Variant missing from model output"},
                        }
                    )
                    continue

                if matched.get("error"):
                    output_variants.append(
                        {
                            "preset_id": str(requested_id),
                            "error": {
                                "code": str(matched.get("error", {}).get("code") or "VARIANT_ERROR"),
                                "message": str(matched.get("error", {}).get("message") or "Variant generation failed"),
                            },
                        }
                    )
                    continue

                draft = {
                    "preset_id": str(requested_id),
                    "subject": str(matched.get("subject") or "").strip(),
                    "body": str(matched.get("body") or "").strip(),
                    "used_hook_ids": list(matched.get("used_hook_ids") or atoms.get("used_hook_ids") or []),
                    "selected_angle_id": selected_angle_id,
                }
                draft = self._mechanical_postprocess(draft, slider_params, cta_line, trace)

                validation_codes = validate_email_draft(
                    draft,
                    brief=messaging_brief,
                    cta_final_line=cta_line,
                    sliders=slider_params,
                )
                if validation_codes:
                    trace.add_validation_error(stage=f"{STAGES['C']}:{requested_id}", codes=validation_codes)

                try:
                    qa = await self._run_stage(
                        trace=trace,
                        config=StageConfig(
                            stage=STAGES["D"],
                            max_tokens=800,
                            reasoning_effort=self.settings.openai_reasoning_high,
                            response_format=RF_QA_REPORT,
                        ),
                        messages=stage_d.build_messages(draft, messaging_brief, atoms, cta_line),
                        validator=None,
                    )
                    qa = normalize_qa_report(qa)

                    if qa.get("pass_rewrite_needed") or validation_codes:
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
                                sliders=slider_params,
                            ),
                            validator=None,
                        )
                        draft["preset_id"] = str(requested_id)
                        draft["selected_angle_id"] = selected_angle_id
                        draft.setdefault("used_hook_ids", list(atoms.get("used_hook_ids") or []))
                        draft = self._mechanical_postprocess(draft, slider_params, cta_line, trace)

                    final_codes = validate_email_draft(
                        draft,
                        brief=messaging_brief,
                        cta_final_line=cta_line,
                        sliders=slider_params,
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

    def _mechanical_postprocess(self, draft: dict[str, Any], sliders: dict[str, Any], cta_line: str, trace: Trace) -> dict[str, Any]:
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
        return out

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
