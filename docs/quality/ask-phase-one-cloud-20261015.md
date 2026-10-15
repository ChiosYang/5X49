# PR #28 evaluation compatibility and review status

Status: **Blocked pending independent review and a passing canary.**
The bilingual live acceptance gate has not passed.

## Technical changes

- SDK credits/generation lookups use `dict[str, object]`, matching the locked
  OpenAI SDK response parser. Regression tests use the real SDK with synthetic
  `httpx.MockTransport` responses.
- The evaluator pins `deepseek/deepseek-v4.1-flash` and its exact official
  canonical ID, `deepseek/deepseek-v4.1-flash-20260910`. Public model metadata
  must explicitly establish this mapping on every preflight. Missing,
  duplicate or changed mappings stop before inference; no prefix matching,
  inferred dates or automatic version upgrades are accepted.
- Provider routing is restricted to `decart/fp4`, with fallback disabled,
  parameters required and reasoning disabled. Generation identity, native
  token bounds and zero reasoning must corroborate the completion receipt.
- Normal evaluation requires completion `usage.cost` to match the generation
  receipt before the response reaches strict JSON validation.

## General reconciliation and budget controls

The fixed ignored evaluation ledger persists across runs and retries. It must
never be deleted, replaced or reset to repeat testing. Maximum request exposure
is reserved transactionally before transport. Unresolved requests retain their
reserve and stop subsequent attempts; configured stop and lifetime limits apply
cumulatively.

Historical reconciliation uses only official metadata and generation GETs.
It checks the original attempt/run/generation, exact model mapping, provider,
price evidence, native usage, token bounds, zero reasoning, cache conditions and
completion status. The independently calculated amount must match the supplied
expected amount and authoritative receipt. Missing or inconsistent evidence
retains the stop state.

A successful transaction retains the original failure and reserve, writes an
audit row with prior state, allowlisted evidence, digest and timestamp, and
accounts the verified amount exactly once. Stable evidence makes repeated and
concurrent reconciliation idempotent. Accounting recovery keeps a blocking
review hold and cannot authorize another model request.

Operational credential state, account details and actual test billing records
are excluded from this technical report. Private receipts and the continuous
ledger remain in the ignored evaluation-artifacts directory.

## Targeted review-hold release

The separate `--release-review PRIVATE_APPROVAL_JSON` mode requires the explicit
`I_AUTHORIZE_RECONCILED_REVIEW_HOLD_RELEASE` authorization. It is mutually
exclusive with inference and reconciliation modes and never constructs a model
client. The private approval must bind one attempt and reconciliation digest to
an independent review reference, exact reviewed commit and CI run.

Before opening the ledger, verification requires a clean working tree, the
reviewed commit as an ancestor, and only documentation changes after that
commit. The official repository CI workflow must have completed successfully
for the exact reviewed head and this PR; its run ID and attempt are audited.
Unavailable or inconsistent evidence
stops the operation.

The transaction releases only the reconciled target's review hold. Original
attempt, generation, failure, reservation, accounting and reconciliation records
are retained. A new release audit stores the review/CI evidence, reconciliation
digest, prior state and timestamp. Repeated/concurrent release is idempotent;
unreconciled attempts, other unknowns and new contract failures remain blocked.
This path still requires independent review before operational use.

## Validation and unmet acceptance

- 31 evaluation/budget/reconciliation/review-release tests passed, including real SDK parsing,
  exact alias/canonical mapping, wrong-model/provider/receipt rejection,
  inconsistent usage/reasoning, failed reconciliation, replay and concurrency.
  Release tests additionally cover exact CI/head binding, unreviewed code,
  documentation-only followups, targeted state changes and surviving unknowns.
- The focused Ask regression family passed all 54 tests.
- The 58/58 offline fixtures validate the contract and error boundary; they do
  not measure real model understanding.
- The original canary did not complete strict JSON and completion-receipt
  validation. Compatibility/accounting repairs do not retroactively pass it.
- Live supported parsing accuracy >=95% and the zero rejected-case failure
  gate remain unaccepted. No full bilingual live acceptance pass is claimed.
- Independent parent review and explicit authorization are required before a
  fresh canary. A passing canary must precede the bilingual corpus.
- Product behavior, application data and Analysis V2 visibility are unchanged.

See [phase-one quality](ask-phase-one.md) for the fixture contract, general
execution controls and prior engineering verification.
