#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


STAGE_ORDER = [
    "CONTEXT_SYNTHESIS",
    "FIT_REASONING",
    "ANGLE_PICKER",
    "ONE_LINER_COMPRESSOR",
    "EMAIL_GENERATION",
    "EMAIL_QA",
    "EMAIL_REWRITE",
]

CTA_CODES = {
    "cta_not_final_line",
    "duplicate_cta_line",
}

COPY_QA_CODES = {
    "banned_phrase",
    "personalization_generic_opener",
    "personalization_missing_used_hook",
    "repetition_detected",
    "template_leakage_token",
    "too_many_sentences_for_preset",
    "ungrounded_personalization_claim",
    "word_count_out_of_band",
}

PROVIDER_MARKERS = (
    "openai unavailable",
    "openai_unavailable",
    "nodename nor servname",
    "timeout",
    "connection",
    "transport",
    "provider unavailable",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize an EmailDJ trace and classify the failure.")
    parser.add_argument("trace_path", help="Path to a summary or raw trace JSON file")
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected_dict_json:{path}")
    return data


def _load_summary_and_raw(trace_path: Path) -> tuple[Path | None, dict[str, Any] | None, Path | None, dict[str, Any] | None]:
    data = _load_json(trace_path)
    summary_path: Path | None = None
    summary_data: dict[str, Any] | None = None
    raw_path: Path | None = None
    raw_data: dict[str, Any] | None = None

    if isinstance(data.get("stage_payloads"), list):
        raw_path = trace_path
        raw_data = data
        if trace_path.parent.name == "_raw":
            candidate = trace_path.parent.parent / trace_path.name
            if candidate.exists():
                summary_path = candidate
                summary_data = _load_json(candidate)
    else:
        summary_path = trace_path
        summary_data = data
        candidate = trace_path.parent / "_raw" / trace_path.name
        if candidate.exists():
            raw_path = candidate
            raw_data = _load_json(candidate)

    return summary_path, summary_data, raw_path, raw_data


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _append_unique(items: list[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def _collect_stage_statuses(summary_data: dict[str, Any] | None, raw_data: dict[str, Any] | None) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for entry in _dict_items((summary_data or {}).get("stage_stats")):
        stage = str(entry.get("stage") or "").strip()
        status = str(entry.get("status") or "").strip()
        if stage and status:
            statuses[stage] = status
    for entry in _dict_items((raw_data or {}).get("stage_payloads")):
        stage = str(entry.get("stage") or "").strip()
        status = str(entry.get("status") or "").strip()
        if stage and status:
            statuses[stage] = status
    ordered: dict[str, str] = {}
    for stage in STAGE_ORDER:
        if stage in statuses:
            ordered[stage] = statuses[stage]
    for stage, status in statuses.items():
        if stage not in ordered:
            ordered[stage] = status
    return ordered


def _collect_error_codes(summary_data: dict[str, Any] | None, raw_data: dict[str, Any] | None) -> tuple[list[str], list[str], list[str]]:
    error_codes: list[str] = []
    validation_codes: list[str] = []
    artifact_statuses: list[str] = []

    outcome = (summary_data or {}).get("outcome")
    if isinstance(outcome, dict):
        _append_unique(error_codes, outcome.get("code"))

    for entry in _dict_items((summary_data or {}).get("stage_stats")):
        _append_unique(error_codes, entry.get("error_code"))
        _append_unique(artifact_statuses, entry.get("artifact_status"))
        details = entry.get("details")
        if isinstance(details, dict):
            _append_unique(artifact_statuses, details.get("artifact_status"))
            for code in details.get("codes") or []:
                _append_unique(validation_codes, code)

    for entry in _dict_items((summary_data or {}).get("validation_errors")):
        for code in entry.get("codes") or []:
            _append_unique(validation_codes, code)

    for entry in _dict_items((raw_data or {}).get("stage_payloads")):
        _append_unique(error_codes, entry.get("error_code"))
        _append_unique(artifact_statuses, entry.get("artifact_status"))
        details = entry.get("details")
        if isinstance(details, dict):
            _append_unique(artifact_statuses, details.get("artifact_status"))
            for code in details.get("codes") or []:
                _append_unique(validation_codes, code)

    for code in validation_codes:
        _append_unique(error_codes, code)

    return error_codes, validation_codes, artifact_statuses


def _collect_text_fragments(summary_data: dict[str, Any] | None, raw_data: dict[str, Any] | None) -> list[str]:
    fragments: list[str] = []
    outcome = (summary_data or {}).get("outcome")
    if isinstance(outcome, dict):
        _append_unique(fragments, outcome.get("message"))

    for entry in _dict_items((summary_data or {}).get("stage_stats")):
        details = entry.get("details")
        if isinstance(details, dict):
            _append_unique(fragments, details.get("error"))
            _append_unique(fragments, details.get("first_error"))

    for entry in _dict_items((raw_data or {}).get("stage_payloads")):
        details = entry.get("details")
        if isinstance(details, dict):
            _append_unique(fragments, details.get("error"))
            _append_unique(fragments, details.get("first_error"))

    return fragments


def _failed_stage(summary_data: dict[str, Any] | None, raw_data: dict[str, Any] | None) -> str | None:
    outcome = (summary_data or {}).get("outcome")
    if isinstance(outcome, dict):
        stage = str(outcome.get("stage") or "").strip()
        if stage:
            return stage

    for entry in _dict_items((summary_data or {}).get("stage_stats")):
        if str(entry.get("status") or "").strip() == "failed":
            stage = str(entry.get("stage") or "").strip()
            if stage:
                return stage

    for entry in _dict_items((raw_data or {}).get("stage_payloads")):
        if str(entry.get("status") or "").strip() == "failed":
            stage = str(entry.get("stage") or "").strip()
            if stage:
                return stage

    return None


def _classify(
    *,
    error_codes: list[str],
    validation_codes: list[str],
    artifact_statuses: list[str],
    text_fragments: list[str],
) -> str:
    codes_lower = {code.lower() for code in error_codes}
    validation_lower = {code.lower() for code in validation_codes}
    haystack = " ".join(text_fragments).lower()

    if "openai_unavailable" in codes_lower or any(marker in haystack for marker in PROVIDER_MARKERS):
        return "transport_or_provider"
    if "fallback" in haystack or "deterministic_fallback_disabled" in haystack:
        return "fallback_leakage"
    if validation_lower & CTA_CODES or ("cta" in haystack and ("final line" in haystack or "exact" in haystack)):
        return "cta_drift"
    if validation_lower & COPY_QA_CODES or "template leakage" in haystack:
        return "repetition_or_copy_qa"
    if validation_codes:
        return "validator_failure"
    if any("artifact_missing" in status.lower() for status in artifact_statuses):
        return "missing_artifact"
    if any("json" in code or "schema" in code for code in codes_lower) or "json" in haystack or "schema" in haystack:
        return "schema_contract"
    if error_codes:
        return "schema_contract"
    return "unknown"


def _explanation(
    *,
    failed_stage: str | None,
    classification: str,
    error_codes: list[str],
    validation_codes: list[str],
    text_fragments: list[str],
) -> str:
    stage_text = failed_stage or "unknown_stage"
    code_text = ", ".join(error_codes[:4]) if error_codes else "no_codes"
    validation_text = ", ".join(validation_codes[:4]) if validation_codes else "no_validator_codes"
    detail = next((text for text in text_fragments if text), "no_additional_error_text")
    return (
        f"{stage_text} classified as {classification}; "
        f"codes={code_text}; validator_codes={validation_text}; detail={detail}"
    )


def main() -> None:
    args = _parse_args()
    input_path = Path(args.trace_path).resolve()
    summary_path, summary_data, raw_path, raw_data = _load_summary_and_raw(input_path)

    trace_id = (
        str((summary_data or {}).get("trace_id") or "")
        or str((raw_data or {}).get("trace_id") or "")
        or input_path.stem
    )
    stage_statuses = _collect_stage_statuses(summary_data, raw_data)
    error_codes, validation_codes, artifact_statuses = _collect_error_codes(summary_data, raw_data)
    text_fragments = _collect_text_fragments(summary_data, raw_data)
    failed_stage = _failed_stage(summary_data, raw_data)
    classification = _classify(
        error_codes=error_codes,
        validation_codes=validation_codes,
        artifact_statuses=artifact_statuses,
        text_fragments=text_fragments,
    )

    outcome_code = None
    outcome = (summary_data or {}).get("outcome")
    if isinstance(outcome, dict):
        outcome_code = str(outcome.get("code") or "").strip() or None

    payload = {
        "trace_id": trace_id,
        "summary_path": str(summary_path) if summary_path else None,
        "raw_path": str(raw_path) if raw_path else None,
        "failed_stage": failed_stage,
        "outcome_code": outcome_code,
        "stage_statuses": stage_statuses,
        "error_codes": error_codes,
        "artifact_statuses": artifact_statuses,
        "classification": classification,
        "explanation": _explanation(
            failed_stage=failed_stage,
            classification=classification,
            error_codes=error_codes,
            validation_codes=validation_codes,
            text_fragments=text_fragments,
        ),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
