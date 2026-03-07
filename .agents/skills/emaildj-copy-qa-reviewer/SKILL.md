---
name: emaildj-copy-qa-reviewer
description: Review EmailDJ final email copy, rewrite output, QA artifacts, and validator results for language-quality drift. Use when a draft looks fluffy, repetitive, spammy, weak on proof, generic in the opener, template-like, or suspicious around CTA-final-line lock even if the pipeline technically completed.
---

# EmailDJ Copy QA Reviewer

## Overview

Review copy with EmailDJ's own guardrails instead of generic writing advice. Anchor every finding to a validator code, trace field, or exact line from the draft.

## Review Workflow

1. Read the final draft, rewritten draft, QA report, and any validation codes together.
2. Load `references/copy-qa-rubric.md` before making judgments about tone, proof, or CTA placement.
3. Produce findings under exactly three headings:
   - `blocking`
   - `warn`
   - `rewrite_direction`
4. Cite evidence for each finding:
   - existing validator code when present
   - otherwise the exact subject or body line that violates the repo rule
5. Treat the following as blocking by default: CTA drift, invented proof, ungrounded personalization, template leakage, banned phrases, repeated paragraphs, and copy that contradicts the selected hooks.

## Review Rules

- Prefer repo terms such as `repetition_detected`, `banned_phrase`, `ungrounded_personalization_claim`, `cta_not_final_line`, and `duplicate_cta_line`.
- Do not ask for "more personalization" unless the brief already supports it.
- Do not reward hype, cleverness, or extra proof that is not grounded in the brief.
- Keep rewrite guidance surgical. Point to the sentence to cut or rewrite, not vague "tighten this up" advice.

## Commands

```bash
rg -n "BANNED_PHRASES|MECHANICAL_VALIDATION_CODES|SEMANTIC_VALIDATION_CODES" backend/app/engine/validators.py
```

## References

- Read `references/copy-qa-rubric.md` for the repo-specific blocking and warning taxonomy before reviewing copy.
