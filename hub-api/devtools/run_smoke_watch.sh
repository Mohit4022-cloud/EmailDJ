#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HUB_API_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -x "${HUB_API_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${HUB_API_DIR}/.venv/bin/python"
else
  PYTHON_BIN="python"
fi

run_once() {
  local stamp
  stamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo
  echo "[${stamp}] Running smoke harness..."
  (cd "${HUB_API_DIR}" && "${PYTHON_BIN}" -m devtools.http_smoke_runner --mode smoke)
}

if [[ $# -gt 1 ]]; then
  echo "Usage: $(basename "$0") [minutes]"
  exit 2
fi

if [[ $# -eq 1 ]]; then
  interval_min="$1"
  if ! [[ "${interval_min}" =~ ^[0-9]+$ ]] || [[ "${interval_min}" -le 0 ]]; then
    echo "Minutes must be a positive integer."
    exit 2
  fi
  interval_sec=$((interval_min * 60))
  echo "Watch mode: running every ${interval_min} minute(s). Ctrl+C to stop."
  while true; do
    run_once
    echo "Sleeping ${interval_min} minute(s)..."
    sleep "${interval_sec}"
  done
else
  echo "Watch mode: press Enter to run smoke, or type q then Enter to quit."
  while true; do
    read -r -p "> " input
    if [[ "${input}" == "q" ]]; then
      echo "Exiting."
      break
    fi
    run_once
  done
fi
