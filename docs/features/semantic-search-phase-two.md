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
- Provider text is bounded plot/theme content, screened before truncation.
  Provider output must have the expected count/dimensions, finite values and
  local candidate identities. Never interpret document text as instructions.

## Slices

### Offline foundation

Status: In Progress

- Provider-independent cache/ranking and source selection.
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
- Phase one is merged at fb745f2cb3173d062aca170b3450ceb474d8a1f1, tree equal to
  reviewed d12a5319dbf4f5fb142d4bb77b295c1eaa5cfa52. CI39721297391: backend
  468/1 skip, tooling 15, frontend 138, audit/lint/types/build, E2E 272.

## Remaining risks

- No real embedding or reranker quality, speed, resource use or model-server
  interoperability has been validated. Production semantic behavior is not enabled.
- Exact scan is a bounded baseline, not a large-library ANN performance claim.
- Mixed-language content coverage and human relevance labels need real evaluation.
