import json
import os
from pathlib import Path

import pytest


def test_openapi_contains_mvp_paths():
    spec = json.loads(Path('openapi.json').read_text())
    paths = spec['paths']
    assert '/generate/quick' in paths
    assert '/generate/stream/{request_id}' in paths
    assert '/vault/ingest' in paths
    assert '/vault/context/{prospect_id}' in paths


def test_quick_generate_schema_present():
    spec = json.loads(Path('openapi.json').read_text())
    schemas = spec['components']['schemas']
    assert 'QuickGenerateRequest' in schemas
    assert 'QuickGenerateAccepted' in schemas
    assert 'WebGenerateRequest' in schemas
    assert 'WebGenerateAccepted' in schemas
    assert 'WebRemixRequest' in schemas
    assert 'WebRemixAccepted' in schemas


def test_openapi_snapshot_matches_runtime_core_paths():
    fastapi = pytest.importorskip('fastapi')
    _ = fastapi  # silence lint
    os.environ.setdefault('CHROME_EXTENSION_ORIGIN', 'chrome-extension://dev')

    from main import app

    runtime = app.openapi()
    frozen = json.loads(Path('openapi.json').read_text())

    for path in [
        '/generate/quick',
        '/generate/stream/{request_id}',
        '/web/v1/generate',
        '/web/v1/remix',
        '/web/v1/stream/{request_id}',
        '/web/v1/feedback',
        '/vault/ingest',
        '/vault/context/{prospect_id}',
        '/assignments/poll',
    ]:
        assert path in runtime['paths']
        assert path in frozen['paths']
