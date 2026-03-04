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
    assembled_prompt_messages,
    axis_to_slider,
    normalize_batch_preview_request,
    normalize_generate_request,
    normalize_single_preview_request,
    run_engine,
)
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
        self.requests: dict[str, RequestRecord] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.rate: dict[str, list[float]] = {}
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


def _log_prompt_trace(stage: str, payload: dict[str, Any]) -> None:
    logger.info("prompt_trace stage=%s payload=%s", stage, payload)


router = APIRouter()


@router.get("/")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.5.0"}


@router.get("/web/v1/debug/config")
async def debug_config(x_emaildj_beta_key: str | None = Header(default=None)) -> dict[str, Any]:
    _require_beta(x_emaildj_beta_key)
    openai_ready = state.openai.enabled()
    return {
        "app_env": state.settings.app_env,
        "runtime_mode": "real" if openai_ready else "unavailable",
        "provider_stub_enabled": state.settings.provider_stub_enabled,
        "debug_prompt": state.settings.debug_prompt,
        "openai_model": state.settings.openai_model,
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
    state.sessions[session_id] = {
        "session_id": session_id,
        "generate_request": req.model_dump(mode="json"),
        "preset_id": req.preset_id,
        "style_profile": req.style_profile.model_dump(),
        "response_contract": _normalize_contract(req.response_contract),
        "draft_id_counter": 0,
    }
    state.requests[request_id] = RequestRecord(
        kind="generate",
        session_id=session_id,
        payload={
            "style_profile": req.style_profile.model_dump(),
            "preset_id": req.preset_id,
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
    session["style_profile"] = req.style_profile.model_dump()

    request_id = str(uuid4())
    state.requests[request_id] = RequestRecord(
        kind="remix",
        session_id=req.session_id,
        payload={
            "style_profile": req.style_profile.model_dump(),
            "preset_id": req.preset_id,
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

    ctx = normalize_single_preview_request(req)
    if state.settings.debug_prompt:
        _log_prompt_trace(
            "normalize.preview",
            {
                "source": ctx.source,
                "seller_offerings": ctx.seller_offerings,
                "internal_modules": ctx.internal_modules,
                "product_category": ctx.product_category,
                "category_confidence": ctx.category_confidence,
            },
        )
    result = run_engine(ctx, max_repairs=2)
    if state.settings.debug_prompt:
        _log_prompt_trace(
            "plan.preview",
            {
                "hook_type": result.plan.hook_type,
                "selected_beat_ids": result.plan.selected_beat_ids,
                "value_prop": result.plan.value_prop,
            },
        )
        _log_prompt_trace(
            "assembled_messages.preview",
            {
                "messages": assembled_prompt_messages(ctx, result.plan),
                "selected_template_or_beat_ids": result.draft.selected_beat_ids,
            },
        )
        _log_prompt_trace(
            "provenance.preview",
            {
                "subject_source": result.draft.subject_source,
                "body_sources": result.draft.body_sources,
                "selected_beat_ids": result.draft.selected_beat_ids,
            },
        )
    style_summary = _slider_summary_from_style(ctx.style_profile)

    warning = ", ".join(result.debug.violations[:3]) if result.debug.violations else None
    return PresetPreviewResponse(
        preset_id=req.preset_id,
        subject=result.draft.subject,
        body=result.draft.body,
        vibeLabel=req.preset_id.replace("_", " ").title(),
        vibeTags=_vibe_tags(ctx.style_profile),
        whyItWorks=_why_it_works(),
        sliderSummary=style_summary,
        validationWarning=warning,
        debug={
            "hook_type": result.plan.hook_type,
            "violations": result.debug.violations,
            "repair_attempt_count": result.debug.repair_attempt_count,
            "degraded": result.debug.degraded,
            "stage_latency_ms": result.debug.stage_latency_ms,
        },
        meta={
            "trace_id": str(uuid4()),
            "prompt_template_hash": prompt_template_hash(),
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            "validator_attempt_count": result.debug.validator_attempt_count,
            "repair_attempt_count": result.debug.repair_attempt_count,
            "repaired": bool(result.debug.repaired),
            "degraded": bool(result.debug.degraded),
        },
    )


@router.post("/web/v1/preset-previews/batch", response_model=PresetPreviewBatchResponse)
async def preset_previews_batch(
    req: PresetPreviewBatchRequest,
    x_emaildj_beta_key: str | None = Header(default=None),
) -> PresetPreviewBatchResponse:
    _require_beta(x_emaildj_beta_key)

    started_at = time.perf_counter()
    previews: list[PresetPreviewBatchItem] = []
    failures = 0

    for preset in req.presets:
        preset_started = time.perf_counter()
        try:
            ctx = normalize_batch_preview_request(req, preset)
            if state.settings.debug_prompt:
                _log_prompt_trace(
                    "normalize.preview_batch",
                    {
                        "preset_id": preset.preset_id,
                        "seller_offerings": ctx.seller_offerings,
                        "internal_modules": ctx.internal_modules,
                        "product_category": ctx.product_category,
                        "category_confidence": ctx.category_confidence,
                    },
                )
            result = run_engine(ctx, max_repairs=1)
            if state.settings.debug_prompt:
                _log_prompt_trace(
                    "plan.preview_batch",
                    {
                        "preset_id": preset.preset_id,
                        "hook_type": result.plan.hook_type,
                        "selected_beat_ids": result.plan.selected_beat_ids,
                    },
                )
                _log_prompt_trace(
                    "assembled_messages.preview_batch",
                    {
                        "preset_id": preset.preset_id,
                        "messages": assembled_prompt_messages(ctx, result.plan),
                        "selected_template_or_beat_ids": result.draft.selected_beat_ids,
                    },
                )
            debug_payload = {
                "hook_type": result.plan.hook_type,
                "violations": result.debug.violations,
                "repair_attempt_count": result.debug.repair_attempt_count,
                "degraded": result.debug.degraded,
                "stage_latency_ms": result.debug.stage_latency_ms,
            }
            item = PresetPreviewBatchItem(
                preset_id=preset.preset_id,
                label=preset.label,
                effective_sliders=dict(ctx.sliders),
                vibeLabel=preset.label,
                vibeTags=_vibe_tags(ctx.style_profile),
                whyItWorks=_why_it_works(),
                subject=result.draft.subject,
                body=result.draft.body,
                debug=debug_payload,
            )
            previews.append(item)
            logger.info(
                "preset_preview_batch preset=%s latency_ms=%s repaired=%s degraded=%s",
                preset.preset_id,
                int(round((time.perf_counter() - preset_started) * 1000)),
                result.debug.repaired,
                result.debug.degraded,
            )
        except Exception as exc:  # noqa: BLE001
            failures += 1
            logger.exception("preset_preview_batch_failed preset=%s error=%s", preset.preset_id, exc)
            fallback_subject = f"Quick idea for {req.prospect.company}"[:78]
            fallback_body = "\n\n".join(
                [
                    f"Hi {req.prospect_first_name or req.prospect.name.split()[0] or 'there'},",
                    f"{req.offer_lock} could help improve execution consistency for this workflow.",
                    req.cta_lock or req.cta_lock_text or "Open to a quick chat to see if this is relevant?",
                ]
            )
            previews.append(
                PresetPreviewBatchItem(
                    preset_id=preset.preset_id,
                    label=preset.label,
                    effective_sliders=dict(req.global_sliders.model_dump(mode="json")),
                    vibeLabel=preset.label,
                    vibeTags=["Balanced"],
                    whyItWorks=["Graceful fallback returned due to generation error."],
                    subject=fallback_subject,
                    body=fallback_body,
                    debug={"degraded": True, "violations": ["preset_generation_exception"]},
                )
            )

    total_latency_ms = int(round((time.perf_counter() - started_at) * 1000))
    return PresetPreviewBatchResponse(
        previews=previews,
        meta={
            "trace_id": str(uuid4()),
            "prompt_template_hash": prompt_template_hash(),
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            "preset_count": len(req.presets),
            "failure_count": failures,
            "total_latency_ms": total_latency_ms,
            "degraded": bool(failures),
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

    draft_id = int(session.get("draft_id_counter") or 0) + 1
    session["draft_id_counter"] = draft_id
    generation_id = str(uuid4())
    trace_id = str(uuid4())

    req_payload = WebGenerateRequest(**session["generate_request"])
    style_payload = record.payload.get("style_profile") or session.get("style_profile") or {}
    style_model = req_payload.style_profile.__class__(**style_payload)
    preset_id = str(record.payload.get("preset_id") or session.get("preset_id") or req_payload.preset_id or "") or None
    response_contract = _normalize_contract(str(record.payload.get("response_contract") or session.get("response_contract") or req_payload.response_contract))

    req_payload = req_payload.model_copy(
        update={
            "style_profile": style_model,
            "preset_id": preset_id,
            "response_contract": response_contract,
        }
    )

    ctx = normalize_generate_request(req_payload, preset_id=preset_id)
    if state.settings.debug_prompt:
        _log_prompt_trace(
            "normalize.generate",
            {
                "source": ctx.source,
                "seller_offerings": ctx.seller_offerings,
                "internal_modules": ctx.internal_modules,
                "product_category": ctx.product_category,
                "category_confidence": ctx.category_confidence,
            },
        )
    started = time.perf_counter()
    result = run_engine(ctx, max_repairs=2)
    if state.settings.debug_prompt:
        _log_prompt_trace(
            "plan.generate",
            {
                "hook_type": result.plan.hook_type,
                "selected_beat_ids": result.plan.selected_beat_ids,
                "value_prop": result.plan.value_prop,
            },
        )
        _log_prompt_trace(
            "assembled_messages.generate",
            {
                "messages": assembled_prompt_messages(ctx, result.plan),
                "selected_template_or_beat_ids": result.draft.selected_beat_ids,
            },
        )
        _log_prompt_trace(
            "provenance.generate",
            {
                "subject_source": result.draft.subject_source,
                "body_sources": result.draft.body_sources,
                "selected_beat_ids": result.draft.selected_beat_ids,
            },
        )
    duration_ms = int(round((time.perf_counter() - started) * 1000))

    subject = result.draft.subject
    body = result.draft.body
    legacy_text = render_to_text(subject, body)

    session["last_render"] = {"subject": subject, "body": body}
    session["last_validation"] = {
        "passed": not result.debug.violations,
        "violations": result.debug.violations,
        "validator_attempt_count": result.debug.validator_attempt_count,
        "repair_attempt_count": result.debug.repair_attempt_count,
        "repaired": result.debug.repaired,
        "degraded": result.debug.degraded,
    }
    sources = _sources_from_generate_request(req_payload)
    session["last_sources"] = sources

    debug_payload = {
        "hook_type": result.plan.hook_type,
        "violations": result.debug.violations,
        "validator_attempt_count": result.debug.validator_attempt_count,
        "repair_attempt_count": result.debug.repair_attempt_count,
        "repaired": result.debug.repaired,
        "degraded": result.debug.degraded,
        "stage_latency_ms": result.debug.stage_latency_ms,
        "total_latency_ms": duration_ms,
    }

    done_extra = {
        "session_id": record.session_id,
        "generation_id": generation_id,
        "draft_id": draft_id,
        "trace_id": trace_id,
        "provider": "openai" if state.openai.enabled() else "stub",
        "model": state.settings.openai_model,
        "prompt_template_hash": prompt_template_hash(),
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "validator_attempt_count": result.debug.validator_attempt_count,
        "repair_attempt_count": result.debug.repair_attempt_count,
        "repaired": result.debug.repaired,
        "degraded": result.debug.degraded,
        "violations": result.debug.violations,
        "validation": session.get("last_validation"),
        "sources": sources,
    }

    if response_contract == "email_json_v1":
        done_extra["final"] = {
            "subject": subject,
            "body": body,
            "debug": debug_payload,
        }
    else:
        # Backward-compatible legacy_text stream output.
        done_extra["final"] = {
            "subject": subject,
            "body": legacy_text,
            "debug": debug_payload,
        }

    async def wrapper() -> AsyncGenerator[dict[str, Any], None]:
        stage = "plan_start" if record.kind == "generate" else "plan_remix"
        message = "Planning and realizing draft..." if record.kind == "generate" else "Remixing draft..."
        yield {"event": "progress", "data": {"stage": stage, "message": message}}
        stream_text = legacy_text
        chunk_size = state.settings.stream_chunk_size
        for idx in range(0, len(stream_text), chunk_size):
            chunk = stream_text[idx : idx + chunk_size]
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
