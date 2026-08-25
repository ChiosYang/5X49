# Analysis V2 Persistence

Status: In Progress
Last updated: 2026-08-25
Related: W4 and Gate B in `docs/product-roadmap.md`, `docs/domain-model.md`,
`docs/analysis-v2-contract.md`

## Goal

Turn validated Analysis V2 output into durable, reviewable Graph data without
letting model output invent identities, overwrite user decisions, or become an
unbounded raw-data archive.

## Scope

- Add the versioned Assertion predicate registry and schema version 8 for
  Assertion, Evidence, AnalysisRun, provenance, links, and resolution review.
- Establish deterministic hashes, review rules, Evidence URI policy, and
  privacy-safe persistence boundaries.
- Data migration version 9 and runtime metadata synchronization materialize
  factual Genre Assertions. Later slices connect Analysis V2 runtime writes,
  migrate compatible legacy analysis, and complete Gate B.

## Non-goals

- Graph API or UI, review UI, Explore, Cinema DNA, or Ask.
- Model execution, Evidence retrieval, legacy `analysis_data` backfill, or
  runtime projection changes in Slice 1.
- Raw prompt/response, web-page body, hidden reasoning, path, or credential
  retention.
- Declaring Gate A or Gate B passed.

## Existing behavior

W3 schema version 7 supplies canonical Film, Person, Credit, Concept, Genre
vocabulary, provenance, and runtime metadata observations. Schema version 8
adds the durable W4 boundary. Data migration version 9 now materializes trusted
Legacy Genre facts, while NFO and TMDB refresh the same Assertions in the
existing metadata transaction. The legacy analysis service still writes only
Movie projection fields and events.

## Acceptance criteria

- [x] Schema version 8 is additive and preserves all version 1–7 checksums and
  existing domain rows.
- [x] The predicate registry contains the eight model predicates plus factual
  `HAS_GENRE`; `HAS_GENRE` is not accepted as model output.
- [x] Assertion identity excludes run, provenance, scope, and review state.
- [x] Automatic model writes are inferred proposals; trusted structured Genre
  imports may use versioned policy acceptance.
- [x] Evidence stores only verified HTTP(S) metadata and bounded claims, never
  source bodies or raw Analysis payloads.
- [x] Unresolved or rejected candidates have a bounded, deterministic analysis
  review identity and cannot create formal Graph nodes directly.
- [x] Ordinary Library clear preserves W4 durable data; full data clear removes
  it in FK order while preserving predicate reference rows and migration state.
- [x] HTTP routes and legacy response shapes remain unchanged.
- [x] Trusted Legacy, NFO, and TMDB Genre facts synchronize source-scoped,
  policy-accepted `HAS_GENRE` Assertions without overwriting user decisions.
- [ ] Analysis runtime persistence, legacy analysis transition, evaluation, and
  Gate B evidence are complete.

## Decisions

- `assertion-predicate.v1` contains `HAS_GENRE`, `HAS_THEME`, `HAS_MOVEMENT`,
  `HAS_VISUAL_STYLE`, `HAS_MICRO_GENRE`, `INFLUENCED_BY`, `REMAKE_OF`,
  `ADAPTED_FROM`, and `VISUALLY_SIMILAR_TO`.
- The eight Analysis V2 model predicates remain a strict subset of the stored
  registry. `HAS_GENRE` is reserved for structured or curated sources.
- A trusted NFO, TMDB, or Legacy Genre observation that resolves uniquely may
  be accepted by `structured-genre-import.v1`; ambiguous values remain review
  items.
- Evidence v1 is `catalog`, `web`, or `dataset` material retrieved over a safe
  public HTTP(S) route. NFO is provenance and user explanation is curated
  rationale, not Evidence.
- AnalysisRun keeps versions, hashes, bounded validated summary, cost, status,
  trace IDs, and redacted errors. It does not keep raw input/output.
- Job and Event IDs are diagnostic strings rather than foreign keys because
  those operational records may be cleared independently of durable runs.
- Accepted/rejected review state is user-owned. Automated refresh can only
  preserve it, never reset it.

## Open questions

- Evidence redirect/DNS retrieval limits, retry scheduling, and stale-link
  refresh frequency are implementation details for Slice 3, within the fixed
  public-network-only policy.
- Gate B quality thresholds still require the adjudicated evaluation dataset.

## Slices

### Slice 1 — Persistence contract and schema v8

Status: Complete

- Intended behavior: add the predicate registry, persistence models,
  deterministic helpers, additive migration, lifecycle integration, and
  documentation without changing runtime analysis.
- Dependencies: completed W3 structured metadata and adopted Analysis V2
  contract; no API key, network, Docker, or Gate A pass required.
- Verification: schema constraints, nine legacy fixtures, fresh/create_all
  equivalence, backup/idempotence, clear semantics, focused and full backend
  regressions, and isolated W3/Gate A tool regressions.

### Slice 2 — Factual Genre Assertions

Status: Complete

- Intended behavior: deterministically materialize W3 Genre observations as
  factual `HAS_GENRE` Assertions and keep their provenance synchronized.
- Dependencies: Slice 1 and `structured-genre-import.v1`.
- Verification: backfill/runtime idempotence, source removal, conflict review,
  accepted-state preservation, and compatibility reads.

### Slice 3 — Analysis V2 runtime and legacy transition

Status: Pending

- Intended behavior: create/reuse AnalysisRun, resolve references, persist
  proposed Assertions and verified Evidence transactionally, and transition
  compatible legacy analysis without raw artifact retention.
- Dependencies: Slice 2 and an implemented safe Evidence retrieval boundary.
- Verification: retries, version changes, unresolved review, rollback,
  rejected-state protection, privacy, and legacy projection compatibility.

### Slice 4 — Evaluation and Gate B handoff

Status: Pending

- Intended behavior: run the fixed 30–50 film adjudicated evaluation set and
  produce a privacy-safe Graph quality report and Gate B conclusion.
- Dependencies: Slices 1–3.
- Verification: entity resolution, precision, duplicate rate, helpfulness,
  cost, restore, and a strict passed/failed/blocked Gate B matrix.

## Verification evidence

- `python -m unittest test_analysis_persistence_schema.py` — 8 tests passed.
- Focused Analysis persistence, migration, Canonical, W3, and Gate A run — 64
  tests passed.
- Complete backend discovery excluding credential-dependent `test_agent.py` —
  169 tests passed in 104.005 seconds.
- W3 rehearsal `w4-v8-20260825-02` — passed on the fixed offline input after
  upgrading its isolated work copy to schema v8.
- Gate A rehearsal `w4-v8-20260825-02` — every local phase passed at v8,
  including predicate-registry preservation; overall status remains Blocked
  because Docker evidence is absent.
- `python -m compileall -q app` and `git diff --check` — passed; Git reported
  only the repository's existing LF-to-CRLF checkout warnings.
- Slice 2 focused Genre Assertion, Analysis persistence, migration, Canonical,
  W3, TMDB, and Gate run — 82 tests passed.
- Complete backend discovery excluding credential-dependent `test_agent.py` —
  176 tests passed in 110.096 seconds after Slice 2.
- W3 rehearsal `w4-s2-v9-20260825-01` — passed at current schema v9.
- Gate A rehearsal `w4-s2-v9-20260825-01` — every local check passed at v9 and
  the source remained unchanged; strict status remains Blocked without Docker.
- Git-safe Slice 2 evidence is recorded in
  `docs/quality/analysis-v2-persistence-slice2.md`.

## Remaining risks

- Schema constraints cannot perform DNS resolution; Slice 3 must revalidate the
  resolved address and every redirect before Evidence is persisted.
- Genre import protects user accepted/rejected decisions, but Analysis V2
  runtime persistence and its broader rejected-state protection remain Slice 3.
- Gate A remains independently Blocked, and Gate B is Pending.
