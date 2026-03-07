from __future__ import annotations

from email_generation.policies.cta_policy import resolve_cta_lock


def test_resolve_cta_lock_bans_either_or_for_straight_shooter():
    cta = resolve_cta_lock(
        existing_lock=None,
        cta_type="time_ask",
        risk_surface="Trademark Search, Screening, and Brand Protection",
        directness=70,
        preset_id="straight_shooter",
        prospect_title="Head of Brand Risk",
    )

    assert "Worth a look / Not a priority?" not in cta


def test_resolve_cta_lock_bans_either_or_for_exec_titles():
    cta = resolve_cta_lock(
        existing_lock=None,
        cta_type="time_ask",
        risk_surface="Trademark Search, Screening, and Brand Protection",
        directness=70,
        preset_id="challenger",
        prospect_title="CEO",
    )

    assert "Worth a look / Not a priority?" not in cta


def test_resolve_cta_lock_keeps_either_or_for_allowed_non_exec_presets():
    cta = resolve_cta_lock(
        existing_lock=None,
        cta_type="time_ask",
        risk_surface="Trademark Search, Screening, and Brand Protection",
        directness=70,
        preset_id="challenger",
        prospect_title="Head of Brand Risk",
    )

    assert "Worth a look / Not a priority?" in cta
