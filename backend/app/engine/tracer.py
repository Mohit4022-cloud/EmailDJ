from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
from pathlib import Path
from typing import Any


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_json(value: Any) -> str:
    try:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except TypeError:
        payload = json.dumps(str(value), ensure_ascii=True)
    return _sha256(payload)


class Trace:
    def __init__(self, trace_id: str, app_env: str, *, debug_trace_raw: bool = False):
        self.trace_id = trace_id
        self.app_env = app_env
        self.debug_trace_raw = bool(debug_trace_raw)
        self.started_at = time.time()
        self._stage_started: dict[str, float] = {}
        self.stage_stats: list[dict[str, Any]] = []
        self.validation_errors: list[dict[str, Any]] = []
        self.postprocess_steps: list[str] = []
        self.hashes: dict[str, str] = {}
        self.meta: dict[str, Any] = {}
        self.raw_stage_payloads: list[dict[str, Any]] = []

    def start_stage(self, *, stage: str, model: str) -> None:
        self._stage_started[stage] = time.perf_counter()
        self.stage_stats.append(
            {
                "stage": stage,
                "status": "started",
                "model": model,
                "elapsed_ms": 0,
                "schema_ok": False,
                "attempt_count": 0,
            }
        )

    def end_stage(
        self,
        *,
        stage: str,
        model: str,
        schema_ok: bool,
        output: Any,
        attempt_count: int,
        details: dict[str, Any] | None = None,
    ) -> int:
        started = self._stage_started.get(stage, time.perf_counter())
        elapsed_ms = int(round((time.perf_counter() - started) * 1000))
        self.stage_stats.append(
            {
                "stage": stage,
                "status": "complete",
                "model": model,
                "elapsed_ms": elapsed_ms,
                "schema_ok": bool(schema_ok),
                "attempt_count": int(attempt_count),
                **(details or {}),
            }
        )
        self.hashes[f"output:{stage}"] = hash_json(output)
        if self.debug_trace_raw:
            self.raw_stage_payloads.append(
                {
                    "stage": stage,
                    "status": "complete",
                    "attempt_count": int(attempt_count),
                    "schema_ok": bool(schema_ok),
                    "output": output,
                }
            )
        return elapsed_ms

    def fail_stage(self, *, stage: str, model: str, error_code: str, details: dict[str, Any] | None = None) -> int:
        return self.fail_stage_with_artifact(
            stage=stage,
            model=model,
            error_code=error_code,
            details=details,
            artifact_status=None,
            output=None,
            raw_output=None,
            attempt_count=None,
        )

    def fail_stage_with_artifact(
        self,
        *,
        stage: str,
        model: str,
        error_code: str,
        details: dict[str, Any] | None = None,
        artifact_status: str | None = None,
        output: Any = None,
        raw_output: str | None = None,
        attempt_count: int | None = None,
    ) -> int:
        started = self._stage_started.get(stage, time.perf_counter())
        elapsed_ms = int(round((time.perf_counter() - started) * 1000))
        stage_entry = {
            "stage": stage,
            "status": "failed",
            "model": model,
            "elapsed_ms": elapsed_ms,
            "error_code": error_code,
            "details": details or {},
        }
        if artifact_status:
            stage_entry["artifact_status"] = artifact_status
        if attempt_count is not None:
            stage_entry["attempt_count"] = int(attempt_count)
        self.stage_stats.append(
            stage_entry
        )
        if self.debug_trace_raw:
            raw_entry = {
                "stage": stage,
                "status": "failed",
                "error_code": error_code,
                "details": details or {},
            }
            if artifact_status:
                raw_entry["artifact_status"] = artifact_status
            if attempt_count is not None:
                raw_entry["attempt_count"] = int(attempt_count)
            if output is not None:
                raw_entry["output"] = output
            if raw_output:
                raw_entry["raw_output"] = raw_output
            self.raw_stage_payloads.append(raw_entry)
        return elapsed_ms

    def add_validation_error(self, *, stage: str, codes: list[str], details: dict[str, Any] | None = None) -> None:
        self.validation_errors.append(
            {
                "stage": stage,
                "codes": list(codes),
                "details": details or {},
            }
        )

    def add_postprocess_step(self, step: str) -> None:
        if step and step not in self.postprocess_steps:
            self.postprocess_steps.append(step)

    def put_hash(self, key: str, value: Any) -> None:
        self.hashes[key] = hash_json(value)

    def set_meta(self, **kwargs: Any) -> None:
        self.meta.update(kwargs)

    def payload(self, *, outcome: dict[str, Any]) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "app_env": self.app_env,
            "started_at": self.started_at,
            "finished_at": time.time(),
            "duration_ms": int(round((time.time() - self.started_at) * 1000)),
            "stage_stats": self.stage_stats,
            "validation_errors": self.validation_errors,
            "postprocess_steps": self.postprocess_steps,
            "hashes": self.hashes,
            "meta": self.meta,
            "outcome": outcome,
        }

    def finalize(self, *, outcome: dict[str, Any], write_debug: bool) -> dict[str, Any]:
        payload = self.payload(outcome=outcome)
        if write_debug:
            today = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
            root = Path(__file__).resolve().parents[2] / "debug_traces" / today
            root.mkdir(parents=True, exist_ok=True)
            path = root / f"{self.trace_id}.json"
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
            if self.debug_trace_raw and self.app_env in {"local", "dev"}:
                raw_root = root / "_raw"
                raw_root.mkdir(parents=True, exist_ok=True)
                raw_payload = {
                    "trace_id": self.trace_id,
                    "app_env": self.app_env,
                    "started_at": self.started_at,
                    "finished_at": payload.get("finished_at"),
                    "duration_ms": payload.get("duration_ms"),
                    "meta": self.meta,
                    "outcome": outcome,
                    "stage_payloads": self.raw_stage_payloads,
                }
                raw_path = raw_root / f"{self.trace_id}.json"
                raw_path.write_text(json.dumps(raw_payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return payload
