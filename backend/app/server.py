from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, AsyncGenerator
from uuid import uuid4

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, load_settings
from app.enrichment import EnrichmentService
from app.engine import (
    axis_to_slider,
)
from app.engine.ai_orchestrator import AIOrchestrator, available_presets
from app.engine.brief_cache import BriefCache
from app.engine.tracer import Trace
from app.openai_client import OpenAIClient
from app.prompts import PROMPT_TEMPLATE_VERSION, prompt_template_hash
from app.rendering import render_to_text
from app.schemas import (
    EnrichmentAccepted,
    PresetPreviewBatchItem,
    PresetPreviewBatchRequest,
    PresetPreviewBatchResponse,
    PresetPreviewRequest,
    PresetPreviewResponse,
    ResearchCreateResponse,
    ResearchRequest,
    ResearchResult,
    ResearchStatusResponse,
    SenderEnrichmentRequest,
    TargetEnrichmentRequest,
    WebFeedbackRequest,
    WebGenerateAccepted,
    WebGenerateRequest,
    WebRemixAccepted,
    WebRemixRequest,
)
from app.sse import stream_response


logger = logging.getLogger(__name__)


@dataclass
class RequestRecord:
    kind: str
    session_id: str | None
    payload: dict[str, Any]
    created_at: float


@dataclass
class ResearchJob:
    job_id: str
    payload: dict[str, Any]
    status: str
    progress: str | None
    result: ResearchResult | str | None
    error: str | None
    created_at: float
    updated_at: float


class AppState:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.openai = OpenAIClient(settings)
        self.enrichment = EnrichmentService(settings, self.openai)
        self.brief_cache = BriefCache(max_size=200, ttl_seconds=30 * 60)
        self.orchestrator = AIOrchestrator(openai=self.openai, settings=self.settings, brief_cache=self.brief_cache)
        self.requests: dict[str, RequestRecord] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.rate: dict[str, list[float]] = {}
        self.session_rate: dict[str, list[float]] = {}
        self.research_jobs: dict[str, ResearchJob] = {}

    def cleanup_requests(self, ttl_seconds: int = 5 * 60) -> None:
        now = time.time()
        expired = [rid for rid, rec in self.requests.items() if now - rec.created_at > ttl_seconds]
        for rid in expired:
            self.requests.pop(rid, None)

    def cleanup_research_jobs(self, ttl_seconds: int = 30 * 60) -> None:
        now = time.time()
        expired = [job_id for job_id, job in self.research_jobs.items() if now - job.updated_at > ttl_seconds]
        for job_id in expired:
            self.research_jobs.pop(job_id, None)


state = AppState(load_settings())


def _normalize_contract(value: str | None) -> str:
    raw = str(value or "legacy_text").strip()
    if raw == "rc_tco_json_v1":
        return "email_json_v1"
    return raw or "legacy_text"


def _require_beta(beta_key: str | None) -> None:
    key = (beta_key or "").strip()
    if not key or key not in state.settings.beta_keys:
        raise HTTPException(status_code=401, detail={"error": "invalid_beta_key"})

    now = time.time()
    window_start = now - 60
    history = state.rate.setdefault(key, [])
    history[:] = [ts for ts in history if ts >= window_start]
    if len(history) >= state.settings.web_rate_limit_per_min:
        raise HTTPException(status_code=429, detail={"error": "rate_limited"})
    history.append(now)


def _require_session_rate(session_key: str) -> None:
    key = str(session_key or "").strip() or "anonymous"
    now = time.time()
    window_start = now - 60
    history = state.session_rate.setdefault(key, [])
    history[:] = [ts for ts in history if ts >= window_start]
    if len(history) >= 10:
        raise HTTPException(status_code=429, detail={"error": "rate_limited_session"})
    history.append(now)


def _slider_summary_from_style(style_profile: dict[str, float]) -> dict[str, int]:
    return {
        "formality": axis_to_slider(float(style_profile.get("formality", 0.0))),
        "orientation": axis_to_slider(float(style_profile.get("orientation", 0.0))),
        "length": axis_to_slider(float(style_profile.get("length", 0.0))),
        "assertiveness": axis_to_slider(float(style_profile.get("assertiveness", 0.0))),
    }


def _vibe_tags(style_profile: dict[str, float]) -> list[str]:
    return [
        "Problem-Led" if float(style_profile.get("orientation", 0.0)) < 0 else "Outcome-Led",
        "Short-Form" if float(style_profile.get("length", 0.0)) < 0 else "Long-Form",
        "Bold" if float(style_profile.get("assertiveness", 0.0)) < 0 else "Diplomatic",
    ]


def _why_it_works() -> list[str]:
    return [
        "First line is grounded in provided research or explicitly hedged hypothesis.",
        "Proof point comes from provided context only.",
        "CTA lock is preserved verbatim as the final line.",
    ]


def _sources_from_generate_request(req: WebGenerateRequest) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for profile in (req.target_profile_override, req.contact_profile_override, req.sender_profile_override):
        if profile is None:
            continue
        for citation in getattr(profile, "citations", []) or []:
            if hasattr(citation, "model_dump"):
                out.append(citation.model_dump(mode="json"))
            elif isinstance(citation, dict):
                out.append(dict(citation))
    return out


def _style_axis_to_length(axis_value: float) -> str:
    slider = axis_to_slider(axis_value)
    if slider <= 33:
        return "short"
    if slider >= 67:
        return "long"
    return "medium"


def _sliders_from_style_profile(style_profile: dict[str, float]) -> dict[str, Any]:
    tone = 1.0 - (axis_to_slider(float(style_profile.get("formality", 0.0))) / 100.0)
    framing = axis_to_slider(float(style_profile.get("orientation", 0.0))) / 100.0
    stance = axis_to_slider(float(style_profile.get("assertiveness", 0.0))) / 100.0
    return {
        "tone": max(0.0, min(1.0, tone)),
        "framing": max(0.0, min(1.0, framing)),
        "length": _style_axis_to_length(float(style_profile.get("length", 0.0))),
        "stance": max(0.0, min(1.0, stance)),
    }


def _preview_request_to_generate(req: PresetPreviewRequest, *, sliders: dict[str, Any]) -> WebGenerateRequest:
    return WebGenerateRequest(
        prospect=req.prospect,
        prospect_first_name=req.prospect_first_name,
        research_text=req.research_text,
        offer_lock=req.offer_lock,
        cta_offer_lock=req.cta_offer_lock,
        cta_type=req.cta_type,
        preset_id=req.preset_id,
        mode="single",
        sliders=sliders,
        response_contract="email_json_v1",
        style_profile=req.style_profile,
        company_context=req.company_context,
    )


def _sliders_from_batch_request(req: PresetPreviewBatchRequest) -> dict[str, Any]:
    global_sliders = req.global_sliders.model_dump(mode="json")
    formality = int(global_sliders.get("formality", 50))
    personalization = int(global_sliders.get("personalization", 50))
    directness = int(global_sliders.get("directness", 50))
    brevity = int(global_sliders.get("brevity", 50))
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


def _batch_preview_to_generate(req: PresetPreviewBatchRequest, *, sliders: dict[str, Any]) -> WebGenerateRequest:
    return WebGenerateRequest(
        prospect=req.prospect,
        prospect_first_name=req.prospect_first_name,
        research_text=req.raw_research.deep_research_paste,
        offer_lock=req.offer_lock,
        cta_offer_lock=req.cta_lock or req.cta_lock_text,
        cta_type=req.cta_type,
        preset_id=(req.presets[0].preset_id if req.presets else "direct"),
        preset_ids=[item.preset_id for item in req.presets],
        mode="preset_browse",
        sliders=sliders,
        response_contract="email_json_v1",
        company_context={
            "current_product": req.product_context.product_name,
            "company_notes": req.raw_research.company_notes,
            "seller_offerings": req.product_context.proof_points,
            "cta_offer_lock": req.cta_lock or req.cta_lock_text,
            "cta_type": req.cta_type,
        },
    )


def _effective_batch_sliders(req: PresetPreviewBatchRequest, preset: Any) -> dict[str, int]:
    base = dict(req.global_sliders.model_dump(mode="json"))
    for key in ("formality", "brevity", "directness", "personalization"):
        if key in (preset.slider_overrides or {}):
            base[key] = int(preset.slider_overrides[key])
    return base


def _engine_debug_payload(result: Any, *, total_latency_ms: int | None = None) -> dict[str, Any]:
    payload = {
        "hook_type": result.plan.hook_type,
        "violations": result.debug.violations,
        "validator_attempt_count": result.debug.validator_attempt_count,
        "repair_attempt_count": result.debug.repair_attempt_count,
        "repaired": result.debug.repaired,
        "degraded": result.debug.degraded,
        "draft_source": result.debug.draft_source,
        "llm_attempt_count": result.debug.llm_attempt_count,
        "stage_latency_ms": result.debug.stage_latency_ms,
        "length_input_raw": result.debug.length_input_raw,
        "length_normalized": result.debug.length_normalized,
        "word_band_min": result.debug.word_band_min,
        "word_band_max": result.debug.word_band_max,
        "word_count_llm_raw": result.debug.word_count_llm_raw,
        "word_count_final": result.debug.word_count_final,
        "postprocess_applied": result.debug.postprocess_applied,
        "validation_error_codes_raw": result.debug.validation_error_codes_raw,
        "validation_error_codes_final": result.debug.validation_error_codes_final,
    }
    if total_latency_ms is not None:
        payload["total_latency_ms"] = total_latency_ms
    return payload


def _log_prompt_trace(stage: str, payload: dict[str, Any]) -> None:
    logger.info("prompt_trace stage=%s payload=%s", stage, _sanitize_prompt_trace(payload))


def _truncate(value: str, *, limit: int = 420) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...<truncated>"


def _sanitize_prompt_trace(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, raw in value.items():
            lowered = str(key).lower()
            if isinstance(raw, str) and lowered in {"research_text", "company_notes"}:
                out[key] = _truncate(raw, limit=420)
                continue
            if isinstance(raw, str) and lowered in {"body", "draft_body"} and state.settings.app_env != "local":
                out[key] = "<redacted_body>"
                continue
            out[key] = _sanitize_prompt_trace(raw)
        return out
    if isinstance(value, list):
        return [_sanitize_prompt_trace(item) for item in value]
    if isinstance(value, str):
        return _truncate(value, limit=1000 if state.settings.app_env == "local" else 300)
    return value


router = APIRouter()


@router.get("/")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.5.0"}


@router.get("/web/v1/debug/config")
async def debug_config(x_emaildj_beta_key: str | None = Header(default=None)) -> dict[str, Any]:
    _require_beta(x_emaildj_beta_key)
    provider_configured = state.openai.enabled()
    return {
        "app_env": state.settings.app_env,
        "runtime_mode": "real" if provider_configured else "unavailable",
        "provider_stub_enabled": state.settings.provider_stub_enabled,
        "provider_configured": provider_configured,
        "llm_drafting_enabled": True,
        "llm_draft_runtime": "ai_only_fail_closed",
        "debug_prompt": state.settings.debug_prompt,
        "debug_trace_raw": state.settings.debug_trace_raw,
        "openai_model": "gpt-5-nano",
        "available_presets": available_presets(),
        "prompt_template_versions": {
            "web_mvp_prompt_hash": prompt_template_hash(),
            "web_mvp_prompt_version": PROMPT_TEMPLATE_VERSION,
        },
    }


@router.post("/web/v1/generate", response_model=WebGenerateAccepted)
async def web_generate(req: WebGenerateRequest, x_emaildj_beta_key: str | None = Header(default=None)) -> WebGenerateAccepted:
    _require_beta(x_emaildj_beta_key)
    state.cleanup_requests()

    session_id = str(uuid4())
    request_id = str(uuid4())
    mode = str(req.mode or "single")
    if mode not in {"single", "preset_browse"}:
        mode = "single"
    preset_ids = [str(item).strip() for item in (req.preset_ids or []) if str(item).strip()]
    if mode == "preset_browse" and not preset_ids:
        preset_ids = [str(req.preset_id or "direct")]

    state.sessions[session_id] = {
        "session_id": session_id,
        "generate_request": req.model_dump(mode="json"),
        "preset_id": req.preset_id,
        "preset_ids": preset_ids,
        "mode": mode,
        "style_profile": req.style_profile.model_dump(),
        "sliders": (req.sliders.model_dump(mode="json") if req.sliders else None),
        "response_contract": _normalize_contract(req.response_contract),
        "draft_id_counter": 0,
    }
    state.requests[request_id] = RequestRecord(
        kind="generate",
        session_id=session_id,
        payload={
            "style_profile": req.style_profile.model_dump(),
            "preset_id": req.preset_id,
            "preset_ids": preset_ids,
            "mode": mode,
            "sliders": (req.sliders.model_dump(mode="json") if req.sliders else None),
            "response_contract": _normalize_contract(req.response_contract),
        },
        created_at=time.time(),
    )
    return WebGenerateAccepted(request_id=request_id, session_id=session_id, stream_url=f"/web/v1/stream/{request_id}")


@router.post("/web/v1/remix", response_model=WebRemixAccepted)
async def web_remix(req: WebRemixRequest, x_emaildj_beta_key: str | None = Header(default=None)) -> WebRemixAccepted:
    _require_beta(x_emaildj_beta_key)
    state.cleanup_requests()

    session = state.sessions.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail={"error": "session_not_found"})

    if req.preset_id:
        session["preset_id"] = req.preset_id
    session["mode"] = "single"
    session["style_profile"] = req.style_profile.model_dump()

    request_id = str(uuid4())
    state.requests[request_id] = RequestRecord(
        kind="remix",
        session_id=req.session_id,
        payload={
            "style_profile": req.style_profile.model_dump(),
            "preset_id": req.preset_id,
            "mode": "single",
            "response_contract": session.get("response_contract") or "legacy_text",
        },
        created_at=time.time(),
    )
    return WebRemixAccepted(request_id=request_id, stream_url=f"/web/v1/stream/{request_id}")


@router.post("/web/v1/enrich/target", response_model=EnrichmentAccepted)
async def enrich_target(req: TargetEnrichmentRequest, x_emaildj_beta_key: str | None = Header(default=None)) -> EnrichmentAccepted:
    _require_beta(x_emaildj_beta_key)
    request_id = str(uuid4())
    state.requests[request_id] = RequestRecord(
        kind="enrich_target",
        session_id=None,
        payload=req.model_dump(mode="json"),
        created_at=time.time(),
    )
    return EnrichmentAccepted(request_id=request_id, stream_url=f"/web/v1/stream/{request_id}")


@router.post("/web/v1/enrich/prospect", response_model=EnrichmentAccepted)
async def enrich_prospect(req: dict[str, Any], x_emaildj_beta_key: str | None = Header(default=None)) -> EnrichmentAccepted:
    _require_beta(x_emaildj_beta_key)
    if not (req.get("target_company_name") or req.get("target_company_url") or req.get("prospect_company")):
        raise HTTPException(status_code=422, detail={"error": "target_company_anchor_required"})
    request_id = str(uuid4())
    state.requests[request_id] = RequestRecord(
        kind="enrich_prospect",
        session_id=None,
        payload=dict(req),
        created_at=time.time(),
    )
    return EnrichmentAccepted(request_id=request_id, stream_url=f"/web/v1/stream/{request_id}")


@router.post("/web/v1/enrich/sender", response_model=EnrichmentAccepted)
async def enrich_sender(req: SenderEnrichmentRequest, x_emaildj_beta_key: str | None = Header(default=None)) -> EnrichmentAccepted:
    _require_beta(x_emaildj_beta_key)
    request_id = str(uuid4())
    state.requests[request_id] = RequestRecord(
        kind="enrich_sender",
        session_id=None,
        payload=req.model_dump(mode="json"),
        created_at=time.time(),
    )
    return EnrichmentAccepted(request_id=request_id, stream_url=f"/web/v1/stream/{request_id}")


@router.post("/web/v1/preset-preview", response_model=PresetPreviewResponse)
async def preset_preview(req: PresetPreviewRequest, x_emaildj_beta_key: str | None = Header(default=None)) -> PresetPreviewResponse:
    _require_beta(x_emaildj_beta_key)
    sliders = _sliders_from_style_profile(req.style_profile.model_dump(mode="json"))
    generate_req = _preview_request_to_generate(req, sliders=sliders)
    trace = Trace(str(uuid4()), state.settings.app_env, debug_trace_raw=state.settings.debug_trace_raw)
    result = await state.orchestrator.run_pipeline_single(
        request=generate_req,
        trace=trace,
        preset_id=req.preset_id,
        sliders=sliders,
    )
    if not result.ok:
        raise HTTPException(status_code=422, detail=result.error or {"error": "preview_generation_failed"})

    style_summary = _slider_summary_from_style(req.style_profile.model_dump(mode="json"))
    return PresetPreviewResponse(
        preset_id=req.preset_id,
        subject=result.subject or "",
        body=result.body or "",
        vibeLabel=req.preset_id.replace("_", " ").title(),
        vibeTags=_vibe_tags(req.style_profile.model_dump(mode="json")),
        whyItWorks=_why_it_works(),
        sliderSummary=style_summary,
        validationWarning=None,
        debug={},
        meta={
            "trace_id": result.trace_id,
            "prompt_template_hash": prompt_template_hash(),
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            "stage_stats": result.stage_stats,
        },
    )


@router.post("/web/v1/preset-previews/batch", response_model=PresetPreviewBatchResponse)
async def preset_previews_batch(
    req: PresetPreviewBatchRequest,
    x_emaildj_beta_key: str | None = Header(default=None),
) -> PresetPreviewBatchResponse:
    _require_beta(x_emaildj_beta_key)
    started_at = time.perf_counter()
    sliders = _sliders_from_batch_request(req)
    generate_req = _batch_preview_to_generate(req, sliders=sliders)
    preset_ids = [str(item.preset_id) for item in req.presets]
    trace = Trace(str(uuid4()), state.settings.app_env, debug_trace_raw=state.settings.debug_trace_raw)
    orchestrated = await state.orchestrator.run_pipeline_presets(
        request=generate_req,
        trace=trace,
        preset_ids=preset_ids,
        sliders=sliders,
    )

    previews: list[PresetPreviewBatchItem] = []
    by_preset: dict[str, dict[str, Any]] = {
        str(item.get("preset_id") or ""): item for item in (orchestrated.variants or [])
    }
    failures = 0
    for preset in req.presets:
        matched = by_preset.get(str(preset.preset_id)) or {}
        error_payload = matched.get("error")
        if not error_payload and (not orchestrated.ok):
            error_payload = orchestrated.error or {"code": "PRESET_BATCH_FAILED", "message": "Preset browse failed"}
        if error_payload:
            failures += 1
        previews.append(
            PresetPreviewBatchItem(
                preset_id=preset.preset_id,
                label=preset.label,
                effective_sliders=_effective_batch_sliders(req, preset),
                vibeLabel=preset.label,
                vibeTags=["Preset"],
                whyItWorks=_why_it_works(),
                subject=(str(matched.get("subject") or "").strip() or None),
                body=(str(matched.get("body") or "").strip() or None),
                error=(dict(error_payload) if isinstance(error_payload, dict) else None),
                debug={"stage_stats": orchestrated.stage_stats},
            )
        )

    if not orchestrated.ok and not previews:
        raise HTTPException(status_code=422, detail=orchestrated.error or {"error": "preset_batch_failed"})

    total_latency_ms = int(round((time.perf_counter() - started_at) * 1000))
    return PresetPreviewBatchResponse(
        previews=previews,
        meta={
            "trace_id": orchestrated.trace_id,
            "prompt_template_hash": prompt_template_hash(),
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            "preset_count": len(req.presets),
            "failure_count": failures,
            "total_latency_ms": total_latency_ms,
            "degraded": bool(failures),
            "ok": orchestrated.ok,
            "error": orchestrated.error,
        },
    )


@router.post("/web/v1/feedback")
async def feedback(_: WebFeedbackRequest, x_emaildj_beta_key: str | None = Header(default=None)) -> dict[str, bool]:
    _require_beta(x_emaildj_beta_key)
    return {"ok": True}


async def _run_generate_like(record: RequestRecord, request_id: str) -> tuple[AsyncGenerator[dict[str, Any], None], dict[str, Any]]:
    session = state.sessions.get(record.session_id or "")
    if session is None:
        raise HTTPException(status_code=404, detail={"error": "session_not_found"})
    _require_session_rate(str(record.session_id or ""))

    draft_id = int(session.get("draft_id_counter") or 0) + 1
    session["draft_id_counter"] = draft_id
    generation_id = str(uuid4())
    trace_id = str(uuid4())

    req_payload = WebGenerateRequest(**session["generate_request"])
    style_payload = record.payload.get("style_profile") or session.get("style_profile") or {}
    style_model = req_payload.style_profile.__class__(**style_payload)
    preset_id = str(record.payload.get("preset_id") or session.get("preset_id") or req_payload.preset_id or "") or None
    preset_ids = [str(item).strip() for item in (record.payload.get("preset_ids") or session.get("preset_ids") or req_payload.preset_ids or []) if str(item).strip()]
    mode = str(record.payload.get("mode") or session.get("mode") or req_payload.mode or "single")
    sliders = record.payload.get("sliders") or session.get("sliders") or (req_payload.sliders.model_dump(mode="json") if req_payload.sliders else None)
    response_contract = _normalize_contract(str(record.payload.get("response_contract") or session.get("response_contract") or req_payload.response_contract))

    req_payload = req_payload.model_copy(
        update={
            "style_profile": style_model,
            "preset_id": preset_id,
            "preset_ids": preset_ids or req_payload.preset_ids,
            "mode": mode,
            "response_contract": response_contract,
        }
    )
    trace = Trace(trace_id, state.settings.app_env, debug_trace_raw=state.settings.debug_trace_raw)
    if mode == "preset_browse":
        orchestrated = await state.orchestrator.run_pipeline_presets(
            request=req_payload,
            trace=trace,
            preset_ids=preset_ids or [preset_id or "direct"],
            sliders=(sliders if isinstance(sliders, dict) else None),
        )
    else:
        orchestrated = await state.orchestrator.run_pipeline_single(
            request=req_payload,
            trace=trace,
            preset_id=preset_id,
            sliders=(sliders if isinstance(sliders, dict) else None),
        )

    done_extra = {
        **orchestrated.to_done_payload(),
        "session_id": record.session_id,
        "generation_id": generation_id,
        "draft_id": draft_id,
        "provider": "openai" if state.openai.enabled() else "unavailable",
        "model": "gpt-5-nano",
        "prompt_template_hash": prompt_template_hash(),
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
    }

    if orchestrated.ok and orchestrated.subject and orchestrated.body:
        session["last_render"] = {"subject": orchestrated.subject, "body": orchestrated.body}
        legacy_text = render_to_text(orchestrated.subject, orchestrated.body)
        if response_contract == "email_json_v1":
            done_extra["final"] = {"subject": orchestrated.subject, "body": orchestrated.body}
        else:
            done_extra["final"] = {"subject": orchestrated.subject, "body": legacy_text}
    else:
        legacy_text = ""

    async def wrapper() -> AsyncGenerator[dict[str, Any], None]:
        for item in orchestrated.stage_stats:
            stage_name = str(item.get("stage") or "UNKNOWN")
            status = str(item.get("status") or "complete")
            yield {
                "event": "stage",
                "data": {
                    "trace_id": orchestrated.trace_id,
                    "stage": stage_name,
                    "status": status,
                    "elapsed_ms": int(item.get("elapsed_ms") or 0),
                    "model": str(item.get("model") or "gpt-5-nano"),
                    "generation_id": generation_id,
                    "draft_id": draft_id,
                },
            }

        if orchestrated.ok and legacy_text:
            chunk_size = state.settings.stream_chunk_size
            for idx in range(0, len(legacy_text), chunk_size):
                chunk = legacy_text[idx : idx + chunk_size]
                await asyncio.sleep(0.004 if idx else 0.01)
                yield {
                    "event": "token",
                    "data": {
                        "token": chunk,
                        "chunk_index": idx // chunk_size,
                        "chunk_len": len(chunk),
                        "chunk_mode": "stable_chars",
                        "generation_id": generation_id,
                        "draft_id": draft_id,
                    },
                }

    return wrapper(), done_extra


async def _run_enrichment(record: RequestRecord) -> tuple[AsyncGenerator[dict[str, Any], None], dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    trace_id = str(uuid4())

    async def progress(event: str, data: dict[str, Any]) -> None:
        await queue.put({"event": event, "data": data})

    async def worker() -> None:
        try:
            if record.kind == "enrich_target":
                payload = TargetEnrichmentRequest(**record.payload)
                result = await state.enrichment.enrich_target(
                    company_name=payload.company_name,
                    company_url=payload.company_url,
                    refresh=payload.refresh,
                    progress=progress,
                )
                await queue.put({"event": "result", "data": {"target_profile": result.model_dump(mode="json")}})
            elif record.kind == "enrich_prospect":
                payload = dict(record.payload)
                result = await state.enrichment.enrich_contact(
                    prospect_name=str(payload.get("prospect_name") or ""),
                    prospect_title=str(payload.get("prospect_title") or "") or None,
                    prospect_company=str(payload.get("prospect_company") or "") or None,
                    prospect_linkedin_url=str(payload.get("prospect_linkedin_url") or "") or None,
                    target_company_name=str(payload.get("target_company_name") or "") or None,
                    target_company_url=str(payload.get("target_company_url") or "") or None,
                    refresh=bool(payload.get("refresh")),
                    progress=progress,
                )
                await queue.put({"event": "result", "data": {"contact_profile": result.model_dump(mode="json")}})
            else:
                payload = SenderEnrichmentRequest(**record.payload)
                result = await state.enrichment.enrich_sender(
                    company_name=payload.company_name,
                    current_product=payload.current_product,
                    company_notes=payload.company_notes,
                    other_products=payload.other_products,
                    refresh=payload.refresh,
                    progress=progress,
                )
                await queue.put({"event": "result", "data": {"sender_profile": result.model_dump(mode="json")}})
        except Exception as exc:  # noqa: BLE001
            await queue.put({"event": "error", "data": {"error": str(exc)}})
        finally:
            await queue.put(None)

    asyncio.create_task(worker())

    async def stream() -> AsyncGenerator[dict[str, Any], None]:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    done = {
        "trace_id": trace_id,
        "prompt_template_hash": prompt_template_hash(),
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
    }
    return stream(), done


def _research_result_text(result: ResearchResult) -> str:
    lines = [result.summary]
    for product in result.products[:3]:
        lines.append(f"Product: {product}")
    for item in result.proof_points[:3]:
        lines.append(f"Proof: {item}")
    for news in result.news[:3]:
        lines.append(f"{news.date} — {news.headline}: {news.why_it_matters}")
    return "\n".join([line for line in lines if line.strip()])


async def _run_research_job(job_id: str, payload: ResearchRequest) -> None:
    job = state.research_jobs.get(job_id)
    if job is None:
        return
    job.status = "running"
    job.progress = "Starting company research job."
    job.updated_at = time.time()

    async def on_progress(_event: str, data: dict[str, Any]) -> None:
        progress_msg = str(data.get("message") or data.get("stage") or "").strip()
        if progress_msg:
            job.progress = progress_msg
            job.updated_at = time.time()

    try:
        domain = (payload.domain or "").strip()
        company_url = ""
        if domain:
            company_url = domain if domain.startswith("http") else f"https://{domain}"

        profile = await state.enrichment.enrich_target(
            company_name=payload.company_name,
            company_url=company_url or None,
            refresh=False,
            progress=on_progress,
        )
        result = ResearchResult(
            domain=profile.official_domain,
            summary=profile.summary,
            products=profile.products,
            ICP=profile.icp,
            differentiators=profile.differentiators,
            proof_points=profile.proof_points,
            news=profile.recent_news,
            citations=profile.citations,
            result_text="",
        )
        result.result_text = _research_result_text(result)
        job.result = result
        job.status = "complete"
        job.progress = "Research complete."
        job.updated_at = time.time()
    except Exception as exc:  # noqa: BLE001
        logger.exception("research_job_failed job_id=%s error=%s", job_id, exc)
        job.status = "failed"
        job.error = str(exc)
        job.progress = "Research failed."
        job.updated_at = time.time()


@router.post("/research/", response_model=ResearchCreateResponse)
async def research_create(req: ResearchRequest) -> ResearchCreateResponse:
    state.cleanup_research_jobs()
    job_id = str(uuid4())
    now = time.time()
    state.research_jobs[job_id] = ResearchJob(
        job_id=job_id,
        payload=req.model_dump(mode="json"),
        status="queued",
        progress="Queued",
        result=None,
        error=None,
        created_at=now,
        updated_at=now,
    )
    asyncio.create_task(_run_research_job(job_id, req))
    return ResearchCreateResponse(job_id=job_id, status="queued")


@router.get("/research/{job_id}/status", response_model=ResearchStatusResponse)
async def research_status(job_id: str) -> ResearchStatusResponse:
    state.cleanup_research_jobs()
    job = state.research_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"error": "job_not_found"})
    return ResearchStatusResponse(
        job_id=job.job_id,
        status=job.status,  # type: ignore[arg-type]
        progress=job.progress,
        result=job.result,
        error=job.error,
    )


@router.get("/web/v1/stream/{request_id}")
async def web_stream(request_id: str, request: Request, x_emaildj_beta_key: str | None = Header(default=None)):
    _require_beta(x_emaildj_beta_key)
    state.cleanup_requests()

    record = state.requests.pop(request_id, None)
    if record is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})

    if record.kind in {"generate", "remix"}:
        generator, done_extra = await _run_generate_like(record, request_id)
        return await stream_response(request_id=request_id, generator=generator, done_extra=done_extra)

    if record.kind in {"enrich_target", "enrich_prospect", "enrich_sender"}:
        generator, done_extra = await _run_enrichment(record)
        return await stream_response(request_id=request_id, generator=generator, done_extra=done_extra)

    raise HTTPException(status_code=400, detail={"error": "unsupported_request_kind"})


def create_app() -> FastAPI:
    logging.basicConfig(level=state.settings.log_level)
    app = FastAPI(title="EmailDJ MVP 0.5 API", version="0.5.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            state.settings.web_app_origin,
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
