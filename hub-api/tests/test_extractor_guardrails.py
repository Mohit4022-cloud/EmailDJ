import os

from context_vault import extractor
from context_vault.models import AccountContext


def test_enrichment_min_confidence_invalid_values_fallback(monkeypatch):
    monkeypatch.setenv('EMAILDJ_EXTRACTOR_ENRICH_CONFIDENCE_MIN', 'abc')
    assert extractor._enrichment_min_confidence() == 0.75

    monkeypatch.setenv('EMAILDJ_EXTRACTOR_ENRICH_CONFIDENCE_MIN', '2.0')
    assert extractor._enrichment_min_confidence() == 0.75


def test_confidence_overlay_skips_low_confidence_fields(monkeypatch):
    monkeypatch.setenv('EMAILDJ_EXTRACTOR_ENRICH_CONFIDENCE_MIN', '0.9')

    base = AccountContext(account_id='a1', next_action='Follow up', timing='Q3 2026')
    enriched = AccountContext(account_id='a1', next_action='Send proposal', timing='in 2 months')
    confidence = {'next_action': 0.8, 'timing': 0.85}

    out = extractor._apply_confidence_overlay(base, enriched, confidence)
    assert out.next_action == 'Follow up'
    assert out.timing == 'Q3 2026'


def test_confidence_overlay_applies_high_confidence_fields(monkeypatch):
    monkeypatch.setenv('EMAILDJ_EXTRACTOR_ENRICH_CONFIDENCE_MIN', '0.75')

    base = AccountContext(account_id='a1', next_action='Follow up')
    enriched = AccountContext(account_id='a1', next_action='Send proposal')
    confidence = {'next_action': 0.9}

    out = extractor._apply_confidence_overlay(base, enriched, confidence)
    assert out.next_action == 'Send proposal'
