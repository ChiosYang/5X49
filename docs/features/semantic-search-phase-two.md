# Semantic Search Phase Two

Status: In Progress
Last updated: 2026-10-22
Related: enhanced-search-phase-one.md; PR45

## Goal

Retrieve by local film content across languages and by the content of an
identified reference Film, with the same strict factual conditions as phase one.
Preserve the Explore input, cards and navigation. Do not recreate Ask or forms.

## Current delivery boundary

This branch first builds an **offline foundation**: source selection, a disposable
SQLite vector cache, replaceable embedding/reranker protocols, hybrid ranking,
local hard-filter integration, resumable snapshots and repeatable evaluation.
It does not yet activate a production semantic route, download a model, install
an inference runtime or call a paid provider. Mock pipeline tests establish
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

- Repository currently has no embedding runtime. Keep dependencies unchanged;
  use Python standard library plus existing SQLModel. No vector server.
- Read-only Windows inventory on 2026-10-22: 15.8 GiB system RAM, NVIDIA RTX 3050
  (WMI reports 4 GiB VRAM; usable memory is unverified), C: about 25 GiB free,
  D: about 667 GiB free.
- Candidate: Qwen3-Embedding-0.6B, official max 1024 dimensions and multilingual
  training; these are vendor specifications, not measured 5X49 results.
  [Official model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B).
- A 0.6B FP16 model is roughly 1.2 GB of weight data by parameter arithmetic.
  Download manifests, revision, inference dependencies, peak RAM/VRAM and actual
  CPU/GPU latency must be checked before approval. No download has happened.
- Prefer a separately managed on-device provider. Proposed first evaluation:
  fixed model revision, short content chunks, batch 1 initially, synthetic or
  separately approved public plot fixtures; no user library sent externally.
  Report exact download/dependency sizes and target D: cache path before action.
- Do not initially download Qwen3-Reranker-0.6B. First compare keyword, dense and
  hybrid recall/ranking; request a second model only if a bounded rerank experiment
  is justified. Keep the reranker optional and off by default.
- Any hosted alternative requires separate endpoint, credential, data-field and
  request/token budget approval. Do not reuse configured chat credentials.
- PR28/live-quality/budget hold remains unchanged. No real calls are authorized.
- Concrete first-pilot proposal: fixed model revision
  97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3 (official file listing about 1.21 GB).
  Use D:\CodexModelTrials\5X49\qwen3-embedding-0.6b-97b0c61, currently absent,
  with isolated venv/cache/temp. CPU-only PyTorch plus the official Transformers
  last-token pooling path avoids CUDA, sentence-transformers and a second model.
  Expected download 2–3 GB, proposed total download ceiling 3 GB and disk budget
  6 GB; dependency manifest/versions must be locked before execution. Stop rather
  than enlarge the budget. Four CPU threads, batch 1, max 512 tokens, RAM budget
  6 GiB and a 30-minute trial limit. These are limits to implement, not measured
  runtime needs or current resource consumption.
- Pilot data is committed in fixtures/semantic_search/quality-v1.json: eight
  fictional plot records, 12 EN + 12 ZH cases, explicit hard-condition oracles
  and two reference-Film cases. No application DB or user library is read.
  At most 64 text encodings including repetitions/warmup; all inference local,
  no API charge. This is a feasibility pilot, not production quality acceptance.
  The manifest supplies oracle content queries/hard plans and does not test a
  natural-language router. User authorization is still pending.

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

Status: Pending resource/provider authorization

- Decide and authorize a fixed provider/model/runtime/download/data budget.
- Measure real multilingual retrieval quality, hard-condition violations,
  latency and memory; separate embedding and reranker effects.
- Wire the validated provider into the existing Explore submission/results state
  with explicit unavailable/stale fallback, identity clarification, chips and
  unchanged Back/Return/mutation/race guarantees.
- Full tests, desktop/mobile/keyboard inspection, draft PR and exact-head review.

## Verification evidence

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
