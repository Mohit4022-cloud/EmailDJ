#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACK_PID=""
FRONT_PID=""

BACKEND_ENV_FILE="${ROOT_DIR}/hub-api/.env"
if [[ -f "${BACKEND_ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${BACKEND_ENV_FILE}"
  set +a
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY is required for real-AI mode. Export it and re-run make dev." >&2
  exit 1
fi

if [[ "${USE_PROVIDER_STUB:-0}" == "1" ]]; then
  echo "USE_PROVIDER_STUB=1 is not allowed in this dev script. Set USE_PROVIDER_STUB=0." >&2
  exit 1
fi

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
  cd "${ROOT_DIR}/hub-api"
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -r requirements.txt >/dev/null
  export APP_ENV="${EMAILDJ_DEV_APP_ENV:-local}"
  export EMAILDJ_LAUNCH_MODE="${EMAILDJ_DEV_LAUNCH_MODE:-dev}"
  export WEB_APP_ORIGIN="${EMAILDJ_DEV_WEB_APP_ORIGIN:-http://localhost:5174}"
  export CHROME_EXTENSION_ORIGIN="${EMAILDJ_DEV_CHROME_EXTENSION_ORIGIN:-chrome-extension://dev}"
  export EMAILDJ_WEB_BETA_KEYS="${EMAILDJ_DEV_WEB_BETA_KEYS:-dev-beta-key}"
  export EMAILDJ_WEB_RATE_LIMIT_PER_MIN="${EMAILDJ_WEB_RATE_LIMIT_PER_MIN:-300}"
  export REDIS_FORCE_INMEMORY="${EMAILDJ_DEV_REDIS_FORCE_INMEMORY:-1}"
  export USE_PROVIDER_STUB="${USE_PROVIDER_STUB:-0}"
  uvicorn main:app --host 127.0.0.1 --port 8000
) &
BACK_PID=$!

(
  cd "${ROOT_DIR}/web-app"
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
