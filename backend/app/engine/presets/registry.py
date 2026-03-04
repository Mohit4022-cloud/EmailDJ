from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "preset_id",
    "name",
    "tone_descriptor",
    "style_rules",
    "structure_rules",
    "banned_phrases_additions",
    "formatting_hints",
}

FORBIDDEN_TOKENS = {
    "palantir",
    "corsearch",
    "acme",
    "[name]",
    "[company]",
    "[my name]",
}


class PresetError(ValueError):
    pass


def _preset_dir() -> Path:
    return Path(__file__).resolve().parent


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PresetError(f"invalid_preset_json:{path.name}:{exc}") from exc
    if not isinstance(data, dict):
        raise PresetError(f"invalid_preset_shape:{path.name}")
    return data


def _validate_preset(data: dict[str, Any], source: str) -> None:
    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        raise PresetError(f"preset_missing_fields:{source}:{sorted(missing)}")

    for key in ("style_rules", "structure_rules", "banned_phrases_additions"):
        value = data.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
            raise PresetError(f"preset_invalid_list:{source}:{key}")

    corpus = "\n".join(
        [
            str(data.get("tone_descriptor", "")),
            str(data.get("formatting_hints", "")),
            *[str(item) for item in data.get("style_rules", [])],
            *[str(item) for item in data.get("structure_rules", [])],
        ]
    ).lower()
    for token in FORBIDDEN_TOKENS:
        if token in corpus:
            raise PresetError(f"preset_forbidden_token:{source}:{token}")


def load_all_presets() -> dict[str, dict[str, Any]]:
    presets: dict[str, dict[str, Any]] = {}
    for path in sorted(_preset_dir().glob("*.json")):
        data = _load_json(path)
        _validate_preset(data, path.name)
        preset_id = str(data.get("preset_id") or "").strip()
        if not preset_id:
            raise PresetError(f"preset_missing_id:{path.name}")
        presets[preset_id] = data

    base = presets.get("base")
    if base:
        merged: dict[str, dict[str, Any]] = {}
        for preset_id, item in presets.items():
            if preset_id == "base":
                continue
            merged[preset_id] = {
                **base,
                **item,
                "style_rules": [*base.get("style_rules", []), *item.get("style_rules", [])],
                "structure_rules": [*base.get("structure_rules", []), *item.get("structure_rules", [])],
                "banned_phrases_additions": [
                    *base.get("banned_phrases_additions", []),
                    *item.get("banned_phrases_additions", []),
                ],
            }
        presets = merged
    else:
        presets = {k: v for k, v in presets.items() if k != "base"}

    if not presets:
        raise PresetError("preset_registry_empty")
    return presets


def load_preset(preset_id: str) -> dict[str, Any]:
    presets = load_all_presets()
    key = str(preset_id or "").strip()
    if key and key in presets:
        return presets[key]
    if "direct" in presets:
        return presets["direct"]
    # deterministic fallback to first preset definition (style only, not copy)
    first_key = sorted(presets.keys())[0]
    return presets[first_key]
