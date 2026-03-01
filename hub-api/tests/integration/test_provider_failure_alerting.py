import os

import pytest


@pytest.mark.asyncio
async def test_provider_failure_threshold_alerting_with_suppression(monkeypatch):
    os.environ['REDIS_FORCE_INMEMORY'] = '1'
    os.environ['QUICK_PROVIDER_FAILURE_ALERT_THRESHOLD'] = '3'
    os.environ['QUICK_PROVIDER_FAILURE_ALERT_STEP'] = '5'
    os.environ['SLACK_WEBHOOK_URL'] = 'https://example.com/slack'
    os.environ['PROVIDER_FAILURE_METRICS_WEBHOOK_URL'] = 'https://example.com/metrics'
    os.environ['APP_ENV'] = 'test'

    from infra.redis_client import close_redis

    await close_redis()

    from email_generation.quick_generate import _record_provider_failure

    slack_events = []
    metrics_events = []

    async def fake_slack(payload):
        slack_events.append(payload)

    async def fake_metrics(payload):
        metrics_events.append(payload)

    monkeypatch.setattr('infra.alerting.send_slack_alert', fake_slack)
    monkeypatch.setattr('infra.alerting.send_metrics_event', fake_metrics)

    for _ in range(2):
        await _record_provider_failure(provider='openai', error='boom')
    assert len(slack_events) == 0
    assert len(metrics_events) == 0

    await _record_provider_failure(provider='openai', error='boom')
    assert len(slack_events) == 1
    assert len(metrics_events) == 1

    payload = slack_events[0]
    assert payload['event'] == 'quick_provider_failure_threshold_exceeded'
    assert payload['provider'] == 'openai'
    assert payload['failure_count'] == 3
    assert payload['threshold'] == 3
    assert payload['alert_step'] == 5
    assert payload['environment'] == 'test'
    assert payload['service'] == 'hub-api'
    assert payload['error_sample'] == 'boom'
    assert len(payload['date_utc']) == 8
    assert payload['timestamp_utc'].endswith('Z')

    for _ in range(4):
        await _record_provider_failure(provider='openai', error='boom')
    assert len(slack_events) == 1
    assert len(metrics_events) == 1

    await _record_provider_failure(provider='openai', error='boom')
    assert len(slack_events) == 2
    assert len(metrics_events) == 2
    assert slack_events[1]['failure_count'] == 8


@pytest.mark.asyncio
async def test_provider_failure_alert_sink_errors_do_not_bubble(monkeypatch):
    os.environ['REDIS_FORCE_INMEMORY'] = '1'
    os.environ['QUICK_PROVIDER_FAILURE_ALERT_THRESHOLD'] = '1'
    os.environ['QUICK_PROVIDER_FAILURE_ALERT_STEP'] = '5'
    os.environ['SLACK_WEBHOOK_URL'] = 'https://example.com/slack'
    os.environ['PROVIDER_FAILURE_METRICS_WEBHOOK_URL'] = 'https://example.com/metrics'
    os.environ['APP_ENV'] = 'test'

    from infra.redis_client import close_redis

    await close_redis()

    from email_generation.quick_generate import _record_provider_failure

    metrics_events = []

    async def failing_slack(_payload):
        raise RuntimeError('slack down')

    async def fake_metrics(payload):
        metrics_events.append(payload)

    monkeypatch.setattr('infra.alerting.send_slack_alert', failing_slack)
    monkeypatch.setattr('infra.alerting.send_metrics_event', fake_metrics)

    await _record_provider_failure(provider='openai', error='provider failed')
    assert len(metrics_events) == 1
    assert metrics_events[0]['failure_count'] == 1
