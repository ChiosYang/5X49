# Fresh Canonical Baseline

Status: Complete
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

## Previous behavior

Before this cutover, Canonical tables were overlaid on a Movie compatibility
runtime with aliases, selectable reads, replay and JSON analysis projection.
The Fresh Canonical baseline deliberately removes that development-only history.

## Acceptance criteria

- [x] Fresh startup creates only `fresh-canonical-v1` and fixed reference rows.
- [x] Old v1-v10 databases are rejected without modification.
- [x] Runtime code contains no Legacy Movie table, alias, shadow read, dual
  write, Movie projector, compatibility analysis JSON, or legacy source kind.
- [x] Library APIs and UI use Film IDs; LibraryItem IDs are used only for local
  edition operations.
- [x] Scan, metadata, artwork, scores, personal state, analysis, jobs, Activity,
  and bounded restore remain available.
- [x] One Film appears once in the Library and exposes all non-retired editions.
- [x] Full backend and frontend verification passes, including Gate B offline
  tooling regression.
- [x] The active database is recoverably archived and replaced with an empty
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

Status: Complete

- Intended behavior: establish the new epoch, domain tables, normalized score
  and operation snapshot records, and reject pre-baseline databases.
- Verification: clean boot, idempotent boot, schema equivalence, constraints,
  and old-database rejection.

### Slice 2 — Canonical runtime and events

Status: Complete

- Intended behavior: make all commands write Canonical tables directly and
  rebuild audit/restore around stable aggregates.
- Verification: scan/relink, metadata, personal state, analysis, scores,
  transactions, Activity, and snapshot restore tests.

### Slice 3 — Resource API and frontend

Status: Complete

- Intended behavior: switch backend routes and frontend types/hooks/pages to
  Film-centric resource contracts while preserving the current product UX.
- Verification: API contracts, frontend lint/typecheck/build, and responsive
  bilingual browser smoke.

### Slice 4 — Cleanup and cutover

Status: Complete

- Intended behavior: remove historical compatibility tools and documentation,
  update Gate B tooling, complete regression checks, and initialize the active
  fresh database.
- Verification: static Legacy-symbol audit, full tests, Compose validation,
  recoverable database archive, and empty-database health smoke.

## Verification evidence

- Fresh schema snapshot matches registered SQLModel metadata; focused migration,
  lifecycle and Analysis schema run passed 20 tests.
- Full backend discovery passed 114 tests.
- Backend `compileall` passed.
- Frontend lint, sequential typecheck and production build passed.
- Browser smoke passed for English Library, Film detail, Watch History,
  Activity, Management and Settings, plus Chinese Library/Film detail. Desktop
  and 375px checks found no document-level horizontal overflow or current
  console errors; a manual watched command appeared in Watch History.
- Runtime compatibility-symbol audit is clean.
- Both Compose files parse, expose `5549:3000`, and contain no removed read-source
  environment setting. Docker CLI is unavailable, so `docker compose config`
  remains unverified.
- Gate B offline run `fresh-canonical-v1-20260826-01` reported tooling passed and
  strict live/human/overall blocked with dataset hash prefix `fbfc9a1a481aef30`.
- The former active database was moved to
  `backend/data/archive/fresh-canonical-cutover-20260826T111552Z/`. The new
  active database has epoch `fresh-canonical-v1`, applied version 1, nine
  predicates, nineteen Genre references, zero Films, no removed tables and
  `PRAGMA integrity_check=ok`.

## Remaining risks

- This is an intentional breaking cutover. Any unarchived old database cannot
  be opened by the new application.
- Docker runtime first-install evidence remains unavailable on this machine.
- Gate B live Evidence and complete human review remain independently blocked.
