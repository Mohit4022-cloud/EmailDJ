# Launch Preflight

- Generated at: `2026-05-07T04:19:01.274802Z`
- Ready: `False`
- Failure bucket: `operator_input_missing`
- Provider: `openai`
- Provider env: `OPENAI_API_KEY`
- Timeout seconds: `15.0`

> `STAGING_BASE_URL` and `PROD_BASE_URL` must be hub-api root URLs, not frontend URLs. `BETA_KEY` must match one deployed `EMAILDJ_WEB_BETA_KEYS` value.

## Required Inputs

- `STAGING_BASE_URL` present=`False`
- `PROD_BASE_URL` present=`False`
- `BETA_KEY` present=`False`
- `OPENAI_API_KEY` present=`True`

## Operator Input Sources

- `STAGING_BASE_URL` explicit_env_present=`False` dotenv_value_present=`False` dotenv_value_ignored=`False` effective_present=`False`
- `PROD_BASE_URL` explicit_env_present=`False` dotenv_value_present=`False` dotenv_value_ignored=`False` effective_present=`False`
- `BETA_KEY` explicit_env_present=`False` dotenv_value_present=`True` dotenv_value_ignored=`True` effective_present=`False`

## Transport Probe

- `transport_checked`: `False`
- `transport_ok`: `None`
- `probe_url`: `unset`
- `probe_status_code`: `n/a`

## Next Steps

- Set `STAGING_BASE_URL` to the staging hub-api root URL (for example `https://hub-staging.example.com`) before running launch verification.
- Set `PROD_BASE_URL` to the production hub-api root URL (for example `https://hub.example.com`) before running launch verification.
- Set `BETA_KEY` to one exact deployed `EMAILDJ_WEB_BETA_KEYS` value before running launch verification.
