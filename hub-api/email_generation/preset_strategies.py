"""Preset strategy registry for deterministic email planning."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PresetStrategy:
    preset_id: str
    label: str
    hook_type: str
    cta_type: str
    structure_template: tuple[str, ...]
    narrative: str


PRESET_STRATEGIES: dict[str, PresetStrategy] = {
    "straight_shooter": PresetStrategy(
        preset_id="straight_shooter",
        label="Straight Shooter",
        hook_type="direct_wedge",
        cta_type="time_ask",
        structure_template=("problem", "outcome", "proof", "cta"),
        narrative="Direct wedge, evidence, then specific ask.",
    ),
    "headliner": PresetStrategy(
        preset_id="headliner",
        label="Headliner",
        hook_type="curiosity_headline",
        cta_type="time_ask",
        structure_template=("hook", "problem", "proof", "cta"),
        narrative="Curiosity-led opening and a single wedge angle.",
    ),
    "giver": PresetStrategy(
        preset_id="giver",
        label="Giver",
        hook_type="value_first",
        cta_type="value_asset",
        structure_template=("hook", "outcome", "proof", "cta"),
        narrative="Lead with a practical deliverable before the ask.",
    ),
    "challenger": PresetStrategy(
        preset_id="challenger",
        label="Challenger",
        hook_type="contrarian_risk",
        cta_type="pilot",
        structure_template=("problem", "hook", "outcome", "cta"),
        narrative="Reframe inaction cost with a contrarian point.",
    ),
    "industry_insider": PresetStrategy(
        preset_id="industry_insider",
        label="Industry Insider",
        hook_type="domain_pattern",
        cta_type="value_asset",
        structure_template=("hook", "problem", "proof", "cta"),
        narrative="Use domain vocabulary and observed patterns.",
    ),
    "c_suite_sniper": PresetStrategy(
        preset_id="c_suite_sniper",
        label="C-Suite Sniper",
        hook_type="executive_brief",
        cta_type="time_ask",
        structure_template=("outcome", "proof", "cta"),
        narrative="Three-sentence executive framing.",
    ),
}


_PRESET_ALIASES = {
    "1": "straight_shooter",
    "2": "headliner",
    "3": "giver",
    "4": "challenger",
    "5": "industry_insider",
    "6": "giver",
    "7": "industry_insider",
    "8": "c_suite_sniper",
    "9": "headliner",
    "10": "industry_insider",
    "the straight shooter": "straight_shooter",
    "the headliner": "headliner",
    "the giver": "giver",
    "the challenger": "challenger",
    "the industry insider": "industry_insider",
    "the c-suite sniper": "c_suite_sniper",
}


def normalize_preset_id(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return "straight_shooter"
    if raw in PRESET_STRATEGIES:
        return raw
    return _PRESET_ALIASES.get(raw, "straight_shooter")


def get_preset_strategy(value: str | None) -> PresetStrategy:
    preset_id = normalize_preset_id(value)
    return PRESET_STRATEGIES[preset_id]

