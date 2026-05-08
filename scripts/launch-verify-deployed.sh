#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HUB_API_ROOT="$ROOT/hub-api"
REAL_SMOKE_CASES="${EMAILDJ_LAUNCH_REAL_SMOKE_CASES:-10}"
DEPLOYED_SMOKE_MODE="${EMAILDJ_DEPLOYED_SMOKE_MODE:-smoke}"
DEPLOYED_SMOKE_FLOWS="${EMAILDJ_DEPLOYED_SMOKE_FLOWS:-generate,remix}"
DEPLOYED_SMOKE_OUT="${EMAILDJ_DEPLOYED_SMOKE_OUT:-debug_runs/smoke/deployed-staging}"
DEPLOYED_SMOKE_CONCURRENCY="${EMAILDJ_DEPLOYED_SMOKE_CONCURRENCY:-3}"
DEPLOYED_SMOKE_TIMEOUT="${EMAILDJ_DEPLOYED_SMOKE_TIMEOUT:-60}"
DEPLOYED_SMOKE_MAX_RETRIES="${EMAILDJ_DEPLOYED_SMOKE_MAX_RETRIES:-8}"
RELEASE_HUB_URL="${EMAILDJ_EXPECTED_HUB_URL:-${STAGING_BASE_URL:-}}"
RELEASE_PREVIEW_PIPELINE="${EMAILDJ_EXPECTED_PRESET_PREVIEW_PIPELINE:-${VITE_PRESET_PREVIEW_PIPELINE:-off}}"
RELEASE_BETA_KEY="${EMAILDJ_EXPECTED_BETA_KEY:-${BETA_KEY:-}}"

normalize_root_value() {
  local value="${1:-}"
  while [[ "$value" == */ ]]; do
    value="${value%/}"
  done
  printf '%s' "$value"
}

assert_same_launch_value() {
  local label="$1"
  local release_value="$2"
  local runtime_value="$3"
  local override_hint="$4"
  local normalized_release
  local normalized_runtime
  normalized_release="$(normalize_root_value "$release_value")"
  normalized_runtime="$(normalize_root_value "$runtime_value")"
  if [[ -n "$normalized_release" && -n "$normalized_runtime" && "$normalized_release" != "$normalized_runtime" ]]; then
    echo "$label mismatch: release verification resolves to '$release_value' but deployed runtime proof uses '$runtime_value'. Unset $override_hint or run the narrower release-bundle verifier outside make launch-verify-deployed." >&2
    exit 2
  fi
}

cd "$HUB_API_ROOT"

if [[ ! -f ".venv/bin/activate" ]]; then
  echo "missing hub-api virtualenv at hub-api/.venv; run make hub-api-setup first" >&2
  exit 1
fi

source .venv/bin/activate

python scripts/launch_preflight.py
assert_same_launch_value "Hub API target" "$RELEASE_HUB_URL" "$STAGING_BASE_URL" "EMAILDJ_EXPECTED_HUB_URL/VITE_HUB_URL"
assert_same_launch_value "Beta key" "$RELEASE_BETA_KEY" "$BETA_KEY" "EMAILDJ_EXPECTED_BETA_KEY/VITE_EMAILDJ_BETA_KEY"
cd "$ROOT"
EMAILDJ_EXPECTED_HUB_URL="$RELEASE_HUB_URL" \
  VITE_HUB_URL="${VITE_HUB_URL:-$RELEASE_HUB_URL}" \
  EMAILDJ_EXPECTED_PRESET_PREVIEW_PIPELINE="$RELEASE_PREVIEW_PIPELINE" \
  VITE_PRESET_PREVIEW_PIPELINE="${VITE_PRESET_PREVIEW_PIPELINE:-$RELEASE_PREVIEW_PIPELINE}" \
  make launch-verify-web-app
EMAILDJ_EXPECTED_HUB_URL="$RELEASE_HUB_URL" \
  VITE_HUB_URL="${VITE_HUB_URL:-$RELEASE_HUB_URL}" \
  EMAILDJ_EXPECTED_BETA_KEY="$RELEASE_BETA_KEY" \
  VITE_EMAILDJ_BETA_KEY="${VITE_EMAILDJ_BETA_KEY:-$RELEASE_BETA_KEY}" \
  make launch-verify-extension
cd "$HUB_API_ROOT"
python scripts/capture_runtime_snapshot.py \
  --label staging \
  --url "$STAGING_BASE_URL" \
  --header "x-emaildj-beta-key: $BETA_KEY"
python scripts/capture_runtime_snapshot.py \
  --label production \
  --url "$PROD_BASE_URL" \
  --header "x-emaildj-beta-key: $BETA_KEY"
./scripts/eval:full --real --mode smoke --min-cases "$REAL_SMOKE_CASES"
IFS=',' read -r -a smoke_flows <<< "$DEPLOYED_SMOKE_FLOWS"
summary_paths=()
for raw_flow in "${smoke_flows[@]}"; do
  flow="$(echo "$raw_flow" | tr -d '[:space:]')"
  if [[ -z "$flow" ]]; then
    continue
  fi
  flow_out="${DEPLOYED_SMOKE_OUT%/}/${flow}"
  python -m devtools.http_smoke_runner \
    --mode "$DEPLOYED_SMOKE_MODE" \
    --flow "$flow" \
    --base-url "$STAGING_BASE_URL" \
    --beta-key "$BETA_KEY" \
    --out "$flow_out" \
    --concurrency "$DEPLOYED_SMOKE_CONCURRENCY" \
    --timeout "$DEPLOYED_SMOKE_TIMEOUT" \
    --max-retries "$DEPLOYED_SMOKE_MAX_RETRIES"
  summary_paths+=("${flow_out%/}/summary.json")
done
if [[ "${#summary_paths[@]}" -eq 0 ]]; then
  echo "No deployed smoke flows selected. Set EMAILDJ_DEPLOYED_SMOKE_FLOWS to generate, remix, or generate,remix." >&2
  exit 2
fi
merged_summary="${DEPLOYED_SMOKE_OUT%/}/summary.json"
python scripts/merge_http_smoke_summaries.py --out "$merged_summary" "${summary_paths[@]}"
python scripts/launch_check.py \
  --from-artifacts \
  --localhost-smoke-summary "$merged_summary"
