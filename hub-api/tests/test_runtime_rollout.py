from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))


def test_feature_rollout_respects_endpoint_and_percent(monkeypatch):
    import email_generation.runtime_policies as rp

    monkeypatch.setenv("FEATURE_SENTENCE_SAFE_TRUNCATION_GLOBAL", "1")
    monkeypatch.setenv("FEATURE_SENTENCE_SAFE_TRUNCATION_ENDPOINTS", "generate")
    monkeypatch.setenv("FEATURE_SENTENCE_SAFE_TRUNCATION_ROLLOUT_PERCENT", "0")

    with rp.rollout_context(endpoint="generate", bucket_key="session-1"):
        assert rp.feature_sentence_safe_truncation_enabled() is False

    monkeypatch.setenv("FEATURE_SENTENCE_SAFE_TRUNCATION_ROLLOUT_PERCENT", "100")
    with rp.rollout_context(endpoint="generate", bucket_key="session-1"):
        assert rp.feature_sentence_safe_truncation_enabled() is True
    with rp.rollout_context(endpoint="remix", bucket_key="session-1"):
        assert rp.feature_sentence_safe_truncation_enabled() is False


def test_shadow_mode_global_toggle(monkeypatch):
    import email_generation.runtime_policies as rp

    monkeypatch.setenv("FEATURE_SHADOW_MODE_GLOBAL", "1")
    monkeypatch.setenv("FEATURE_SHADOW_MODE_ROLLOUT_PERCENT", "100")
    with rp.rollout_context(endpoint="generate", bucket_key="session-1"):
        assert rp.feature_shadow_mode_enabled() is True


def test_dev_runtime_defaults_enable_p0_features(monkeypatch):
    import email_generation.runtime_policies as rp

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("USE_PROVIDER_STUB", "0")
    with rp.rollout_context(endpoint="generate", bucket_key="session-1"):
        flags = rp.feature_flags_effective()
    assert flags["FEATURE_STRUCTURED_OUTPUT"] is True
    assert flags["FEATURE_SENTENCE_SAFE_TRUNCATION"] is True
    assert flags["FEATURE_LOSSLESS_STREAMING"] is True
    assert flags["FEATURE_FLUENCY_REPAIR"] is True
    assert flags["FEATURE_PERSONA_ROUTER"] is True
    assert flags["FEATURE_NO_PROSPECT_OWNS_GUARDRAIL"] is True
    assert flags["FEATURE_PRESET_TRUE_REWRITE"] is True


def test_runtime_mode_requires_explicit_stub_for_mock(monkeypatch):
    import email_generation.runtime_policies as rp

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("USE_PROVIDER_STUB", raising=False)
    assert rp.resolve_runtime_policies().quick_generate_mode == "real"
    monkeypatch.setenv("USE_PROVIDER_STUB", "1")
    assert rp.resolve_runtime_policies().quick_generate_mode == "mock"
