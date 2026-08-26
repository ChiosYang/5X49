# Analysis V2 Persistence

Status: Blocked
Last updated: 2026-08-26
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
  factual Genre Assertions. Version 10 and the Library worker persist validated
  Analysis V2 runs, relationships, verified Evidence, reviews, and compatible
  Legacy analysis. The remaining slice evaluates quality and concludes Gate B.

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
  existing metadata transaction. Version 10 transitions compatible Legacy
analysis, and the Library analysis worker now treats W4 records as durable data
while continuing to produce the existing Movie projection. Slice 4 tooling and
the human-adjudicated `analysis-eval.v1` corpus are complete, but strict Gate B
evidence is blocked on a pinned live run and its post-output human review.

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
- [x] Analysis runtime persistence and compatible Legacy transition are
  complete without changing HTTP response shapes.
- [x] The 36-case corpus, balanced `gate-b-policy.v1`, deterministic
  scorer, isolated rehearsal, restore/privacy checks, and strict CLI are
  implemented.
- [x] All 36 cases were human-adjudicated before any live output was viewed;
  bounded Concept aliases map equivalent wording to one gold target.
- [ ] The pinned live run plus complete helpfulness/novel-prediction review
  passes Gate B.

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

- The exact OpenRouter model and matching pricing manifest must be selected and
  frozen before the live run.

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

Status: Complete

- Intended behavior: create/reuse AnalysisRun, resolve references, persist
  proposed Assertions and verified Evidence transactionally, and transition
  compatible legacy analysis without raw artifact retention.
- Dependencies: Slice 2 and an implemented safe Evidence retrieval boundary.
- Verification: retries, version changes, unresolved review, rollback,
  rejected-state protection, privacy, and legacy projection compatibility.

### Slice 4 — Evaluation and Gate B handoff

Status: Blocked (tooling complete)

- Intended behavior: run the fixed 36-film adjudicated evaluation set and
  produce a privacy-safe Graph quality report and Gate B conclusion.
- Dependencies: Slices 1–3 and dataset adjudication are complete. OpenRouter
  Key, exact model/pricing evidence, live output, and post-output human review
  are still absent.
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
- Slice 3 focused Analysis runtime, Evidence, Legacy transition, migration,
  Canonical, W3, and Gate regression — 104 tests passed.
- Complete backend discovery excluding credential-dependent `test_agent.py` —
  190 tests passed in 123.781 seconds after Slice 3.
- W3 rehearsal `w4-s3-v10-20260825-01` — passed after upgrading only its
  isolated work copy to current schema v10.
- Gate A rehearsal `w4-s3-v10-20260825-01` — every local phase passed at v10;
  strict status remains Blocked because Docker evidence is absent.
- `python -m compileall -q app` and `git diff --check` — passed before final
  handoff; Git reported only checkout line-ending warnings.
- Git-safe Slice 3 evidence is recorded in
  `docs/quality/analysis-v2-persistence-slice3.md`.
- Gate B dataset validation passed for 36 adjudicated cases with 12 Chinese, 12
  English, and 12 mixed/other cases; the frozen hash prefix is
  `fbfc9a1a481aef30`.
- Offline rehearsal `w4-s4-adjudicated-20260826-03` passed tooling, persistence,
  scoring, verified restore, and privacy checks at schema v10. Its strict
  status is Blocked: live and human evidence were intentionally not fabricated.
- Gate B and Analysis runtime focused tests passed 13 tests in 21.208 seconds.
  Concept aliases matched one gold target and duplicate aliases remained
  detectable. Git-safe status and
  threshold evidence are recorded in `docs/quality/analysis-v2-gate-b.md`.
- Complete backend discovery excluding credential-dependent `test_agent.py`
  passed 199 tests in 136.751 seconds after dataset adjudication.
- W3 rehearsal `w4-s4-gate-b-20260826-01` passed at schema v10; Gate A with
  the same run ID passed every local phase and preserved its source fingerprint,
  while the strict Gate A result remains Blocked because Docker is absent.
- `python -m compileall -q app` and `git diff --check` passed; Git emitted only
  the repository's checkout line-ending warnings.

## Remaining risks

- Automated tests use a fake DNS resolver and HTTP transport. The production
  retriever pins a validated public address and revalidates every redirect, but
  no live Evidence site is part of deterministic acceptance.
- No OpenRouter Key, exact model/pricing evidence, live report, or human review
  of live output is available, so Gate B cannot pass.
- Gate A remains independently Blocked. A future Gate B pass would still not
  authorize Graph UI until Gate A also passes.
