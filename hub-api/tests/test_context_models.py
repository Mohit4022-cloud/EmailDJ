from datetime import datetime, timedelta, timezone

from context_vault.models import AccountContext, EmailDraft


def test_account_context_freshness_bands():
    now = datetime.now(timezone.utc)

    fresh = AccountContext(account_id='a1', last_enriched_at=now - timedelta(days=10))
    aging = AccountContext(account_id='a2', last_enriched_at=now - timedelta(days=45))
    stale = AccountContext(account_id='a3', last_enriched_at=now - timedelta(days=120))

    assert fresh.freshness == 'fresh'
    assert aging.freshness == 'aging'
    assert stale.freshness == 'stale'


def test_email_draft_field_bounds_are_enforced():
    draft = EmailDraft(
        draft_id='d1',
        account_id='a1',
        persona='CFO',
        sequence_position=2,
        model_tier=3,
        personalization_score=9,
    )
    assert draft.sequence_position == 2
    assert draft.model_tier == 3
    assert draft.personalization_score == 9
