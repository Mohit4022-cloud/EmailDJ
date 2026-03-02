A) AS-IS Architecture Diagram  
Repo behavior summary: the web UI sends the full prospect `name` plus `research_text`, `offer_lock`, and `cta_offer_lock` to the backend; the backend **often doesn’t call an LLM at all** because `build_draft()` switches into **mock mode** unless the runtime mode is exactly `"real"`—and that mock generator is hardcoded to greet with the **full name** and to frame copy around **outbound/pipeline outcomes**, which then “looks like” the model ignored `OFFER_LOCK`. In real mode, the prompt includes `DEEP RESEARCH` verbatim (including “pipeline outcomes” language) right alongside the locks, which biases narrative framing away from the offer even when the offer is locked.

Text diagram (runtime pipeline):

* UI  
  * `web-app/src/main.js` renders fields \+ defaults → on Generate builds payload  
  * `web-app/src/api/client.js`  
    * `POST /web/v1/generate` (creates session)  
    * `GET /web/v1/stream/{request_id}` (streams result)  
* Backend (`hub-api`)  
  * `api/routes/web_mvp.py::web_generate`  
    * validates `WebGenerateRequest` → `create_session_payload(...)` → `save_session(...)` → returns `{request_id, session_id}`  
  * `api/routes/web_mvp.py::web_stream`  
    * loads session → `build_draft(session, style_profile, throttled)`  
* Draft engine  
  * `email_generation/remix_engine.py::build_draft`  
    * **Mode switch**: if `mode != "real"` → `_mock_subject` \+ `_mock_body` (no prompt/model call)  
    * else → `_build_real_draft`  
      * `get_web_mvp_prompt(...)` → `_real_generate(prompt, ...)` → `canonicalize_draft(...)`  
  * Provider wrapper  
    * `email_generation/quick_generate.py::_real_generate` selects provider/model; OpenAI path uses `gpt-4.1-nano`, `temperature: 0`  
* Prompt \+ constraints  
  * `email_generation/prompt_templates.py::get_web_mvp_prompt` (described) injects: SELLER, PROSPECT, DEEP RESEARCH, OFFER\_LOCK, CTA\_LOCK, sliders, plus a “VALIDATION FEEDBACK TO FIX” repair block  
  * Validation guard (at least for “other products mentioned”)  
    * `_offer_lock_forbidden_items(session)` and checks draft text for forbidden items

B) File/Module Inventory (table)

| File / Module | Primary responsibility in current flow | Key functions/notes (as referenced) | Known issues surfaced by symptoms |
| ----- | ----- | ----- | ----- |
| `web-app/src/main.js` | Renders inputs, seeds defaults, builds payload | Defaults include `name: 'Alex Karp'` and `DEFAULT_RESEARCH_TEXT` containing “pipeline outcomes”; payload includes `prospect.name`, `research_text`, `offer_lock`, `cta_offer_lock`, plus `company_context.current_product` and `company_context.other_products`. | Full name passes through; default research biases narrative; duplicated “offer” concepts (offer lock vs current\_product) increase drift risk. |
| `web-app/src/api/client.js` | Calls backend generate \+ stream endpoints | `POST /web/v1/generate` then `GET /web/v1/stream/{request_id}` | UI can’t easily communicate/label “mock vs real” if backend mode differs. |
| `web-app/src/components/EmailEditor.js` | (Referenced) Displays/edit generated email | (Unknown details—confirm by opening file) | Potential mismatch between what was generated vs what user edits/saves. |
| `web-app/src/components/SDRPresetLibrary.js` | Presets UX | (Unknown details—confirm by opening file) | Presets may route through preview pipeline that doesn’t match real generation. |
| `web-app/src/components/SliderBoard.js` | Style sliders | Keys: `formality`, `orientation`, `length`, `assertiveness` | “Outcome-led” orientation can amplify “pipeline outcomes” contamination if research mentions it. |
| `web-app/src/components/presetPreviewUtils.js` | Batch preview utilities | “deriveProofPoints consumes other\_products” (noted) | Mapping/services can leak into copy or “why it works” display. |
| `web-app/src/data/sdrPresets.js` | Preset data | (Unknown details—confirm by opening file) | If presets contain outbound/outcomes phrasing, it contaminates previews. |
| `web-app/src/style.js` / `web-app/src/utils.js` | UI helpers | (Unknown details—confirm by opening files) | Could hide/normalize values in ways that obscure the “real prompt inputs”. |
| `hub-api/api/routes/web_mvp.py` | Generate \+ stream routes | `web_generate` builds session; `web_stream` calls `build_draft(...)` | No explicit surfacing of generation mode to UI; streaming can mask mock behavior. |
| `hub-api/api/schemas.py` | Request schema | `WebGenerateRequest` includes `prospect`, `research_text`, `offer_lock`, `cta_offer_lock`, `cta_type`, `style_profile`, `company_context` | Schema allows duplicated offer fields (offer\_lock \+ company\_context.current\_product). |
| `hub-api/email_generation/remix_engine.py` | Central engine: mock/real switch, prompt call, validation | `build_draft` chooses mock vs real; real path uses prompt \+ `canonicalize_draft`; validation includes forbidden other products check | Mock mode hardcodes greeting and outbound framing; validation appears incomplete for “offer binding” and “CTA exactness” beyond what prompt asks. |
| `hub-api/email_generation/prompt_templates.py` | Prompt contract | Includes SELLER/PROSPECT/DEEP RESEARCH/OFFER\_LOCK/CTA\_LOCK \+ repair block | Deep research is uncontained; mapping context is embedded into SELLER block. |
| `hub-api/email_generation/quick_generate.py` | Provider wrapper and model selection | OpenAI default `gpt-4.1-nano`, `temperature: 0` | No structured-output enforcement; model can still “sound right” while breaking locks. |
| `hub-api/email_generation/model_cascade.py` | Model routing | (Unknown details—confirm by opening file) | Cascade may differ between preview vs real generation. |
| `hub-api/email_generation/preset_preview_pipeline.py` | Preset preview backend | (Unknown details—confirm by opening file) | Likely additional path where “mapping” or “outbound outcomes” copy leaks. |
| `hub-api/main.py` | App wiring | (Unknown details—confirm by opening file) | Where env mode defaults are likely set (critical to fix mock/real confusion). |

Unknowns to confirm quickly (so we don’t “assume”): where `create_session_payload` is implemented; how `mode` is derived and its default; what `preset_preview_pipeline.py` does relative to `/web/v1/generate`; and whether UI has any explicit “mode” toggle today. These can be confirmed by opening the referenced files and searching for `EMAILDJ_QUICK_GENERATE_MODE`, `mode =`, and `/preview` routes.

C) Root Causes (bullet list, each tied to a file/function)

* Greeting includes full name (“Hi Alex Karp”)  
  * Cause: UI seeds `prospect.name` as a full name and passes it through unchanged in the payload.  
  * Cause: mock generator greeting is hardcoded as `Hi {name}` / `Hello {name}` (no first-name derivation step exists in UI or backend).  
  * Architectural gap: no canonical “prospect\_first\_name” field anywhere in the request schema.  
* Outbound/pipeline-outcomes language appears even when `OFFER_LOCK` is Brand Protection  
  * Cause (mock mode): `remix_engine.build_draft` uses `_mock_subject/_mock_body` when `mode != "real"`; those templates are explicitly oriented toward outbound outcomes (“…outbound outcomes… reply quality… conversion lift…”).  
  * Cause (real mode bias): `DEEP RESEARCH` can contain direct instructions like “tie messaging quality to pipeline outcomes… propose a low-friction pilot… measurable reply and conversion lift,” which competes with the offer lock for narrative control.  
  * Trigger amplifier: default UI research text already contains “pipeline outcomes,” so a user can see this behavior even before pasting real research.  
* Mock mode impacts perceived quality (and makes debugging misleading)  
  * Cause: mode switch is inside the draft engine; if not “real,” **no prompt is sent** and the user sees a deterministic template that can’t respect real-world constraints.  
  * UX consequence: UI can look like “the model ignored locks,” but the real issue is “you’re not running the model.”  
* Deep research dominates the narrative even with `OFFER_LOCK`  
  * Cause: prompt places `DEEP RESEARCH` as a big, free-form block right next to the locks; it’s treated as high-authority “context,” not as “facts-only evidence.”  
  * Missing guardrail: no “containment” rule like “research can only supply hook facts; must not change what is pitched.” (Not present in the described constraints list; the constraints focus on not pitching other offerings, but don’t prohibit adopting research’s “pilot/reply lift” framing.)  
* Mapping services leak risk (including preset/preview paths)  
  * Cause: `company_context.other_products` is explicitly injected into prompt under `SELLER.other_products_services_mapping`.  
  * Partial mitigation exists: there is a backend guard that flags “forbidden\_other\_product\_mentioned.”  
  * Leak path: preset preview utilities can intentionally consume `other_products` to derive proof points—meaning “preview” can contaminate “real” expectations, and can push users toward mapping content.  
* Offer binding and CTA binding are not enforced as first-class invariants  
  * Observation: prompt asks for exact CTA and offer lock, and there’s a repair block, but the only explicitly cited validator guard is about forbidden other products (not “must mention OFFER\_LOCK exactly once,” “must not talk about pilots,” “must use CTA\_LOCK as final line,” etc.).  
  * Structural risk: payload includes both `offer_lock` and `company_context.current_product`—a drift vector if they ever diverge.

Risk & Quality Assessment (tied to the above)

* Coherence (entity binding, offer binding): weak name normalization \+ duplicated offer fields → inconsistent greetings and “what are we pitching?” drift.  
* Contamination (internal mapping leakage): passing mapping lists to the LLM creates “temptation tokens,” then you rely on downstream detection to catch leaks.  
* Safety/compliance (claims, incentives, hallucinations): research and mock copy contain performance-lift language (“measurable reply and conversion lift”), which is an objective claim category that generally needs substantiation under truth-in-advertising standards. ([Federal Trade Commission](https://www.ftc.gov/legal-library/browse/ftc-policy-statement-regarding-advertising-substantiation?utm_source=chatgpt.com))  
  * If your CTA types or templates ever include gift cards or cash equivalents, that’s a compliance red flag; many anti-bribery policies explicitly prohibit gift cards/cash equivalents. ([usa.kaspersky.com](https://usa.kaspersky.com/anti-corruption-policy?utm_source=chatgpt.com))  
* UX/product: hidden mode switch means users can’t tell if they’re seeing real generation vs placeholder; defaults bias outcomes; mapping field labeling encourages over-trust in preview.  
* Maintainability: parallel “mock vs real” behavior guarantees divergence; prompt contract \+ validation logic aree

D) TO-BE Architecture Proposal (diagram \+ rules)

Diagram (target pipeline):

* UI (single “Prompt Contract” viellast separated or derived), deep research paste, sliders  
  * Shows: **Mode badge** (“REAL” vs “MOCK”) \+ which model/provider is active  
  * Sends: payload with normalized fields:  
    * `prospect_full_name`, `prospect_first_name` (derived client-side or server-side)  
    * `offer_lock` (single source of truth; remove duplication)  
    * `cta_lock` (single source of truth)  
    * `research_raw` (never treated as instructions)  
    * `research_hooks[]` (optional extracted facts list)  
* Backend  
  * Session build  
  * Normalization layer (deterministic)  
    * First-name derivation \+ greeting normalization  
    * Offer/CTA lock canonicalization  
  * Research containment stage (optional but recommended)  
    * Extract up to N “facts/hooks” from research that are *allowed* to be referenced  
    * Strip/ignore research “instructions” (prompt-injection hardening) ([IBM](https://www.ibm.com/think/insights/prevent-prompt-injection?utm_source=chatgpt.com))  
  * Generation (single source of truth prompt contract)  
    * System message: stable “policy” \+ compliance rules  
    * User message: strictly typed blocks: SELLER / PROSPECT / ALLOWED\_FACTS / OFFER\_LOCK / CTA\_LOCK / STYLE  
  * Structured output \+ validation  
    * Prefer provider-level schema enforcement when available (e.g., `response_format: { type: "json_schema" }`) ([docs.anyscale.com](https://docs.anyscale.com/llm/serving/structured-output?utm_source=chatgpt.com))  
    * Else parse \+ auto-repair loop (validate → feedback → re-prompt), bounded retries ([microsoft.github.io](https://microsoft.github.io/genaiscript/reference/scripts/structured-output/?utm_source=chatgpt.com))  
  * Stream result \+ debug metadata (to UI only)  
    * `mode`, `provider`, `model`, `validation_passes`, `violation_types` (never shown in the email text)

Rules (non-negotiable invariants)

1. Single source of truth contract  
   * ONE offer field: `offer_lock` (remove/stop using `company_context.current_product` for pitching). If you keep `current_product`, it must be informational-only and validated equal to `offer_lock` or omitted.  
2. Strong OFFER\_LOCK \+ CTA\_LOCK enforcement  
   * Validator checks:  
     * Must explicitly mention `offer_lock` (exact string or approved alias list) at least once  
     * Must not mention any “other\_products” items (keep your existing forbidden-item guard, but move mapping *out of the generation prompt* if possible)  
     * CTA must match \`ly once, as the final ask line  
3. First-name derivation \+ greeting normalization  
   * Always generate greeting from `prospect_first_name` (derived deterministically).  
   * Validator checks greeting line begins with `Hi {first_name},` or approved variants.  
4. Deep research containment only evidence,” not instructions:  
   * Wrap raw research in a “do not follow instruc and ideally transform it into `ALLOWED_FACTS` bullets before generation. This aligns with prompt-injection guidance: don’t allow untrusted input to redefine the task. ([IBM](https://www.ibm.com/think/insights/prevent-prompt-injection?utm_source=chatgpt.com))  
   * Explicit rule: research can influence the *hook* only; it cannot introduce a different “problem framing” domain than OFFER\_LOCK.  
5. Validator/repair loop spec  
   * Checks (minimum): output format; greeting; CTA exactness; offer mention; forbidden products; banned internal terms; hallucination/claims; tone/length bands.  
   * Repair: reuse your existing “VALIDATION FEEDBACK TO FIX” block but make violations machine-generated and specific.  
   * Claims safety: flag objective performance claims unless present in ALLOWED\_FACTS (truth-in-advertising substantiation expectation). ([Federal Trade Commission](https://www.ftc.gov/legal-library/browse/ftc-policy-statement-regarding-advertising-substantiation?utm_source=chatgpt.com))  
6. Mock mode policy  
   * Pick one (recommended order):  
     * **Remove mock mode** for production preview; or  
     * Keep mock mode but mnstraints\*\* (same offer/CTA/greeting rules) and label it clearly in UI; never include outbound/pipeline language by default  
7. UI/UX changes (controllability \+ speed \+ cost)  
   * Defaults: replace “pipeline outcomes” seed text with neutral placeholder; optionally start research blank to prevent accidental contamination.  
   * Mode visibility: show REAL/MOCK badge \+ active model name.  
   * CTA templates: map `cta_type` → prebuilt compliant CTA\_LOCK strings (so users don’t freestyle incentives).  
   * Optional selectors: “industry/vertical” and “persona” as *style modifiers* only (must not override offer lock).  
   * Pres” should be generated from the same contract inputs (and must never cite mapping-only data).

E) Prioritized Plan (P0/P1/P2)

P0 — fastest, biggest impact (stop the bleeding)

1. Make generation mode exp intended  
   * What: surface `mode` to UI; ensure non-real mode c \- Where: `hub-api/main.py` (likely where env defaults are set — unknown, confirm), `email_generation/remix_engine.py::build_draft` mode selection, UI header in `web-app/src/main.js`.  
   * Verify (manual): generate once with mode=real and once with mock; UI clearly labels which; mock output no longer used silently.  
   * Risks/tradeoffs: if real mode costs money, you need quotas/throttling UX; but correctness \> placebo.  
2. First-name greeting normalization everywhere (mock \+ real)  
   * What: add deterministic first-name derivation and ensure greeting uses it; add a validator rule for greeting.  
   * Where: `web-app/src/main.js` payload building (adds `prospect_first_name`), `api/schemas.py` (optional new fielsreeting in `remix_engine.py`.  
   * Verify: “Alex Karp” → “Hi Alex,” in both mock and real.  
   * Risks/tradeoffs: edge cases (single names, “Dr. …”, multi-part given names) — handle with a conservative parser and fallback.  
3. Remove outbound/pipeline outcomes hardcoding from mock templates  
   * What: rewrite mock subject/body to be offer-locked and neutral; do not mention “outbound outcomes,” “reply lift,” “pipeline outcomes.”  
   * Where: `hub-api/email_generation/remix_engine.py` mock subject/body logic (cited as outbound-oriented). Fh research about AI → output still pitches Brand Protection and doesn’t talk about outbound/pipeline.  
   * Risks/tradeoffs: mock becomes less “impressive,” but it becomes trustworthy.  
4. Fix default UI seed text that injects the wrong narrative  
   * What: change `DEFAULT_RESEARCH_TEXT` to a neutral placeholder; consider starting it empty.  
   * Where: `web-app/src/main.js` defaults.  
   * Verify: new session starts without “pipeline outcomes” bias.efactor (make it controllable)  
5. Eliminate duplicated “offer” sources (single source of truth)  
   * What: ensure the pitch offer comes from exactly one field (`offer_lock`). If `company_context.current_product` remains, enforce equality or treat as display-only.  
   * Where: `web-app/src/main.js` payload; `api/schemas.py`; `api/routes/web_mvp.py::web_generate` se  
   * Verify: intentionallyjected or normalized deterministically.  
   * Risks/tradeoffs: breaking existing clients; mitigate with a migration period.  
6. Deep research containment (facts-only hooks)  
   * What: stop feeding raw research as “instructional context”; instead extract 2–4 “ALLOWED\_FACTS” and pass only those to the generator (raw stored for traceability). ([IBM](https://www.ibm.com/think/insights/prevent-prompt-injection?utm_source=chatgpt.com)) .py`contract + (new) research preprocessing inside`remix\_engine.py\` real path. Verify: paste research that says “pitch AI outreach” while offer lock is brand protection → email stays on brand protection; only uses safe, factual hooks about the prospect/company.  
   * Risks/tradeoffs: less rich personalization if extraction is too strict; tune “allowed facts” selection.  
7. Expand validator to “offer binding” \+ “CTA binding” \+ “claim safety”  
   * What: add explicit checks beyond forbidden other products: CTA exactness, offer mention, banned phrases, and objective claims.  
   * Where: `remix_engine.py` validation layer \+ existing repair block usagerify: force a failing output (e.g., alternate CTA) → auto-repair produces compliant output within retry budget.  
   * Risks/tradeoffs: overly strict rules can cause extra retries (cost). Keep retries bounded and violations high-signal.  
8. Add structured output enforcement for real-mode (where supported)  
   * What: require a structured response schema for `{subject, body}`; use provider schema enforcement when available, else validate+repair loop. ([docs.anyscale.com](https://docs.anyscale.com/llm/serving/structured-output?utm_source=chatgpt.com))  
   * ider calls.  
   * Verify: no more format drift; parser never fails s: cross-provider differences; fall back gracefully.

P2 — presets, batch preview consistency, telemetry (scale & trust)  
9\) Unify preset preview and single-generate pipelines

* What: ensure preset previews call the same backend contract and validators as real generation; if preview uses mock, label it loudly and keep it constraint-identical.  
* Where: `preset_preview_pipeline.py`, `web-app/src/components/SDRPresetLibrary.js`, `presetPreviewUtils.js`.  
* Verify: “Preview 10” equals “Generate 10” in offer/CTA//tradeoffs: higher cost if previews become real; mitigate with caching and shared research extraction per prospect.  
10. Telemetry: contamination \+ lock-violation dashboards  
* What: log validator violations, retry counts, top contamination tokens (e.g., “pipeline outcomes”), and which path produced the email (mock vs real).  
* Where: `web_mvp.py` stream response metadata \+ `remix_engine.py` validator results.  
* Verify: you can answer “why did this email go off-offer?” from logs in \<30 seconds.  
* ro) Compliance hardening (enterprise SDR)  
* What: add rule sets that prevent unsubstantiated performance claims and disallow cash-equivalent incentives in CTAs; align copy with truthful advertising expectations. ([Federal Trade Commission](https://www.ftc.gov/legal-library/browse/ftc-policy-statement-regarding-advertising-substantiation?utm_source=chatgpt.com))  
* Where: validator rules \+ CTA template library.  
* Verify: attempts to generate “gift card” CTAs are blocked; “reply lift” claims are flagged unless supported by provided facts.

