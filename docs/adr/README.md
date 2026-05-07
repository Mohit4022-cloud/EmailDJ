# ADR Index

Use ADRs for durable architecture/policy decisions that affect invariants, contracts, or operations.

## Naming
- File name: `NNNN-short-kebab-title.md`
- Start from `0001` (template is `0000-template.md` and should not be edited for decisions).

## Requirement
CI enforces ADR updates when core invariant paths change (defined in `docs/_meta/docmap.yaml`).

## Decisions
- [ADR-0001: Lock Enforcement Model (offer_lock + cta_lock)](0001-lock-enforcement-model.md)
- [ADR-0002: Launch Runtime Gating](0002-launch-runtime-gating.md)
