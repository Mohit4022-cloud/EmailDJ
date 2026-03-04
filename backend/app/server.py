from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, AsyncGenerator
from uuid import uuid4

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.blueprint import compile_blueprint, merge_manual_overrides
from app.config import Settings, load_settings
from app.enrichment import EnrichmentService
from app.openai_client import OpenAIClient
from app.prompts import PROMPT_TEMPLATE_VERSION, prompt_template_hash
from app.rendering import PRESET_TACTICS, render_email, render_to_text
from app.schemas import (
    ContactProfile,
    EnrichmentAccepted,
    EmailBlueprint,
    PresetPreviewRequest,
    PresetPreviewResponse,
    SenderEnrichmentRequest,
    SenderProfile,
    TargetAccountProfile,
    TargetEnrichmentRequest,
    ValidationResult,
    WebFeedbackRequest,
    WebGenerateAccepted,
    WebGenerateRequest,
    WebRemixAccepted,
    WebRemixRequest,
)
from app.sse import stream_response
from app.validators import fallback_safe_email, preset_diversity_violations, repair_email_deterministic, validate_email


logger = logging.getLogger(__name__)


@dataclass
class RequestRecord:
    kind: str
    session_id: str | None
    payload: dict[str, Any]
    created_at: float


class AppState:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.openai = OpenAIClient(settings)
        self.enrichment = EnrichmentService(settings, self.openai)
        self.requests: dict[str, RequestRecord] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.rate: dict[str, list[float]] = {}

    def cleanup_requests(self, ttl_seconds: int = 5 * 60) -> None:
        now = time.time()
        expired = [rid for rid, rec in self.requests.items() if now - rec.created_at > ttl_seconds]
        for rid in expired:
            self.requests.pop(rid, None)


state = AppState(load_settings())


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


router = APIRouter()


@router.get("/")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.5.0"}


@router.get("/web/v1/debug/config")
async def debug_config() -> dict[str, Any]:
    return {
        "app_env": state.settings.app_env,
        "runtime_mode": "mock" if state.settings.provider_stub_enabled or not state.settings.openai_api_key else "real",
        "provider_stub_enabled": state.settings.provider_stub_enabled,
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
        "draft_id_counter": 0,
    }
    state.requests[request_id] = RequestRecord(
        kind="generate",
        session_id=session_id,
        payload={
            "style_profile": req.style_profile.model_dump(),
            "preset_id": req.preset_id,
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

    generate_req = WebGenerateRequest(
        prospect=req.prospect,
        prospect_first_name=req.prospect_first_name,
        research_text=req.research_text,
        offer_lock=req.offer_lock,
        cta_offer_lock=req.cta_offer_lock,
        cta_type=req.cta_type,
        preset_id=req.preset_id,
        style_profile=req.style_profile,
        company_context=req.company_context,
    )

    blueprint: EmailBlueprint | None = None
    if req.session_id:
        session = state.sessions.get(req.session_id)
        if session and session.get("blueprint"):
            try:
                blueprint = EmailBlueprint(**session.get("blueprint"))
            except Exception:
                blueprint = None

    if blueprint is None:
        sender_profile = SenderProfile(company_name=req.company_context.company_name or "")
        target_profile = TargetAccountProfile(official_domain="Unknown", summary="Unknown", icp="Unknown")
        contact_profile = ContactProfile(
            name=req.prospect.name,
            current_title=req.prospect.title,
            company=req.prospect.company,
            role_summary="Unknown",
        )

        sender_profile, target_profile, contact_profile = merge_manual_overrides(
            req=generate_req,
            sender_profile=sender_profile,
            target_profile=target_profile,
            contact_profile=contact_profile,
        )

        blueprint = await compile_blueprint(
            req=generate_req,
            sender_profile=sender_profile,
            target_profile=target_profile,
            contact_profile=contact_profile,
            openai=state.openai,
            settings=state.settings,
        )

    rendered = await render_email(
        blueprint=blueprint,
        style=req.style_profile,
        preset_id=req.preset_id,
        openai=state.openai,
        settings=state.settings,
    )
    validation = validate_email(
        subject=rendered["subject"],
        body=rendered["body"],
        blueprint=blueprint,
        style=req.style_profile,
    )
    if validation.violations:
        sub, body = repair_email_deterministic(
            subject=rendered["subject"],
            body=rendered["body"],
            blueprint=blueprint,
            style=req.style_profile,
            violations=validation.violations,
        )
        rendered = {"subject": sub, "body": body}
        recheck = validate_email(
            subject=rendered["subject"],
            body=rendered["body"],
            blueprint=blueprint,
            style=req.style_profile,
        )
        validation = recheck

    slider_summary = {
        "formality": int(round((req.style_profile.formality + 1) * 50)),
        "orientation": int(round((req.style_profile.orientation + 1) * 50)),
        "length": int(round((req.style_profile.length + 1) * 50)),
        "assertiveness": int(round((req.style_profile.assertiveness + 1) * 50)),
    }

    tactic = PRESET_TACTICS.get(req.preset_id, {})
    why = [
        "Grounded in compiled blueprint, not raw research on remix.",
        "CTA lock remains verbatim.",
        f"Preset tactic: {tactic.get('angle_shift', 'balanced')}.",
    ]

    warning = ", ".join(validation.violations[:3]) if validation.violations else None
    return PresetPreviewResponse(
        preset_id=req.preset_id,
        subject=rendered["subject"],
        body=rendered["body"],
        vibeLabel=req.preset_id.replace("_", " ").title(),
        vibeTags=[
            "Problem-Led" if req.style_profile.orientation < 0 else "Outcome-Led",
            "Short-Form" if req.style_profile.length < 0 else "Long-Form",
            "Bold" if req.style_profile.assertiveness < 0 else "Diplomatic",
        ],
        whyItWorks=why,
        sliderSummary=slider_summary,
        validationWarning=warning,
        meta={
            "trace_id": str(uuid4()),
            "prompt_template_hash": prompt_template_hash(),
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            "validator_attempt_count": validation.validator_attempt_count,
            "repair_attempt_count": validation.repair_attempt_count,
            "repaired": bool(validation.violations),
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
    style = req_payload.style_profile.__class__(**style_payload)
    preset_id = str(record.payload.get("preset_id") or session.get("preset_id") or req_payload.preset_id or "") or None

    sender_profile = SenderProfile(company_name=req_payload.company_context.company_name or "")
    target_profile = TargetAccountProfile(official_domain="Unknown", summary="Unknown", icp="Unknown")
    contact_profile = ContactProfile(
        name=req_payload.prospect.name,
        current_title=req_payload.prospect.title,
        company=req_payload.prospect.company,
        role_summary="Unknown",
    )

    sender_profile, target_profile, contact_profile = merge_manual_overrides(
        req=req_payload,
        sender_profile=sender_profile,
        target_profile=target_profile,
        contact_profile=contact_profile,
    )

    done_extra = {
        "session_id": record.session_id,
        "generation_id": generation_id,
        "draft_id": draft_id,
        "trace_id": trace_id,
    }

    blueprint: EmailBlueprint | None = None
    if record.kind == "remix" and session.get("blueprint"):
        try:
            blueprint = EmailBlueprint(**session.get("blueprint"))
        except Exception:
            blueprint = None
    if blueprint is None:
        blueprint = await compile_blueprint(
            req=req_payload,
            sender_profile=sender_profile,
            target_profile=target_profile,
            contact_profile=contact_profile,
            openai=state.openai,
            settings=state.settings,
        )
        session["blueprint"] = blueprint.model_dump(mode="json")

    rendered = await render_email(
        blueprint=blueprint,
        style=style,
        preset_id=preset_id,
        openai=state.openai,
        settings=state.settings,
    )
    validation = validate_email(
        subject=rendered["subject"],
        body=rendered["body"],
        blueprint=blueprint,
        style=style,
    )
    attempts = 0
    repaired = False
    while validation.violations and attempts < 2:
        attempts += 1
        repaired = True
        sub, body = repair_email_deterministic(
            subject=rendered["subject"],
            body=rendered["body"],
            blueprint=blueprint,
            style=style,
            violations=validation.violations,
        )
        rendered = {"subject": sub, "body": body}
        validation = validate_email(
            subject=rendered["subject"],
            body=rendered["body"],
            blueprint=blueprint,
            style=style,
        )
    if validation.violations:
        subject, body = fallback_safe_email(blueprint)
        rendered = {"subject": subject, "body": body}

    session["last_render"] = rendered
    session["last_validation"] = {
        "passed": not validation.violations,
        "violations": validation.violations,
        "validator_attempt_count": 1 + attempts,
        "repair_attempt_count": attempts,
        "repaired": repaired,
    }
    session["last_sources"] = (
        (target_profile.citations if hasattr(target_profile, "citations") else [])
        + (contact_profile.citations if hasattr(contact_profile, "citations") else [])
        + (sender_profile.citations if hasattr(sender_profile, "citations") else [])
    )

    done_extra.update(
        {
            "provider": "openai" if state.openai.enabled() else "stub",
            "model": state.settings.openai_model,
            "prompt_template_hash": prompt_template_hash(),
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            "validator_attempt_count": 1 + attempts,
            "repair_attempt_count": attempts,
            "repaired": repaired,
            "violations": validation.violations,
            "validation": session.get("last_validation"),
            "final": {
                "subject": rendered["subject"],
                "body": render_to_text(rendered["subject"], rendered["body"]),
            },
            "sources": [
                item.model_dump() if hasattr(item, "model_dump") else dict(item)
                for item in session.get("last_sources", [])
            ],
        }
    )

    async def wrapper() -> AsyncGenerator[dict[str, Any], None]:
        if record.kind == "generate":
            yield {"event": "progress", "data": {"stage": "compile_start", "message": "Compiling blueprint..."}}
        else:
            yield {"event": "progress", "data": {"stage": "compile_reuse", "message": "Using stored blueprint..."}}
        yield {"event": "progress", "data": {"stage": "render_start", "message": "Rendering draft..."}}
        full_text = render_to_text(rendered["subject"], rendered["body"])
        chunk_size = state.settings.stream_chunk_size
        for idx in range(0, len(full_text), chunk_size):
            chunk = full_text[idx : idx + chunk_size]
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
