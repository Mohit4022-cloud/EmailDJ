SHELL := /bin/bash

.PHONY: setup test build dev launch-preflight launch-check launch-audit localhost-smoke launch-gates-local launch-verify-deployed launch-verify-web-app launch-verify-extension surface-contract render-blueprint-check \
	hub-api-setup web-app-setup chrome-extension-setup \
	hub-api-test web-app-test chrome-extension-test \
	hub-api-build web-app-build chrome-extension-build \
	legacy-backend-test legacy-frontend-test legacy-build legacy-setup \
	eval eval-smoke eval-parity eval-adversarial eval-full lint-copy secret-scan

setup: hub-api-setup web-app-setup chrome-extension-setup

hub-api-setup:
	cd hub-api && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

web-app-setup:
	cd web-app && npm install

chrome-extension-setup:
	cd chrome-extension && npm install

hub-api-test:
	cd hub-api && source .venv/bin/activate && python scripts/run_backend_suite.py

web-app-test:
	cd web-app && npm test && npm run check:syntax

chrome-extension-test:
	cd chrome-extension && npm test && npm run check:syntax

test: hub-api-test web-app-test chrome-extension-test

hub-api-build:
	cd hub-api && source .venv/bin/activate && python -m py_compile $$(find . -path './.venv' -prune -o -name '*.py' -type f -print)

web-app-build:
	cd web-app && npm run build

chrome-extension-build:
	cd chrome-extension && npm run build

build: hub-api-build web-app-build chrome-extension-build

eval: eval-smoke

eval-smoke:
	cd hub-api && source .venv/bin/activate && ./scripts/eval:smoke

eval-parity:
	cd hub-api && source .venv/bin/activate && ./scripts/eval:parity

eval-adversarial:
	cd hub-api && source .venv/bin/activate && ./scripts/eval:adversarial

eval-full:
	cd hub-api && source .venv/bin/activate && ./scripts/eval:full

lint-copy:
	./scripts/check_contamination.sh

secret-scan:
	./scripts/check_no_secrets.sh

surface-contract:
	python3 scripts/check_surface_contract.py

render-blueprint-check:
	python3 scripts/check_render_blueprint.py

dev:
	./scripts/dev.sh

launch-check:
	cd hub-api && source .venv/bin/activate && python scripts/launch_check.py --from-artifacts --allow-not-ready $${LOCALHOST_SMOKE_SUMMARY:+--localhost-smoke-summary $${LOCALHOST_SMOKE_SUMMARY}}

launch-audit:
	cd hub-api && source .venv/bin/activate && python scripts/launch_audit.py

launch-preflight:
	cd hub-api && source .venv/bin/activate && python scripts/launch_preflight.py

localhost-smoke:
	./scripts/localhost-smoke.sh

launch-verify-deployed:
	./scripts/launch-verify-deployed.sh

launch-verify-web-app:
	cd web-app && npm test && npm run check:syntax && npm run build && npm run check:release-config

launch-verify-extension:
	cd chrome-extension && npm test && npm run check:syntax && npm run build && npm run check:release-config

launch-gates-local: surface-contract render-blueprint-check hub-api-test web-app-test chrome-extension-test eval-smoke eval-parity eval-adversarial eval-full launch-check launch-audit

legacy-setup:
	cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
	cd frontend && npm install

legacy-backend-test:
	cd backend && source .venv/bin/activate && pytest -q

legacy-frontend-test:
	cd frontend && npm test && npm run check:syntax

legacy-build:
	cd frontend && npm run build
