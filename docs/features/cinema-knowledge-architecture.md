# Provenance-Driven Cinema Knowledge Architecture

Status: In Progress
Last updated: 2026-08-27
Related: `docs/product-roadmap.md`, `docs/domain-model.md`,
`docs/features/analysis-v2-persistence.md`

## Goal

Evolve Fresh Canonical into an explainable cinema-knowledge platform without
turning the database into an event-sourced system. Canonical domain tables
remain the only source of truth. Provenance resolution selects current values,
synchronous CQRS read models serve product queries, durable workflows own long
operations, and the Analysis pipeline remains bounded and reviewable.

## Architecture contract

```text
Canonical Domain
      ↓
Provenance Resolution
      ↓
Synchronous Read Models
      ├─ Library / Detail / Search
      └─ Factual Graph

Commands → Durable Workflow → Canonical Domain
Analysis → Historian → Resolver → Critic → Evidence → Persistence
```

- Canonical Film, LibraryItem, Person, Concept, Assertion and Viewing records
  are durable facts.
- Resolution is deterministic and versioned. It reports conflicts instead of
  silently hiding them.
- Read models are transactional, disposable and fully rebuildable without
  network or filesystem access.
- Workflows and Jobs coordinate execution; neither is a domain fact source.
- Export packages are portable snapshots, not a second database or sync log.
- EventRecord remains an audit trail, not a replay source.

## Decisions

- Source precedence is `curated > nfo > tmdb > filename` under
  `provenance-selection.v1`.
- CQRS projections update in the same SQLite transaction as their source
  mutation. There is no eventual-consistency worker.
- Gate B does not block accepted factual Graph data. It does block all inferred
  Graph visibility.
- The first Graph product surface is a Film-detail SVG panel with an accessible
  list fallback and no new frontend dependency.
- Durable execution uses WorkflowRun and WorkflowStep records plus the existing
  Job worker as a private step queue. External workflow engines are out of
  scope.
- Analysis uses one model call. Entity resolution, Evidence verification and
  policy criticism are deterministic.
- Local-first work stops at a versioned export contract. Device registration,
  import merge, HLC persistence, CRDT and cloud sync are out of scope.

## Acceptance criteria

- [x] Every selected metadata value is produced by one resolver and exposes a
  safe public source summary.
- [x] Library, Film detail and local search read exclusively from versioned
  synchronous read models.
- [x] Read models rebuild to the same digest and never access media or network.
- [ ] Film details expose a bounded factual Graph with no inferred leakage
  before Gate B.
- [ ] Library, metadata and Analysis long operations resume safely from durable
  Workflow steps.
- [ ] Analysis candidates pass deterministic resolver and critic policies
  before persistence.
- [ ] Gate B remains strict and only a valid conclusion may unlock accepted
  inferred Graph edges.
- [ ] `library-export.v1` is deterministic, private and read-only.
- [ ] Backend, frontend, privacy and responsive smoke suites pass.

## Slices

### Slice 0 — Architecture handoff

Status: Complete

- Store this contract and align Roadmap, Domain Model and API documentation.
- Verification: documentation diff review and link validation.

### Slice 1 — Provenance Resolver

Status: Complete

- Introduce `provenance-selection.v1` and a shared `ResolvedValue` contract.
- Resolve titles, countries, Credits, factual Assertions and identity conflicts.
- Maintain Film display caches only through the resolver.
- Verification: precedence, complete-field ownership, conflict, replay and
  privacy tests.

### Slice 2 — Synchronous CQRS read models

Status: Complete

- Add Schema v2 projection state plus Library, Detail, Search and Graph read
  models.
- Refresh affected projections in the caller's SQL transaction.
- Add offline `verify` and `rebuild` commands and strict 503 behavior for stale
  projections.
- Verification: transaction rollback, rebuild digest equality, startup
  bootstrap and API contract tests.

### Slice 3 — Factual Film Graph

Status: Pending

- Add `GET /films/{film_id}/graph` over Graph read models.
- Include selected Credit edges and active accepted factual Assertion edges.
- Add the bounded detail SVG and accessible relation list.
- Verification: visibility policy, stable truncation, accessibility, bilingual
  desktop and 375px smoke.

### Slice 4 — Durable Workflow

Status: Pending

- Add Schema v3 WorkflowRun/WorkflowStep and link private Jobs to steps.
- Migrate Library reconcile, metadata refresh and Analysis V2.
- Replace public Job status with Workflow status and sanitized Workflow SSE.
- Verification: crash recovery, lease expiry, retry, cancel, dedupe,
  compensation, idempotency and privacy.

### Slice 5 — Constrained Analysis pipeline

Status: Pending

- Keep one Historian call and split deterministic Resolver, Policy Critic and
  Evidence verification stages.
- Reject identity contradictions, type/direction errors, unsafe qualifiers,
  semantic duplicates and over-budget candidates into idempotent review.
- Make Gate B use the same production workflow.
- Verification: focused pipeline tests and offline Gate B rehearsal.

### Slice 6 — Gate B conclusion and inferred Graph release

Status: Blocked

- Run all 36 frozen cases with one exact model/pricing snapshot and public
  Evidence policy.
- Complete human review and strict conclusion.
- Release `graph-visibility.v2` only after Gate B Passed.
- Blocking evidence: live Evidence, cost and complete human review are not yet
  available for the final pipeline.

### Slice 7 — Local-first portability boundary

Status: Pending

- Add deterministic `library-export.v1` export and validation commands.
- Export portable Film knowledge and personal state without media, paths,
  secrets, operational state or read models.
- Reserve versioned logical-clock fields without implementing sync.
- Verification: deterministic digest, corruption rejection and privacy scan.

## Public interface plan

- Schema v2 adds projection tables; Schema v3 adds Workflow tables and Job step
  links. Fresh Canonical v1 remains immutable.
- Film detail adds safe `resolved_sources`.
- `GET /films/{film_id}/graph` returns bounded `FilmGraphView`.
- Workflow list/detail/cancel/retry replace public Job resources after the
  frontend cutover.
- `library-export.v1` is a CLI/file contract and has no import or sync endpoint.

## Verification evidence

- `python -m unittest test_provenance_resolver.py test_structured_metadata_runtime.py test_canonical_runtime.py test_api_routes.py -q`
  — 21 tests passed.
- `python -m unittest test_projections.py -v` — 4 projection transaction,
  strict-read, privacy and deterministic-rebuild tests passed.
- `python -m unittest test_database_migrations.py test_canonical_schema.py test_canonical_runtime.py test_api_routes.py -q`
  — 23 migration and runtime regression tests passed.
- `npm run lint` and `npm run typecheck` — passed after the safe DTO cutover.

## Remaining risks

- Projection fan-out must stay bounded so synchronous writes remain responsive.
- Workflow recovery must never repeat uncontrolled filesystem or network side
  effects.
- Gate B remains blocked until the final pipeline has complete live and human
  evidence.
- A future sync implementation will require a separate conflict and threat
  model; the export contract does not authorize it.
