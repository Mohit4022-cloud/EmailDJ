#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HUB_API_ROOT="$ROOT/hub-api"
REAL_SMOKE_CASES="${EMAILDJ_LAUNCH_REAL_SMOKE_CASES:-10}"

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
python scripts/launch_check.py --from-artifacts
