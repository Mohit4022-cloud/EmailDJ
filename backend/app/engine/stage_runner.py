from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from app.openai_client import ENFORCED_OPENAI_MODEL, OpenAIClient


@dataclass(slots=True)
class StageConfig:
    stage: str
    max_tokens: int
    reasoning_effort: str
    response_format: dict[str, Any]


@dataclass(slots=True)
class StageRunResult:
    payload: dict[str, Any]
    attempts: int
    usage: dict[str, Any]


class StageError(RuntimeError):
    def __init__(self, *, stage: str, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.stage = stage
        self.code = code
        self.message = message
        self.details = details or {}


def _extract_message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text") or ""))
        content = "".join(text_parts)
    return str(content or "").strip()


def _parse_message_content(text: str) -> dict[str, Any]:
    if not text:
        return {}
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        fenced = text.strip().strip("`")
        out = json.loads(fenced)
    if not isinstance(out, dict):
        raise ValueError("json_root_not_object")
    return out


def _resolve_ref(root_schema: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported_schema_ref:{ref}")
    target: Any = root_schema
    for part in ref[2:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(target, dict) or key not in target:
            raise ValueError(f"unresolved_schema_ref:{ref}")
        target = target[key]
    if not isinstance(target, dict):
        raise ValueError(f"schema_ref_not_object:{ref}")
    return target


def _append_error(errors: list[str], path: list[str], message: str) -> None:
    path_str = ".".join(path) if path else "$"
    errors.append(f"{path_str}:{message}")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_schema_node(
    value: Any,
    schema: dict[str, Any],
    *,
    root_schema: dict[str, Any],
    path: list[str],
    errors: list[str],
) -> None:
    if "$ref" in schema:
        ref_schema = _resolve_ref(root_schema, str(schema["$ref"]))
        _validate_schema_node(value, ref_schema, root_schema=root_schema, path=path, errors=errors)
        return

    if "oneOf" in schema:
        candidates = list(schema.get("oneOf") or [])
        pass_count = 0
        for item in candidates:
            local_errors: list[str] = []
            if isinstance(item, dict):
                _validate_schema_node(value, item, root_schema=root_schema, path=path, errors=local_errors)
            else:
                local_errors.append("invalid_oneof_schema")
            if not local_errors:
                pass_count += 1
        if pass_count != 1:
            _append_error(errors, path, "oneOf_mismatch")
        return

    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, dict):
            _append_error(errors, path, "type_mismatch_expected_object")
            return
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        additional = schema.get("additionalProperties", True)

        for key in required:
            if isinstance(key, str) and key not in value:
                _append_error(errors, [*path, key], "required_missing")

        if additional is False:
            for key in value:
                if key not in properties:
                    _append_error(errors, [*path, str(key)], "additional_property_not_allowed")

        for key, prop_schema in properties.items():
            if key in value and isinstance(prop_schema, dict):
                _validate_schema_node(value[key], prop_schema, root_schema=root_schema, path=[*path, str(key)], errors=errors)
        return

    if expected_type == "array":
        if not isinstance(value, list):
            _append_error(errors, path, "type_mismatch_expected_array")
            return
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if isinstance(min_items, int) and len(value) < min_items:
            _append_error(errors, path, f"min_items:{len(value)}<{min_items}")
        if isinstance(max_items, int) and len(value) > max_items:
            _append_error(errors, path, f"max_items:{len(value)}>{max_items}")
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for idx, item in enumerate(value):
                _validate_schema_node(item, items_schema, root_schema=root_schema, path=[*path, str(idx)], errors=errors)
        return

    if expected_type == "string":
        if not isinstance(value, str):
            _append_error(errors, path, "type_mismatch_expected_string")
            return
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        if isinstance(min_length, int) and len(value) < min_length:
            _append_error(errors, path, f"min_length:{len(value)}<{min_length}")
        if isinstance(max_length, int) and len(value) > max_length:
            _append_error(errors, path, f"max_length:{len(value)}>{max_length}")
    elif expected_type == "number":
        if not _is_number(value):
            _append_error(errors, path, "type_mismatch_expected_number")
            return
    elif expected_type == "integer":
        if not _is_integer(value):
            _append_error(errors, path, "type_mismatch_expected_integer")
            return
    elif expected_type == "boolean":
        if not isinstance(value, bool):
            _append_error(errors, path, "type_mismatch_expected_boolean")
            return
    elif expected_type == "null":
        if value is not None:
            _append_error(errors, path, "type_mismatch_expected_null")
            return

    if "enum" in schema:
        allowed = list(schema.get("enum") or [])
        if value not in allowed:
            _append_error(errors, path, "enum_mismatch")

    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if minimum is not None:
        if not _is_number(value):
            _append_error(errors, path, "minimum_with_non_number")
        elif float(value) < float(minimum):
            _append_error(errors, path, f"minimum_violation:{value}<{minimum}")
    if maximum is not None:
        if not _is_number(value):
            _append_error(errors, path, "maximum_with_non_number")
        elif float(value) > float(maximum):
            _append_error(errors, path, f"maximum_violation:{value}>{maximum}")


def _validate_schema(payload: dict[str, Any], response_format: dict[str, Any]) -> None:
    schema_payload = response_format.get("json_schema", {}).get("schema", response_format)
    if not isinstance(schema_payload, dict):
        raise ValueError("schema_payload_invalid")
    errors: list[str] = []
    _validate_schema_node(payload, schema_payload, root_schema=schema_payload, path=[], errors=errors)
    if errors:
        joined = "; ".join(errors[:8])
        raise ValueError(f"schema_validation_failed:{joined}")


def _repair_messages(raw_output: str, schema: dict[str, Any], error_text: str) -> list[dict[str, str]]:
    schema_payload = schema.get("json_schema", {}).get("schema", schema)
    return [
        {
            "role": "system",
            "content": "Return only valid JSON that matches the provided schema exactly. Output JSON only.",
        },
        {
            "role": "user",
            "content": (
                "The following JSON is invalid or missing required fields.\n"
                f"Fix it to match the schema and return only the corrected JSON: {raw_output}\n"
                f"Validation error: {error_text}\n"
                f"Schema:\n{json.dumps(schema_payload, ensure_ascii=True)}\n"
            ),
        },
    ]


async def run_stage(
    *,
    openai: OpenAIClient,
    config: StageConfig,
    messages: list[dict[str, str]],
    validator: Callable[[dict[str, Any]], None] | None = None,
    timeout_seconds: float = 25.0,
) -> StageRunResult:
    attempts = 0
    usage: dict[str, Any] = {}
    last_raw = ""
    first_raw = ""
    repair_raw = ""
    first_payload: dict[str, Any] | None = None
    repair_payload: dict[str, Any] | None = None
    last_error = ""
    first_error = ""
    first_validation_codes: list[str] = []
    first_validation_details: list[dict[str, Any]] = []

    async def _call(request_messages: list[dict[str, str]]) -> tuple[str, dict[str, Any]]:
        response = await openai.chat_completion(
            model=ENFORCED_OPENAI_MODEL,
            messages=request_messages,
            reasoning_effort=config.reasoning_effort,
            max_completion_tokens=config.max_tokens,
            response_format=config.response_format,
            timeout_seconds=timeout_seconds,
        )
        message = dict(response.get("message") or {})
        text = _extract_message_text(message)
        return text, dict(response.get("usage") or {})

    for is_repair in (False, True):
        try:
            attempts += 1
            call_messages = messages if not is_repair else _repair_messages(last_raw, config.response_format, last_error)
            raw_text, usage_payload = await _call(call_messages)
            usage = usage_payload or usage
            last_raw = raw_text
            if is_repair:
                repair_raw = raw_text
            else:
                first_raw = raw_text
            payload = _parse_message_content(raw_text)
            if is_repair:
                repair_payload = payload
            else:
                first_payload = payload
            _validate_schema(payload, config.response_format)
            if validator is not None:
                validator(payload)
            return StageRunResult(payload=payload, attempts=attempts, usage=usage)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            validation_codes = list(getattr(exc, "codes", []) or [])
            validation_details = list(getattr(exc, "details", []) or [])
            if not is_repair:
                first_error = last_error
                if validation_codes:
                    first_validation_codes = validation_codes
                if validation_details:
                    first_validation_details = validation_details
                if not last_raw:
                    last_raw = str(exc)
                if not first_raw:
                    first_raw = last_raw
                continue
            artifact_status = "failed_artifact_present" if (first_payload or repair_payload or first_raw or repair_raw) else "artifact_missing"
            error_details: dict[str, Any] = {
                "error": str(exc),
                "first_error": first_error,
                "attempt_count": attempts,
                "artifact_status": artifact_status,
            }
            if first_raw:
                error_details["first_raw"] = first_raw
            if repair_raw:
                error_details["repair_raw"] = repair_raw
            if first_payload is not None:
                error_details["first_payload"] = first_payload
            if repair_payload is not None:
                error_details["repair_payload"] = repair_payload
            if first_validation_codes:
                error_details["codes"] = first_validation_codes
            if first_validation_details:
                error_details["validation_details"] = first_validation_details
                error_details["rejected_facts"] = first_validation_details
            if validation_codes and validation_codes != first_validation_codes:
                error_details["repair_codes"] = validation_codes
            if validation_details and validation_details != first_validation_details:
                error_details["repair_validation_details"] = validation_details
                error_details["repair_rejected_facts"] = validation_details
            raise StageError(
                stage=config.stage,
                code="STAGE_JSON_OR_VALIDATION_FAILED",
                message=f"{config.stage} failed after repair attempt",
                details=error_details,
            ) from exc

    raise StageError(
        stage=config.stage,
        code="STAGE_UNKNOWN_FAILURE",
        message=f"{config.stage} failed",
        details={},
    )
