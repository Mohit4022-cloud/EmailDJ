#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export REDIS_FORCE_INMEMORY=1

if ! command -v pytest >/dev/null 2>&1; then
  echo "pytest not found. Activate venv and install requirements first."
  exit 127
fi

if ! command -v node >/dev/null 2>&1; then
  echo "node not found. Install Node.js first."
  exit 127
fi

echo "[1/8] python compile"
python3 -m py_compile $(find "$ROOT" -name '*.py' -type f)

echo "[2/8] pytest"
pytest -q "$ROOT/tests"

echo "[3/8] generate openapi"
python3 "$ROOT/scripts/generate_openapi.py"

echo "[4/8] extension js syntax"
for f in $(find "$ROOT/../chrome-extension/src" -name '*.js' -type f); do
  node --check "$f"
done

echo "[5/8] extension build"
(cd "$ROOT/../chrome-extension" && npm run build)

echo "[6/8] mock e2e smoke"
python3 "$ROOT/scripts/mock_e2e_smoke.py"

echo "[7/8] lock compliance eval smoke"
"$ROOT/scripts/eval:smoke"

echo "[8/8] real mode smoke"
python3 "$ROOT/scripts/real_mode_smoke.py"

echo "all checks passed"
