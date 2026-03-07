from __future__ import annotations

from email_generation.model_defaults import openai_reasoning_effort, openai_supports_temperature_override


def test_openai_temperature_override_supported_for_legacy_models():
    assert openai_supports_temperature_override("gpt-4.1-nano") is True
    assert openai_supports_temperature_override("gpt-4o") is True


def test_openai_temperature_override_disabled_for_gpt5_models():
    assert openai_supports_temperature_override("gpt-5-nano") is False
    assert openai_supports_temperature_override("gpt-5") is False
    assert openai_supports_temperature_override("gpt-5-nano-2025-08-07") is False


def test_openai_temperature_override_defaults_to_supported_for_unknown_or_empty_model():
    assert openai_supports_temperature_override("") is True
    assert openai_supports_temperature_override(None) is True
    assert openai_supports_temperature_override("custom-openai-model") is True


def test_openai_reasoning_effort_defaults_to_high_for_extraction():
    assert openai_reasoning_effort(raw_env_vars={}, model_name="gpt-5-nano", transform_type="extraction") == "high"
    assert openai_reasoning_effort(raw_env_vars={}, model_name="gpt-4.1-mini", transform_type="enrichment") == "high"


def test_openai_reasoning_effort_defaults_to_low_for_drafting_rendering_and_rewrite():
    assert openai_reasoning_effort(raw_env_vars={}, model_name="gpt-5-nano", transform_type="drafting") == "low"
    assert openai_reasoning_effort(raw_env_vars={}, model_name="gpt-5-nano", transform_type="rendering") == "low"
    assert openai_reasoning_effort(raw_env_vars={}, model_name="gpt-5-nano", transform_type="rewrite") == "low"


def test_openai_reasoning_effort_env_override_wins_globally():
    env = {"EMAILDJ_OPENAI_REASONING_EFFORT": "high"}
    assert openai_reasoning_effort(raw_env_vars=env, model_name="gpt-5-nano", transform_type="drafting") == "high"
    assert openai_reasoning_effort(raw_env_vars=env, model_name="gpt-5-nano", transform_type="extraction") == "high"


def test_openai_reasoning_effort_scoped_env_overrides_by_transform_bucket():
    env = {
        "EMAILDJ_OPENAI_REASONING_EFFORT_ENRICHMENT": "medium",
        "EMAILDJ_OPENAI_REASONING_EFFORT_DRAFT": "minimal",
    }
    assert openai_reasoning_effort(raw_env_vars=env, transform_type="extraction") == "medium"
    assert openai_reasoning_effort(raw_env_vars=env, transform_type="enrichment") == "medium"
    assert openai_reasoning_effort(raw_env_vars=env, transform_type="drafting") == "minimal"
    assert openai_reasoning_effort(raw_env_vars=env, transform_type="rendering") == "minimal"


def test_openai_reasoning_effort_unknown_transform_defaults_to_enrichment_bucket():
    assert openai_reasoning_effort(raw_env_vars={}, transform_type="unknown") == "high"
    assert openai_reasoning_effort(raw_env_vars={}, transform_type=None) == "high"
