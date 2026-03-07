# EmailDJ Copy QA Rubric

## Blocking

Treat these as blocking by default:

- CTA drift or duplicate CTA
- invented or circular proof
- prospect-as-proof
- ungrounded personalization
- template leakage
- repeated paragraphs or obvious sentence repetition
- banned phrases such as `touch base`, `circle back`, `synergy`, `leverage`, `game-changer`, `I hope this email finds you`

## Warning

Use warnings for:

- weak subject specificity
- generic opener that still stays technically grounded
- over-explaining mechanism instead of outcome
- sentence count or length pressure that has not yet broken the contract
- angle drift across presets that still preserves hooks and CTA

## Rewrite direction

Give surgical rewrite guidance only:

- quote the offending line
- say whether to cut, replace, or compress it
- preserve the locked CTA verbatim
- preserve grounded proof and selected hooks

## Validator vocabulary

Prefer the repo's own terms when they apply:

- mechanical: `subject_too_long`, `cta_not_final_line`, `duplicate_cta_line`, `word_count_out_of_band`, `too_many_sentences_for_preset`
- semantic: `banned_phrase`, `ungrounded_personalization_claim`, `repetition_detected`, `personalization_missing_used_hook`, `personalization_generic_opener`

If a finding is not already represented by a validator code, cite the exact draft line and explain the violated repo rule.
