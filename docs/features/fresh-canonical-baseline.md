# Fresh Canonical Baseline

Status: In Progress
Last updated: 2026-08-26
Related: `docs/domain-model.md`, `docs/product-roadmap.md`,
`docs/analysis-v2-contract.md`

## Goal

Treat 5X49 as a new product with one Canonical domain model. Remove the Legacy
Movie compatibility runtime and expose Film, LibraryItem, Viewing, AnalysisRun,
and other durable resources directly to the frontend.

## Scope

- Replace schema versions 1-10 with the `fresh-canonical-v1` baseline.
- Remove Legacy tables, aliases, shadow reads, dual writes, projections,
  backfills, Gate A tooling, and compatibility-only API routes.
- Keep all current product capabilities through resource-oriented Canonical
  services and APIs.
- Present one Library card per Film and expose multiple local LibraryItems as
  editions on the Film detail page.
- Rebuild Activity and bounded operation restore on stable Canonical aggregate
  IDs.
- Archive the active development database before initializing a blank v1
  database; never alter media files.

## Non-goals

- Importing any old database or preserving its API identifiers.
- Accounts, multiple profiles, Graph UI, or a new UI visual direction.
- Passing Gate B without the required live, Evidence, cost, and human-review
  evidence.
- Adding a new dependency or changing the default frontend port.

## Existing behavior

Canonical tables are the default read source, but runtime commands still write
Legacy Movie and MovieUserState projections. Old aliases, shadow/legacy read
modes, Movie event replay, `analysis_data`, and schema-specific backfills keep
the application tied to the former data model. The frontend consumes those
compatibility DTOs and treats the old Movie ID as both Film and LibraryItem.

## Acceptance criteria

- [ ] Fresh startup creates only `fresh-canonical-v1` and fixed reference rows.
- [ ] Old v1-v10 databases are rejected without modification.
- [ ] Runtime code contains no Legacy Movie table, alias, shadow read, dual
  write, Movie projector, compatibility analysis JSON, or legacy source kind.
- [ ] Library APIs and UI use Film IDs; LibraryItem IDs are used only for local
  edition operations.
- [ ] Scan, metadata, artwork, scores, personal state, analysis, jobs, Activity,
  and bounded restore remain available.
- [ ] One Film appears once in the Library and exposes all non-retired editions.
- [ ] Full backend and frontend verification passes, including Gate B offline
  tooling regression.
- [ ] The active database is recoverably archived and replaced with an empty
  fresh baseline database without modifying media.

## Decisions

- Film is the product-facing aggregate and LibraryItem is a local edition.
- Personal rating and notes live on FilmProfileState. Viewing stores watching
  facts; clearing watched status only retracts the manual Viewing source.
- Analysis views are derived from AnalysisRun, Assertion, Evidence, and Review;
  no compatibility JSON projection is stored.
- Activity is an audit log over Canonical aggregates. Restore uses explicit,
  bounded operation snapshots and optimistic hashes, not arbitrary replay.
- The custom migration runner remains. Its new v1 is a fixed baseline, and
  future schema changes start at v2.
- Gate A is retired. Gate B remains the Analysis V2 quality boundary.

## Open questions

- None.

## Slices

### Slice 1 — Fresh schema baseline

Status: In Progress

- Intended behavior: establish the new epoch, domain tables, normalized score
  and operation snapshot records, and reject pre-baseline databases.
- Verification: clean boot, idempotent boot, schema equivalence, constraints,
  and old-database rejection.

### Slice 2 — Canonical runtime and events

Status: Pending

- Intended behavior: make all commands write Canonical tables directly and
  rebuild audit/restore around stable aggregates.
- Verification: scan/relink, metadata, personal state, analysis, scores,
  transactions, Activity, and snapshot restore tests.

### Slice 3 — Resource API and frontend

Status: Pending

- Intended behavior: switch backend routes and frontend types/hooks/pages to
  Film-centric resource contracts while preserving the current product UX.
- Verification: API contracts, frontend lint/typecheck/build, and responsive
  bilingual browser smoke.

### Slice 4 — Cleanup and cutover

Status: Pending

- Intended behavior: remove historical compatibility tools and documentation,
  update Gate B tooling, complete regression checks, and initialize the active
  fresh database.
- Verification: static Legacy-symbol audit, full tests, Compose validation,
  recoverable database archive, and empty-database health smoke.

## Verification evidence

- None yet.

## Remaining risks

- This is an intentional breaking cutover. Any unarchived old database cannot
  be opened by the new application.
- The existing Event replay and timeline restore implementation cannot be
  reused mechanically because it projects Legacy Movie rows.
