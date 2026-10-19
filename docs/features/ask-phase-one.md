# AI Film Finder phase one

Status: Blocked
Last updated: 2026-10-19
Related: Ask MVP; Factual Explore
The core engineering baseline was independently reviewed and locally accepted.
The current permission-hardening and UI-integration follow-up has completed
offline verification and awaits final independent review. Earlier Windows
tooling, editor-focus and historical-reconciliation follow-ups remain recorded.
The 52-case live model quality suite has not run; a fresh passing canary and
unchanged quality/billing gates remain required. The six simulated fault/format
controls passed offline. PR #28 remains draft.

## Goal

Interpret a Chinese/English question on the dedicated `/ask` page, let the user
edit and confirm the entire plan, then show owned Films with verifiable local
match reasons. Explore retains its ordinary compact input and factual browsing.

## Scope

- Reuse Ask and factual Explore, preserving genre/person role/country/decade,
  watched state and title/year sorting.
- Add exact effective duration and Film personal overall stars (1–5), with
  unknowns excluded only when the corresponding condition is active.
- Provider disclosure/consent, bounded validation, timeout, manual fallback,
  cancellation and stale-response protection; no inferred Analysis V2 edges.
- 58 bilingual acceptance cases and offline fixture evaluation. A separate
  live evaluation entrypoint must require explicit authorization and budget.

## Decisions

- Duration uses positive primary-edition video seconds, then positive Film
  runtime minutes. Inclusive/exclusive minute bounds compare exact seconds.
- Rating is FilmProfileState.rating; external or per-Viewing scores never fill it.
- A model receives only the question and static schema. No library/path/note
  context is attached. Unsupported/ambiguous requests must not become queries.
- Zero results offer condition removal, followed by another review/confirmation.
- Single configured model, one provider request, no retries or model routing.
- Evaluation-only provider/model remains deepseek/deepseek-v4.1-flash on
  OpenRouter decart/fp4, with the exact official canonical slug pinned.
  Cumulative limits, request reservations and reconciliation apply across
  retries; accounting recovery never grants permission for further inference.

## Explore entry simplification (2026-10-19)

Explore no longer mounts the embedded Ask component. The compact "Find a film"
input remains editable; focus, typing and Enter do not expand a mode selector,
open a manual condition form, hide factual exploration, restore an Ask session,
or issue any Ask API request. It has no bound submit action and shows no search
success or result claim. Connecting that input to search requires a separate
product decision. The superseded input/button alignment change is not retained.

The dedicated `/ask` page, navigation-menu Ask entry and search-page Ask link
remain available. Their provider consent, editable conditions, explicit local
confirmation, cancellation, retry protection and backend capabilities remain.
Explore's existing "Find a fact" picker, lenses, filters, Film deep links and
history remain factual browsing controls. Large titles and transparent navigation
are preserved. English/Chinese desktop and narrow checks verify no ghost mode
buttons, focus-induced layout shift, hidden content or Ask requests.

## Acceptance criteria

- [x] Review/edit/confirm/cancel/return and zero-result relaxation are explicit.
- [x] Exact numeric bounds, null semantics and facts match confirmed conditions.
- [x] Unsupported/negated/similar/taste requests never silently broaden results.
- [x] Privacy, malicious output and interface failure cases fail closed.
- [x] Complete backend/frontend checks and real-backend responsive UI E2E pass.
- [x] Draft PR [#28](https://github.com/ChiosYang/5X49/pull/28) is delivered; independent review of the engineering follow-ups completed, with exact-code CI passing.
- [ ] Fresh passing canary and full 52-case live quality suite, including supported parsing accuracy >=95%, zero rejected-case failures and strict JSON/identity/usage validation.

## Slices

1. Acceptance corpus and backend contract/query — complete.
2. Standalone Ask interaction safety and simplified Explore input — complete.
3. Evaluation guards and offline verification — complete; draft PR delivered; independent-review follow-up and complete offline replay verified.
4. Live synthetic evaluation — blocked pending a fresh passing canary and
   the full 52-case suite. Strict JSON and bilingual live quality remain unaccepted;
   unknown/reservation stops continue to apply.

## Verification evidence

- Windows acceptance on the reviewed code baseline `adcbc606`: 497 backend tests (3 platform skips), 94 focused Ask/evaluation regressions, 58/58 offline fixtures, 97/97 frontend units, lint/typecheck/production build and 95/95 real-backend E2E, including 21 Ask flows. Provider transport is mocked in browser E2E.
- The six simulated interface/malicious-response controls passed offline 6/6. The 52-case live suite was not run and no live parsing/strict-JSON quality gate is claimed.
- [CI 39190324783](https://github.com/ChiosYang/5X49/actions/runs/39190324783) passed all three jobs on the exact reviewed runtime baseline. Desktop/narrow English/Chinese inspection preserved the large title and transparent navigation.
- Details and exact commands: [quality evidence](../quality/ask-phase-one.md).
- Historical compatibility review: [technical status](../quality/ask-phase-one-cloud-20261015.md).
- Evaluation/reconciliation/review-release/diagnostics: 94 focused Ask tests passed, covering
  SDK parsing, exact identity verification, audited/idempotent accounting
  recovery, precise review/CI binding, preservation of other unknowns and
  sanitized transport errors that survive settlement failures, and a singleton
  conservative continuation that retains unknown cost/full exposure and cannot
  exempt subsequent failures.
- Receipt lookup regressions use the real SDK with simulated transport to verify
  routing/query parameters, bounded reads and clear separation of completion
  receipt failures from model-response failures; budget protection is unchanged.
- Self-review fixed atomic query snapshots, person-choice/editor race, stale responses and the zero-unsupported-failure evaluation gate. No live model quality is claimed.

## Remaining risks

- Full live quality/usefulness, strict JSON and usage corroboration remain
  unverified. The fixed model/provider identity and reconciliation protections
  are implemented and reviewed, but a fresh passing canary and full 52-case
  completion are outstanding. Offline and real-backend UI results do not satisfy
  the live model gate. Unknown/reservation blocking and per-run authorization
  requirements remain unchanged; postponing provider diagnosis grants no bypass.

## Additional conservative authorization follow-up

One extra evaluation-only approval path is implemented for independent review.
It requires an exact target fingerprint, a complete existing-ledger snapshot,
a distinct explicit user approval and matching review/CI evidence. It appends
one optional singleton audit without changing the original singleton, original
history, unknown costs or full reservations. Concurrent identical approvals
are idempotent; different/future unknowns cannot acquire further exemptions.
The next complete reservation still obeys both cumulative limits.

This delta adds 21 synthetic regressions; the complete backend replay passed
518 tests with 3 platform skips. It uses only synthetic ledgers and mocked
provider transport in verification. It does not apply the new permission to real accounting or start
model inference. Review and exact-head CI remain prerequisites for application;
a fresh passing canary and the full 52-case live quality gate remain outstanding.

## Independent review corrections

- Recognize explicit English quantity syntax (articles, full cardinal vocabulary and compounds, common fractions, decimal and abbreviated units) while retaining real OR/ambiguity guards. A 19-quantity/four-comparison backend matrix covers 76 unchanged provider payloads; six added fixture expressions have real-backend UI coverage.
- Bind each interpretation and retry to current consent and the actual provider target.
- Historical embedded Explore recovery was scoped to normalized fact queries and history entries; the embedding is now removed. Navigation tests instead verify that factual Explore never restores or sends Ask plans.
- Preserve existing local changes and saved test evidence through execution-environment outages.

- Historical embedded composer behavior (removed by the 2026-10-19 simplification): initial source recovery gates composer readiness; first history-scope discovery never clears initial interaction state. Nonempty questions retain consent controls. Deterministic blocked-hydration E2E covers the Linux-discovered first-input race.


## Private response checkpoint and offline recovery

The synthetic live evaluator saves an allowlisted response before its first
receipt lookup. A same-directory, fsynced temporary file is atomically published
without replacing an existing checkpoint. Save failure records an unknown paid
attempt at its full reservation and stops before receipt lookup or another POST.
The receipt-failure behavior, budget limits, model/provider policy and inference
retry policy are unchanged. Application API responses and frontend styling are
unchanged; production Ask does not log model content.

The private checkpoint binds the exact attempt/run/case, locale, complete case,
request and prompt digests, corpus bytes, preflight and Git/source-file identity.
Only response ID/model, content, finish reason and selected usage fields are
retained. Requests, prompt/question text, credentials, headers and arbitrary SDK
fields are excluded. Response content remains private under the ignored
`.evaluation-artifacts/ask-response-checkpoints/` directory.

`--resume-report` is an offline evidence check for one saved failed canary.
It requires independently retained original-report and receipt file hashes;
the original report anchors the checkpoint's hash. It verifies identities,
receipt/token arithmetic and the recorded usage, then passes the same saved
content through the existing interpreter and compares its plan with the bound
case. It opens no ledger or provider client and writes only a new private result.
It never changes the failed report, settles costs, releases review, grants a
continuation or retries inference. A valid receipt cannot turn invalid JSON or
missing original usage into a passing response.

No lost completion can be reconstructed retrospectively. Earlier failures
without a checkpoint remain unavailable for offline quality checks. Independent
review of supplied evidence is still required before any separately authorized
accounting/release or subsequent live work; this change adds no budget exception.

## Integrated local follow-up verification (2026-10-19)

- Create checkpoint temporary files with owner-only mode in the creation syscall;
  20 checkpoint tests include empty/exclusive creation and a permissive-umask
  subprocess. Windows inherits existing ACL restrictions; POSIX verifies `0600`
  before any response bytes are written.
- Ordinary merge of main `a01049e6` retains the Library four-column desktop grid,
  filter drawer and pointer/keyboard/touch inspector. Ordinary integration of
  Explore copy cleanup `9a1b4637` keeps helper text removed and preserves the
  accessible hidden journey label. The standalone Ask implementation is unchanged.
- Windows offline backend: 538 tests, 3 platform skips; frontend: 98 unit tests,
  lint, typecheck and production build; real-backend browser acceptance: 111/111.
  This includes 25 Ask/input checks, six bilingual Explore layout/filter checks,
  four-column Library and drawer interactions, backup recovery and restart flows.
- Browser and backend tests use isolated synthetic state and substituted provider
  transport. No real ledger operation or model request is part of this follow-up.
  The retained Explore input is not bound to submission.
- Use canonical system TEMP for Windows browser fixtures. A long workspace TEMP
  path exceeded the platform limit for generated backup manifests; the same
  synthetic flow and full suite passed with the shorter temporary root. Product
  backup behavior and timeouts were not changed.
