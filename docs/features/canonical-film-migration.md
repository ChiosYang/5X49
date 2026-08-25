# Canonical Film Migration

Status: Blocked
Last updated: 2026-08-24
Related: `docs/domain-model.md`, `docs/database-migrations.md`,
`docs/analysis-v2-contract.md`, W2–W3 in `docs/product-roadmap.md`

## Goal

Introduce stable Film identities and separate a work from its local library
items and media assets, while preserving the current Library, user-state,
watch-history, and audit API behavior throughout migration.

## Scope

- Add the canonical identity and collection schema needed by W3.
- Backfill existing Movie rows deterministically with an auditable report.
- Preserve legacy Movie IDs through aliases and keep old tables readable.
- Migrate favorite, rating, notes, and watched data without collapsing multiple
  future Viewing records into one mutable state row.
- Compare legacy and canonical reads before switching existing API handlers.
- Prove upgrade, repeat execution, failure recovery, and backup restoration
  against supported legacy fixtures.

## Non-goals

- Graph UI, Global Graph, path finding, or a new navigation surface.
- Analysis V2 generation, Assertion acceptance policy, or evidence fetching.
- Film merge/unmerge UI or bulk conflict resolution.
- Removing, renaming, or destructively rewriting Movie, MovieUserState, Job, or
  EventRecord tables.
- Changing existing public response shapes during the migration slices.
- Multi-profile UX, Jellyfin synchronization, or a new database dialect.

## Existing behavior

- Movie currently combines work identity, local media, metadata, analysis, and
  library lifecycle fields in one table.
- MovieUserState stores one mutable watched/favorite/rating/notes row per Movie.
- Public Library and user-state endpoints use legacy Movie IDs.
- EventRecord is the current audit source and must remain readable without event
  ID or payload rewriting.
- Schema migration version 1 records checksums and status in
  `schema_migrations`, creates a verified SQLite online backup before upgrading
  an existing database, and absorbs the former Movie/Job `ADD COLUMN` logic.
- Nine SQL fixture profiles cover empty, oldest-supported, current-unversioned,
  partial-column, single-table, and legacy user-state/event databases. The
  offline restore command is exercised against an upgraded and then mutated
  legacy database before the restored backup is migrated again.
- Schema migration version 2 adds the canonical identity/library tables and a
  singleton LocalProfile without modifying legacy Movie reads or events.
- Schema migration version 3 deterministically backfills Film identities,
  LibraryItems, MediaAssets, permanent aliases, conflict review records, and a
  path-free aggregate report while preserving legacy rows.
- Schema migration version 4 adds FilmProfileState and multi-record Viewing,
  migrates meaningful legacy user state, preserves contradictory rows as
  `needs_review`, and leaves the legacy API as source of truth during shadow
  validation.
- Schema migration version 5 adds nullable platform file identity and complete
  content hash fields to MediaAsset. Runtime commands now dual-write canonical
  records and the legacy compatibility projection in one transaction, while
  `LIBRARY_READ_SOURCE` selects canonical, shadow, or emergency legacy reads.

## Acceptance criteria

- [x] A new installation and every supported legacy fixture reach the canonical
  schema through ordered, checksum-validated migrations.
- [x] Film, ExternalIdentity, LibraryItem, MediaAsset, LocalProfile, and
  LegacyMovieAlias constraints match the accepted domain RFC.
- [x] Exact TMDB/IMDb identity matches reuse a Film; conflicting identities do
  not auto-merge and produce a review record.
- [x] Repeating a scan or backfill creates no duplicate Film, LibraryItem,
  MediaAsset, alias, Viewing, or durable review record.
- [x] A local rename/move relinks only one unambiguous LibraryItem candidate;
  ambiguous candidates remain separate and are reported for review.
- [x] Every legacy Movie remains resolvable by its old ID, including after Film
  merge redirects or a local path change.
- [x] Favorite and non-empty legacy watched/rating/notes data survive migration;
  LibraryItem deletion or retirement does not delete Film-level personal data.
- [x] `/library`, movie detail, user-state, watch-history, and audit contract
  tests retain their current public response shapes until an explicitly
  versioned API change is approved.
- [x] Canonical shadow reads produce an explainable field/count difference
  report before any existing handler switches its read source.
- [x] A pre-upgrade backup can be restored offline after an upgraded database is
  mutated, and integrity, counts, sentinel values, and manifest hash are checked.
- [x] Migration reports and logs contain no credentials, hidden reasoning, raw
  user media lists, or unredacted absolute paths.
- [ ] Gate A evidence is recorded in `docs/domain-model.md` before Graph UI work
  begins.

## Decisions

- Use additive migrations. Legacy tables stay available until compatibility
  reads, restore exercises, and a later cleanup RFC prove they can be retired.
- Keep internal Film IDs independent of paths, titles, and provider IDs.
- Treat ExternalIdentity as source-qualified durable identity; title/year is a
  candidate signal, never a global unique key.
- Perform deterministic data conversion locally. Migration and backfill do not
  call TMDB, OpenRouter, or any other network service.
- Separate schema creation from data backfill so each migration and report has a
  narrow rollback and verification surface.
- Use shadow comparison before switching legacy API reads; do not introduce a
  flag day rewrite.
- Keep Graph/Analysis work out of this feature except for the durable foreign-key
  boundaries required by the accepted domain model.
- Preserve one compatibility Movie row per non-retired LibraryItem. Multiple
  editions of one Film remain visible and keep item-specific IDs, paths, status,
  and assets.
- Relink a moved local item only from an unambiguous source-key, platform file
  identity, or bounded sampled fingerprint match. Full hashes run only as a
  single-concurrency background disambiguation step; title/year never auto-merge
  items.
- Preserve `watched=false` legacy rows with rating/notes as `needs_review`
  Viewings. They retain the fields but do not count as watched until confirmed.

## Open questions

- No Gate A blocking domain questions remain for the W3 schema. The three former
  blockers were accepted in `docs/domain-model.md` on 2026-08-21.
- Non-blocking for the first schema slice: retention for Analysis raw artifacts,
  controlled Concept vocabulary, Evidence fetching boundaries, and merge UI.

## Slices

### Slice 0 — Gate A safety baseline

Status: Complete

- Intended behavior: enforce the accepted blocking decisions; expand legacy
  fixtures; fix the current NFO file-snapshot backfill regression; exercise
  verified offline backup restoration.
- Likely affected areas: `docs/domain-model.md`, `backend/fixtures/database/`,
  `backend/test_database_migrations.py`, migration backup/restore tooling, event
  backfill tests.
- Dependencies: migration version 1 and database backup strategy are complete.
- Verification: fixture migration twice, injected failure/retry, open-WAL backup,
  offline restore, record/sentinel/hash comparison, and event audit regression.

### Slice 1 — Canonical identity and library schema

Status: Complete

- Intended behavior: add LocalProfile, Film, ExternalIdentity, LibraryItem,
  MediaAsset, LegacyMovieAlias, and locator-history tables without changing
  current reads.
- Likely affected areas: SQLModel models, migration version 2, schema tests, and
  domain consistency checks.
- Dependencies: accepted Gate A decisions; Slice 0 restore path is executable.
- Verification: empty/current/legacy schema upgrades, FK and unique constraints,
  delete restrictions, and repeat migration.

### Slice 2 — Deterministic Movie backfill

Status: Complete

- Intended behavior: backfill Film identities, library items, media assets, and
  aliases with dry-run and execution reports.
- Likely affected areas: migration/backfill services, migration version 3 or a
  resumable post-schema runner, fixtures, and consistency reporting.
- Dependencies: Slice 1 schema and accepted identity conflict policy.
- Verification: count and sentinel reports, exact provider identity reuse,
  conflict fail-closed behavior, rerun idempotence, and no network calls.

### Slice 3 — Personal state and Viewing

Status: Complete

- Intended behavior: create FilmProfileState and Viewing records from
  MovieUserState while preserving favorites and inconsistent legacy fields.
- Likely affected areas: models, migration/backfill code, compatibility
  projection, user-state and watch-history tests.
- Dependencies: Slice 2 aliases and the accepted inconsistent-state decision.
- Verification: state mapping fixtures, multiple legacy Movies resolving to one
  Film, idempotent source record IDs, and LibraryItem deletion isolation.

### Slice 4 — Shadow reads and compatibility switch

Status: Complete

- Intended behavior: compose current Movie response shapes from canonical data,
  compare them with legacy reads, then switch handlers only after differences
  are accepted.
- Completed behavior: canonical Movie, user-state, and watch-history composition
  now back the existing handlers by default. Runtime writes are transactional
  dual writes; `shadow` returns legacy data while recording sanitized
  differences, and `legacy` provides restart-based rollback. Local moves use
  source keys, platform identity, bounded fingerprints, and a single-concurrency
  complete-hash job when candidates are ambiguous.
- Likely affected areas: Library query services, compatibility projection,
  existing API handlers, contract tests, and API documentation if behavior
  changes.
- Dependencies: Slices 2–3 and a stable difference report.
- Verification: Library/detail/user-state/watch-history/audit contracts, long-ID
  aliases, multiple LibraryItems, missing/restore, and rollback to legacy reads.

### Slice 5 — Gate A evidence and handoff

Status: Blocked

- Intended behavior: collect repeatable, privacy-safe evidence and make Canonical
  Library, Media, Viewing, and the compatibility layer eligible for a strict
  Gate A conclusion.
- Implemented behavior: `python -m app.migrations.gate_a rehearse` validates the
  fixed offline input contract, creates a verified backup and isolated working
  database, proves upgrade/idempotence/consistency/restore, runs repeatable media
  reconcile and clear/restore exercises when real media is present, and writes a
  versioned sanitized report. Its isolated mini-library covers platform-ID
  rename relink, missing/restore, multiple items per Film, the bounded sampling
  budget, deduped collision jobs, and complete-hash disambiguation. `conclude`
  refuses to pass incomplete local or
  Docker evidence. `backend/scripts/gate_a_docker_smoke.ps1` uses unique resource
  names, random host ports, and isolated bind mounts.
- Evidence state: the manually exercised curated acceptance library passed all
  local upgrade, consistency, runtime, restore, and privacy phases in
  `acceptance-final-20260824-1810`. It is still generated media rather than a
  naturally aged private library. Docker is not installed. Strict Gate A
  therefore remains `Blocked`; neither Slice 5 nor this Feature may be marked
  complete from curated fixtures or a development clone.
- Likely affected areas: feature document, domain RFC, migration/restore runbook,
  and quality reports.
- Dependencies: all prior slices.
- Verification: complete fixture matrix, real-library-copy rehearsal, restore
  exercise, sensitive-data scan, and recorded Gate A review conclusion.

Person/Credit/Concept schema, deterministic Legacy backfill, and transactional
NFO/TMDB runtime synchronization are complete in the independent W3
structured-metadata feature through migration v7. Assertion, Evidence, and
AnalysisRun belong to W4 and Gate B. Their additive persistence schema now
exists in version 8, while runtime deduplication, rejected-state protection,
legacy transition, and quality evaluation remain pending; none of these are
Gate A implementation requirements.

The completed W3 work is tracked independently in
`docs/features/structured-metadata-migration.md`. Its v7 W3 rehearsal passed
without expanding Gate A's evidence boundary or changing Gate A's Blocked
conclusion.

## Verification evidence

- The Git-safe Slice 5 evidence summary is
  `docs/quality/canonical-gate-a.md`. It records Gate A as `Blocked`; raw
  versioned reports remain under ignored `backend/data/gate-a/` run directories.
- `.\.venv\Scripts\python.exe -m unittest` over every `test_*.py` module except
  credential-dependent `test_agent.py` — 127 tests passed on 2026-08-24 in
  42.867 seconds, including public Job redaction and pending-file alias recovery.
- The focused Gate/migration/runtime command ran 50 tests covering Gate CLI,
  schema/backfill, nine legacy fixture profiles, backup/restore, Viewing, and
  Canonical runtime behavior; all passed on 2026-08-24.
- `.\.venv\Scripts\python.exe -X utf8 -m compileall -q app scripts test_gate_a.py test_canonical_runtime.py`
  passed. `npm run lint`, `npm run typecheck`, and `npm run build` also passed.
- Both Compose YAML files parsed, and
  `backend/scripts/gate_a_docker_smoke.ps1` passed PowerShell syntax validation.
  Docker runtime evidence remains blocked because the Docker CLI is unavailable.
- A byte-identical development-database copy reached v5 with no second-run
  migration/backup or Shadow drift, restored exactly, and preserved the source
  hash/size/sidecars. The strict conclusion remained blocked because it was a
  development clone with no real media root and no Docker report.

- A 115-test backend run excluding the credential-dependent `test_agent.py`
  passed on 2026-08-24 in 49.555 seconds with exit code 0. It includes runtime
  dual writes and rollback, canonical/shadow/legacy reads, alias and personal
  state projection, legacy-compatible sorting, relink resolution and privacy,
  ordinary/full clears, migration/restore, events, metadata, projections, and
  generated fixtures.
- `.\.venv\Scripts\python.exe -X utf8 -W error::ResourceWarning -m unittest test_canonical_schema.py test_canonical_backfill.py test_database_migrations.py test_database_restore.py test_viewing_migration.py`
  — 28 migration-focused tests passed on 2026-08-24, including all nine legacy
  fixtures and fresh `create_all` databases reaching schema v5 idempotently.
- `.\.venv\Scripts\python.exe -X utf8 -m compileall -q app test_canonical_runtime.py test_canonical_schema.py test_generate_test_data.py`
  — passed on 2026-08-24.
- `npm run lint`, `npm run typecheck`, and `npm run build` passed on
  2026-08-24. A second production build with
  `BACKEND_URL=http://127.0.0.1:8000` also passed for local smoke testing.
- Both Compose files parsed successfully and expose
  `LIBRARY_READ_SOURCE=${LIBRARY_READ_SOURCE:-canonical}`. Docker CLI config and
  runtime smoke could not be executed because Docker is not installed on this
  machine.
- Production browser smoke on port 5549 covered Chinese and English Library,
  detail, Watch History, Activity, and Library Management pages with no console
  errors. A 375 px viewport had no document-level horizontal overflow.
- An isolated normal-profile library was cleared and reconciled on 2026-08-24:
  the cleared alias returned 404 while 12 Films, its Viewing, and favorite state
  remained; reconcile restored all 12 aliases and the original favorite,
  watched, rating, notes, and one-Film watch-history entry.

- A 101-test backend run excluding the credential-dependent `test_agent.py`
  passed on 2026-08-21 in 37.972 seconds with exit code 0. Database and media
  paths were isolated under a validated temporary directory and cleaned after
  the run.
- `.\.venv\Scripts\python.exe -X utf8 -W error::ResourceWarning -m unittest test_viewing_migration.py test_canonical_schema.py test_canonical_backfill.py test_database_migrations.py test_database_restore.py test_api_routes.py test_event_sourced_commands.py test_generate_test_data.py`
  — 44 tests passed on 2026-08-21 after migration v4, covering favorite OR
  aggregation, confirmed/needs-review mapping, idempotence, constraint checks,
  retirement isolation, canonical Movie/user-state/watch-history composition,
  hashed shadow differences, nine legacy upgrades, and unchanged API routes.
- `.\.venv\Scripts\python.exe -X utf8 -W error::ResourceWarning -m unittest test_canonical_schema.py test_event_sourced_commands.py test_viewing_migration.py test_database_migrations.py test_database_restore.py`
  — 30 tests passed on 2026-08-21 after enabling SQLite foreign keys for
  application connections and making legacy clear/missing cleanup delete
  dependent MovieUserState rows before Movie rows.
- `.\.venv\Scripts\python.exe -X utf8 -W error::ResourceWarning -m unittest test_canonical_schema.py test_canonical_backfill.py test_database_migrations.py test_database_restore.py`
  — 22 tests passed on 2026-08-21 after migration v3, including exact identity
  reuse, cross-provider conflict review, no title/year auto-merge, one alias and
  item per legacy Movie, asset/status mapping, path-free reports, repeat
  execution, eight legacy upgrades, backup, and restore.
- `.\.venv\Scripts\python.exe -X utf8 -W error::ResourceWarning -m unittest test_canonical_schema.py test_database_migrations.py test_database_restore.py`
  — 19 tests passed on 2026-08-21, covering canonical table presence,
  singleton profile creation, identity/source/asset constraints, FK delete
  restriction, seven legacy upgrades, repeat migration, backup, and restore.

- `.\.venv\Scripts\python.exe -X utf8 -W error::ResourceWarning -m unittest test_database_migrations.py`
  — 7 tests passed on 2026-08-21 across seven legacy fixture profiles, including
  open-WAL backup, checksum rejection, failure rollback/retry, and idempotence.
- `.\.venv\Scripts\python.exe -X utf8 -W error::ResourceWarning -m unittest test_database_restore.py`
  — 8 tests passed on 2026-08-21, including read-only verification, manifest
  tamper/path-traversal rejection, confirmation mismatch, active-writer
  refusal, CLI replacement, and an upgraded/mutated/restore/remigrate exercise.
- `.\.venv\Scripts\python.exe -X utf8 -W error::ResourceWarning -m unittest test_event_backfill.py`
  — 6 tests passed on 2026-08-21 after correcting Windows NFO snapshot path
  resolution.
- `.\.venv\Scripts\python.exe -X utf8 -m unittest test_generate_test_data.py`
  — 8 tests passed on 2026-08-21.
- An 82-test backend run excluding the credential-dependent `test_agent.py`
  passed on 2026-08-21 with database and media paths isolated under a verified
  temporary directory.
- `.\.venv\Scripts\python.exe -X utf8 -m compileall -q app test_database_restore.py test_database_migrations.py test_event_backfill.py`
  — passed on 2026-08-21.

## Remaining risks

- Slice 4 is complete, but Slice 5 and the overall Feature are blocked until a
  naturally aged real-library-copy rehearsal and the Docker evidence matrix both
  pass. The curated acceptance rehearsal passes locally but Gate A has not
  passed.
- The nine migration fixtures and generated runtime fixtures now extend through schema v8,
  identity conflicts, multiple editions, aliases, relink fingerprints, dual
  writes, and compatibility switching. They are not a substitute for exercising
  a private real-world library copy with large media files.
- The current real development database has not been migrated; only temporary
  databases and generated fixtures have been exercised.
- Docker config, runtime upgrade, environment rollback, and restore behavior
  remain unverified because Docker is not installed on this machine.
