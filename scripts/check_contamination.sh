#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PATTERN='outbound execution|first-touch|manual review|messaging logic|example sequence|reply quality'
FILES=(
  "$ROOT/backend/app/engine/pipeline.py"
  "$ROOT/backend/app/server.py"
  "$ROOT/frontend/src/components/presetPreviewUtils.js"
)

MATCHES=$(rg -n "$PATTERN" "${FILES[@]}" || true)
if [[ -n "$MATCHES" ]]; then
  echo "Contamination phrases found in neutral fallback/helper paths:"
  echo "$MATCHES"
  exit 1
fi

echo "Contamination lint passed (neutral fallback/helper paths are clean)."
