# 5X49 Fresh Canonical Database Lifecycle

- Status: Adopted
- Epoch: `fresh-canonical-v1`
- Current version: `2`

## Baseline decision

The historical v1–v10 development sequence has been compressed into one new
production baseline. The application still owns a linear SQLite migration
runner, but a new installation is created only by that runner. Startup no
longer combines `SQLModel.metadata.create_all()`, historical migrations and a
projection rebuild.

The baseline migration is static and repository-owned:

```text
backend/app/migrations/versions/v0001_fresh_canonical_baseline.py
backend/app/migrations/schema/fresh_canonical_v1.sql
```

The SQL snapshot is generated from registered SQLModel metadata during
development, reviewed in Git, and verified by schema-equivalence tests. Runtime
never regenerates it.

## Epoch and journal

`schema_metadata` contains the epoch marker `fresh-canonical-v1`.
`schema_migrations` journals the immutable version, name, checksum, timestamps,
status and bounded error summary.

Startup behavior:

1. Resolve the exact SQLite path.
2. Inspect it read-only before creating application tables.
3. If empty, apply baseline v1 and fixed reference rows transactionally.
4. If it has the current epoch, validate checksums and apply future pending v2+.
5. If it contains pre-epoch application tables or another epoch, refuse startup
   without modifying the file.
6. Bootstrap and verify synchronous read models without filesystem or network
   access.
7. Start Job workers, watcher and HTTP traffic only after the journal and
   projections reach the current version.

Repeated startup is a no-op for schema and reference data.

## Baseline contents

Baseline v1 creates the current canonical domain:

- Film/GraphEntity/ExternalIdentity;
- LibraryItem/LocatorHistory/MediaAsset;
- LocalProfile/FilmProfileState/Viewing;
- Person/Credit/Concept/FilmTitle/FilmCountry and provenance/reviews;
- Assertion/Evidence/AnalysisRun and resolution reviews;
- FilmExternalScore/ExternalScoreRefreshState;
- OperationSnapshot;
- Job/EventRecord/Setting.

It also seeds the fixed Assertion predicate registry and the versioned 19-item
TMDB Movie Genre vocabulary. It creates no user Film, media, profile history or
analysis rows.

The baseline intentionally has no Movie table, per-Movie state, legacy alias,
historical backfill report or compatibility projection.

## Additive Schema v2

Schema v2 adds disposable synchronous CQRS tables for Library, Film detail,
search and factual Graph reads, plus `projection_state`. Domain writes refresh
affected rows in the same SQLite transaction. A projection failure rolls back
the domain write and EventRecord as well.

Projection payloads contain only public DTO data and never media locators,
credentials or source payloads. They can be verified or rebuilt without media
or network access:

```powershell
uv run python -m app.projections verify
uv run python -m app.projections rebuild --all
uv run python -m app.projections rebuild --film <film-id>
```

Library and detail APIs never silently fall back to live Canonical joins. A
missing or stale projection returns `503` with code `projection_unavailable`.

## Old database cutover

An old development database is not upgraded or imported. Cutover is an explicit
offline operator action:

1. Stop frontend and backend writers.
2. Resolve only `backend/data/library.db` and its exact `-wal`/`-shm` sidecars.
3. Move existing files to
   `backend/data/archive/fresh-canonical-cutover-<UTC timestamp>/`.
4. Apply Fresh Canonical baseline v1 to a new empty `library.db`.
5. Verify integrity, epoch, version, fixed reference rows and absence of removed tables.
6. Do not copy old settings, scan media or modify video/NFO/artwork files.

The archive is Git-ignored and manually recoverable with an older compatible
application build. The Fresh Canonical application has no old-database import
entry point.

## Future migrations

Future changes resume at version 3. Each migration must have a monotonically
increasing integer version, stable name, deterministic checksum and one
transactional upgrade.

- Never edit an applied migration; add the next version.
- Do not access network services, credentials or media files from migrations.
- Prefer additive schema changes and deterministic bounded data transforms.
- Do not log row content, secrets or paths in journal errors.
- Compare fresh baseline-plus-migrations with the registered current SQLModel schema.
- Test repeat execution, checksum mismatch, transactional failure and recovery.

## Backup and restore

Existing same-epoch databases with future pending migrations use SQLite's
online backup API before mutation. A backup is reopened, integrity-checked,
hashed and described by a path-free manifest. Copying only a live `.db` file is
not an acceptable backup when WAL may be active.

Offline verification:

```powershell
uv run python -m app.migrations.restore --manifest <backup.manifest.json>
```

Replacement requires stopped writers, the exact target and its current SHA-256:

```powershell
uv run python -m app.migrations.restore `
  --manifest <backup.manifest.json> `
  --replace `
  --target data/library.db `
  --confirm-current-sha256 <current-sha256>
```

The restore command creates a safety backup, checks exclusivity, validates the
manifest and target hash, handles exact sidecars and verifies the restored
database. Downgrade migrations are not supported; rollback means restoring a
verified backup and running the corresponding earlier application build.

## Release verification

Before releasing a migration change:

- create a fresh database in an isolated directory;
- run startup twice and compare schema/reference digests;
- verify a deliberately old/pre-epoch database is rejected byte-for-byte;
- exercise failure rollback and checksum mismatch;
- exercise verified backup/restore for a same-epoch database;
- run the full backend test suite and `python -m compileall -q app`.

Gate A and its legacy-fixture/Docker migration matrix are retired. Analysis V2
continues to use Gate B independently; Gate B does not authorize a database
epoch conversion.
