"""Fail-fast smoke: real mode without provider credentials must fail clearly."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
os.environ["EMAILDJ_QUICK_GENERATE_MODE"] = "real"
os.environ.setdefault("EMAILDJ_REAL_PROVIDER", "openai")
os.environ["EMAILDJ_PRESET_PREVIEW_PIPELINE"] = "off"

provider = os.environ.get("EMAILDJ_REAL_PROVIDER", "openai").strip().lower() or "openai"
provider_key_env = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
}
required_key = provider_key_env.get(provider, "OPENAI_API_KEY")

for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"):
    os.environ.pop(key, None)

from main import _validate_env

try:
    _validate_env()
except RuntimeError as exc:
    message = str(exc)
    expected = f"requires {required_key}"
    if expected not in message:
        raise AssertionError(
            f"Expected fail-fast error containing '{expected}', got: {message}"
        ) from exc
    print(f"real mode fail-fast smoke passed ({expected})")
    raise SystemExit(0)

raise AssertionError("Expected _validate_env() to fail in real mode without provider key.")

