#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

forbidden_files=()

while IFS= read -r -d '' file; do
  case "$file" in
    .env|*/.env|.env.local|*/.env.local|.env.*|*/.env.*)
      case "$file" in
        *.env.example|*/.env.example|*.env.sample|*/.env.sample|*.env.template|*/.env.template)
          ;;
        *)
          forbidden_files+=("$file")
          ;;
      esac
      ;;
    *.pem|*.key|*.crt|*.p12|*.pfx|*.secret|*.secrets.*|secret.*|secrets/*|*/secrets/*|.secrets/*|*/.secrets/*)
      forbidden_files+=("$file")
      ;;
  esac
done < <(git ls-files -z)

if ((${#forbidden_files[@]} > 0)); then
  echo "Tracked secret-bearing files are not allowed:"
  printf '  %s\n' "${forbidden_files[@]}" | sort -u
  exit 1
fi

secret_pattern='AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}|sk-proj-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|gsk_[A-Za-z0-9_-]{20,}|pcsk_[A-Za-z0-9_-]{20,}|ls__[A-Za-z0-9_-]{20,}|SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}'

matches_file="$(mktemp)"
trap 'rm -f "$matches_file"' EXIT

if git grep -n -I -E "$secret_pattern" >"$matches_file"; then
  echo "Potential hardcoded secrets found:"
  awk -F: '{print "  " $1 ":" $2}' "$matches_file" | sort -u
  exit 1
fi

echo "Secret scan passed."
