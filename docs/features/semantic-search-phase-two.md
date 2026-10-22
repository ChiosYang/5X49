# Semantic Search Phase Two

Status: In Progress
Last updated: 2026-10-22
Related: enhanced-search-phase-one.md; PR45; PR46

## Goal

Retrieve by local film content across languages and by the content of an
identified reference Film, with the same strict factual conditions as phase one.
Preserve the Explore input, cards and navigation. Do not recreate Ask or forms.

## Current delivery boundary

The merged **offline foundation** provides source selection, a disposable
SQLite vector cache, replaceable embedding/reranker protocols, hybrid ranking,
local hard-filter integration, resumable snapshots and repeatable evaluation.
Production semantic routing remains disabled. The separate explicit pilot below
may call only the authorized hosted embedding fixture; no local model/runtime
is downloaded or installed. Mock pipeline tests establish
contracts, not real semantic quality. Phase two is not complete until the real
provider, quality and UI integration gates below have passed.

## Existing data

- Use effective local overview, honoring manual overrides. Historical scalar
  overview has no per-field NFO/TMDB provenance: label it library metadata.
- Use only active, accepted, unconflicted theme assertions with current
  provenance. Subjective themes remain labeled as reviewed interpretations,
  never promoted into factual filters. Do not read viewing history, ratings,
  reviews, notes, media paths or credentials.
- There is no independent trusted keyword table. Do not invent one from model
  output or fetch external recommendations. Titles/aliases support lexical
  identity resolution; a title alone is insufficient similarity content.

## Resources and provider gate

- The user cancelled the local CPU model proposal on 2026-10-22. Do not download
  local weights or trial runtimes. No vector server or new dependency is needed.
- A separate, explicit authorization now permits only this OpenRouter embedding
  smoke: qwen/qwen3-embedding-8b, eight fictional films, at most 24 EN/ZH questions,
  cumulative cost at most USD 1, no recharge. It does not permit chat/rerank calls,
  real-library export/indexing, production enablement or expansion of PR28's
  earlier live-quality/budget hold.
- Reuse the existing deployment credential source in memory only. No secret in
  arguments, logs, reports or new persistent settings; chat configuration stays
  unchanged. Missing credentials block execution instead of creating a key.
- Pin deepinfra/us, disable retries, redirects and provider fallbacks, require
  data_collection=deny and ZDR. Preflight public endpoint metadata before dispatch:
  the checked input quote is USD 0.01/M tokens, output charge zero; reject unknown
  nonzero price components and input price above USD 0.04/M.
- app/services/openrouter_embeddings.py implements the existing embedding
  protocol with an exact synthetic-text allowlist. Outgoing fields are model,
  input, encoding_format=float and provider preferences. Query instructions are
  versioned; documents have no instruction prefix. No IDs, titles, hard-plan
  answers, year/duration/viewing fields, paths or notes are sent.
- One owned durable run directory prevents an automatic replay. Reserve USD 0.01
  before each request and retain that reservation: at most 32 POSTs/64 texts,
  20,000 conservative input-token reservations, 20-second requests, serial calls.
  The maximum held reservation is USD 0.32, below the authorized USD 1. Price
  filters constrain endpoint rates; they are not an account-wide spend setting.
- Record usage.cost when present, otherwise label the pinned-quote/token estimate
  explicitly. Failure, uncertain billing, excess price/usage or malformed output
  halts subsequent dispatch. Reconcile the existing receipt before any further
  action; never delete it or change directories to retry.
- The fixed fixture SHA is
  2a1309d20b4c745fa453f23fb738effed39d6c6415b2964658c42e5004e123a9.
  It contains eight fictional plots, 12 EN + 12 ZH cases, independent hard-plan
  oracles and two reference cases. Prefetch each query once, share vectors across
  lexical/dense/hybrid, and measure remote encoding separately from warm local
  retrieval. This is synthetic feasibility, not a real-library or NLP-router gate.
- No network on import/startup. The CLI defaults to anonymous metadata preflight:
  python -m app.evaluation.openrouter_pilot. Only the separately authorized
  --execute invocation may infer, optionally using --credential-env for an
  existing deployment .env/.env.local. Receipts go to the task-owned ignored
  .mcp-artifacts/openrouter-embedding-smoke-v1 directory.
- The first authorized request at 2026-10-22 07:28:11 UTC returned HTTP 200 but
  failed the initial strict model-string check. One fictional plot was sent;
  zero content queries, chat or rerank requests followed. Actual billed usage
  is unknown; the USD 0.01 reservation remains held, never reported as zero cost.
  That version rejected before retaining the response ID/usage, so the receipt
  cannot recover them. New code saves safe billing/model metadata first and
  recognizes only the canonical slug and exact official Qwen upstream identity.
  These changes have mock coverage; live compatibility is not yet established.
  The existing run stays halted; there is no reset or automatic continuation.
  Authenticated key metadata was accessible (HTTP 200), but the activity API
  requires management access (HTTP 403); no new credential/connection was created.
  Request-level reconciliation needs the original request ID or account-side
  billing confirmation. Do not make another paid request while this is unresolved.
- The user subsequently selected nvidia/nemotron-3.5-embed-8b:free. Qwen will not
  be retried; its original receipt and reservation remain unchanged. Public
  metadata reports nvidia/bf16, 4096 output dimensions and zero input/output
  price. NVIDIA records inputs for security/product improvement and requires
  acceptance of its API Trial Terms. Explicit user confirmation of that change
  is pending: only public metadata and offline preparation are permitted. Do not
  invoke the free endpoint or silently relax the existing ZDR/deny policy.

## Decisions

- Cache is derived, separate from the canonical database, explicitly constructed
  by its caller. No automatic indexing, migration or application-start side effect.
- Bound the exact-scan baseline; reject over-limit corpora rather than silently
  indexing a subset. Model revision/dimensions/content changes invalidate it.
- Read hard conditions from the phase-one SQL executor. Filter eligible IDs
  before top-k selection and optional reranking; unknown/conflicted facts retain
  the same positive/negative behavior.
- Similarity requires a local exact Film identity choice, then content vectors;
  never compare title embeddings alone. Reject missing content.
- Save only query hashes and ranked Film IDs in bounded, expiring snapshots.
  Restore/repage/reapply factual conditions locally without provider calls.
  Content changes invalidate snapshots; viewing-state changes reapply hard SQL.
- An initially empty hard selection is stored as unevaluated. If later
  eligibility grows, restore returns snapshot_unevaluated without provider calls;
  an explicit new submission computes relevance instead of silently preserving 0.
- Cache policy v2 validates full normalized text, safe bounded chunk boundaries
  and complete assembled transport strings before commit/use. Provenance labels
  remain metadata; no repeated field-label boilerplate is embedded. Old
  experimental v1 caches fail closed and need explicit rebuild.
- Provider text is bounded plot/theme content, screened before truncation.
  Provider output must have the expected count/dimensions, finite values and
  local candidate identities. Never interpret document text as instructions.

## Slices

### Offline foundation

Status: In Progress

- Provider-independent cache/ranking and source selection.
- Explicit dense/lexical/hybrid experiment modes; snapshots bind the mode and
  threshold to avoid mixing an earlier ordering into another strategy's report.
- Strict hard-filter bridge, reference identities and snapshot invalidation.
- EN/ZH synthetic expected-ID evaluation and malformed-provider/privacy tests.

### Production integration and real quality

Status: Pending real quality and production integration

- Complete the separately authorized OpenRouter synthetic smoke within its limits.
- Measure real multilingual retrieval quality, hard-condition violations,
  latency and memory; separate embedding and reranker effects.
- Wire the validated provider into the existing Explore submission/results state
  with explicit unavailable/stale fallback, identity clarification, chips and
  unchanged Back/Return/mutation/race guarantees.
- Full tests, desktop/mobile/keyboard inspection, draft PR and exact-head review.

## Verification evidence

- OpenRouter pilot adapter: 42 mock tests passed (17 new transport/budget/
  credential/receipt tests plus 25 semantic core regressions). The independent
  receipt review found that ID persistence still followed usage validation.
  Safe request ID/model/provider metadata is now atomically saved before any
  billing check; missing/malformed usage and excess-cost regressions assert the
  ID is already on disk at the billing boundary and survives the halted run.
  A second accounting review corrected the total-cost upper bound: a
  missing-cost estimate stays separate, and its entire reservation remains in
  the unreported-cost upper bound even if the sampled quote is cheaper than the
  request's price ceiling. Both sampled-rate variants have regression coverage.
  Earlier broader
  hard-filter/provenance/Explore run passed 74 before the final receipt changes;
  fresh full verification is pending. Live smoke stopped after its first request
  as described above, so no 24-case real-model quality result is claimed.
- Initial targeted run: semantic foundation + enhanced search + provenance
  selection, 32 tests passed. Final targeted run including limits/metrics and
  Explore query regressions: 55 tests passed (16 new semantic contract tests).
- The fixture provider uses a hand-written three-axis map. Its EN/ZH results test
  hybrid mechanics and hard-filter invariants; they do not measure model language
  understanding. Snapshot persistence, 41-to-40 correction, privacy zero-call
  checks, malformed provider/cache data and metadata withdrawal are covered.
- Initial foundation head 11c084d3cf49c7f414eb3ebecbde587b10825eb7 passed full
  local backend 484/3 Windows skips and E2E 272; CI39723997992 succeeded. These
  precede the pilot-manifest and import-isolation increment.
- The increment passed 91 targeted tests (18 semantic tests, Ask, discovery,
  enhanced search, provenance and Explore). Privacy regex literal is unchanged;
  a fresh-process regression verifies the model core imports no application DB
  or chat client. Manifest SHA256:
  2a1309d20b4c745fa453f23fb738effed39d6c6415b2964658c42e5004e123a9.
- Fresh full verification and independent review of the increment are pending.
- Head 6133347aac8e89ed419b2f2465ce9cf46e0a6bed subsequently passed local
  backend 486/3 Windows skips and E2E 272; CI39725356154 passed backend
  486/1 skip + tooling 15, frontend 138/audit/lint/type/build and E2E 272.
- Final transport-boundary/experiment increment: 93 targeted tests passed
  (20 semantic tests). Restored fragments are screened as complete transport
  strings before embedding/reranking; the private-path reconstruction regression
  proves zero provider calls. Fresh full CI and independent review still pending.
- Independent review found two P2s in the earlier prototype: unevaluated empty
  snapshots remained empty after eligibility grew; arbitrary cuts could turn
  Face/Off into a false private-path chunk and poison cache readability. Both are
  corrected with persisted evaluation state and validated, context-safe cuts.
- Review-fix suite: 96 tests passed, including 23 semantic tests. Covers exact
  slash-title boundaries and mixed indexes, ordinary short text, true private
  paths, explicit resubmission after empty eligibility and a real temporary-DB
  year mutation through the same hard SQL bridge. Full fresh CI/re-review pending.
- That head, 82efbdb825b932aa16b07e67fb06d8f5ff4764f5, passed CI39727530954:
  backend 491/1 skip + tooling 15, frontend 138/audit/lint/types/build, E2E 272.
- A further independent privacy regression found repeated/mixed separators in
  relative media paths bypassed the extracted guard. The shared guard and browser
  mirror now reject separator runs without altering the original text or treating
  ordinary Face/Off, V/H/S or 9/11 titles as paths. Regression coverage includes
  whitespace filenames, quote boundaries, source ingestion, the final embedding
  boundary and old/corrupt cache reads, with zero embedding/reranking calls.
  Corrected targeted suite: 98 passed (25 semantic); frontend unit suite: 139.
  New exact-head full verification and independent re-review remain required.
- Phase one is merged at fb745f2cb3173d062aca170b3450ceb474d8a1f1, tree equal to
  reviewed d12a5319dbf4f5fb142d4bb77b295c1eaa5cfa52. CI39721297391: backend
  468/1 skip, tooling 15, frontend 138, audit/lint/types/build, E2E 272.

## Remaining risks

- No real embedding or reranker quality, speed, resource use or model-server
  interoperability has been validated. Production semantic behavior is not enabled.
- Exact scan is a bounded baseline, not a large-library ANN performance claim.
- Mixed-language content coverage and human relevance labels need real evaluation.
