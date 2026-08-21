# Canonical Film Migration

Status: In Progress
Last updated: 2026-08-21
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
- Seven SQL fixture profiles cover empty, oldest-supported, current-unversioned,
  partial-column, single-table, and legacy user-state/event databases. The
  offline restore command is exercised against an upgraded and then mutated
  legacy database before the restored backup is migrated again.
- Schema migration version 2 adds the canonical identity/library tables and a
  singleton LocalProfile without modifying legacy Movie reads or events.

## Acceptance criteria

- [x] A new installation and every supported legacy fixture reach the canonical
  schema through ordered, checksum-validated migrations.
- [x] Film, ExternalIdentity, LibraryItem, MediaAsset, LocalProfile, and
  LegacyMovieAlias constraints match the accepted domain RFC.
- [ ] Exact TMDB/IMDb identity matches reuse a Film; conflicting identities do
  not auto-merge and produce a review record.
- [ ] Repeating a scan or backfill creates no duplicate Film, LibraryItem,
  MediaAsset, alias, Viewing, or durable review record.
- [ ] A local rename/move relinks only one unambiguous LibraryItem candidate;
  ambiguous candidates remain separate and are reported for review.
- [ ] Every legacy Movie remains resolvable by its old ID, including after Film
  merge redirects or a local path change.
- [ ] Favorite and non-empty legacy watched/rating/notes data survive migration;
  LibraryItem deletion or retirement does not delete Film-level personal data.
- [ ] `/library`, movie detail, user-state, watch-history, and audit contract
  tests retain their current public response shapes until an explicitly
  versioned API change is approved.
- [ ] Canonical shadow reads produce an explainable field/count difference
  report before any existing handler switches its read source.
- [x] A pre-upgrade backup can be restored offline after an upgraded database is
  mutated, and integrity, counts, sentinel values, and manifest hash are checked.
- [ ] Migration reports and logs contain no credentials, hidden reasoning, raw
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

Status: Pending

- Intended behavior: backfill Film identities, library items, media assets, and
  aliases with dry-run and execution reports.
- Likely affected areas: migration/backfill services, migration version 3 or a
  resumable post-schema runner, fixtures, and consistency reporting.
- Dependencies: Slice 1 schema and accepted identity conflict policy.
- Verification: count and sentinel reports, exact provider identity reuse,
  conflict fail-closed behavior, rerun idempotence, and no network calls.

### Slice 3 — Personal state and Viewing

Status: Pending

- Intended behavior: create FilmProfileState and Viewing records from
  MovieUserState while preserving favorites and inconsistent legacy fields.
- Likely affected areas: models, migration/backfill code, compatibility
  projection, user-state and watch-history tests.
- Dependencies: Slice 2 aliases and the accepted inconsistent-state decision.
- Verification: state mapping fixtures, multiple legacy Movies resolving to one
  Film, idempotent source record IDs, and LibraryItem deletion isolation.

### Slice 4 — Shadow reads and compatibility switch

Status: Pending

- Intended behavior: compose current Movie response shapes from canonical data,
  compare them with legacy reads, then switch handlers only after differences
  are accepted.
- Likely affected areas: Library query services, compatibility projection,
  existing API handlers, contract tests, and API documentation if behavior
  changes.
- Dependencies: Slices 2–3 and a stable difference report.
- Verification: Library/detail/user-state/watch-history/audit contracts, long-ID
  aliases, multiple LibraryItems, missing/restore, and rollback to legacy reads.

### Slice 5 — Gate A evidence and handoff

Status: Pending

- Intended behavior: collect review evidence, close the implementation checklist,
  and make canonical Film data safe for Analysis V2 and later single-film Graph
  work.
- Likely affected areas: feature document, domain RFC, migration/restore runbook,
  and quality reports.
- Dependencies: all prior slices.
- Verification: complete fixture matrix, real-library-copy rehearsal, restore
  exercise, sensitive-data scan, and recorded Gate A review conclusion.

## Verification evidence

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

- The accepted Gate A decisions are documented but not yet implemented or
  covered by W3 behavior tests.
- The seven migration fixtures cover the version 1 safety baseline; canonical
  identity conflicts, multiple editions, moves, aliases, and Viewing backfill
  still need W3-specific fixtures in later slices.
- The current real development database has not been migrated; only temporary
  databases and generated fixtures have been exercised.
- Docker runtime upgrade and restore behavior remain unverified because the
  recorded clean-install environment did not have Docker available.
