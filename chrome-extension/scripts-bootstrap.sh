#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

npm install
npm run check:syntax
npm run build

echo "Extension bootstrap complete."
