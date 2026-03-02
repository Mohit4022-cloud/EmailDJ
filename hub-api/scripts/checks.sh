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

echo "[1/11] python compile"
python3 -m py_compile $(find "$ROOT" -name '*.py' -type f)

echo "[2/11] pytest"
pytest -q "$ROOT/tests"

echo "[3/11] generate openapi"
python3 "$ROOT/scripts/generate_openapi.py"

echo "[4/11] extension js syntax"
for f in $(find "$ROOT/../chrome-extension/src" -name '*.js' -type f); do
  node --check "$f"
done

echo "[5/11] extension build"
(cd "$ROOT/../chrome-extension" && npm run build)

echo "[6/11] mock e2e smoke"
python3 "$ROOT/scripts/mock_e2e_smoke.py"

echo "[7/11] lock compliance eval smoke"
"$ROOT/scripts/eval:smoke"

echo "[8/11] preview/generate parity gate"
"$ROOT/scripts/eval:parity"

echo "[9/11] adversarial eval suite (mock)"
"$ROOT/scripts/eval:adversarial"

if [ "${EMAILDJ_RUN_JUDGE_SMOKE:-0}" = "1" ]; then
  echo "[10/12] judge smoke (5-case)"
  "$ROOT/scripts/eval:judge:smoke"
  STEP_REAL_FAILFAST="[11/12]"
  STEP_REAL_SMOKE="[12/12]"
else
  STEP_REAL_FAILFAST="[10/11]"
  STEP_REAL_SMOKE="[11/11]"
fi

echo "${STEP_REAL_FAILFAST} real mode fail-fast smoke (missing creds must fail)"
python3 "$ROOT/scripts/real_mode_failfast_smoke.py"

if [ "${EMAILDJ_RUN_REAL_MODE_SMOKE:-0}" = "1" ]; then
  echo "${STEP_REAL_SMOKE} real mode smoke"
  python3 "$ROOT/scripts/real_mode_smoke.py"
else
  echo "${STEP_REAL_SMOKE} real mode smoke (skipped; set EMAILDJ_RUN_REAL_MODE_SMOKE=1 to enable)"
fi

echo "all checks passed"
