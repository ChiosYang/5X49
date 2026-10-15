# AI Film finder phase one quality

## 2026-10-15 evaluation compatibility update

The evaluator now supports the locked SDK's typed dictionary responses and
pins the official exact alias/canonical mapping. Audited reconciliation is
transactional and idempotent, retains prior failure evidence, and preserves a
blocking independent-review hold. A targeted, audited release entrypoint verifies
independent review and exact CI/head evidence before any state transition;
transport-error diagnostics preserve the original failure across settlement.
A singleton, user-approved conservative-continuation path retains one complete
reservation permanently while leaving its actual cost unknown; this addition
awaits independent review. All 71 focused Ask regression tests pass.
The original canary's strict JSON and completion-receipt validation
remain incomplete; no bilingual live accuracy gate has passed.
See [technical review status](ask-phase-one-cloud-20261015.md).

## Evidence classes

`backend/app/evaluation/fixtures/ask_acceptance.json` contains 58 bilingual
cases: 36 supported plans (including ambiguous Person names and empty matches),
10 unsupported/negated requests, 4 clarifications, 2 synthetic privacy cases,
2 interface failures and 4 malicious response fixtures. Supported parsing target
is >=95%; unsupported requirements must never silently disappear. The live gate
also requires zero rejected-case failures; accuracy cannot excuse dropped requirements. Local query
tests separately check the confirmed plan against synthetic canonical facts.

Offline evaluation checks the fixture/validation contract and error boundary,
not a model's understanding. It reports live_supported_accuracy=null and no paid
cost. Real backend UI E2E substitutes only provider transport; SQLite projections,
fact resolution, query routes, pagination and Film cards remain real.

## Offline command

From backend with dotenv disabled and SQLITE_DB_PATH/MEDIA_DIR pointed to owned
temporary paths (never the active library):

```powershell
uv run --no-sync python -X utf8 -m app.evaluation.ask --output <temporary-report.json>
uv run --no-sync python -X utf8 -m unittest test_ask test_ask_evaluation test_explore_query test_library_filters -q
```

## Explicit live evaluation

The live entrypoint requires explicit authorization and a process-provided
OPENROUTER_API_KEY. The entrypoint never loads credential files or modifies
credentials, settings, global model selection, media or Library data. Fixed model
deepseek/deepseek-v4.1-flash; provider decart/fp4. Official endpoint directory is
checked on every run, followed by a read-only existing-credit check. Unknown
balance, nonzero request fee, excess price, unavailable parameters/model/provider
or missing key stops before inference. No top-up is supported.

```powershell
uv run --no-sync python -X utf8 -m app.evaluation.ask --live --canary-only --authorization I_AUTHORIZE_SYNTHETIC_OPENROUTER_TESTS_WITHIN_1_USD_TOTAL --budget-usd 1 --output <canary-report.json>
# Run the corpus only after reviewing the successful canary evidence:
uv run --no-sync python -X utf8 -m app.evaluation.ask --live --authorization I_AUTHORIZE_SYNTHETIC_OPENROUTER_TESTS_WITHIN_1_USD_TOTAL --budget-usd 1 --output <live-report.json>
```

Each run also checks its first supported case as a canary; malformed/incompatible
JSON stops that run. No automatic inference retries. Synthetic privacy cases are
blocked before inference; transport/malicious-response cases remain offline-only.
The report records case IDs, failure classes, complete parsed plans, latency,
requested/returned model versions, token counts and corroborated billing evidence.
It excludes questions, credentials and raw provider bodies.

Provider policy has only=[decart/fp4], allow_fallbacks=false,
require_parameters=true, max_price={prompt:0.10,completion:0.20,request:0}
(prices per million tokens) and reasoning.enabled=false. Output<=1600 tokens.
Input bound uses complete UTF-8 text bytes plus 1024 role/framing tokens, never
a character/word estimate; requests exceeding 8000 are refused. Returned token
counts and zero reasoning tokens must corroborate this bound. Actual cost and
provider/model are corroborated through generation metadata.

The fixed ignored backend/.evaluation-artifacts/ask-live-budget.sqlite3 ledger
persists across all runs. **Do not delete, replace or reset it to repeat testing.**
For billing it also reserves the entire verified 1,048,576-token model context
at the price cap plus 1600 output tokens,
even though the synthetic text bound is <=8000. This absolute fallback protects
the lifetime budget from tokenizer/framing assumptions. Existing credits are
checked before every paid attempt. Settled actual costs release unused reserves.
SQLite transactions reserve maximum input+output cost before transport and
prevent concurrent paid attempts. Costs are actual usage.cost, with generation
IDs; unresolved/crashed/failed requests retain reservations and block later runs.
The separate singleton conservative-approval mode may exempt only one precisely
bound transport failure from blocking, while permanently retaining its full
reserve and unknown actual cost. It cannot exempt any future unknown.
Reservation overruns or token/reasoning contract failures block future runs.
The configured conservative stop is US$0.75 and the lifetime hard limit is US$1,
including canaries, failures and any separately authorized retries.

## Current results

- Offline fixture contract: 58/58 passed; 71 focused Ask regression tests passed (including the zero-unsupported-failure gate and transport diagnostics).
- The original canary did not complete strict JSON and completion-receipt validation.
- Live supported parsing accuracy and usefulness remain unaccepted. Offline
  success and accounting recovery must not be reported as the >=95% model gate.
- Complete backend replay on 2026-10-15: `uv run --no-sync python -X utf8 -m unittest discover -s . -p test_*.py -v` — 438 tests, 3 conditional skips, passed; includes all 12 evaluation/budget tests.
- Frontend `npm run test:unit` — 95 passed; `npm run lint` and `npm run typecheck -- --incremental false` passed.
- `npm run test:e2e` — production build and all 95 real-backend browser tests passed (including 21 Ask tests). English/Chinese, 1440px desktop and 390px narrow layouts were inspected. Existing four-entry Explore first-screen and transparent navigation checks remain passing.
- Python `compileall -q app`, backend Skill validation and `git diff --check` passed.
- Release-tooling tests: 15 run, 12 passed, 1 conditional skip; two Compose checks cannot run locally because Docker CLI is absent. No Docker/release configuration was changed. GitHub CI runs these on its Docker-equipped Linux runner.
- Windows test environment: long temp paths failed backup rehearsal; an 8.3 alias failed media-boundary comparison. The successful run used a short canonical C:/Users/Administrator/AppData/Local/Temp/5x49-unit-task3 directory. A long D-drive replay was stopped after 20 minutes and replaced with visible per-test progress.
- Existing saved-read E2E now gates streamed document refresh before its deliberately failed GET; otherwise the Library event stream could legitimately reconcile props before the stale-props assertion. This changes only test timing, not product behavior.
- Synthetic screenshots: frontend/e2e-artifacts/ask-desktop-zh.png and ask-narrow-zh.png (ignored local evidence).


## Independent review follow-up (2026-10-15)

- Interpretation/retry requires current consent and a public identity of the actual
  frozen model/base URL. Changed targets fail before constructing a provider client.
- Explore recovery uses normalized query plus browser history-entry identity;
  different deep links/fresh entries retain their fact filters, while source
  Film Back revalidates only that entry's confirmed conditions.
- Quantity syntax covers all English cardinal words and compounds, a/an articles,
  common fractions, decimals and abbreviated/compact units. A 19-quantity by
  four-comparison matrix verifies 76 unchanged provider payloads. Actual OR,
  negation, unsupported style and vague length remain blocked. Eight comparison
  fixture additions extend the corpus from 50 to 58 (36 supported).
- The first post-review Linux run (head 5ad87e61, run 38667509491) exposed an
  initialization race: scope discovery could collapse the composer between focus
  and input, hiding consent despite a nonempty question. The local replay also
  reproduced it. Initial source recovery now gates input readiness; first scope
  discovery does not clear interaction state, and nonempty questions keep the
  composer expanded. A deterministic E2E blocks JavaScript hydration to verify
  the SSR input remains unavailable until recovery completes. No blind CI rerun
  or timeout increase masks the fault.
- Final replay: all 438 backend tests passed (3 conditional skips), 58/58 fixture
  cases, 95 frontend unit tests, lint/typecheck, production build and all 95 real
  backend UI tests passed, including 21 Ask flows and both new regressions.
- Live accuracy and usefulness remain unaccepted. Independent review and a
  fresh passing canary are required before the bilingual live corpus.
