import os

import pytest


def test_middleware_present_for_generate_pipeline():
    pytest.importorskip('fastapi')
    os.environ.setdefault('CHROME_EXTENSION_ORIGIN', 'chrome-extension://dev')
    from main import app

    names = [mw.cls.__name__ for mw in app.user_middleware]
    assert 'PiiRedactionMiddleware' in names
    assert 'CostGuardMiddleware' in names
