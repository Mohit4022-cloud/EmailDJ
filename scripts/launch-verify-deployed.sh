#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HUB_API_ROOT="$ROOT/hub-api"
REAL_SMOKE_CASES="${EMAILDJ_LAUNCH_REAL_SMOKE_CASES:-10}"
DEPLOYED_SMOKE_MODE="${EMAILDJ_DEPLOYED_SMOKE_MODE:-smoke}"
DEPLOYED_SMOKE_FLOW="${EMAILDJ_DEPLOYED_SMOKE_FLOW:-generate}"
DEPLOYED_SMOKE_OUT="${EMAILDJ_DEPLOYED_SMOKE_OUT:-debug_runs/smoke/deployed-staging}"
DEPLOYED_SMOKE_CONCURRENCY="${EMAILDJ_DEPLOYED_SMOKE_CONCURRENCY:-3}"
DEPLOYED_SMOKE_TIMEOUT="${EMAILDJ_DEPLOYED_SMOKE_TIMEOUT:-60}"
DEPLOYED_SMOKE_MAX_RETRIES="${EMAILDJ_DEPLOYED_SMOKE_MAX_RETRIES:-8}"

cd "$HUB_API_ROOT"

if [[ ! -f ".venv/bin/activate" ]]; then
  echo "missing hub-api virtualenv at hub-api/.venv; run make hub-api-setup first" >&2
  exit 1
fi

source .venv/bin/activate

python scripts/launch_preflight.py
python scripts/capture_runtime_snapshot.py \
  --label staging \
  --url "$STAGING_BASE_URL" \
  --header "x-emaildj-beta-key: $BETA_KEY"
python scripts/capture_runtime_snapshot.py \
  --label production \
  --url "$PROD_BASE_URL" \
  --header "x-emaildj-beta-key: $BETA_KEY"
./scripts/eval:full --real --mode smoke --min-cases "$REAL_SMOKE_CASES"
python -m devtools.http_smoke_runner \
  --mode "$DEPLOYED_SMOKE_MODE" \
  --flow "$DEPLOYED_SMOKE_FLOW" \
  --base-url "$STAGING_BASE_URL" \
  --beta-key "$BETA_KEY" \
  --out "$DEPLOYED_SMOKE_OUT" \
  --concurrency "$DEPLOYED_SMOKE_CONCURRENCY" \
  --timeout "$DEPLOYED_SMOKE_TIMEOUT" \
  --max-retries "$DEPLOYED_SMOKE_MAX_RETRIES"
python scripts/launch_check.py \
  --from-artifacts \
  --localhost-smoke-summary "${DEPLOYED_SMOKE_OUT%/}/summary.json"
