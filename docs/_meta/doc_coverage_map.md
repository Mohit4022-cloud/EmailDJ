# Doc Coverage Map

This map links code-change domains to required documentation updates and freshness rules.

## Rule Source
- Machine-readable rules: `docs/_meta/docmap.yaml`
- Gate implementation: `scripts/docops/check_doc_freshness.py`

## Coverage Domains
1. Architecture/runtime flow
- Code: `hub-api/main.py`, `hub-api/api/routes/*`, `hub-api/email_generation/*`, `web-app/src/main.js`, `web-app/src/api/*`, `web-app/src/components/*`
- Required docs: architecture overview, SSE contract, control contract, product positioning

2. Contracts/schemas
- Code: `hub-api/openapi.json`, route/schema files, streaming transport
- Required docs: SSE contract and OpenAPI generated docs

3. Ops/CI
- Code: workflow files, check scripts, docops scripts
- Required docs: DocOps runbook and environment matrix

## ADR Requirement
When core policy/invariant files change, at least one ADR in `docs/adr/` must be updated.

## Generated-doc freshness
Generated outputs are:
- `docs/ops/env_matrix.md`
- `docs/contracts/openapi_summary.md`
- `docs/contracts/openapi_diff.md`
- `docs/contracts/openapi_snapshot.json`

CI enforces freshness with `python3 scripts/docops/generate_docs.py --check`.
