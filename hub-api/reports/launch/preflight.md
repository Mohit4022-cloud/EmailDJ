# Launch Preflight

- Generated at: `2026-05-07T22:15:56.785703Z`
- Ready: `False`
- Failure bucket: `operator_input_missing`
- Provider: `openai`
- Provider env: `OPENAI_API_KEY`
- Timeout seconds: `15.0`

> `STAGING_BASE_URL` and `PROD_BASE_URL` must be HTTPS hub-api root URLs, not frontend URLs. `BETA_KEY` must match one non-dev deployed `EMAILDJ_WEB_BETA_KEYS` value.

## Required Inputs

- `STAGING_BASE_URL` present=`False`
- `PROD_BASE_URL` present=`False`
- `BETA_KEY` present=`False`
- `OPENAI_API_KEY` present=`True`

## Operator Input Sources

- `STAGING_BASE_URL` explicit_env_present=`False` dotenv_value_present=`False` dotenv_value_ignored=`False` effective_present=`False`
- `PROD_BASE_URL` explicit_env_present=`False` dotenv_value_present=`False` dotenv_value_ignored=`False` effective_present=`False`
- `BETA_KEY` explicit_env_present=`False` dotenv_value_present=`True` dotenv_value_ignored=`True` effective_present=`False`

## Deployment Discovery Context

- `state`: `present`
- `candidate_web_app_origin`: `https://email-93zl02rcj-mohits-projects-e629a988.vercel.app`
- `usable_as_web_app_origin_candidate`: `True`
- `clears_launch_blockers`: `False`
- `operator_note`: Candidate is for WEB_APP_ORIGIN only. It is a frontend origin, not a STAGING_BASE_URL or PROD_BASE_URL.

## Web App Probe Context

- `state`: `present`
- `client_bundle_usable`: `False`
- `requires_vercel_protection_bypass`: `True`
- `vercel_bypass_env`: `VERCEL_AUTOMATION_BYPASS_SECRET`
- `vercel_bypass_env_present`: `False`
- `operator_note`: The latest web-app probe is blocked by Vercel protection. Export `VERCEL_AUTOMATION_BYPASS_SECRET` before rerunning `make launch-probe-web-app`.

## Transport Probe

- `transport_checked`: `False`
- `transport_ok`: `None`
- `probe_url`: `unset`
- `probe_status_code`: `n/a`

## Next Steps

- Set `STAGING_BASE_URL` to the staging hub-api root URL (for example `https://hub-staging.example.com`) before running launch verification.
- Set `PROD_BASE_URL` to the production hub-api root URL (for example `https://hub.example.com`) before running launch verification.
- Set `BETA_KEY` to one exact non-dev deployed `EMAILDJ_WEB_BETA_KEYS` value before running launch verification.
- Use discovered web-app candidate `https://email-93zl02rcj-mohits-projects-e629a988.vercel.app` only for `WEB_APP_ORIGIN`; do not use it for `STAGING_BASE_URL` or `PROD_BASE_URL`.
