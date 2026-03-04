.PHONY: setup test build dev backend-test frontend-test

setup:
	cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
	cd frontend && npm install

backend-test:
	cd backend && source .venv/bin/activate && pytest -q

frontend-test:
	cd frontend && npm test && npm run check:syntax

test: backend-test frontend-test

build:
	cd frontend && npm run build

dev:
	./scripts/dev.sh
