"""Web MVP routes for generate/remix/feedback workflows."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request

from api.schemas import (
    ComplianceDashboardResponse,
    ComplianceDashboardDay,
    ComplianceViolationBucket,
    WebFeedbackRequest,
    WebGenerateAccepted,
    WebGenerateRequest,
    WebPresetPreviewBatchRequest,
    WebPresetPreviewBatchResponse,
    WebRemixAccepted,
    WebRemixRequest,
)
from email_generation.preset_preview_pipeline import make_response, run_preview_pipeline
from email_generation.remix_engine import (
    build_draft,
    create_session_payload,
    load_session,
    persist_violations,
    save_session,
)
from email_generation.runtime_policies import debug_success_sample_rate
from email_generation.streaming import stream_response
from infra.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter()
_STREAM_SEM = asyncio.Semaphore(32)
_REQUEST_TTL_SECONDS = 5 * 60


@dataclass
class RequestRecord:
    session_id: str
    style_profile: dict
    mode: str
    created_at: float


_REQUESTS: dict[str, RequestRecord] = {}


def _preview_pipeline_enabled() -> bool:
    return os.environ.get("EMAILDJ_PRESET_PREVIEW_PIPELINE", "off").strip().lower() == "on"


def _cleanup_expired() -> None:
    now = time.time()
    expired = [rid for rid, rec in _REQUESTS.items() if now - rec.created_at > _REQUEST_TTL_SECONDS]
    for rid in expired:
        del _REQUESTS[rid]


def _day_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


async def _emit_metric(name: str) -> None:
    redis = get_redis()
    key = f"web_mvp:metric:{_day_key()}:{name}"
    await redis.incr(key)
    await redis.expire(key, 3 * 24 * 60 * 60)


def _token_stream(text: str):
    async def _gen():
        words = text.split(" ")
        first = True
        for token in words:
            if first:
                await asyncio.sleep(0.01)
                first = False
            else:
                await asyncio.sleep(0.005)
            yield token + " "

    return _gen()


def _violation_codes(violations: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for entry in violations:
        code = str(entry).split(":", 1)[0].strip()
        if not code or code in seen:
            continue
        seen.add(code)
        output.append(code)
    return output


def _should_emit_success_debug_bundle() -> bool:
    sample_rate = debug_success_sample_rate()
    if sample_rate <= 0.0:
        return False
    if sample_rate >= 1.0:
        return True
    return random.random() < sample_rate


def _log_debug_bundle(event: str, payload: dict[str, object], *, failure: bool) -> None:
    if failure:
        logger.warning(event, extra=payload)
        return
    if _should_emit_success_debug_bundle():
        logger.info(event, extra=payload)


@router.post("/generate", response_model=WebGenerateAccepted)
async def web_generate(req: WebGenerateRequest) -> WebGenerateAccepted:
    _cleanup_expired()
    await _emit_metric("web_generate_started")

    # Enforce single source of truth: if provided, current_product must match offer_lock.
    current_product = req.company_context.current_product
    if current_product and req.offer_lock and current_product.strip().lower() != req.offer_lock.strip().lower():
        logger.warning(
            "offer_lock_current_product_mismatch",
            extra={"offer_lock": req.offer_lock, "current_product": current_product},
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "offer_lock_current_product_mismatch",
                "message": "company_context.current_product must match offer_lock when provided.",
                "offer_lock": req.offer_lock,
                "current_product": current_product,
            },
        )

    session_id = str(uuid4())
    session = create_session_payload(
        prospect=req.prospect.model_dump(),
        research_text=req.research_text,
        initial_style=req.style_profile.model_dump(),
        offer_lock=req.offer_lock,
        cta_offer_lock=req.cta_offer_lock,
        cta_type=req.cta_type,
        company_context=req.company_context.model_dump(exclude_none=True),
        prospect_first_name=req.prospect_first_name,
        preset_id=req.preset_id,
        response_contract=req.response_contract,
        pipeline_meta=req.pipeline_meta.model_dump(exclude_none=True) if req.pipeline_meta else None,
    )
    await save_session(session_id, session)

    request_id = str(uuid4())
    _REQUESTS[request_id] = RequestRecord(
        session_id=session_id,
        style_profile=req.style_profile.model_dump(),
        mode="generate",
        created_at=time.time(),
    )
    return WebGenerateAccepted(request_id=request_id, session_id=session_id, stream_url=f"/web/v1/stream/{request_id}")


@router.post("/remix", response_model=WebRemixAccepted)
async def web_remix(req: WebRemixRequest) -> WebRemixAccepted:
    _cleanup_expired()
    session = await load_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail={"error": "session_not_found", "session_id": req.session_id})
    if req.preset_id:
        session["preset_id"] = req.preset_id
        await save_session(req.session_id, session)

    await _emit_metric("web_remix_started")
    request_id = str(uuid4())
    _REQUESTS[request_id] = RequestRecord(
        session_id=req.session_id,
        style_profile=req.style_profile.model_dump(),
        mode="remix",
        created_at=time.time(),
    )
    return WebRemixAccepted(request_id=request_id, stream_url=f"/web/v1/stream/{request_id}")


@router.post(
    "/preset-previews/batch",
    response_model=WebPresetPreviewBatchResponse,
)
async def web_preset_previews_batch(req: WebPresetPreviewBatchRequest, request: Request) -> WebPresetPreviewBatchResponse:
    if not _preview_pipeline_enabled():
        raise HTTPException(status_code=503, detail={"error": "preview_pipeline_disabled"})

    await _emit_metric("web_preview_batch_started")
    throttled = bool(getattr(request.state, "cost_throttled", False))
    preview_request_id = str(uuid4())

    try:
        result = await run_preview_pipeline(req=req, throttled=throttled)
        if result.cache_hit:
            await _emit_metric("web_preview_batch_summary_cache_hit")
        if result.violations:
            await persist_violations(result.violations, session_id=None, pipeline="preview")
        await _emit_metric("web_preview_batch_completed")
        logger.info(
            "web_preview_batch_done",
            extra={
                "generation_mode": result.mode,
                "provider": result.provider,
                "model": result.model_name,
                "latency_ms": result.latency_ms,
                "cache_hit": result.cache_hit,
                "preview_count": len(result.previews),
                "violation_count": len(result.violations),
                "violation_codes": result.violation_codes,
                "initial_violation_count": result.initial_violation_count,
                "final_violation_count": result.final_violation_count,
                "repair_attempt_count": result.repair_attempt_count,
                "validator_attempt_count": result.validator_attempt_count,
                "provider_attempt_count": result.provider_attempt_count,
                "repaired": result.repaired,
                "enforcement_level": result.enforcement_level,
                "repair_loop_enabled": result.repair_loop_enabled,
                "request_id": preview_request_id,
            },
        )
        _log_debug_bundle(
            "web_preview_batch_debug_bundle",
            {
                "request_id": preview_request_id,
                "session_id": None,
                "mode": "preview",
                "generation_mode": result.mode,
                "provider": result.provider,
                "model": result.model_name,
                "violation_codes": result.violation_codes,
                "violation_count": result.violation_count,
                "provider_attempt_count": result.provider_attempt_count,
                "validator_attempt_count": result.validator_attempt_count,
                "repair_attempt_count": result.repair_attempt_count,
                "repaired": result.repaired,
                "enforcement_level": result.enforcement_level,
                "repair_loop_enabled": result.repair_loop_enabled,
            },
            failure=result.violation_count > 0,
        )
        return make_response(result, request_id=preview_request_id, session_id=None)
    except Exception as exc:
        await _emit_metric("web_preview_batch_failed")
        logger.exception("web_preview_batch_failed", extra={"error": str(exc), "request_id": preview_request_id})
        _log_debug_bundle(
            "web_preview_batch_debug_bundle",
            {
                "request_id": preview_request_id,
                "session_id": None,
                "mode": "preview",
                "error": str(exc),
            },
            failure=True,
        )
        raise HTTPException(
            status_code=503,
            detail={"error": "preview_pipeline_unavailable", "message": str(exc)},
        ) from exc


@router.get("/stream/{request_id}")
async def web_stream(request_id: str, request: Request):
    _cleanup_expired()
    rec = _REQUESTS.pop(request_id, None)
    if rec is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "request_id": request_id})

    session = await load_session(rec.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail={"error": "session_not_found", "session_id": rec.session_id})

    throttled = bool(getattr(request.state, "cost_throttled", False))
    start = time.perf_counter()

    # Mutable dict populated inside _bounded(); read by stream_response done event
    mode_info: dict[str, object] = {"request_id": request_id, "session_id": rec.session_id}

    async def _bounded():
        async with _STREAM_SEM:
            try:
                result = await build_draft(
                    session=session,
                    style_profile=rec.style_profile,
                    throttled=throttled,
                    session_id=rec.session_id,
                )
                mode_info["mode"] = result.mode
                mode_info["provider"] = result.provider
                mode_info["model"] = result.model_name
                mode_info["cascade_reason"] = result.cascade_reason
                mode_info["provider_attempt_count"] = result.attempt_count
                mode_info["validator_attempt_count"] = result.validator_attempt_count
                mode_info["json_repair_count"] = result.json_repair_count
                mode_info["violation_retry_count"] = result.violation_retry_count
                mode_info["repaired"] = result.repaired
                mode_info["violation_codes"] = result.violation_codes
                mode_info["violation_count"] = result.violation_count
                mode_info["enforcement_level"] = result.enforcement_level
                mode_info["repair_loop_enabled"] = result.repair_loop_enabled
                mode_info["policy_versions"] = result.policy_version_snapshot
                mode_info["response_contract"] = result.response_contract
                async for token in _token_stream(result.draft):
                    yield token
                if rec.mode == "generate":
                    session["metrics"]["generate_count"] = int(session["metrics"].get("generate_count", 0)) + 1
                    await _emit_metric("web_generate_completed")
                else:
                    session["metrics"]["remix_count"] = int(session["metrics"].get("remix_count", 0)) + 1
                    await _emit_metric("web_remix_completed")
                session["metrics"]["last_latency_ms"] = int((time.perf_counter() - start) * 1000)
                await save_session(rec.session_id, session)
                logger.info(
                    "web_mvp_stream_done",
                    extra={
                        "mode": rec.mode,
                        "generation_mode": result.mode,
                        "provider": result.provider,
                        "model": result.model_name,
                        "cascade_reason": result.cascade_reason,
                        "provider_attempt_count": result.attempt_count,
                        "validator_attempt_count": result.validator_attempt_count,
                        "json_repair_count": result.json_repair_count,
                        "violation_retry_count": result.violation_retry_count,
                        "repaired": result.repaired,
                        "violation_codes": result.violation_codes,
                        "violation_count": result.violation_count,
                        "enforcement_level": result.enforcement_level,
                        "repair_loop_enabled": result.repair_loop_enabled,
                        "session_id": rec.session_id,
                        "request_id": request_id,
                        "latency_ms": session["metrics"]["last_latency_ms"],
                    },
                )
                _log_debug_bundle(
                    "web_mvp_stream_debug_bundle",
                    {
                        "request_id": request_id,
                        "session_id": rec.session_id,
                        "mode": result.mode,
                        "provider": result.provider,
                        "model": result.model_name,
                        "violation_codes": result.violation_codes,
                        "violation_count": result.violation_count,
                        "provider_attempt_count": result.attempt_count,
                        "validator_attempt_count": result.validator_attempt_count,
                        "json_repair_count": result.json_repair_count,
                        "violation_retry_count": result.violation_retry_count,
                        "repaired": result.repaired,
                        "enforcement_level": result.enforcement_level,
                        "repair_loop_enabled": result.repair_loop_enabled,
                    },
                    failure=result.violation_count > 0,
                )
            except Exception as exc:
                _log_debug_bundle(
                    "web_mvp_stream_debug_bundle",
                    {
                        "request_id": request_id,
                        "session_id": rec.session_id,
                        "mode": rec.mode,
                        "error": str(exc),
                    },
                    failure=True,
                )
                raise

    return await stream_response(request_id=request_id, generator=_bounded(), done_extra=mode_info)


@router.post("/feedback")
async def web_feedback(req: WebFeedbackRequest):
    session = await load_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail={"error": "session_not_found", "session_id": req.session_id})

    redis = get_redis()
    key = f"web_mvp:feedback:{req.session_id}:{int(time.time())}"
    await redis.hset(
        key,
        mapping={
            "draft_before": req.draft_before,
            "draft_after": req.draft_after,
            "style_profile": json.dumps(req.style_profile.model_dump()),
            "captured_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    await redis.expire(key, 7 * 24 * 60 * 60)
    await _emit_metric("web_copy_clicked")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Compliance dashboard (Batch 3 P3)
# ---------------------------------------------------------------------------

_DASHBOARD_CATEGORIES = [
    "offer_lock_missing",
    "offer_lock_body_verbatim_missing",
    "cta_lock_not_used_exactly_once",
    "cta_near_match_detected",
    "additional_cta_detected",
    "internal_leakage_term",
    "unsubstantiated_claim",
    "unsubstantiated_statistical_claim",
    "unsubstantiated_performance_claim",
    "cash_equivalent_cta_detected",
    "banned_phrase",
    "greeting_missing_or_invalid",
    "greeting_first_name_mismatch",
    "greeting_not_first_name_only",
    "prospect_reference_missing",
    "template_placeholders_present",
    "invalid_output_format",
    "forbidden_other_product_mentioned",
    "length_out_of_range",
]


@router.get("/compliance/dashboard", response_model=ComplianceDashboardResponse)
async def compliance_dashboard(
    days: int = Query(default=1, ge=1, le=3, description="Number of days of history (1-3)"),
) -> ComplianceDashboardResponse:
    redis = get_redis()
    now_utc = datetime.now(timezone.utc)
    result_days: list[ComplianceDashboardDay] = []

    for offset in range(days):
        target_day = (now_utc - timedelta(days=offset)).strftime("%Y%m%d")
        buckets: list[ComplianceViolationBucket] = []
        day_total = 0

        for category in _DASHBOARD_CATEGORIES:
            global_key = f"web_mvp:compliance:violation:{category}:{target_day}"
            remix_key = f"web_mvp:compliance:violation:remix:{category}:{target_day}"
            preview_key = f"web_mvp:compliance:violation:preview:{category}:{target_day}"

            total = int(await redis.get(global_key) or "0")
            if total == 0:
                continue
            remix_count = int(await redis.get(remix_key) or "0")
            preview_count = int(await redis.get(preview_key) or "0")
            buckets.append(
                ComplianceViolationBucket(
                    violation_type=category,
                    total=total,
                    remix=remix_count,
                    preview=preview_count,
                )
            )
            day_total += total

        result_days.append(
            ComplianceDashboardDay(
                date=target_day,
                buckets=sorted(buckets, key=lambda b: b.total, reverse=True),
                total_violations=day_total,
            )
        )

    return ComplianceDashboardResponse(
        days=result_days,
        generated_at=now_utc.isoformat().replace("+00:00", "Z"),
    )
