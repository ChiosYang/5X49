# 5X49 Database Migration and Backup Strategy

- Status: Adopted
- Effective from: schema version 1
- Applies to: the embedded SQLite application database

## Purpose

5X49 treats a user's library database as durable product data. A schema change
must therefore be versioned, repeatable, observable, and preceded by a verified
backup. Application startup must stop when those guarantees cannot be met.

This document is the contract for database evolution. Runtime behavior is
implemented under `backend/app/migrations/`; changes to that behavior and this
document must be reviewed together.

## Decision

5X49 uses a small, repository-owned, linear migration runner for the current
SQLite-only architecture. Each migration is an immutable Python module with a
positive integer version, a stable name, a deterministic checksum, and one
transactional `upgrade` operation.

Alembic was evaluated and is deliberately deferred. It would provide mature
revision graph and multi-dialect tooling, but it would not replace 5X49's
required SQLite online backup, integrity checks, manifest, or data backfill
validation. A linear runner is the smaller operational surface while the app
has one embedded database, one release line, and no downgrade requirement.
Re-evaluate Alembic when any of the following becomes true:

- more than one database dialect is supported;
- independent release branches need concurrent migration heads;
- schema diffs regularly require generated revision review;
- database operations are separated from application deployment.

`SQLModel.metadata.create_all()` remains valid for a brand-new database and for
creating tables introduced after all pending migrations succeed. It is not a
substitute for altering an existing schema.

## Version Journal

The runner owns a `schema_migrations` table with one row per version:

| Column | Meaning |
| --- | --- |
| `version` | Monotonically increasing integer primary key. |
| `name` | Stable human-readable migration name. |
| `checksum` | SHA-256 of the migration's declared operations. |
| `started_at` | UTC timestamp for the most recent attempt. |
| `finished_at` | UTC timestamp for success or failure. |
| `status` | `running`, `applied`, or `failed`. |
| `error_summary` | Bounded diagnostic text; never credentials or row data. |

Applied migrations are immutable. If code presents the same version with a
different name or checksum, startup fails closed. A failed version may be
retried only with the same identity and checksum. Registering duplicate,
non-positive, or non-increasing versions is an application error.

The initial migration, version 1, absorbs the former hand-written `ADD COLUMN`
logic for `movie` and `job`. It is intentionally idempotent so it can stamp a
database that already has the current columns without rewriting data.

Migration version 2 adds the canonical identity and library schema:
`graph_entity`, `local_profile`, `film`, `external_identity`, `library_item`,
`library_item_locator_history`, `media_asset`, `legacy_movie_alias`, identity
review, and canonical backfill report tables. It creates the single local
profile idempotently and leaves all legacy tables and public reads unchanged.

Migration version 3 reads legacy Movie rows in stable ID order. Exact TMDB and
IMDb identities reuse a Film; cross-provider conflicts remain separate and
create an identity review. Title/year never auto-merges. Each legacy row gets
one LibraryItem and permanent alias, local/provider assets are normalized and
deduplicated, and the migration stores aggregate counts without titles or
paths. Re-executing the backfill skips existing aliases and creates no durable
duplicates.

## Startup Sequence

Database initialization runs before the job runtime and filesystem watcher:

1. Resolve the configured SQLite path and inspect whether it contains user
   tables without modifying it.
2. Discover pending migrations. A database without the journal is treated as
   being at version 0.
3. If an existing database has pending migrations, run the backup preflight and
   create one verified online backup before changing schema or creating the
   journal.
4. Apply pending migrations one at a time. Each schema/data operation runs in
   its own transaction; journal status is committed separately so failure is
   diagnosable.
5. Run `SQLModel.metadata.create_all()` only after existing-schema migrations
   succeed. For a new empty database, create the current schema first and then
   run the idempotent migrations without a backup.
6. Start jobs, watchers, and API traffic only after the database reaches the
   current version.

No migration runs from a request handler or background job.

## Pre-upgrade Backup Contract

The backup implementation uses SQLite's online backup API. Copying only a live
`.db` file is forbidden because write-ahead-log state may not be included.

Before migration the runner must:

- run `PRAGMA integrity_check` against the source and require exactly `ok`;
- ensure the backup destination is writable and has enough free space;
- write to a temporary file in the destination directory;
- complete the SQLite online backup, then reopen it independently;
- run `PRAGMA integrity_check` against the backup;
- require the backup to be non-empty and record its byte size;
- compute a SHA-256 hash and atomically move it to its final name;
- atomically write a JSON manifest containing app version, source and target
  schema versions, UTC timestamp, hash, size, table row counts, and filename.

Backups live beside application data under `backups/database/`. Final names
contain the app version, source and target schema versions, UTC timestamp, and a
hash prefix. The source path is intentionally excluded from the manifest so a
support bundle does not disclose a user's filesystem layout.

There is no automatic retention or unattended restore in this first slice.
Backups are never deleted by migration code. Restore is an explicit offline
operator action implemented by `python -m app.migrations.restore` from the
`backend/` directory.

Verification is the default and does not modify the target:

```bash
uv run python -m app.migrations.restore --manifest <backup.manifest.json>
```

Replacement requires the application to be stopped, the exact target path, and
the current target file SHA-256 as a confirmation token:

```bash
uv run python -m app.migrations.restore \
  --manifest <backup.manifest.json> \
  --replace \
  --target data/library.db \
  --confirm-current-sha256 <current-library.db-sha256>
```

Before replacement the command creates and verifies a second backup of the
current target under `backups/pre-restore/`, checkpoints WAL, checks exclusive
access, archives remaining WAL/SHM sidecars, copies the selected backup through
a verified temporary file, atomically replaces the target, and verifies the
restored integrity, hash, size, and row counts. It refuses path traversal,
manifest mismatch, a changed target hash, a busy database, or a failed safety
backup. The previous compatible application version should be used after
restoring an older schema.

## Failure and Recovery Semantics

Migration is fail-closed. The application does not start when source integrity,
disk capacity, backup creation, backup verification, checksum validation, or a
migration operation fails.

Every migration operation is transactional. A failed operation is rolled back,
its journal row is marked `failed`, and the pre-upgrade backup remains available.
Already applied earlier versions are not rolled back automatically. Rerunning
the same release skips applied versions and retries a failed version, making
recovery deterministic after the underlying issue is corrected.

Downgrade migrations are not supported. Rollback means restoring the verified
pre-upgrade backup and running the prior application release.

## Legacy Fixture Policy

Legacy databases are represented as reviewable SQL fixture sources, not checked
in binary `.db` files. Tests materialize them in a temporary directory and may
never open or copy the developer's real `backend/data/library.db`.

The compatibility set is:

- `empty`: no user tables, representing a first installation;
- `oldest-supported`: minimal historical `movie` and `job` tables with rows that
  require column creation and default backfills;
- `current-unversioned`: current-era core tables and representative rows but no
  migration journal, representing an existing installation at adoption time.
- `partial-legacy-columns`: an interrupted or partially upgraded database where
  some version 1 columns and non-default values already exist;
- `movie-only`: a historical database containing only the `movie` table;
- `job-only`: a historical database containing only the `job` table;
- `legacy-user-state-events`: a pre-journal database with movies, jobs, user
  state, and audit events that must survive upgrade and restore unchanged.

Each fixture includes expected invariants such as row counts and sentinel field
values. Fixtures must use synthetic identifiers, relative media paths, and no
credentials or personal filesystem locations.

Every migration change must test, where applicable:

- upgrade from each supported legacy fixture;
- source and backup integrity plus manifest hash/size/counts;
- preservation and expected transformation of sentinel data;
- a second run producing no schema or data changes and no extra backup;
- checksum mismatch rejection;
- migration failure rollback, journal status, and continued readability of the
  legacy tables.

## Change Rules

- Never edit an applied migration; add the next integer version.
- Keep migrations independent of network services, API keys, media files, and
  wall-clock-local time.
- Prefer additive schema changes and resumable, explicitly validated backfills.
- Do not log row contents or sensitive settings in error summaries.
- Update this contract when backup layout, journal semantics, support window, or
  recovery behavior changes.
- Before a release containing a new migration, exercise backup restoration in a
  temporary environment and compare integrity, row counts, and sentinel data.
