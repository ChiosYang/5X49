# AI Film finder phase one quality

## Acceptance status (2026-10-19)

Engineering checks pass on the reviewed Windows code baseline
`adcbc606878e69a68e8f10af1bcc85aa4bfb00d0`. The completed local checks identify
no remaining provider-independent functional blocker. The large title,
transparent navigation and explicit review/confirm workflow are preserved.

Live model quality remains unaccepted. The fresh canary did not complete the
required provider/response validation, so the 52-case live suite was not run.
The six interface-failure/malicious-response controls passed offline and are
not live model evidence. Keep PR #28 draft: supported parsing accuracy >=95%,
zero rejected-case failures, strict JSON and model/provider/usage corroboration
remain required. Existing unknown/reservation stops remain binding; postponing
provider diagnosis does not authorize another request or change these gates.

## Historical evaluation compatibility update (2026-10-15)

The evaluator now supports the locked SDK's typed dictionary responses and
pins the official exact alias/canonical mapping. Audited reconciliation is
transactional and idempotent, retains prior failure evidence, and preserves a
blocking independent-review hold. A targeted, audited release entrypoint verifies
independent review and exact CI/head evidence before any state transition;
transport-error diagnostics preserve the original failure across settlement.
A singleton, user-approved conservative-continuation path retains one complete
reservation permanently while leaving its actual cost unknown. At that snapshot the shared
receipt-reader update awaited independent review and added allowlisted
query traces and distinguished a returned completion object from an unverified
receipt, without increasing retries or changing budget stops. All 82 focused
Ask regression tests pass.
The original canary's strict JSON and completion-receipt validation
remain incomplete; no bilingual live accuracy gate has passed.
See [historical technical review status](ask-phase-one-cloud-20261015.md).

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

## Current engineering results (2026-10-19)

These checks cover the runtime code at `adcbc606878e69a68e8f10af1bcc85aa4bfb00d0`;
subsequent acceptance-document edits do not change that runtime baseline.

- Backend full replay: 497 tests, OK with 3 platform-conditional skips, using
  `uv run --no-sync python -X utf8 -m unittest discover -s . -p test_*.py -v`.
  The focused Ask/evaluation/accounting regression group passed 94 tests.
- Offline bilingual fixture contract: 58/58 passed. The separately replayed
  six interface/malicious-response controls also passed 6/6 with mocked transport.
- Frontend: `npm run test:unit` passed 97/97; `npm run lint`,
  `npm run typecheck -- --incremental false` and production build passed.
- Real-backend browser E2E: 95/95 passed, including 21 Ask flows. Only provider
  transport is replaced; routes, SQLite facts, resolution/query, Film cards,
  pagination and browser history remain real.
- Manual English/Chinese inspection at 1440px desktop and 390px narrow widths
  preserved the large title, transparent navigation and local fallback flow.
- Backend `compileall -q app` and `git diff --check` passed. No dependency or
  lockfile update was needed for the Windows follow-ups.
- [CI 39190324783](https://github.com/ChiosYang/5X49/actions/runs/39190324783)
  passed Backend, Frontend and Real API E2E for that exact code baseline.
  Docker CLI is unavailable on this Windows host; Compose/release-tooling
  checks passed on the Linux CI runner. Platform-specific filesystem skips
  are retained rather than counted as executed coverage.

The reviewed follow-ups are separately committed: Windows cross-drive Next
ESLint root resolution (`4df4d901`), deferred Ask editor focus respecting the
user's next field (`4c224836`), and exact reconciliation target selection from
an unchanged cumulative report with existing-ledger safeguards (`adcbc606`).
The focus regression controls frame completion; it does not relax timeouts or
add inference retries.

## Live quality evidence still required

The corpus has 58 cases. The formal live runner selects 52, with synthetic
privacy/intent guards still applied before provider access. The other six
interface/malicious-response cases are offline-only fault injections. Neither
58/58 fixture success nor 95/95 real-backend browser E2E establishes model
understanding or a successful live canary.

A fresh passing canary, full 52-case completion, supported parsing accuracy
>=95%, zero rejected-case failures, strict JSON and corroborated identity/usage
remain required. No full live quality result is claimed. Accounting recovery
and review-hold release do not establish this gate or exempt later unknowns.

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


## One additional exact conservative continuation

The original task-wide singleton remains unchanged. A separately approved
`--continue-additionally` mode can append at most one additional authorization
for an exact transport-failure attempt after the original slot is consumed.
This implementation is submitted for independent review; this change does not
apply an authorization to a real ledger or perform inference.

The private approval uses version `ask-additional-conservative-approval.v1`
and scope `one_additional_transport_failure_full_reserve_permanent`. It binds
`attempt_id`, its complete-row `attempt_sha256`, the existing file's
`ledger_sha256`, a distinct `user_approval_ref` and UTC `user_approved_at`,
`user_confirmed=true`, and the reviewed head, successful CI run and review ref.
Use the explicitly approved snapshot; do not substitute a new target or revise
the snapshot hash to make a failed approval pass.

```powershell
uv run --no-sync python -X utf8 -m app.evaluation.ask --continue-additionally <private-approval.json> --authorization I_AUTHORIZE_ONE_ADDITIONAL_TRANSPORT_FAILURE_AT_FULL_RESERVE --output <private-result.json>
```

The command uses only the existing default ledger and cannot combine with
`--live` or redirect its path. It verifies review/CI before any optional schema
write, opens with existing-only `mode=rw`, then checks the whole-file hash under
`BEGIN IMMEDIATE` with delete-journal mode. The latest attempt must match the
approved fingerprint, be a distinct transport-failure unknown with its complete
reservation, and be the only unexempted unknown. The next complete reservation
must still fit both cumulative limits.

Only this explicit transaction creates the optional
`additional_conservative_continuation` singleton audit. Ordinary startup and
reconciliation never create it. All four original tables, original approval and
unknown cost/state/reservations remain unchanged. The audit stores the complete
original four-table logical snapshot and its bound digest. Later reads verify
that history as an unchanged prefix while allowing newly appended attempts.
The exact approval is idempotent; a different approval cannot consume another
additional slot. Both complete reservations remain permanently in exposure;
any other or later unknown still blocks. The original stop/hard limits, fixed
route, no-fallback policy and no automatic inference retry remain unchanged.

Synthetic verification for this delta: 21 new additional-path tests; 31 combined
new/original-singleton tests; full backend replay 518 tests with 3 platform skips;
58/58 offline fixture contracts, Python compilation and diff checks passed.
Provider clients are mocked in these tests. No real authorization is applied by
this change, and independent review of the delta is still pending.

Independent review and matching CI must precede any real application. Applying
this command records approval only and performs no inference. A fresh canary
must pass before the separate 52-case live suite; a new failure stops again.

## Selecting a historical reconciliation target

Only `--reconcile-report` accepts `--attempt-id` and `--ledger-path`. A report
containing several historical attempts requires one explicit ID matching exactly
one original row and the saved canary run/case. A one-attempt report can retain
its implicit target. Repeated options, unknown or duplicate IDs, and attempts
from another run fail before provider access.

The full original report is passed unchanged to verification and hashing; never
crop a cumulative report to make it look like a single attempt. An explicit
ledger must already exist with the expected core schema (and, if present, only
the recognized additional singleton audit table). Reconciliation
uses SQLite `mode=rw` on every connection, verifies schema/integrity, and refuses
missing, incompatible or unexpected write-hook schemas without initializing or
migrating them. The default reconciliation ledger must already exist as well.
These options are rejected in live, offline, review-release and continuation
modes, and cannot redirect the live budget ledger.

After separate authorization to record an accounting recovery, the CLI shape is:

```powershell
uv run --no-sync python -X utf8 -m app.evaluation.ask --reconcile-report <original-canary.json> --attempt-id <exact-attempt-id> --ledger-path <existing-ledger.sqlite3> --expected-cost-usd <verified-cost> --output <private-reconciliation.json>
```

This command reads official receipt metadata and then **writes** only the target's
verified cost and reconciliation audit, retaining its original reserve/outcome
and a blocking review hold. It does not release review, consume another
continuation, rewrite other unknowns, or authorize inference. Read-only dry-runs
should use the pure verifier rather than this mutating command. Private reports,
receipts, ledger files and actual runtime identifiers stay outside Git.
