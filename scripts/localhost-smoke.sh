#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HUB_DIR="${ROOT_DIR}/hub-api"

BASE_URL="${EMAILDJ_SMOKE_BASE_URL:-http://127.0.0.1:8000}"
BETA_KEY="${EMAILDJ_SMOKE_BETA_KEY:-dev-beta-key}"
MODE="${EMAILDJ_SMOKE_MODE:-smoke}"
FLOWS="${EMAILDJ_SMOKE_FLOWS:-${EMAILDJ_SMOKE_FLOW:-generate,remix}}"
OUT_DIR="${EMAILDJ_SMOKE_OUT:-debug_runs/smoke/manual}"
CONCURRENCY="${EMAILDJ_SMOKE_CONCURRENCY:-3}"
TIMEOUT="${EMAILDJ_SMOKE_TIMEOUT:-60}"
MAX_RETRIES="${EMAILDJ_SMOKE_MAX_RETRIES:-8}"
JUDGE_LIMIT="${EMAILDJ_SMOKE_JUDGE_LIMIT:-0}"

if [[ "${EMAILDJ_CONFIRM_LOCALHOST_SMOKE:-}" != "1" ]]; then
  cat >&2 <<'MSG'
localhost smoke can call the provider configured on the running Hub API.
Start the Hub API intentionally, then rerun:

  EMAILDJ_CONFIRM_LOCALHOST_SMOKE=1 make localhost-smoke

Common overrides:
  EMAILDJ_SMOKE_BASE_URL=http://127.0.0.1:8000
  EMAILDJ_SMOKE_BETA_KEY=dev-beta-key
  EMAILDJ_SMOKE_FLOWS=generate,remix
  EMAILDJ_SMOKE_OUT=debug_runs/smoke/manual
MSG
  exit 2
fi

cd "${HUB_DIR}"
if [[ ! -d .venv ]]; then
  echo "hub-api/.venv is missing. Run make hub-api-setup first." >&2
  exit 2
fi

# shellcheck disable=SC1091
source .venv/bin/activate

IFS=',' read -r -a smoke_flows <<< "${FLOWS}"
summary_paths=()
for raw_flow in "${smoke_flows[@]}"; do
  flow="$(echo "${raw_flow}" | tr -d '[:space:]')"
  if [[ -z "${flow}" ]]; then
    continue
  fi
  flow_out="${OUT_DIR%/}/${flow}"
  smoke_args=(
    -m devtools.http_smoke_runner
    --mode "${MODE}"
    --flow "${flow}"
    --base-url "${BASE_URL}"
    --beta-key "${BETA_KEY}"
    --out "${flow_out}"
    --concurrency "${CONCURRENCY}"
    --timeout "${TIMEOUT}"
    --max-retries "${MAX_RETRIES}"
    --judge_limit "${JUDGE_LIMIT}"
  )

  if [[ -n "${EMAILDJ_SMOKE_PACK:-}" ]]; then
    smoke_args+=(--pack "${EMAILDJ_SMOKE_PACK}")
  fi

  python "${smoke_args[@]}"
  summary_paths+=("${flow_out%/}/summary.json")
done

if [[ "${#summary_paths[@]}" -eq 0 ]]; then
  echo "No smoke flows selected. Set EMAILDJ_SMOKE_FLOWS to generate, remix, or generate,remix." >&2
  exit 2
fi

summary_path="${OUT_DIR%/}/summary.json"
python scripts/merge_http_smoke_summaries.py --out "${summary_path}" "${summary_paths[@]}"
python scripts/launch_check.py \
  --from-artifacts \
  --allow-not-ready \
  --localhost-smoke-summary "${summary_path}"
