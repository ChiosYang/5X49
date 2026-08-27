# Analysis V2 Persistence and Gate B

- Status: Blocked
- Owner: Backend / Analysis
- Updated: 2026-08-26

## Goal

Persist validated analysis as resolvable, reviewable graph facts without raw
model artifacts, and prove its usefulness and safety with a fixed public
evaluation set.

## Current contract

- Canonical Film input only; no media path, filename, Viewing, profile notes,
  credentials or raw source document.
- Strict `analysis-output.v2`, bounded public summary, up to eight Assertions
  and up to two Evidence candidates per Assertion.
- Model output creates only inferred/proposed Assertions.
- Exact identities, title/year consistency and entity kinds are validated before
  creating an edge. Unresolved/conflicting targets create bounded reviews.
- The deterministic `analysis-policy-critic.v1` runs before Evidence retrieval,
  enforces type/direction/self-reference, alias uniqueness, qualifier, semantic
  duplicate and eight-Assertion limits, and is shared by production and Gate B.
- Accepted/rejected user decisions survive refresh and re-analysis.
- Evidence is stored only after public HTTP(S) network/content validation; page
  bodies are hashed in memory and discarded.
- AnalysisRun idempotency includes Film, model/provider, versions and input hash.
- `GET /films/{film_id}/analysis` reads AnalysisRun/Assertion/Evidence/Review
  directly. There is no compatibility analysis JSON.

## Delivery slices

### Slice 1 — Persistence contract and schema

Status: Complete in Fresh Canonical v1.

- Assertion predicate registry.
- AnalysisRun, Assertion, Evidence, links, provenance and resolution review.
- Stable canonical hashing and privacy validators.

### Slice 2 — Factual genre Assertions

Status: Complete in Fresh Canonical v1.

- Fixed TMDB Movie Genre vocabulary.
- NFO/TMDB genre observations materialize shared factual accepted `HAS_GENRE`.
- Source-scoped provenance supersedes/restores without changing user decisions.

### Slice 3 — Runtime persistence

Status: Complete in Fresh Canonical v1.

- Canonical input builder and strict historian.
- Direction-aware entity resolution and non-owned exact Film support.
- Transactional AnalysisRun/Assertion/Evidence/Review persistence.
- Idempotent successful-run reuse, safe retry and bounded failure state.
- Structured FilmAnalysisView with no raw/hidden artifacts.

### Slice 4 — Fixed evaluation and Gate B

Status: Blocked; tooling complete.

- 36 public cases and human-adjudicated expected relationships are frozen.
- Offline isolated rehearsal, scoring, rejected/revoked protection, restore and
  privacy checks pass.
- A diagnostic pilot has run against the pinned model.
- Strict 36-case live Evidence and complete post-output human review are missing.

### Architecture pipeline hardening

Status: Complete.

- Analysis now runs through the versioned durable Workflow entrypoint.
- Historian remains the only model call; Resolver, Policy Critic and Evidence
  verifier are deterministic stages.
- Gate B live and offline persistence paths call the same Workflow entrypoint
  and production Critic rather than a test-specific resolver.
- The current versions are `genealogy-v2.v3`, `analysis-resolver.v3` and
  `analysis-policy-critic.v1`.

## Gate B exit criteria

`gate-b-policy.v2` requires, among other frozen thresholds:

- 36/36 successful adjudicated cases;
- at least 85% acceptable displayed edges;
- at least 95% entity-resolution decision accuracy;
- at least 75% required Assertion recall;
- zero forbidden/harmful edges, invented entities or rejected-state revival;
- zero semantic duplicates and replay-created rows;
- complete human review, median helpfulness at least 4/5 and 80% at least 4;
- at least 70% qualifying Evidence coverage for evidence-priority relations;
- every persisted Evidence passing `evidence-http.v1` and freshness rules;
- total cost at most USD 5 and p95 per case at most USD 0.25;
- verified restore equality and zero privacy leaks.

Missing live, pricing, Evidence or human evidence is `blocked`; complete evidence
that misses a threshold is `failed`. Only the strict `conclude` command may
record Passed.

## Remaining work

1. Make the public Evidence preflight reliable under the production SSRF boundary.
2. Run all 36 cases with one exact model and pricing manifest.
3. Complete `analysis-eval-human-review.v1` after seeing the output.
4. Run strict conclusion and update only the redacted quality summary.
5. Start Film Graph UI only after Gate B passes and separate UI/product acceptance succeeds.

## Risks

- Free model availability and behavior may change without notice.
- DNS pinning/TLS behavior must remain secure; do not weaken it to obtain a pass.
- Human usefulness and novel-relation review cannot be replaced by automatic scoring.
- A Gate B pass validates the frozen scope, not unlimited whole-library analysis.
