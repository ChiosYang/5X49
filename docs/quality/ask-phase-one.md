# AI Film finder phase one quality

## Evidence classes

`backend/app/evaluation/fixtures/ask_acceptance.json` contains 50 bilingual
cases: 28 supported plans (including ambiguous Person names and empty matches),
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

Only after user authorization and an existing, safely exported
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
at the price cap plus 1600 output tokens (US$0.1051776 per in-flight request),
even though the synthetic text bound is <=8000. This absolute fallback protects
the lifetime budget from tokenizer/framing assumptions. Existing credits are
checked before every paid attempt. Settled actual costs release unused reserves.
SQLite transactions reserve maximum input+output cost before transport and
prevent concurrent paid attempts. Costs are actual usage.cost, with generation
IDs; unresolved/crashed/failed requests retain reservations and block later runs.
Reservation overruns or token/reasoning contract failures block future runs.
The conservative stop is US$0.75; the user's lifetime task hard limit is US$1,
including canaries, failures and any separately authorized retries.

## Current results

- Offline fixture contract: 50/50 passed; 12 evaluation/budget tests passed (including the zero-unsupported-failure gate).
- Live canary preflight: blocked before any inference because an existing
  exported OPENROUTER_API_KEY is missing in this execution environment.
- Actual paid model requests in this task: 0. Actual model spend: US$0.
- Live supported parsing accuracy, actual provider latency/cost, and usefulness
  are unverified. Offline success must not be reported as the >=95% model gate.
- Complete backend: `uv run --no-sync python -X utf8 -m unittest discover -s . -p test_*.py -v` — 435 tests, 3 conditional skips, passed. The final evaluation-gate addition was then verified by `uv run --no-sync python -X utf8 -m unittest test_ask_evaluation -q` — 12 passed.
- Frontend `npm run test:unit` — 93 passed; `npm run lint` and `npm run typecheck -- --incremental false` passed.
- `npm run test:e2e` — production build and all 87 real-backend browser tests passed (including 13 Ask tests). English/Chinese, 1440px desktop and 390px narrow layouts were inspected. Existing four-entry Explore first-screen and transparent navigation checks remain passing.
- Python `compileall -q app`, backend Skill validation and `git diff --check` passed.
- Release-tooling tests: 15 run, 12 passed, 1 conditional skip; two Compose checks cannot run locally because Docker CLI is absent. No Docker/release configuration was changed. GitHub CI runs these on its Docker-equipped Linux runner.
- Windows test environment: long temp paths failed backup rehearsal; an 8.3 alias failed media-boundary comparison. The successful run used a short canonical C:/Users/Administrator/AppData/Local/Temp/5x49-unit-task3 directory. A long D-drive replay was stopped after 20 minutes and replaced with visible per-test progress.
- Existing saved-read E2E now gates streamed document refresh before its deliberately failed GET; otherwise the Library event stream could legitimately reconcile props before the stale-props assertion. This changes only test timing, not product behavior.
- Synthetic screenshots: frontend/e2e-artifacts/ask-desktop-zh.png and ask-narrow-zh.png (ignored local evidence).
