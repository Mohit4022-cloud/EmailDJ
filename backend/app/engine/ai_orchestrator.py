from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re
from typing import Any

from app.config import Settings
from app.openai_client import ENFORCED_OPENAI_MODEL, OpenAIClient
from app.schemas import WebGenerateRequest

from .budget_planner import (
    atom_structure,
    cta_alignment_status,
    draft_cta_alignment_status,
    plan_budget,
)
from .brief_cache import BriefCache, compute_brief_cache_key
from .normalize import normalize_generate_request
from .postprocess import deterministic_postprocess_draft
from .preset_contract import resolve_output_contract, sentence_count as preset_sentence_count, word_count as preset_word_count
from .presets.registry import load_all_presets, load_preset
from .prompts import stage_a, stage_b, stage_b0, stage_c, stage_c0, stage_d, stage_e
from .schemas import (
    RF_ANGLE_SET,
    RF_EMAIL_DRAFT,
    RF_EMAIL_REWRITE_PATCH,
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
    augment_qa_report_from_draft_heuristics,
    augment_qa_report_from_validation_codes,
    build_cta_lock,
    build_proof_basis,
    canonical_hook_ids,
    dominant_validation_code,
    normalize_qa_report,
    normalize_cta_text,
    opener_contract,
    opener_is_simple,
    proof_basis_key,
    PROOF_GAP_TEXT,
    resolve_hook_ids,
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
_ATOM_WORD_RE = re.compile(r"[a-z0-9]+")
_ATOM_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?%?\b")


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

    def _select_angle(self, *, angle_set: dict[str, Any], selected_angle_id: str) -> dict[str, Any]:
        angles = list(angle_set.get("angles") or [])
        if selected_angle_id:
            for angle in angles:
                if str(angle.get("angle_id") or "") == str(selected_angle_id or ""):
                    return dict(angle)
        return dict(angles[0]) if angles else {}

    def _fit_hypothesis_map(self, fit_map: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            str(item.get("fit_hypothesis_id") or "").strip(): dict(item)
            for item in (fit_map.get("hypotheses") or [])
            if isinstance(item, dict) and str(item.get("fit_hypothesis_id") or "").strip()
        }

    def _risk_level_from_flags(self, risk_flags: list[Any]) -> str:
        lowered = {str(item or "").strip().lower() for item in risk_flags if str(item or "").strip()}
        if lowered & {"proof_gap", "seller_proof_gap", "unsupported_recency", "unsupported_initiative"}:
            return "high"
        if lowered:
            return "medium"
        return "low"

    def _simplify_opener_text(self, text: Any) -> str:
        opener = normalize_cta_text(text)
        if not opener:
            return ""
        if opener_is_simple(opener, contract=opener_contract()):
            return opener
        parts = [
            chunk.strip()
            for chunk in re.split(r"(?<=[.!?])\s+|,\s+|;\s+|:\s+", opener)
            if chunk.strip()
        ]
        for chunk in parts:
            candidate = chunk.strip()
            if len(candidate.split()) < 4:
                continue
            if candidate and candidate[-1] not in ".!?":
                candidate = candidate.rstrip(",;:") + "."
            if opener_is_simple(candidate, contract=opener_contract()):
                return candidate
        return opener

    def _sanitize_fit_map_payload(
        self,
        fit_map: dict[str, Any],
        *,
        messaging_brief: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        out = dict(fit_map or {})
        actions: list[str] = []
        hypotheses: list[dict[str, Any]] = []
        for raw_hypothesis in (out.get("hypotheses") or []):
            hypothesis = dict(raw_hypothesis or {})
            hook_id = str(hypothesis.get("selected_hook_id") or "").strip()
            fit_hypothesis_id = str(hypothesis.get("fit_hypothesis_id") or "").strip()
            proof_basis = dict(hypothesis.get("proof_basis") or {})
            if not proof_basis:
                proof_basis = build_proof_basis(
                    hypothesis.get("proof"),
                    messaging_brief=messaging_brief,
                    selected_hook_id=hook_id,
                    selected_fit_hypothesis_id=fit_hypothesis_id,
                )
                actions.append("derive_fit_proof_basis")
            if str(proof_basis.get("kind") or "") == "none":
                if str(hypothesis.get("proof") or "").strip() != PROOF_GAP_TEXT:
                    hypothesis["proof"] = PROOF_GAP_TEXT
                    actions.append("lock_fit_proof_gap_text")
            hypothesis["proof_basis"] = proof_basis
            hypotheses.append(hypothesis)
        out["hypotheses"] = hypotheses
        return out, {"fit_sanitation_report": {"actions": actions}}

    def _sanitize_angle_set_payload(
        self,
        angle_set: dict[str, Any],
        *,
        messaging_brief: dict[str, Any],
        fit_map: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        out = dict(angle_set or {})
        actions: list[str] = []
        hypothesis_map = self._fit_hypothesis_map(fit_map)
        angles: list[dict[str, Any]] = []
        for raw_angle in (out.get("angles") or []):
            angle = dict(raw_angle or {})
            hypothesis = hypothesis_map.get(str(angle.get("selected_fit_hypothesis_id") or "").strip(), {})
            proof_basis = dict(angle.get("proof_basis") or hypothesis.get("proof_basis") or {})
            if not proof_basis:
                proof_basis = build_proof_basis(
                    angle.get("proof"),
                    messaging_brief=messaging_brief,
                    selected_hook_id=str(angle.get("selected_hook_id") or "").strip(),
                    selected_fit_hypothesis_id=str(angle.get("selected_fit_hypothesis_id") or "").strip(),
                )
                actions.append("derive_angle_proof_basis")
            if str(proof_basis.get("kind") or "") == "none" and str(angle.get("proof") or "").strip() != PROOF_GAP_TEXT:
                angle["proof"] = PROOF_GAP_TEXT
                actions.append("lock_angle_proof_gap_text")
            angle["proof_basis"] = proof_basis
            angle["primary_pain"] = normalize_cta_text(angle.get("primary_pain") or angle.get("pain") or "")
            angle["primary_value_motion"] = normalize_cta_text(angle.get("primary_value_motion") or angle.get("value") or "")
            angle["primary_proof_basis"] = str(angle.get("primary_proof_basis") or proof_basis_key(proof_basis)).strip()
            angle["framing_type"] = str(angle.get("framing_type") or angle.get("angle_type") or "").strip()
            angle["risk_level"] = str(angle.get("risk_level") or self._risk_level_from_flags(angle.get("risk_flags") or [])).strip()
            angles.append(angle)
        out["angles"] = angles
        return out, {"angle_sanitation_report": {"actions": actions}}

    def _body_sentences_without_cta(self, draft: dict[str, Any], *, cta_line: str) -> list[str]:
        body = str(draft.get("body") or "").strip()
        if not body:
            return []
        locked_cta = normalize_cta_text(cta_line)
        narrative_lines = [
            line.strip()
            for line in body.splitlines()
            if line.strip() and normalize_cta_text(line) != locked_cta
        ]
        narrative = " ".join(narrative_lines).strip()
        if not narrative:
            return []
        return [part.strip() for part in re.split(r"(?<=[.!?])\s+", narrative) if part.strip()]

    def _matching_sentence_indexes(self, sentences: list[str], *candidates: Any) -> list[int]:
        indexes: list[int] = []
        normalized_sentences = [normalize_cta_text(sentence).lower() for sentence in sentences]
        for raw_candidate in candidates:
            candidate = normalize_cta_text(raw_candidate).lower()
            if not candidate:
                continue
            for idx, sentence in enumerate(normalized_sentences):
                if candidate in sentence or sentence in candidate:
                    indexes.append(idx)
        return list(dict.fromkeys(indexes))

    def _build_rewrite_context(
        self,
        *,
        draft: dict[str, Any],
        qa_report: dict[str, Any],
        cta_line: str,
    ) -> dict[str, Any]:
        original_sentences = self._body_sentences_without_cta(draft, cta_line=cta_line)
        targeted: list[int] = []
        for issue in (qa_report.get("issues") or []):
            if not isinstance(issue, dict):
                continue
            targeted.extend(
                self._matching_sentence_indexes(
                    original_sentences,
                    issue.get("evidence_quote"),
                    issue.get("offending_span_or_target_section"),
                )
            )
        for action in (qa_report.get("rewrite_plan") or []):
            if not isinstance(action, dict):
                continue
            targeted.extend(self._matching_sentence_indexes(original_sentences, action.get("target")))
        targeted_indexes = sorted(set(targeted))
        preserve_indexes = [idx for idx in range(len(original_sentences)) if idx not in set(targeted_indexes)]
        return {
            "original_sentences": [{"index": idx, "text": text} for idx, text in enumerate(original_sentences)],
            "targeted_sentence_indexes": targeted_indexes,
            "preserve_sentence_indexes": preserve_indexes,
            "locked_cta": build_cta_lock(cta_line),
        }

    def _sanitize_rewrite_patch_payload(
        self,
        patch: dict[str, Any],
        *,
        original_draft: dict[str, Any],
        atoms: dict[str, Any],
        cta_line: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        out = dict(patch or {})
        actions: list[str] = []
        out["preset_id"] = str(original_draft.get("preset_id") or atoms.get("preset_id") or "").strip()
        out["selected_angle_id"] = str(original_draft.get("selected_angle_id") or atoms.get("selected_angle_id") or "").strip()
        out["used_hook_ids"] = list(original_draft.get("used_hook_ids") or atoms.get("used_hook_ids") or [])
        out["cta_lock"] = build_cta_lock(cta_line)
        preserve_indexes = []
        for raw_index in (out.get("preserve_sentence_indexes") or []):
            try:
                preserve_indexes.append(int(raw_index))
            except (TypeError, ValueError):
                continue
        out["preserve_sentence_indexes"] = sorted(set(preserve_indexes))
        normalized_operations: list[dict[str, Any]] = []
        for raw_operation in (out.get("sentence_operations") or []):
            if not isinstance(raw_operation, dict):
                continue
            try:
                target_index = int(raw_operation.get("target_sentence_index"))
            except (TypeError, ValueError):
                continue
            normalized_operations.append(
                {
                    "issue_code": str(raw_operation.get("issue_code") or "other").strip() or "other",
                    "action": str(raw_operation.get("action") or "").strip(),
                    "target_sentence_index": target_index,
                    "text": normalize_cta_text(raw_operation.get("text") or ""),
                }
            )
        out["sentence_operations"] = normalized_operations
        return out, {"rewrite_patch_report": {"actions": actions}}

    def _reconstruct_draft_from_patch(
        self,
        *,
        patch: dict[str, Any],
        original_draft: dict[str, Any],
        cta_line: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        original_sentences = self._body_sentences_without_cta(original_draft, cta_line=cta_line)
        preserve_indexes = {int(item) for item in (patch.get("preserve_sentence_indexes") or []) if isinstance(item, int)}
        rewrites: dict[int, str] = {}
        deletions: set[int] = set()
        insertions: dict[int, list[str]] = {}
        dropped_operations: list[str] = []
        for operation in (patch.get("sentence_operations") or []):
            if not isinstance(operation, dict):
                continue
            action = str(operation.get("action") or "").strip()
            target_index = int(operation.get("target_sentence_index") or 0)
            text = normalize_cta_text(operation.get("text") or "")
            if target_index < 0 or target_index >= len(original_sentences):
                dropped_operations.append("drop_patch_invalid_index")
                continue
            if action in {"rewrite", "delete"} and target_index in preserve_indexes:
                dropped_operations.append("drop_patch_against_preserve")
                continue
            if action == "rewrite" and text:
                rewrites[target_index] = text
            elif action == "delete":
                deletions.add(target_index)
            elif action == "insert_after" and text:
                insertions.setdefault(target_index, []).append(text)
            elif action == "keep":
                continue
        rebuilt_sentences: list[str] = []
        for idx, sentence in enumerate(original_sentences):
            if idx not in deletions:
                rebuilt_sentences.append(rewrites.get(idx, sentence).strip())
            for inserted in insertions.get(idx, []):
                rebuilt_sentences.append(inserted.strip())
        narrative = " ".join(part for part in rebuilt_sentences if part).strip()
        locked_cta = normalize_cta_text(cta_line)
        rebuilt_body = f"{narrative}\n\n{locked_cta}" if narrative else locked_cta
        rebuilt_draft = {
            "version": str(original_draft.get("version") or "1.0"),
            "preset_id": str(patch.get("preset_id") or original_draft.get("preset_id") or "").strip(),
            "selected_angle_id": str(patch.get("selected_angle_id") or original_draft.get("selected_angle_id") or "").strip(),
            "used_hook_ids": list(patch.get("used_hook_ids") or original_draft.get("used_hook_ids") or []),
            "subject": str(original_draft.get("subject") or "").strip(),
            "body": rebuilt_body,
        }
        return rebuilt_draft, {
            "rewrite_patch_operation_count": len(list(patch.get("sentence_operations") or [])),
            "rewrite_patch_preserve_count": len(preserve_indexes),
            "rewrite_patch_dropped_operations": dropped_operations,
        }

    def _budget_plan(
        self,
        *,
        preset_id: str,
        preset_contract: dict[str, Any],
        selected_angle: dict[str, Any],
        message_atoms: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return plan_budget(
            preset_id=str(preset_id or "").strip(),
            preset_contract=preset_contract,
            selected_angle=selected_angle,
            message_atoms=message_atoms,
        )

    def _mark_budget_feasibility(self, *, trace: Trace, stage_name: str, budget_plan: dict[str, Any]) -> None:
        if str(budget_plan.get("feasibility_status") or "") == "infeasible" and "first_budget_infeasible_stage" not in trace.meta:
            trace.set_meta(
                first_budget_infeasible_stage=stage_name,
                first_budget_infeasible_reason=str(budget_plan.get("feasibility_reason") or ""),
            )

    def _normalize_message_atoms(self, atoms: dict[str, Any], *, trace: Trace) -> dict[str, Any]:
        out = dict(atoms)
        for field in (
            "preset_id",
            "selected_angle_id",
            "opener_atom",
            "opener_line",
            "value_atom",
            "proof_atom",
            "cta_atom",
            "cta_intent",
            "required_cta_line",
        ):
            raw_value = out.get(field)
            normalized = str(raw_value or "").strip()
            if normalized != str(raw_value or ""):
                trace.add_postprocess_step(f"normalize_{field}_whitespace")
            out[field] = normalized
        used_hook_ids: list[str] = []
        seen_hook_ids: set[str] = set()
        for raw_item in out.get("used_hook_ids") or []:
            item = str(raw_item or "").strip()
            if not item or item in seen_hook_ids:
                continue
            seen_hook_ids.add(item)
            used_hook_ids.append(item)
        if used_hook_ids != list(out.get("used_hook_ids") or []):
            trace.add_postprocess_step("normalize_used_hook_ids")
        out["used_hook_ids"] = used_hook_ids
        out["canonical_hook_ids"] = [
            str(item or "").strip()
            for item in (out.get("canonical_hook_ids") or [])
            if str(item or "").strip()
        ]
        out["opener_contract"] = dict(out.get("opener_contract") or opener_contract())
        out["proof_basis"] = dict(out.get("proof_basis") or {})
        out["cta_lock"] = dict(out.get("cta_lock") or build_cta_lock(out.get("required_cta_line") or out.get("cta_atom") or ""))
        if str(out.get("proof_atom") or "") == "":
            trace.add_postprocess_step("normalize_proof_atom_empty")
        return out

    def _proof_atom_has_seller_grounding(self, proof_atom: str, seller_proof_texts: list[str]) -> bool:
        proof_text = str(proof_atom or "").strip().lower()
        if not proof_text:
            return True
        proof_tokens = {token for token in _ATOM_WORD_RE.findall(proof_text) if len(token) > 2}
        proof_numbers = set(_ATOM_NUMBER_RE.findall(proof_text))
        seller_tokens: set[str] = set()
        seller_numbers: set[str] = set()
        for seller_text in seller_proof_texts:
            lowered = str(seller_text or "").strip().lower()
            if not lowered:
                continue
            seller_tokens.update(token for token in _ATOM_WORD_RE.findall(lowered) if len(token) > 2)
            seller_numbers.update(_ATOM_NUMBER_RE.findall(lowered))
        if len(proof_tokens & seller_tokens) < 2:
            return False
        if proof_numbers and proof_numbers.isdisjoint(seller_numbers):
            return False
        return True

    def _sanitize_message_atoms_payload(
        self,
        atoms: dict[str, Any],
        *,
        preset_id: str,
        selected_angle: dict[str, Any],
        cta_line: str,
        messaging_brief: dict[str, Any],
        budget_plan: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        out = dict(atoms or {})
        actions: list[str] = []

        for field in (
            "preset_id",
            "selected_angle_id",
            "opener_atom",
            "opener_line",
            "value_atom",
            "proof_atom",
            "cta_atom",
            "cta_intent",
            "required_cta_line",
        ):
            raw_value = out.get(field)
            normalized = str(raw_value or "").strip()
            if normalized != str(raw_value or ""):
                actions.append(f"normalize_{field}_whitespace")
            out[field] = normalized

        selected_hook_id = str(selected_angle.get("selected_hook_id") or "").strip()
        raw_hook_ids = list(out.get("used_hook_ids") or [])
        used_hook_ids, hook_actions = resolve_hook_ids(
            raw_hook_ids,
            messaging_brief=messaging_brief,
            selected_hook_id=selected_hook_id,
        )
        actions.extend(hook_actions)
        out["used_hook_ids"] = used_hook_ids
        out["canonical_hook_ids"] = canonical_hook_ids(messaging_brief)

        expected_preset_id = str(preset_id or "").strip()
        if str(out.get("preset_id") or "") != expected_preset_id:
            out["preset_id"] = expected_preset_id
            actions.append("lock_atoms_preset_id")

        expected_angle_id = str(selected_angle.get("angle_id") or "").strip()
        if expected_angle_id and str(out.get("selected_angle_id") or "") != expected_angle_id:
            out["selected_angle_id"] = expected_angle_id
            actions.append("lock_atoms_selected_angle_id")

        locked_cta = normalize_cta_text(cta_line)
        if str(out.get("cta_atom") or "") != locked_cta:
            out["cta_atom"] = locked_cta
            actions.append("lock_atoms_cta_atom")
        if str(out.get("required_cta_line") or "") != locked_cta:
            out["required_cta_line"] = locked_cta
            actions.append("lock_atoms_required_cta_line")
        cta_lock = build_cta_lock(locked_cta)
        if dict(out.get("cta_lock") or {}) != cta_lock:
            out["cta_lock"] = cta_lock
            actions.append("lock_atoms_cta_lock")

        simplified_opener = self._simplify_opener_text(out.get("opener_atom") or "")
        if simplified_opener and simplified_opener != str(out.get("opener_atom") or ""):
            out["opener_atom"] = simplified_opener
            actions.append("simplify_opener_atom")
        if str(out.get("opener_line") or "") != str(out.get("opener_atom") or ""):
            out["opener_line"] = str(out.get("opener_atom") or "")
            actions.append("lock_atoms_opener_line")
        if dict(out.get("opener_contract") or {}) != opener_contract():
            out["opener_contract"] = opener_contract()
            actions.append("lock_atoms_opener_contract")

        facts = [item for item in (messaging_brief.get("facts_from_input") or []) if isinstance(item, dict)]
        seller_proof_texts = [
            str(item.get("text") or "").strip()
            for item in facts
            if str(item.get("fact_kind") or "").strip() == "seller_proof" and str(item.get("text") or "").strip()
        ]
        proof_atom = str(out.get("proof_atom") or "").strip()
        proof_basis = dict(out.get("proof_basis") or selected_angle.get("proof_basis") or {})
        if not proof_basis:
            proof_basis = build_proof_basis(
                proof_atom,
                messaging_brief=messaging_brief,
                selected_hook_id=selected_hook_id,
                selected_fit_hypothesis_id=str(selected_angle.get("selected_fit_hypothesis_id") or "").strip(),
            )
            actions.append("derive_atoms_proof_basis")
        if str(proof_basis.get("kind") or "") not in {"hard_proof", "soft_signal"}:
            if proof_atom:
                out["proof_atom"] = ""
                proof_atom = ""
                actions.append("clear_atoms_proof_for_nonproof_basis")
            if str(proof_basis.get("kind") or "") != "none":
                proof_basis = build_proof_basis(
                    "",
                    messaging_brief=messaging_brief,
                    selected_hook_id=selected_hook_id,
                    selected_fit_hypothesis_id=str(selected_angle.get("selected_fit_hypothesis_id") or "").strip(),
                )
                actions.append("downgrade_atoms_proof_basis_to_none")
        elif proof_atom and (not seller_proof_texts or not self._proof_atom_has_seller_grounding(proof_atom, seller_proof_texts)):
            out["proof_atom"] = ""
            proof_atom = ""
            proof_basis = build_proof_basis(
                "",
                messaging_brief=messaging_brief,
                selected_hook_id=selected_hook_id,
                selected_fit_hypothesis_id=str(selected_angle.get("selected_fit_hypothesis_id") or "").strip(),
            )
            actions.append("clear_atoms_ungrounded_proof_atom")
        out["proof_basis"] = proof_basis

        target_word_budget = int(budget_plan.get("target_total_words") or 0)
        if target_word_budget and int(out.get("target_word_budget") or 0) != target_word_budget:
            out["target_word_budget"] = target_word_budget
            actions.append("lock_atoms_target_word_budget")

        target_sentence_budget = sum(
            1
            for field in ("opener_atom", "value_atom", "proof_atom", "cta_atom")
            if str(out.get(field) or "").strip()
        )
        if int(out.get("target_sentence_budget") or 0) != target_sentence_budget:
            out["target_sentence_budget"] = target_sentence_budget
            actions.append("recount_atoms_target_sentence_budget")

        return out, {
            "atom_sanitation_report": {
                "actions": actions,
            }
        }

    def _qa_primary_issue_code(self, qa_report: dict[str, Any]) -> str | None:
        for issue in qa_report.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            issue_code = str(issue.get("issue_code") or issue.get("type") or "").strip()
            if issue_code:
                return issue_code
        return None

    def _annotate_atoms_stage(
        self,
        *,
        trace: Trace,
        stage_name: str,
        atoms: dict[str, Any],
        preset_contract: dict[str, Any],
        budget_plan: dict[str, Any],
        cta_line: str,
    ) -> None:
        self._mark_budget_feasibility(trace=trace, stage_name=stage_name, budget_plan=budget_plan)
        trace.annotate_stage(
            stage=stage_name,
            details={
                "preset_id": str(atoms.get("preset_id") or "").strip(),
                "preset_contract": dict(preset_contract),
                "preset_contract_hash": hash_json(preset_contract),
                "budget_plan": dict(budget_plan),
                "budget_plan_hash": hash_json(budget_plan),
                "target_word_budget": int(atoms.get("target_word_budget") or 0),
                "target_sentence_budget": int(atoms.get("target_sentence_budget") or 0),
                "actual_pre_generation_atom_count": len(atom_structure(atoms)),
                "actual_pre_generation_atom_structure": atom_structure(atoms),
                "atom_validation_result": "passed",
                "cta_alignment_status": cta_alignment_status(
                    candidate=atoms.get("cta_atom"),
                    required_cta_line=cta_line,
                ),
                "pre_generation_budget_feasibility": str(budget_plan.get("feasibility_status") or ""),
                "pre_generation_budget_feasibility_reason": str(budget_plan.get("feasibility_reason") or ""),
                "first_budget_infeasible_stage": trace.meta.get("first_budget_infeasible_stage"),
            },
            output={
                "preset_id": str(atoms.get("preset_id") or "").strip(),
                "selected_angle_id": str(atoms.get("selected_angle_id") or "").strip(),
                "used_hook_ids": list(atoms.get("used_hook_ids") or []),
                "canonical_hook_ids": list(atoms.get("canonical_hook_ids") or []),
                "opener_atom": str(atoms.get("opener_atom") or "").strip(),
                "opener_line": str(atoms.get("opener_line") or "").strip(),
                "value_atom": str(atoms.get("value_atom") or "").strip(),
                "proof_atom": str(atoms.get("proof_atom") or "").strip(),
                "proof_basis": dict(atoms.get("proof_basis") or {}),
                "cta_atom": str(atoms.get("cta_atom") or "").strip(),
                "required_cta_line": str(atoms.get("required_cta_line") or "").strip(),
                "cta_lock": dict(atoms.get("cta_lock") or {}),
            },
        )

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
        budget_plan: dict[str, Any] | None = None,
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
        if budget_plan:
            self._mark_budget_feasibility(trace=trace, stage_name=stage_name, budget_plan=budget_plan)
            details.setdefault("budget_plan", dict(budget_plan))
            details.setdefault("budget_plan_hash", hash_json(budget_plan))
            details.setdefault("target_word_budget", int(budget_plan.get("target_total_words") or 0))
            details.setdefault("target_sentence_budget", int(budget_plan.get("target_sentence_count") or 0))
            details.setdefault("pre_generation_budget_feasibility", str(budget_plan.get("feasibility_status") or ""))
            details.setdefault("pre_generation_budget_feasibility_reason", str(budget_plan.get("feasibility_reason") or ""))
        details.setdefault("first_budget_infeasible_stage", trace.meta.get("first_budget_infeasible_stage"))
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
        budget_plan: dict[str, Any],
        draft: dict[str, Any],
        qa_report: dict[str, Any],
        generation_validation_codes: list[str],
    ) -> None:
        issues = [item for item in qa_report.get("issues") or [] if isinstance(item, dict)]
        dominant_issue = self._qa_primary_issue_code(qa_report)
        trace.annotate_stage(
            stage=stage_name,
            details={
                "preset_id": str(preset_id or ""),
                "preset_contract": dict(preset_contract),
                "preset_contract_hash": hash_json(preset_contract),
                "budget_plan": dict(budget_plan),
                "budget_plan_hash": hash_json(budget_plan),
                "target_word_budget": int(budget_plan.get("target_total_words") or 0),
                "target_sentence_budget": int(budget_plan.get("target_sentence_count") or 0),
                "pre_generation_budget_feasibility": str(budget_plan.get("feasibility_status") or ""),
                "pre_generation_budget_feasibility_reason": str(budget_plan.get("feasibility_reason") or ""),
                "pre_rewrite_word_count": preset_word_count(str(draft.get("body") or "").strip()),
                "pre_rewrite_sentence_count": preset_sentence_count(str(draft.get("body") or "").strip()),
                "dominant_failing_rule": dominant_issue or dominant_validation_code(generation_validation_codes),
                "first_budget_infeasible_stage": trace.meta.get("first_budget_infeasible_stage"),
                "salvage_applied": False,
                "salvage_result": "not_run",
            },
            output=qa_report,
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
        budget_plan: dict[str, Any],
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
                budget_plan=budget_plan,
                failure_code=dominant_validation_code(final_codes) or "word_count_out_of_band",
            ),
            validator=None,
            trace_stage=salvage_stage,
        )
        salvage_draft["preset_id"] = str(preset_id)
        salvage_draft["selected_angle_id"] = str(draft.get("selected_angle_id") or atoms.get("selected_angle_id") or "")
        salvage_draft["used_hook_ids"] = list(draft.get("used_hook_ids") or atoms.get("used_hook_ids") or [])
        salvage_pre_details = {
            "pre_postprocess_word_count": preset_word_count(str(salvage_draft.get("body") or "").strip()),
            "pre_postprocess_sentence_count": preset_sentence_count(str(salvage_draft.get("body") or "").strip()),
            "pre_postprocess_cta_alignment_status": draft_cta_alignment_status(
                body=salvage_draft.get("body"),
                required_cta_line=cta_line,
            ),
        }
        salvage_draft, salvage_steps = self._mechanical_postprocess(
            salvage_draft,
            slider_params,
            cta_line,
            trace,
            budget_plan=budget_plan,
        )
        salvage_codes = validate_email_draft(
            salvage_draft,
            brief=messaging_brief,
            cta_final_line=cta_line,
            sliders=slider_params,
            message_atoms=atoms,
            preset_contract=preset_contract,
            budget_plan=budget_plan,
        )
        self._annotate_draft_stage(
            trace=trace,
            stage_name=salvage_stage,
            draft=salvage_draft,
            validation_codes=salvage_codes,
            mechanical_steps=salvage_steps,
            final_validation_status="failed" if salvage_codes else "passed",
            preset_contract=preset_contract,
            budget_plan=budget_plan,
            stage_details={
                **salvage_pre_details,
                "dominant_failing_rule": dominant_validation_code(final_codes) or "word_count_out_of_band",
                "salvage_applied": True,
                "salvage_result": "failed" if salvage_codes else "passed",
                "post_salvage_word_count": preset_word_count(str(salvage_draft.get("body") or "").strip()),
                "cta_alignment_status": draft_cta_alignment_status(body=salvage_draft.get("body"), required_cta_line=cta_line),
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
            selected_angle = self._select_angle(angle_set=angle_set, selected_angle_id=selected_angle_id)
            preset = load_preset(ctx.preset_id)
            preset_contract = self._resolved_preset_contract(preset=preset, sliders=slider_params)
            self._remember_preset_contract(trace=trace, preset_id=ctx.preset_id, preset_contract=preset_contract)
            budget_seed_plan = self._budget_plan(
                preset_id=ctx.preset_id,
                preset_contract=preset_contract,
                selected_angle=selected_angle,
                message_atoms=None,
            )
            atoms_stage = self._trace_stage_name(STAGES["C0"])
            atoms = await self._run_stage(
                trace=trace,
                config=StageConfig(
                    stage=STAGES["C0"],
                    max_tokens=400,
                    reasoning_effort=self.settings.openai_reasoning_low,
                    response_format=RF_MESSAGE_ATOMS,
                ),
                messages=stage_c0.build_messages(
                    messaging_brief=messaging_brief,
                    fit_map=fit_map,
                    angle_set=angle_set,
                    selected_angle_id=selected_angle_id,
                    preset_id=ctx.preset_id,
                    preset_contract=preset_contract,
                    budget_plan=budget_seed_plan,
                    sliders=slider_params,
                    cta_final_line=cta_line,
                ),
                validator=lambda payload: validate_message_atoms(
                    payload,
                    preset_id=ctx.preset_id,
                    cta_final_line=cta_line,
                    messaging_brief=messaging_brief,
                    selected_angle=selected_angle,
                    preset_contract=preset_contract,
                    forbidden_patterns=list(messaging_brief.get("forbidden_claim_patterns") or []),
                    budget_plan=budget_seed_plan,
                ),
                postprocess=lambda payload: self._sanitize_message_atoms_payload(
                    payload,
                    preset_id=ctx.preset_id,
                    selected_angle=selected_angle,
                    cta_line=cta_line,
                    messaging_brief=messaging_brief,
                    budget_plan=budget_seed_plan,
                ),
                trace_stage=atoms_stage,
            )
            atoms = self._normalize_message_atoms(atoms, trace=trace)
            budget_plan = self._budget_plan(
                preset_id=ctx.preset_id,
                preset_contract=preset_contract,
                selected_angle=selected_angle,
                message_atoms=atoms,
            )
            self._annotate_atoms_stage(
                trace=trace,
                stage_name=atoms_stage,
                atoms=atoms,
                preset_contract=preset_contract,
                budget_plan=budget_plan,
                cta_line=cta_line,
            )
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
                    preset_contract=preset_contract,
                    budget_plan=budget_plan,
                    sliders=slider_params,
                    cta_final_line=cta_line,
                ),
                validator=None,
                trace_stage=generation_stage,
            )
            draft.setdefault("preset_id", ctx.preset_id)
            draft.setdefault("selected_angle_id", selected_angle_id)
            draft.setdefault("used_hook_ids", list(atoms.get("used_hook_ids") or []))
            generation_pre_details = {
                "pre_postprocess_word_count": preset_word_count(str(draft.get("body") or "").strip()),
                "pre_postprocess_sentence_count": preset_sentence_count(str(draft.get("body") or "").strip()),
                "pre_postprocess_cta_alignment_status": draft_cta_alignment_status(
                    body=draft.get("body"),
                    required_cta_line=cta_line,
                ),
            }

            draft, generation_steps = self._mechanical_postprocess(
                draft,
                slider_params,
                cta_line,
                trace,
                budget_plan=budget_plan,
            )

            validation_codes = validate_email_draft(
                draft,
                brief=messaging_brief,
                cta_final_line=cta_line,
                sliders=slider_params,
                message_atoms=atoms,
                preset_contract=preset_contract,
                budget_plan=budget_plan,
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
                budget_plan=budget_plan,
                stage_details={
                    **generation_pre_details,
                    "pre_rewrite_word_count": preset_word_count(str(draft.get("body") or "").strip()),
                    "actual_pre_generation_atom_count": len(atom_structure(atoms)),
                    "actual_pre_generation_atom_structure": atom_structure(atoms),
                    "cta_alignment_status": draft_cta_alignment_status(body=draft.get("body"), required_cta_line=cta_line),
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
                messages=stage_d.build_messages(draft, messaging_brief, atoms, cta_line, preset_contract, budget_plan),
                validator=None,
                trace_stage=qa_stage,
            )
            qa = normalize_qa_report(qa, draft=draft, locked_cta=cta_line)
            qa = augment_qa_report_from_validation_codes(
                qa,
                draft=draft,
                locked_cta=cta_line,
                validation_codes=validation_codes,
            )
            qa = augment_qa_report_from_draft_heuristics(
                qa,
                draft=draft,
                locked_cta=cta_line,
            )
            self._annotate_qa_stage(
                trace=trace,
                stage_name=qa_stage,
                preset_id=ctx.preset_id,
                preset_contract=preset_contract,
                budget_plan=budget_plan,
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
                budget_plan=budget_plan,
                stage_details={
                    "dominant_failing_rule": dominant_validation_code(validation_codes)
                    or self._qa_primary_issue_code(qa),
                },
            )

            rewrite_applied = False
            if qa.get("pass_rewrite_needed") or validation_codes:
                rewrite_applied = True
                rewrite_stage = self._trace_stage_name(STAGES["E"])
                rewrite_context = self._build_rewrite_context(
                    draft=draft,
                    qa_report=qa,
                    cta_line=cta_line,
                )
                rewrite_patch = await self._run_stage(
                    trace=trace,
                    config=StageConfig(
                        stage=STAGES["E"],
                        max_tokens=800,
                        reasoning_effort=self.settings.openai_reasoning_low,
                        response_format=RF_EMAIL_REWRITE_PATCH,
                    ),
                    messages=stage_e.build_messages(
                        email_draft=draft,
                        qa_report=qa,
                        messaging_brief=messaging_brief,
                        message_atoms=atoms,
                        cta_final_line=cta_line,
                        rewrite_context=rewrite_context,
                        preset_contract=preset_contract,
                        budget_plan=budget_plan,
                        sliders=slider_params,
                    ),
                    postprocess=lambda payload: self._sanitize_rewrite_patch_payload(
                        payload,
                        original_draft=draft,
                        atoms=atoms,
                        cta_line=cta_line,
                    ),
                    validator=None,
                    trace_stage=rewrite_stage,
                )
                draft, rewrite_patch_details = self._reconstruct_draft_from_patch(
                    patch=rewrite_patch,
                    original_draft=draft,
                    cta_line=cta_line,
                )
                rewrite_pre_details = {
                    "pre_postprocess_word_count": preset_word_count(str(draft.get("body") or "").strip()),
                    "pre_postprocess_sentence_count": preset_sentence_count(str(draft.get("body") or "").strip()),
                    "pre_postprocess_cta_alignment_status": draft_cta_alignment_status(
                        body=draft.get("body"),
                        required_cta_line=cta_line,
                    ),
                }
                draft, rewrite_steps = self._mechanical_postprocess(
                    draft,
                    slider_params,
                    cta_line,
                    trace,
                    budget_plan=budget_plan,
                )
                final_codes = validate_email_draft(
                    draft,
                    brief=messaging_brief,
                    cta_final_line=cta_line,
                    sliders=slider_params,
                    message_atoms=atoms,
                    preset_contract=preset_contract,
                    budget_plan=budget_plan,
                )
                self._annotate_draft_stage(
                    trace=trace,
                    stage_name=rewrite_stage,
                    draft=draft,
                    validation_codes=final_codes,
                    mechanical_steps=rewrite_steps,
                    final_validation_status="failed" if final_codes else "passed",
                    preset_contract=preset_contract,
                    budget_plan=budget_plan,
                    stage_details={
                        **rewrite_pre_details,
                        **rewrite_patch_details,
                        "post_rewrite_word_count": preset_word_count(str(draft.get("body") or "").strip()),
                        "dominant_failing_rule": dominant_validation_code(final_codes),
                        "cta_alignment_status": draft_cta_alignment_status(body=draft.get("body"), required_cta_line=cta_line),
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
                        budget_plan=budget_plan,
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
            postprocess=lambda payload: self._sanitize_fit_map_payload(payload, messaging_brief=messaging_brief),
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
            postprocess=lambda payload: self._sanitize_angle_set_payload(
                payload,
                messaging_brief=messaging_brief,
                fit_map=fit_map,
            ),
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
            selected_angle = self._select_angle(angle_set=angle_set, selected_angle_id=selected_angle_id)

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
                    budget_seed_plan = self._budget_plan(
                        preset_id=str(requested_id),
                        preset_contract=preset_contract,
                        selected_angle=selected_angle,
                        message_atoms=None,
                    )
                    atoms_stage = self._trace_stage_name(STAGES["C0"], preset_id=requested_id)
                    atoms = await self._run_stage(
                        trace=trace,
                        config=StageConfig(
                            stage=STAGES["C0"],
                            max_tokens=400,
                            reasoning_effort=self.settings.openai_reasoning_low,
                            response_format=RF_MESSAGE_ATOMS,
                        ),
                        messages=stage_c0.build_messages(
                            messaging_brief=messaging_brief,
                            fit_map=fit_map,
                            angle_set=angle_set,
                            selected_angle_id=selected_angle_id,
                            preset_id=str(requested_id),
                            preset_contract=preset_contract,
                            budget_plan=budget_seed_plan,
                            sliders=variant_sliders,
                            cta_final_line=cta_line,
                        ),
                        validator=lambda payload, rid=str(requested_id), contract=preset_contract, seed=budget_seed_plan: validate_message_atoms(
                            payload,
                            preset_id=rid,
                            cta_final_line=cta_line,
                            messaging_brief=messaging_brief,
                            selected_angle=selected_angle,
                            preset_contract=contract,
                            forbidden_patterns=list(messaging_brief.get("forbidden_claim_patterns") or []),
                            budget_plan=seed,
                        ),
                        postprocess=lambda payload, rid=str(requested_id), seed=budget_seed_plan, contract_angle=selected_angle: self._sanitize_message_atoms_payload(
                            payload,
                            preset_id=rid,
                            selected_angle=contract_angle,
                            cta_line=cta_line,
                            messaging_brief=messaging_brief,
                            budget_plan=seed,
                        ),
                        trace_stage=atoms_stage,
                    )
                    atoms = self._normalize_message_atoms(atoms, trace=trace)
                    budget_plan = self._budget_plan(
                        preset_id=str(requested_id),
                        preset_contract=preset_contract,
                        selected_angle=selected_angle,
                        message_atoms=atoms,
                    )
                    self._annotate_atoms_stage(
                        trace=trace,
                        stage_name=atoms_stage,
                        atoms=atoms,
                        preset_contract=preset_contract,
                        budget_plan=budget_plan,
                        cta_line=cta_line,
                    )
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
                            preset_contract=preset_contract,
                            budget_plan=budget_plan,
                            sliders=variant_sliders,
                            cta_final_line=cta_line,
                        ),
                        validator=None,
                        trace_stage=generation_stage,
                    )
                    draft.setdefault("preset_id", str(requested_id))
                    draft.setdefault("selected_angle_id", selected_angle_id)
                    draft.setdefault("used_hook_ids", list(atoms.get("used_hook_ids") or []))
                    generation_pre_details = {
                        "pre_postprocess_word_count": preset_word_count(str(draft.get("body") or "").strip()),
                        "pre_postprocess_sentence_count": preset_sentence_count(str(draft.get("body") or "").strip()),
                        "pre_postprocess_cta_alignment_status": draft_cta_alignment_status(
                            body=draft.get("body"),
                            required_cta_line=cta_line,
                        ),
                    }
                    draft, generation_steps = self._mechanical_postprocess(
                        draft,
                        variant_sliders,
                        cta_line,
                        trace,
                        budget_plan=budget_plan,
                    )

                    validation_codes = validate_email_draft(
                        draft,
                        brief=messaging_brief,
                        cta_final_line=cta_line,
                        sliders=variant_sliders,
                        message_atoms=atoms,
                        preset_contract=preset_contract,
                        budget_plan=budget_plan,
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
                        budget_plan=budget_plan,
                        stage_details={
                            **generation_pre_details,
                            "pre_rewrite_word_count": preset_word_count(str(draft.get("body") or "").strip()),
                            "actual_pre_generation_atom_count": len(atom_structure(atoms)),
                            "actual_pre_generation_atom_structure": atom_structure(atoms),
                            "cta_alignment_status": draft_cta_alignment_status(body=draft.get("body"), required_cta_line=cta_line),
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
                        messages=stage_d.build_messages(draft, messaging_brief, atoms, cta_line, preset_contract, budget_plan),
                        validator=None,
                        trace_stage=qa_stage,
                    )
                    qa = normalize_qa_report(qa, draft=draft, locked_cta=cta_line)
                    qa = augment_qa_report_from_validation_codes(
                        qa,
                        draft=draft,
                        locked_cta=cta_line,
                        validation_codes=validation_codes,
                    )
                    qa = augment_qa_report_from_draft_heuristics(
                        qa,
                        draft=draft,
                        locked_cta=cta_line,
                    )
                    self._annotate_qa_stage(
                        trace=trace,
                        stage_name=qa_stage,
                        preset_id=str(requested_id),
                        preset_contract=preset_contract,
                        budget_plan=budget_plan,
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
                        budget_plan=budget_plan,
                        stage_details={
                            "dominant_failing_rule": dominant_validation_code(validation_codes)
                            or self._qa_primary_issue_code(qa),
                        },
                    )

                    rewrite_applied = False
                    if qa.get("pass_rewrite_needed") or validation_codes:
                        rewrite_applied = True
                        rewrite_context = self._build_rewrite_context(
                            draft=draft,
                            qa_report=qa,
                            cta_line=cta_line,
                        )
                        rewrite_patch = await self._run_stage(
                            trace=trace,
                            config=StageConfig(
                                stage=STAGES["E"],
                                max_tokens=800,
                                reasoning_effort=self.settings.openai_reasoning_low,
                                response_format=RF_EMAIL_REWRITE_PATCH,
                            ),
                            messages=stage_e.build_messages(
                                email_draft=draft,
                                qa_report=qa,
                                messaging_brief=messaging_brief,
                                message_atoms=atoms,
                                cta_final_line=cta_line,
                                rewrite_context=rewrite_context,
                                preset_contract=preset_contract,
                                budget_plan=budget_plan,
                                sliders=variant_sliders,
                            ),
                            postprocess=lambda payload, original=draft, atom_payload=atoms: self._sanitize_rewrite_patch_payload(
                                payload,
                                original_draft=original,
                                atoms=atom_payload,
                                cta_line=cta_line,
                            ),
                            validator=None,
                            trace_stage=rewrite_stage,
                        )
                        draft, rewrite_patch_details = self._reconstruct_draft_from_patch(
                            patch=rewrite_patch,
                            original_draft=draft,
                            cta_line=cta_line,
                        )
                        rewrite_pre_details = {
                            "pre_postprocess_word_count": preset_word_count(str(draft.get("body") or "").strip()),
                            "pre_postprocess_sentence_count": preset_sentence_count(str(draft.get("body") or "").strip()),
                            "pre_postprocess_cta_alignment_status": draft_cta_alignment_status(
                                body=draft.get("body"),
                                required_cta_line=cta_line,
                            ),
                        }
                        draft, rewrite_steps = self._mechanical_postprocess(
                            draft,
                            variant_sliders,
                            cta_line,
                            trace,
                            budget_plan=budget_plan,
                        )

                        final_codes = validate_email_draft(
                            draft,
                            brief=messaging_brief,
                            cta_final_line=cta_line,
                            sliders=variant_sliders,
                            message_atoms=atoms,
                            preset_contract=preset_contract,
                            budget_plan=budget_plan,
                        )
                        self._annotate_draft_stage(
                            trace=trace,
                            stage_name=rewrite_stage,
                            draft=draft,
                            validation_codes=final_codes,
                            mechanical_steps=rewrite_steps,
                            final_validation_status="failed" if final_codes else "passed",
                            preset_contract=preset_contract,
                            budget_plan=budget_plan,
                            stage_details={
                                **rewrite_pre_details,
                                **rewrite_patch_details,
                                "post_rewrite_word_count": preset_word_count(str(draft.get("body") or "").strip()),
                                "dominant_failing_rule": dominant_validation_code(final_codes),
                                "cta_alignment_status": draft_cta_alignment_status(body=draft.get("body"), required_cta_line=cta_line),
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
                                budget_plan=budget_plan,
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
                        message_atoms=atoms,
                        preset_contract=preset_contract,
                        budget_plan=budget_plan,
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
        *,
        budget_plan: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        _, max_words = _length_band(str(sliders.get("length") or "medium"))
        if isinstance((budget_plan or {}).get("allowed_max_words"), int):
            max_words = int((budget_plan or {}).get("allowed_max_words") or max_words)
        legacy = LegacyEmailDraft(subject=str(draft.get("subject") or ""), body=str(draft.get("body") or ""))
        normalized_cta = normalize_cta_text(cta_line)
        result = deterministic_postprocess_draft(
            legacy,
            max_words=max_words,
            cta_line=normalized_cta,
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
