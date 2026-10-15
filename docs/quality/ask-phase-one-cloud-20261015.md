# PR #28 cloud live acceptance — 2026-10-15

Result: **Blocked at the canary; bilingual live acceptance was not run.**
Read-only reconciliation is now complete: the same ledger records the known
US$0.00012861 cost once and retains a blocking review hold. No new inference
was performed during the compatibility/reconciliation repair.

## Source and isolation

- Repository: `/workspace/5X49`, branch `ai/pr28-cloud-acceptance-20261015`.
- Base HEAD: `9979562b425021bc9bb5855a9c0f0145e6e20d90`, the requested PR #28 head.
- Python: backend virtual environment 3.13.5. `uv sync --project backend --locked`
  installed the missing locked `psutil==7.2.2`; no lockfile changed.
- Dotenv disabled. SQLite and media environment targets were owned temporary
  paths under `/tmp/5x49-pr28-acceptance`. No application/library database,
  media, notes, credential files or global model settings were read or changed.
- Only the existing environment credential was used for OpenRouter requests.
  No credential contents were printed, saved, configured or transferred.
- No merge, deployment, top-up, Analysis V2 operation or new inference retry.

## Guard verification and scoped repair

The original 12 evaluation/budget tests passed. The existing fixed ledger was
absent in this cloud checkout. Its starting point was the explicitly confirmed
historical task total of zero requests and US$0; it was created at the existing
fixed path `backend/.evaluation-artifacts/ask-live-budget.sqlite3` and retained.

The original canary invocation (`pr28-cloud-canary-20261015-01`) stopped before
inference with `credit_balance_unavailable`. Read-only diagnosis identified an
SDK parsing error: `cast_to=dict` reaches `openai._models.construct_type`, which
requires dictionary type arguments in the installed locked SDK 2.36.0.

The initial evaluation implementation repair changes the three credits/generation
lookups to `cast_to=dict[str, object]`. A regression test uses the real SDK with
`httpx.MockTransport` and synthetic credits, completion and generation responses;
it makes no network calls. The live evidence below uses that evaluation-only
patch over the stated base HEAD, rather than claiming the original evaluator
passed. Subsequent changes pin the exact official canonical mapping, verify
generation identity and native token/reasoning evidence, and add audited,
idempotent historical reconciliation. Product code is unchanged. All **21**
evaluation/budget/reconciliation tests pass; changes target PR #28's existing
`ai/ask-phase-one` branch for independent parent review.

## Real canary evidence

The second invocation (`pr28-cloud-canary-20261015-02`) passed public endpoint
and existing-credit preflight, then sent exactly **one** inference request:
the synthetic English case `ask-01` ("Show all films.") plus the static schema.

| Item | Observed result |
| --- | --- |
| Requested model | `deepseek/deepseek-v4.1-flash` |
| Provider policy | Only `decart/fp4`; fallback disabled; parameters required |
| Actual provider from generation metadata | `Decart` |
| Actual model from generation metadata | `deepseek/deepseek-v4.1-flash-20260910` |
| Official directory canonical slug for the requested alias | `deepseek/deepseek-v4.1-flash-20260910` |
| Reasoning policy / native reasoning tokens | Disabled / **0** |
| Native input / output tokens | **1267 / 81** |
| Generation API normalized prompt / completion tokens | 1147 / 75 |
| Generation API total cost | **US$0.00012861** |
| Case wall latency | **4711.002 ms** |
| Provider latency / generation time | 483 / 1964 ms |
| Finish reason | `stop` |
| Evaluator result | `uncertain_billing_stop`; canary not passed |

The original evaluator required the generation model and completion response model to
equal the requested alias literally. The generation model is the dated canonical
slug, so identity/billing corroboration failed before the completion could be
returned to the strict JSON parser. This is an evaluator identity-compatibility
blocker; the `ask_invalid_response` application error does **not** establish
malformed model JSON. Original completion `usage.cost`, completion-model value
and strict JSON validity were not preserved/accepted by that failed boundary.

A later **read-only** generation lookup provided the actual cost/tokens/provider
above. A public `/models` lookup separately confirmed the alias-to-canonical-slug
mapping. No additional inference followed the failed canary.

## Audited reconciliation and continuous budget

The public model directory explicitly maps the requested alias to the one
pinned canonical ID shown above. The repaired preflight requires that exact
mapping on every run; a missing/duplicate/changed mapping stops before inference.
Only the alias and this canonical string are accepted. No prefix matching or
automatic date/version upgrades are used.

The read-only reconciliation re-fetched official model/endpoint metadata and
the original generation receipt. Provider, generation ID, original attempt/run,
price snapshot, current matching prices, token bounds, zero cached/reasoning
tokens, normal completion and no BYOK/cancellation all matched. Native usage
independently reproduces the bill exactly:

`1267 × US$0.00000009 + 81 × US$0.00000018 = US$0.00012861`.

This is historical billing recovery from authoritative generation usage, not
recovery of the lost completion `usage.cost` or strict JSON result. Both remain
explicitly unverified. Future normal paid evaluation still requires completion
`usage.cost` equality with generation cost, both exact model identities, and
native token/reasoning agreement before returning to the JSON parser.

- Historical confirmed spend before cloud inference: US$0.
- Total actual inference requests in the task: **1**.
- Actual cost evidenced by the generation API: **US$0.00012861**.
- The same original attempt is accounted at **US$0.00012861**. Its original
  generation ID, failure outcome and **US$0.10517760** reserved value are retained.
- One transaction stores an audit row with the prior `unknown` state, outcome,
  reserve, allowlisted evidence, evidence digest and timestamp, and sets the
  attempt to `blocked` with the verified cost. No attempt is deleted or replaced.
- Conservative exposure is now the verified US$0.00012861 cost; the unused
  reserve is released only after successful reconciliation. The original reserve
  column remains unchanged and the blocking review hold prohibits inference.
- Actual repeated reconciliation returned `applied=false`: one original attempt,
  one audit row, one charge. Evidence was identical; no double counting.
- US$0.75 conservative stop and US$1 lifetime hard limit are unchanged.
- Validation/identity/price/usage/cost failures retain `unknown` and its full reserve.

Independent parent review and renewed canary authorization are still required.
This repair provides no automatic way to reopen the blocked attempt. No further
inference was sent. Another canary must pass all identity, usage-cost, strict
JSON and reasoning checks before the bilingual corpus.

The separate read-only command (from `backend/`, with dotenv disabled and the
owned temporary SQLite/media environment targets above) was run twice:

```bash
uv run --no-sync python -X utf8 -m app.evaluation.ask --reconcile-report .evaluation-artifacts/pr28-cloud-canary-20261015-02.json --expected-cost-usd 0.00012861 --output .evaluation-artifacts/pr28-cloud-reconciliation-20261015-01.json
```

The repeat used a different output filename to preserve both receipts. This
mode only performs official metadata/generation GETs and cannot request inference.

## Acceptance status and evidence files

No live supported-case accuracy, rejected-case safety gate or overall acceptance
pass is claimed. The 36 supported and 16 rejected/privacy cases were not run as
a live corpus. The report's single blocked supported observation is not a model
understanding score; zero rejected failures reflects zero rejected cases run.
Offline fixtures remain separate contract evidence.

Retained ignored evidence in `backend/.evaluation-artifacts/`:

- `pr28-cloud-canary-20261015-01.json`: original SDK/preflight blocker.
- `pr28-cloud-preflight-diagnostic-20261015.json`: public pricing/policy and SDK diagnostic.
- `pr28-cloud-canary-20261015-02.json`: stopped real-canary report and reserve.
- `pr28-cloud-canary-20261015-02-generation.json`: allowlisted read-only billing evidence.
- `pr28-cloud-model-directory-20261015.json`: official alias/canonical mapping.
- `pr28-cloud-acceptance-summary-20261015.json`: consolidated machine-readable status.
- `pr28-cloud-reconciliation-source-20261015.json`: allowlisted official source evidence.
- `pr28-cloud-reconciliation-20261015-01.json` and `-02.json`: applied and idempotent repeat receipts.
- `ask-live-budget.sqlite3`: original continuous budget ledger; retain it.

Validation: 21 evaluation/budget/reconciliation tests passed, including the 58/58 offline
fixture contract; installed-package compatibility check and `git diff --check`
passed. These checks do not constitute a live model acceptance pass.
