"""Web MVP routes for generate/remix/feedback workflows."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
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
from email_generation.preset_preview_pipeline import (
    make_response,
    preview_prompt_template_hashes,
    run_preview_pipeline,
)
from email_generation.prompt_templates import web_mvp_prompt_template_hash
from email_generation.remix_engine import (
    _extract_subject_and_body,
    build_draft,
    create_session_payload,
    emit_quality_metric,
    load_session,
    persist_violations,
    save_session,
)
from email_generation.runtime_policies import (
    debug_success_sample_rate,
    feature_flags_effective,
    feature_lossless_streaming_enabled,
    launch_mode,
    feature_rollout_snapshot,
    preview_pipeline_enabled,
    quick_generate_mode,
    real_provider_preference,
    resolve_runtime_policies,
    route_enabled,
    route_gate_sources,
    route_gates,
    rollout_context,
    web_mvp_stream_chunk_size,
)
from email_generation.streaming import stream_response
from infra.redis_client import get_redis
from runtime_debug import build_runtime_debug_payload

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
    token_vault: dict[str, str]


_REQUESTS: dict[str, RequestRecord] = {}
_SESSION_TOKEN_VAULTS: dict[str, tuple[dict[str, str], float]] = {}


def _preview_pipeline_enabled() -> bool:
    return preview_pipeline_enabled()


def _require_route_enabled(route: str) -> None:
    normalized = (route or "").strip().lower()
    if route_enabled(normalized):
        return
    raise HTTPException(
        status_code=503,
        detail={
            "error": "route_disabled",
            "route": normalized,
            "launch_mode": launch_mode(),
            "route_enabled": False,
        },
    )


def _cleanup_expired() -> None:
    now = time.time()
    expired = [rid for rid, rec in _REQUESTS.items() if now - rec.created_at > _REQUEST_TTL_SECONDS]
    for rid in expired:
        del _REQUESTS[rid]
    stale_sessions = [
        session_id
        for session_id, (_, created_at) in _SESSION_TOKEN_VAULTS.items()
        if now - created_at > 24 * 60 * 60
    ]
    for session_id in stale_sessions:
        del _SESSION_TOKEN_VAULTS[session_id]


def _request_token_vault(request: Request) -> dict[str, str]:
    vault = getattr(request.state, "token_vault", {}) or {}
    return dict(vault)


def _day_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


async def _emit_metric(name: str) -> None:
    redis = get_redis()
    key = f"web_mvp:metric:{_day_key()}:{name}"
    await redis.incr(key)
    await redis.expire(key, 3 * 24 * 60 * 60)


def _sha256_hex(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _lossless_chunks(text: str, chunk_size: int) -> list[str]:
    payload = text or ""
    if not payload:
        return [""]
    if chunk_size <= 0:
        chunk_size = 1
    return [payload[idx : idx + chunk_size] for idx in range(0, len(payload), chunk_size)]


def _token_stream(text: str, mode_info: dict[str, object]):
    async def _gen():
        emitted_chunks: list[str] = []
        if feature_lossless_streaming_enabled():
            chunks = _lossless_chunks(text, web_mvp_stream_chunk_size())
            mode_info["stream_chunk_mode"] = "stable_chars"
            mode_info["total_chunks"] = len(chunks)
            mode_info["total_chars"] = len(text)
            emitted = 0
            for chunk_index, chunk in enumerate(chunks):
                await asyncio.sleep(0.004 if chunk_index else 0.01)
                emitted += 1
                emitted_chunks.append(chunk)
                yield {
                    "token": chunk,
                    "chunk_index": chunk_index,
                    "chunk_len": len(chunk),
                    "chunk_mode": "stable_chars",
                }
            missing = max(0, len(chunks) - emitted)
            mode_info["stream_missing_chunks"] = missing
        else:
            words = text.split(" ")
            mode_info["stream_chunk_mode"] = "word_split"
            mode_info["total_chunks"] = len(words)
            emitted = 0
            for index, token in enumerate(words):
                await asyncio.sleep(0.005 if index else 0.01)
                chunk = token + " "
                emitted += 1
                emitted_chunks.append(chunk)
                yield chunk
            mode_info["total_chars"] = sum(len(part) for part in emitted_chunks)
            mode_info["stream_missing_chunks"] = max(0, len(words) - emitted)

        reconstructed = "".join(emitted_chunks)
        mode_info["stream_checksum"] = _sha256_hex(reconstructed)
        mode_info["stream_integrity_server_ok"] = mode_info.get("stream_missing_chunks", 0) == 0

    return _gen()


def _final_subject_body(draft: str, response_contract: str) -> tuple[str, str]:
    if response_contract == "rc_tco_json_v1":
        try:
            parsed = json.loads(draft)
            email = parsed.get("email") if isinstance(parsed, dict) else {}
            return str((email or {}).get("subject") or "").strip(), str((email or {}).get("body") or "").strip()
        except Exception:
            return "", draft.strip()
    return _extract_subject_and_body(draft)


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


def _debug_endpoints_enabled() -> bool:
    app_env = resolve_runtime_policies().app_env
    if app_env in {"local", "dev", "development", "test"}:
        return True
    explicit = os.environ.get("EMAILDJ_ENABLE_DEBUG_ENDPOINTS", "0").strip().lower()
    return explicit in {"1", "true", "yes", "on"}


def _flags_snapshot_for(endpoint: str, bucket_key: str) -> dict[str, dict[str, object]]:
    with rollout_context(endpoint=endpoint, bucket_key=bucket_key):
        return feature_rollout_snapshot()


def _effective_flags_for(endpoint: str, bucket_key: str) -> dict[str, bool]:
    with rollout_context(endpoint=endpoint, bucket_key=bucket_key):
        return feature_flags_effective()


def _prompt_template_versions() -> dict[str, object]:
    return {
        "web_mvp_prompt_hash": web_mvp_prompt_template_hash(),
        "preview_prompt_hashes": preview_prompt_template_hashes(),
    }


def _provider_path_from_trace(trace: dict[str, Any] | None) -> str:
    attempts = list((trace or {}).get("attempts") or [])
    parse_methods = {str(item.get("parse_method") or "") for item in attempts}
    if "salvage_substring" in parse_methods:
        return "salvage_used"
    if parse_methods and parse_methods.issubset({"strict_openai"}):
        return "openai_strict"
    return "fallback_parser"


def _fact_summary(session: dict[str, Any]) -> dict[str, object]:
    structured = list(session.get("allowed_facts_structured") or [])
    high_conf = [item for item in structured if str(item.get("confidence", "")).lower() == "high"]
    fact_types: list[str] = []
    for item in structured:
        kind = str(item.get("type") or "other").strip() or "other"
        if kind not in fact_types:
            fact_types.append(kind)
    return {
        "count": len(structured),
        "high_conf_count": len(high_conf),
        "types": fact_types,
    }


def _truncation_summary(session: dict[str, Any]) -> dict[str, object]:
    meta = session.get("truncation_metadata") or {}
    notes = meta.get("company_notes") or {}
    research = meta.get("research_excerpt") or {}
    return {
        "notes_cut": bool(notes.get("cut_mid_sentence")),
        "research_cut": bool(research.get("cut_mid_sentence")),
        "boundary_used": {
            "notes": notes.get("boundary_used", "none"),
            "research": research.get("boundary_used", "none"),
        },
    }


@router.get("/debug/config")
async def debug_config(
    endpoint: str = Query(default="generate", pattern="^(generate|remix|preview|stream)$"),
    bucket_key: str = Query(default="debug"),
) -> dict[str, object]:
    policies = resolve_runtime_policies()
    feature_flags = _flags_snapshot_for(endpoint=endpoint, bucket_key=bucket_key)
    effective_flags = _effective_flags_for(endpoint=endpoint, bucket_key=bucket_key)
    return {
        "app_env": policies.app_env,
        "runtime_mode": policies.quick_generate_mode,
        "provider_stub_enabled": policies.provider_stub_enabled,
        "quick_generate_mode": policies.quick_generate_mode,
        "real_provider_preference": policies.real_provider_preference,
        "launch_mode": policies.launch_mode,
        "route_gates": route_gates(),
        "route_gate_sources": route_gate_sources(),
        "preview_pipeline_enabled": policies.preview_pipeline_enabled,
        "p0_flags_effective": policies.p0_flags_effective,
        "p0_all_enabled": policies.p0_all_enabled,
        "feature_flags": feature_flags,
        "effective_flags": effective_flags,
        "prompt_template_versions": _prompt_template_versions(),
        "feature_env_raw": {key: value for key, value in os.environ.items() if key.startswith("FEATURE_")},
        **build_runtime_debug_payload(),
    }

@router.post("/generate", response_model=WebGenerateAccepted)
async def web_generate(req: WebGenerateRequest, request: Request) -> WebGenerateAccepted:
    _require_route_enabled("generate")
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
    request_id = str(uuid4())
    token_vault = _request_token_vault(request)
    if token_vault:
        _SESSION_TOKEN_VAULTS[session_id] = (token_vault, time.time())
    feature_flags = _flags_snapshot_for(endpoint="generate", bucket_key=session_id)
    flags_effective = _effective_flags_for(endpoint="generate", bucket_key=session_id)
    logger.info(
        "web_generate_config",
        extra={
            "endpoint": "generate",
            "request_id": request_id,
            "session_id": session_id,
            "preset_id": req.preset_id,
            "style_profile": req.style_profile.model_dump(),
            "feature_flags": feature_flags,
            "flags_effective": flags_effective,
            "prompt_template_versions": _prompt_template_versions(),
            "quick_generate_mode": quick_generate_mode(),
            "real_provider_preference": real_provider_preference(),
        },
    )
    with rollout_context(endpoint="generate", bucket_key=session_id):
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
    session["request_config"] = {
        "request_id": request_id,
        "endpoint": "generate",
        "preset_id": req.preset_id,
        "style_profile": req.style_profile.model_dump(),
        "feature_flags": feature_flags,
        "flags_effective": flags_effective,
        "prompt_template_versions": _prompt_template_versions(),
    }
    await save_session(session_id, session)

    _REQUESTS[request_id] = RequestRecord(
        session_id=session_id,
        style_profile=req.style_profile.model_dump(),
        mode="generate",
        created_at=time.time(),
        token_vault=token_vault,
    )
    return WebGenerateAccepted(request_id=request_id, session_id=session_id, stream_url=f"/web/v1/stream/{request_id}")


@router.post("/remix", response_model=WebRemixAccepted)
async def web_remix(req: WebRemixRequest) -> WebRemixAccepted:
    _require_route_enabled("remix")
    _cleanup_expired()
    session = await load_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail={"error": "session_not_found", "session_id": req.session_id})
    if req.preset_id:
        session["preset_id"] = req.preset_id
        await save_session(req.session_id, session)

    await _emit_metric("web_remix_started")
    request_id = str(uuid4())
    token_vault, _ = _SESSION_TOKEN_VAULTS.get(req.session_id, ({}, time.time()))
    feature_flags = _flags_snapshot_for(endpoint="remix", bucket_key=req.session_id)
    flags_effective = _effective_flags_for(endpoint="remix", bucket_key=req.session_id)
    logger.info(
        "web_remix_config",
        extra={
            "endpoint": "remix",
            "request_id": request_id,
            "session_id": req.session_id,
            "preset_id": session.get("preset_id"),
            "style_profile": req.style_profile.model_dump(),
            "feature_flags": feature_flags,
            "flags_effective": flags_effective,
            "prompt_template_versions": _prompt_template_versions(),
            "quick_generate_mode": quick_generate_mode(),
            "real_provider_preference": real_provider_preference(),
        },
    )
    session["request_config"] = {
        "request_id": request_id,
        "endpoint": "remix",
        "preset_id": session.get("preset_id"),
        "style_profile": req.style_profile.model_dump(),
        "feature_flags": feature_flags,
        "flags_effective": flags_effective,
        "prompt_template_versions": _prompt_template_versions(),
    }
    await save_session(req.session_id, session)
    _REQUESTS[request_id] = RequestRecord(
        session_id=req.session_id,
        style_profile=req.style_profile.model_dump(),
        mode="remix",
        created_at=time.time(),
        token_vault=token_vault,
    )
    return WebRemixAccepted(request_id=request_id, stream_url=f"/web/v1/stream/{request_id}")


@router.post(
    "/preset-previews/batch",
    response_model=WebPresetPreviewBatchResponse,
)
async def web_preset_previews_batch(req: WebPresetPreviewBatchRequest, request: Request) -> WebPresetPreviewBatchResponse:
    _require_route_enabled("preview")
    if not _preview_pipeline_enabled():
        raise HTTPException(status_code=503, detail={"error": "preview_pipeline_disabled"})

    await _emit_metric("web_preview_batch_started")
    throttled = bool(getattr(request.state, "cost_throttled", False))
    preview_request_id = str(uuid4())
    feature_flags = _flags_snapshot_for(endpoint="preview", bucket_key=preview_request_id)
    flags_effective = _effective_flags_for(endpoint="preview", bucket_key=preview_request_id)
    logger.info(
        "web_preview_batch_config",
        extra={
            "endpoint": "preview",
            "request_id": preview_request_id,
            "preset_ids": [item.preset_id for item in req.presets],
            "cta_type": req.cta_type,
            "feature_flags": feature_flags,
            "flags_effective": flags_effective,
            "prompt_template_versions": _prompt_template_versions(),
            "quick_generate_mode": quick_generate_mode(),
            "real_provider_preference": real_provider_preference(),
        },
    )

    try:
        with rollout_context(endpoint="preview", bucket_key=preview_request_id):
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
                "provider_source": ("external_provider" if result.mode == "real" else "provider_stub"),
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
                "status": result.status,
                "degraded_reason": result.degraded_reason,
                "request_id": preview_request_id,
            },
        )
        _log_debug_bundle(
            "web_preview_batch_debug_bundle",
            {
                "request_id": preview_request_id,
                "feature_flags": feature_flags,
                "flags_effective": flags_effective,
                "session_id": None,
                "mode": "preview",
                "generation_mode": result.mode,
                "provider_source": ("external_provider" if result.mode == "real" else "provider_stub"),
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
                "status": result.status,
                "degraded_reason": result.degraded_reason,
            },
            failure=result.violation_count > 0 or result.status == "degraded",
        )
        preview_payload = "\n".join(
            [f"Subject: {item.subject}\nBody:\n{item.body}" for item in result.previews]
        )
        execution_trace = {
            "flags_effective": flags_effective,
            "provider_path": (
                "degraded_fallback"
                if result.status == "degraded"
                else "openai_strict" if result.mode == "real" and result.provider == "openai" else "fallback_parser"
            ),
            "outcome": result.status,
            "degraded_reason": result.degraded_reason,
            "truncation": {"notes_cut": False, "research_cut": False, "boundary_used": "none"},
            "facts": {
                "count": len(result.summary_pack.facts if result.summary_pack else []),
                "high_conf_count": 0,
                "types": ["summary_pack"],
            },
            "preset_contracts": {
                "selected_preset": "batch",
                "violations": result.violation_codes,
            },
            "final_email": {
                "len_chars": len(preview_payload),
                "checksum": _sha256_hex(preview_payload),
            },
        }
        return make_response(
            result,
            request_id=preview_request_id,
            session_id=None,
            flags_effective=flags_effective,
            prompt_template_versions=_prompt_template_versions(),
            execution_trace=execution_trace,
        )
    except Exception as exc:
        await _emit_metric("web_preview_batch_failed")
        logger.exception("web_preview_batch_failed", extra={"error": str(exc), "request_id": preview_request_id})
        _log_debug_bundle(
            "web_preview_batch_debug_bundle",
            {
                "request_id": preview_request_id,
                "feature_flags": feature_flags,
                "flags_effective": flags_effective,
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
    generation_id = str(uuid4())
    draft_id = int(session.get("draft_id_counter") or 0) + 1
    session["draft_id_counter"] = draft_id

    # Mutable dict populated inside _bounded(); read by stream_response done event
    endpoint_name = rec.mode if rec.mode in {"generate", "remix"} else "stream"
    mode_info: dict[str, object] = {
        "request_id": request_id,
        "session_id": rec.session_id,
        "generation_id": generation_id,
        "draft_id": draft_id,
        # Debug provenance — surfaced at top level for smoke runner + dashboard
        "endpoint_name": f"web_v1_{endpoint_name}",
        "preset_name": session.get("preset_id"),
        "slider_config": rec.style_profile,
        "prompt_template_hash": web_mvp_prompt_template_hash(),
    }

    async def _bounded():
        async with _STREAM_SEM:
            try:
                flags_effective = _effective_flags_for(endpoint=endpoint_name, bucket_key=rec.session_id)
                mode_info["flags_effective"] = flags_effective
                with rollout_context(endpoint=endpoint_name, bucket_key=rec.session_id):
                    result = await build_draft(
                        session=session,
                        style_profile=rec.style_profile,
                        throttled=throttled,
                        session_id=rec.session_id,
                    )
                mode_info["mode"] = result.mode
                mode_info["provider_source"] = "external_provider" if result.mode == "real" else "provider_stub"
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
                mode_info["generation_status"] = result.generation_status
                mode_info["fallback_reason"] = result.fallback_reason
                mode_info["claims_policy_intervention_count"] = result.claims_policy_intervention_count
                mode_info["policy_versions"] = result.policy_version_snapshot
                mode_info["response_contract"] = result.response_contract
                final_subject, final_body = _final_subject_body(result.draft, response_contract=result.response_contract)
                rendered_email = f"Subject: {final_subject}\nBody:\n{final_body}".strip() if final_body else result.draft
                generation_trace = session.get("last_generation_trace") or {}
                execution_trace = {
                    "flags_effective": flags_effective,
                    "provider_path": _provider_path_from_trace(generation_trace),
                    "truncation": _truncation_summary(session),
                    "facts": _fact_summary(session),
                    "preset_contracts": {
                        "selected_preset": session.get("preset_id"),
                        "violations": result.violation_codes,
                    },
                    "final_email": {
                        "len_chars": len(rendered_email or ""),
                        "checksum": _sha256_hex(rendered_email or ""),
                    },
                    "prompt_template_versions": _prompt_template_versions(),
                }
                mode_info["final"] = {
                    "subject": final_subject,
                    "body": final_body,
                    "rendered_draft": result.draft,
                }
                mode_info["execution_trace"] = execution_trace
                with rollout_context(endpoint=endpoint_name, bucket_key=rec.session_id):
                    async for token in _token_stream(result.draft, mode_info):
                        yield token
                stream_missing_chunks = int(mode_info.get("stream_missing_chunks", 0) or 0)
                await emit_quality_metric("stream_count")
                await emit_quality_metric("draft_count")
                if stream_missing_chunks > 0:
                    await emit_quality_metric("stream_missing_chunk_count", amount=stream_missing_chunks)
                    await emit_quality_metric("stream_integrity_fail_count")
                if not bool(mode_info.get("stream_integrity_server_ok", True)):
                    await emit_quality_metric("stream_integrity_fail_count")
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
                        "provider_source": mode_info.get("provider_source"),
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
                        "generation_status": result.generation_status,
                        "fallback_reason": result.fallback_reason,
                        "claims_policy_intervention_count": result.claims_policy_intervention_count,
                        "session_id": rec.session_id,
                        "request_id": request_id,
                        "latency_ms": session["metrics"]["last_latency_ms"],
                        "stream_chunk_mode": mode_info.get("stream_chunk_mode"),
                        "stream_total_chunks": mode_info.get("total_chunks"),
                        "stream_total_chars": mode_info.get("total_chars"),
                        "stream_checksum": mode_info.get("stream_checksum"),
                        "stream_missing_chunks": stream_missing_chunks,
                        "generation_id": generation_id,
                        "draft_id": draft_id,
                        "execution_trace": execution_trace,
                    },
                )
                _log_debug_bundle(
                    "web_mvp_stream_debug_bundle",
                    {
                        "request_id": request_id,
                        "session_id": rec.session_id,
                        "mode": result.mode,
                        "provider_source": mode_info.get("provider_source"),
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
                        "generation_status": result.generation_status,
                        "fallback_reason": result.fallback_reason,
                        "claims_policy_intervention_count": result.claims_policy_intervention_count,
                        "stream_chunk_mode": mode_info.get("stream_chunk_mode"),
                        "stream_total_chunks": mode_info.get("total_chunks"),
                        "stream_total_chars": mode_info.get("total_chars"),
                        "stream_checksum": mode_info.get("stream_checksum"),
                        "stream_missing_chunks": stream_missing_chunks,
                        "generation_id": generation_id,
                        "draft_id": draft_id,
                        "execution_trace": execution_trace,
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

    return await stream_response(
        request_id=request_id,
        generator=_bounded(),
        done_extra=mode_info,
        event_extra={"session_id": rec.session_id, "generation_id": generation_id, "draft_id": draft_id},
        token_vault=rec.token_vault,
    )


@router.get("/debug/eval")
async def debug_eval_report() -> dict[str, object]:
    if not _debug_endpoints_enabled():
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    report_path = Path(__file__).resolve().parents[2] / "reports" / "sdr_quality" / "latest.json"
    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"error": "sdr_eval_report_missing", "path": str(report_path)},
        )
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": "sdr_eval_report_unreadable", "message": str(exc)}) from exc


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
