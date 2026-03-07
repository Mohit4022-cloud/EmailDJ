# DocOps Guardian

This repository uses path-aware and generated-doc gates so docs cannot silently drift from code.

## Source Files
- Coverage map: `docs/_meta/docmap.yaml`
- Glossary: `docs/_meta/glossary.md`
- Freshness gate: `scripts/docops/check_doc_freshness.py`
- Generators: `scripts/docops/generate_docs.py`

## Local Commands
1. Regenerate generated docs
```bash
python3 scripts/docops/generate_docs.py
```

2. Verify generated docs are fresh
```bash
python3 scripts/docops/generate_docs.py --check
```

3. Run doc freshness against your branch diff
```bash
python3 scripts/docops/check_doc_freshness.py --base origin/main --head HEAD
```

4. Produce a patch if generated docs are stale
```bash
python3 scripts/docops/generate_docs.py --check --write-patch /tmp/docops-generated.patch
```

## CI Enforcement
- PR/push gate in `.github/workflows/ci.yml`:
  - path-to-doc freshness check
  - generated docs freshness check
- Nightly sweep in `.github/workflows/docs-nightly.yml`:
  - regenerate generated docs
  - open/update a single maintenance PR when drift exists

## ADR Rule
If core invariants/policy code changes, at least one ADR in `docs/adr/` must be updated.
Core invariant paths are defined in `docs/_meta/docmap.yaml` under `adr.core_paths`.
