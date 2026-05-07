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

echo "[1/12] python compile"
python3 -m py_compile $(find "$ROOT" -name '*.py' -type f)

echo "[2/12] pytest"
python3 "$ROOT/scripts/run_backend_suite.py"

echo "[3/12] generate openapi"
python3 "$ROOT/scripts/generate_openapi.py"

echo "[4/12] extension js syntax"
for f in $(find "$ROOT/../chrome-extension/src" -name '*.js' -type f); do
  node --check "$f"
done

echo "[5/12] extension build"
(cd "$ROOT/../chrome-extension" && npm run build)

echo "[6/12] mock e2e smoke"
python3 "$ROOT/scripts/mock_e2e_smoke.py"

echo "[7/12] lock compliance eval smoke"
"$ROOT/scripts/eval:smoke"

echo "[8/12] preview/generate parity gate"
"$ROOT/scripts/eval:parity"

echo "[9/12] adversarial eval suite (mock)"
"$ROOT/scripts/eval:adversarial"

echo "[10/12] full eval suite (mock)"
"$ROOT/scripts/eval:full"

if [ "${EMAILDJ_RUN_JUDGE_SMOKE:-0}" = "1" ]; then
  echo "[11/14] judge smoke (5-case)"
  "$ROOT/scripts/eval:judge:smoke"
  echo "[12/14] judge sanity sentinel suite"
  "$ROOT/scripts/eval:judge:sanity"
  STEP_REAL_FAILFAST="[13/14]"
  STEP_REAL_SMOKE="[14/14]"
else
  STEP_REAL_FAILFAST="[11/12]"
  STEP_REAL_SMOKE="[12/12]"
fi

echo "${STEP_REAL_FAILFAST} real mode fail-fast smoke (missing creds must fail)"
python3 "$ROOT/scripts/real_mode_failfast_smoke.py"

if [ "${EMAILDJ_RUN_REAL_MODE_SMOKE:-0}" = "1" ]; then
  echo "${STEP_REAL_SMOKE} real mode smoke"
  python3 "$ROOT/scripts/real_mode_smoke.py"
  PROVIDER_GREEN="green"
else
  echo "${STEP_REAL_SMOKE} real mode smoke (skipped; set EMAILDJ_RUN_REAL_MODE_SMOKE=1 to enable)"
  PROVIDER_GREEN="not_run"
fi

echo "launch check"
python3 "$ROOT/scripts/launch_check.py" --from-artifacts --allow-not-ready
echo "launch completion audit"
python3 "$ROOT/scripts/launch_audit.py"
echo "launch operator handoff"
python3 "$ROOT/scripts/launch_handoff.py"
echo "all checks passed"
