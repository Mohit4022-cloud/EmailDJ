# EmailDJ Stage Map

## Stage map

| Selector | Trace stage | Prompt module | Primary artifact | Response format | Validator or normalizer | Useful tests |
| --- | --- | --- | --- | --- | --- | --- |
| `a` | `CONTEXT_SYNTHESIS` | `backend/app/engine/prompts/stage_a.py` | `MessagingBrief` | `RF_MESSAGING_BRIEF` | `validate_messaging_brief` | `backend/tests/test_stage_a_validator.py`, `backend/tests/test_messaging_brief_quality.py` |
| `b` | `FIT_REASONING` | `backend/app/engine/prompts/stage_b.py` | `FitMap` | `RF_FIT_MAP` | `validate_fit_map` | `backend/tests/test_stage_runner.py`, `backend/tests/test_engine_evals.py` |
| `b0` | `ANGLE_PICKER` | `backend/app/engine/prompts/stage_b0.py` | `AngleSet` | `RF_ANGLE_SET` | `validate_angle_set` | `backend/tests/test_stage_runner.py`, `backend/tests/test_engine_evals.py` |
| `c0` | `ONE_LINER_COMPRESSOR` | `backend/app/engine/prompts/stage_c0.py` | `MessageAtoms` | `RF_MESSAGE_ATOMS` | `validate_message_atoms` | `backend/tests/test_budget_planner.py`, `backend/tests/test_stage_runner.py` |
| `c` | `EMAIL_GENERATION` | `backend/app/engine/prompts/stage_c.py` | `EmailDraft` | `RF_EMAIL_DRAFT` | `validate_email_draft` | `backend/tests/test_ai_orchestrator_fail_closed.py`, `backend/tests/test_llm_realizer_pipeline.py` |
| `d` | `EMAIL_QA` | `backend/app/engine/prompts/stage_d.py` | `QAReport` | `RF_QA_REPORT` | `normalize_qa_report` plus downstream rewrite planning | `backend/tests/test_ai_orchestrator_fail_closed.py`, `backend/tests/test_engine_evals.py` |
| `e` | `EMAIL_REWRITE` | `backend/app/engine/prompts/stage_e.py` | `EmailDraft` | `RF_EMAIL_DRAFT` | final `validate_email_draft` pass plus rewrite checks in stage judge | `backend/tests/test_ai_orchestrator_fail_closed.py`, `backend/tests/test_eval_run_artifacts.py` |

## Update rules

When changing any staged contract, update these layers together:

1. prompt instructions
2. `backend/app/engine/schemas.py`
3. `backend/app/engine/validators.py` or normalization logic
4. orchestrator or consumer code
5. stage judge expectations in `backend/evals/stage_judge.py`
6. targeted tests

## Commands

```bash
rg -n "RF_MESSAGING_BRIEF|RF_FIT_MAP|RF_ANGLE_SET|RF_MESSAGE_ATOMS|RF_EMAIL_DRAFT|RF_QA_REPORT" backend/app/engine/schemas.py
rg -n "def validate_|def normalize_qa_report" backend/app/engine/validators.py
pytest backend/tests/test_stage_runner.py -q
```
