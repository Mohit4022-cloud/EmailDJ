.PHONY: setup test build dev backend-test frontend-test eval lint-copy

setup:
	cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
	cd frontend && npm install

backend-test:
	cd backend && source .venv/bin/activate && pytest -q

eval:
	cd backend && source .venv/bin/activate && pytest -q tests/test_engine_evals.py

frontend-test:
	cd frontend && npm test && npm run check:syntax

test: backend-test frontend-test eval

lint-copy:
	./scripts/check_contamination.sh

build:
	cd frontend && npm run build

dev:
	./scripts/dev.sh
