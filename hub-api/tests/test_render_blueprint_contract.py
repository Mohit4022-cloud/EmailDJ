from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "check_render_blueprint.py"
BLUEPRINT_PATH = ROOT / "render.yaml"

spec = importlib.util.spec_from_file_location("check_render_blueprint", SCRIPT_PATH)
check_render_blueprint = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = check_render_blueprint
spec.loader.exec_module(check_render_blueprint)


def _current_blueprint() -> str:
    return BLUEPRINT_PATH.read_text(encoding="utf-8")


def test_render_blueprint_contract_current_file_passes():
    assert check_render_blueprint.validate_blueprint_path(BLUEPRINT_PATH) == []


def test_render_blueprint_contract_rejects_dev_beta_key():
    text = _current_blueprint().replace("sync: false", "value: dev-beta-key", 1)

    failures = check_render_blueprint.validate_blueprint_text(text)

    assert any("dev-beta-key" in failure for failure in failures)
    assert any("must not hardcode a value" in failure for failure in failures)


def test_render_blueprint_contract_requires_managed_database_reference():
    text = _current_blueprint().replace("name: emaildj-postgres", "name: local-postgres", 1)

    failures = check_render_blueprint.validate_blueprint_text(text)

    assert "`DATABASE_URL` must reference `emaildj-postgres`" in failures


def test_render_blueprint_contract_requires_launch_defaults():
    text = _current_blueprint().replace('value: "0"', 'value: "1"', 1)

    failures = check_render_blueprint.validate_blueprint_text(text)

    assert "`USE_PROVIDER_STUB` must be `0`, found `1`" in failures
