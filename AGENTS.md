# EmailDJ Repo Guidance

- Keep email generation fail-closed. In `backend/app/engine/**`, do not reintroduce deterministic or template fallback drafts. Enrichment fallback is separate and must stay tool-based.
- Preserve the exact CTA final line across `MessageAtoms`, `EmailDraft`, QA, rewrite, postprocess, and trace artifacts. Treat CTA drift as blocking and report it with the pipeline stage name plus validator or error code.
- Preserve staged artifacts and traceability. Do not remove stage outputs, prompt/version hashes, or `backend/debug_traces/**` artifacts just to make a failure disappear.
- Explain failures in pipeline terms: `CONTEXT_SYNTHESIS`, `FIT_REASONING`, `ANGLE_PICKER`, `ONE_LINER_COMPRESSOR`, `EMAIL_GENERATION`, `EMAIL_QA`, `EMAIL_REWRITE`.
- When changing a staged contract, update the prompt, response schema, validator or normalizer, downstream consumer, stage judge, and tests together.
- Treat presets and sliders as style modifiers only. For the same request, do not let them change grounded brief facts, hook logic, proof availability, or locked CTA text.
- Reject invented proof, prospect-as-proof, ungrounded personalization, template leakage, and fallback leakage. Keep validator codes visible in traces and explanations.
- Prefer the existing repo harnesses in `backend/evals/` over ad hoc eval scripts.
