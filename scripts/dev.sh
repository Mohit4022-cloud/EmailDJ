#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACK_PID=""
FRONT_PID=""

cleanup() {
  if [[ -n "${BACK_PID}" ]] && kill -0 "${BACK_PID}" >/dev/null 2>&1; then
    kill -INT "${BACK_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${FRONT_PID}" ]] && kill -0 "${FRONT_PID}" >/dev/null 2>&1; then
    kill -INT "${FRONT_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

(
  cd "${ROOT_DIR}/backend"
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -r requirements.txt >/dev/null
  export APP_ENV="${APP_ENV:-local}"
  export WEB_APP_ORIGIN="${WEB_APP_ORIGIN:-http://localhost:5174}"
  export EMAILDJ_WEB_BETA_KEYS="${EMAILDJ_WEB_BETA_KEYS:-dev-beta-key}"
  export EMAILDJ_WEB_RATE_LIMIT_PER_MIN="${EMAILDJ_WEB_RATE_LIMIT_PER_MIN:-300}"
  export USE_PROVIDER_STUB="${USE_PROVIDER_STUB:-1}"
  uvicorn main:app --host 127.0.0.1 --port 8000
) &
BACK_PID=$!

(
  cd "${ROOT_DIR}/frontend"
  npm install >/dev/null
  npm run dev -- --port 5174
) &
FRONT_PID=$!

while true; do
  if [[ -n "${BACK_PID}" ]] && ! kill -0 "${BACK_PID}" >/dev/null 2>&1; then
    break
  fi
  if [[ -n "${FRONT_PID}" ]] && ! kill -0 "${FRONT_PID}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
