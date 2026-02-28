"""Generate openapi.json from FastAPI runtime."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")

from main import app  # noqa: E402


if __name__ == "__main__":
    out = ROOT / "openapi.json"
    out.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
    print(f"wrote {out}")
