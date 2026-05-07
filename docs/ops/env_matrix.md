# Environment Matrix

Generated from `hub-api/.env.example` + repository env usage.

| Variable | In `.env.example` | Example / Default | Observed in code | Sample locations |
|---|---|---|---|---|
| ALERT_SINK_TIMEOUT_SECONDS | yes | 5 | 1 | hub-api/infra/alerting.py |
| ANTHROPIC_API_KEY | yes | sk-ant-...        # Required when EMAILDJ_REAL_PROVIDER=a... | 1 | hub-api/email_generation/quick_generate.py |
| APP_ENV | yes | local                               # local\|staging\|prod.... | 3 | hub-api/email_generation/quick_generate.py, hub-api/scripts/dev_real_defaults_report.py, hub-api/tests/integration/te... |
| BLAST_RADIUS_CONFIRM_THRESHOLD | yes | 200 | 0 | - |
| BOMBORA_API_KEY | yes | ... | 1 | hub-api/tests/integration/test_campaign_assignment_lifecycle.py |
| BOMBORA_API_URL | yes | https://api.bombora.com/v1/company-surge | 0 | - |
| BRAVE_SEARCH_API_KEY | yes | ...       # fallback | 0 | - |
| CHROME_EXTENSION_ORIGIN | yes | chrome-extension://YOUR_EXTENSION_ID  # Required CORS ori... | 19 | hub-api/evals/runner.py, hub-api/main.py, hub-api/runtime_debug.py |
| CONTEXT_VAULT_CACHE_TTL_SECONDS | yes | 3600 | 0 | - |
| DATABASE_URL | yes | postgresql+asyncpg://user:password@localhost:5432/emaildj... | 3 | hub-api/infra/db.py, hub-api/main.py, hub-api/runtime_debug.py |
| DEEP_RESEARCH_JOB_TTL_SECONDS | yes | 86400 | 1 | hub-api/api/routes/deep_research.py |
| DEEP_RESEARCH_RATE_LIMIT_PER_HOUR | yes | 200 | 0 | - |
| EMAILDJ_CAMPAIGN_INTELLIGENCE_MODE | yes | auto  # auto\|real\|mock\|fallback | 1 | hub-api/tests/integration/test_campaign_assignment_lifecycle.py |
| EMAILDJ_CRM_PROVIDER | yes | salesforce          # salesforce\|mock | 0 | - |
| EMAILDJ_DEBUG_SUCCESS_SAMPLE_RATE | yes | 0.01         # 0.0-1.0 | 2 | hub-api/email_generation/runtime_policies.py, hub-api/main.py |
| EMAILDJ_ENABLE_DEBUG_ENDPOINTS | no | - | 2 | hub-api/api/routes/web_mvp.py, hub-api/main.py |
| EMAILDJ_EXTRACTOR_ENABLE_ENRICHMENT | yes | 0 | 0 | - |
| EMAILDJ_EXTRACTOR_ENRICH_CONFIDENCE_MIN | yes | 0.75 | 1 | hub-api/context_vault/extractor.py |
| EMAILDJ_GIT_SHA | no | - | 1 | hub-api/tests/integration/test_web_mvp_api.py |
| EMAILDJ_INTENT_PROVIDER | yes | bombora          # bombora\|mock | 0 | - |
| EMAILDJ_JUDGE_CACHE_DIR | no | - | 1 | hub-api/evals/runner.py |
| EMAILDJ_JUDGE_CANDIDATE_ID | no | - | 1 | hub-api/evals/runner.py |
| EMAILDJ_JUDGE_MODE | no | - | 5 | hub-api/evals/judge/calibrate_thresholds.py, hub-api/evals/judge/client.py, hub-api/evals/judge/real_corpus_runner.py |
| EMAILDJ_JUDGE_MODEL | no | - | 5 | hub-api/evals/judge/calibrate_thresholds.py, hub-api/evals/judge/client.py, hub-api/evals/judge/real_corpus_runner.py |
| EMAILDJ_JUDGE_MODEL_VERSION | no | - | 7 | hub-api/evals/judge/calibrate_thresholds.py, hub-api/evals/judge/client.py, hub-api/evals/judge/pairwise_runner.py |
| EMAILDJ_JUDGE_PAIRWISE_SEED | no | - | 1 | hub-api/evals/judge/reliability.py |
| EMAILDJ_JUDGE_RUBRIC_VERSION | no | - | 1 | hub-api/evals/judge/rubric.py |
| EMAILDJ_JUDGE_SAMPLE_COUNT | no | - | 4 | hub-api/evals/judge/calibrate_thresholds.py, hub-api/evals/judge/client.py, hub-api/evals/judge/real_corpus_runner.py |
| EMAILDJ_JUDGE_SECONDARY_MODEL | no | - | 5 | hub-api/evals/judge/calibrate_thresholds.py, hub-api/evals/judge/client.py, hub-api/evals/judge/real_corpus_runner.py |
| EMAILDJ_JUDGE_TIMEOUT_SEC | no | - | 5 | hub-api/evals/judge/calibrate_thresholds.py, hub-api/evals/judge/client.py, hub-api/evals/judge/real_corpus_runner.py |
| EMAILDJ_LAUNCH_MODE | yes | dev                     # dev\|limited_rollout\|broad_launc... | 4 | hub-api/main.py, hub-api/scripts/capture_ui_session.py, hub-api/tests/integration/test_web_mvp_api.py |
| EMAILDJ_OPENAI_MODEL | yes | gpt-5-nano | 0 | - |
| EMAILDJ_OPENAI_REASONING_EFFORT | yes | high         # minimal\|low\|medium\|high | 0 | - |
| EMAILDJ_PRESET_PREVIEW_MODEL_EXTRACTOR | yes | gpt-5-nano | 1 | hub-api/main.py |
| EMAILDJ_PRESET_PREVIEW_MODEL_FALLBACK | yes | gpt-5-nano | 1 | hub-api/email_generation/preset_preview_pipeline.py |
| EMAILDJ_PRESET_PREVIEW_MODEL_GENERATOR | yes | gpt-5-nano | 3 | hub-api/email_generation/preset_preview_pipeline.py, hub-api/main.py, hub-api/tests/test_preset_preview_pipeline.py |
| EMAILDJ_PRESET_PREVIEW_PIPELINE | yes | off                         # Set on only when preview ro... | 4 | hub-api/scripts/capture_ui_session.py, hub-api/scripts/real_mode_failfast_smoke.py, hub-api/tests/integration/test_pr... |
| EMAILDJ_PRESET_PREVIEW_SUMMARY_CACHE_TTL_SEC | yes | 900 | 0 | - |
| EMAILDJ_PREVIEW_ENFORCEMENT_LEVEL | yes | warn             # warn\|repair\|block | 2 | hub-api/tests/integration/test_preview_generate_parity.py, hub-api/tests/test_preset_preview_pipeline.py |
| EMAILDJ_PREVIEW_INCLUDE_SUMMARY_PACK | yes | 0 | 2 | hub-api/email_generation/preset_preview_pipeline.py, hub-api/tests/test_preset_preview_pipeline.py |
| EMAILDJ_QUICK_GENERATE_MODE | yes | real    # Legacy override. Mock is ignored unless USE_PRO... | 2 | hub-api/main.py, hub-api/runtime_debug.py |
| EMAILDJ_REAL_PROVIDER | yes | openai        # Deployed provider preference: openai\|anth... | 9 | hub-api/main.py, hub-api/scripts/capture_ui_session.py, hub-api/scripts/debug_run_harness.py |
| EMAILDJ_REPAIR_LOOP_ENABLED | yes | 1                  # 1\|0 | 2 | hub-api/scripts/debug_run_harness.py, hub-api/tests/integration/test_web_mvp_api.py |
| EMAILDJ_ROUTE_GENERATE_ENABLED | no | - | 1 | hub-api/tests/integration/test_web_mvp_api.py |
| EMAILDJ_ROUTE_PREVIEW_ENABLED | no | - | 1 | hub-api/tests/integration/test_web_mvp_api.py |
| EMAILDJ_ROUTE_REMIX_ENABLED | no | - | 1 | hub-api/tests/integration/test_web_mvp_api.py |
| EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL | yes | repair   # warn\|repair\|block | 5 | hub-api/email_generation/runtime_policies.py, hub-api/main.py, hub-api/scripts/capture_ui_session.py |
| EMAILDJ_WEB_BETA_KEYS | yes | dev-beta-key                          # Required in stagi... | 8 | hub-api/api/middleware/beta_access.py, hub-api/main.py, hub-api/runtime_debug.py |
| EMAILDJ_WEB_RATE_LIMIT_PER_MIN | yes | 30                           # Required in staging/prod.... | 7 | hub-api/api/middleware/beta_access.py, hub-api/main.py, hub-api/runtime_debug.py |
| FEATURE_LOSSLESS_STREAMING | no | - | 1 | hub-api/tests/integration/test_web_mvp_api.py |
| GITHUB_SHA | no | - | 1 | hub-api/evals/runner.py |
| GROQ_API_KEY | yes | gsk_...                # Required when EMAILDJ_REAL_PROVI... | 1 | hub-api/email_generation/quick_generate.py |
| LANGCHAIN_API_KEY | yes | ls__... | 0 | - |
| LANGCHAIN_PROJECT | yes | emaildj-prod | 0 | - |
| LANGCHAIN_TRACING_V2 | yes | true | 0 | - |
| LOG_LEVEL | yes | INFO | 1 | hub-api/main.py |
| MONTHLY_COST_CEILING | yes | 100 | 1 | hub-api/api/middleware/cost_guard.py |
| MONTHLY_COST_THROTTLE_MULTIPLIER | yes | 3 | 0 | - |
| OPENAI_API_KEY | yes | sk-...               # Required when EMAILDJ_REAL_PROVIDE... | 12 | .github/workflows/ci.yml, .github/workflows/eval_regression.yml, hub-api/email_generation/preset_preview_pipeline.py |
| PINECONE_API_KEY | yes | pcsk_... | 0 | - |
| PINECONE_ENVIRONMENT | yes | us-east-1 | 0 | - |
| PINECONE_INDEX_NAME | yes | emaildj-contexts | 0 | - |
| PROVIDER_FAILURE_METRICS_WEBHOOK_URL | yes | https://metrics.example.com/events | 2 | hub-api/infra/alerting.py, hub-api/tests/integration/test_provider_failure_alerting.py |
| QUICK_MAX_CONCURRENT_STREAMS | yes | 32 | 1 | hub-api/api/routes/quick_generate.py |
| QUICK_PROVIDER_FAILURE_ALERT_STEP | yes | 5 | 2 | hub-api/email_generation/quick_generate.py, hub-api/tests/integration/test_provider_failure_alerting.py |
| QUICK_PROVIDER_FAILURE_ALERT_THRESHOLD | yes | 5 | 2 | hub-api/email_generation/quick_generate.py, hub-api/tests/integration/test_provider_failure_alerting.py |
| QUICK_REQUEST_TTL_SECONDS | yes | 300 | 1 | hub-api/api/routes/quick_generate.py |
| REDIS_FORCE_INMEMORY | yes | 0              # Local/test only. Staging/prod must stay... | 19 | hub-api/evals/runner.py, hub-api/infra/redis_client.py, hub-api/main.py |
| REDIS_URL | yes | redis://localhost:6379/0  # Required for deployed hub-api... | 3 | hub-api/infra/redis_client.py, hub-api/main.py, hub-api/runtime_debug.py |
| SALESFORCE_ACCESS_TOKEN | yes | ... | 1 | hub-api/tests/integration/test_campaign_assignment_lifecycle.py |
| SALESFORCE_API_VERSION | yes | v59.0 | 0 | - |
| SALESFORCE_CLIENT_ID | yes | ... | 0 | - |
| SALESFORCE_CLIENT_SECRET | yes | ... | 0 | - |
| SALESFORCE_INSTANCE_URL | yes | https://your-instance.my.salesforce.com | 1 | hub-api/tests/integration/test_campaign_assignment_lifecycle.py |
| SALESFORCE_REDIRECT_URI | yes | http://localhost:8000/auth/callback | 0 | - |
| SERPER_API_KEY | yes | ...             # primary | 0 | - |
| SLACK_WEBHOOK_URL | yes | https://hooks.slack.com/services/... | 2 | hub-api/infra/alerting.py, hub-api/tests/integration/test_provider_failure_alerting.py |
| USE_PROVIDER_STUB | yes | 0                 # Deployed services must use 0. Set 1 o... | 10 | hub-api/evals/runner.py, hub-api/scripts/debug_run_harness.py, hub-api/scripts/mock_e2e_smoke.py |
| VECTOR_STORE_BACKEND | yes | memory     # Local dev default. limited_rollout/broad_lau... | 3 | hub-api/infra/vector_store.py, hub-api/main.py, hub-api/runtime_debug.py |
| VITE_ALLOW_MOCK_AI | no | - | 1 | web-app/src/main.js |
| VITE_RESPONSE_CONTRACT | no | - | 1 | web-app/src/main.js |
| WEB_APP_ORIGIN | yes | http://localhost:5174                         # Required... | 7 | hub-api/main.py, hub-api/runtime_debug.py, hub-api/scripts/capture_ui_session.py |

## Notes

- `In .env.example = no` means code references a variable not declared in `hub-api/.env.example`.
- `Observed in code = 0` means variable is documented but currently not referenced in scanned files.
