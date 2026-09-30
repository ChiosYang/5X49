# 5X49 Fresh Canonical Database Lifecycle

- Status: Adopted
- Epoch: `fresh-canonical-v1`
- Current version: `5`

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
7. Start the private Job worker, watcher and HTTP traffic only after the journal and
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

`verify` opens an existing database read-only, never initializes or repairs it,
and exits 2 with a bounded error code on missing/stale/corrupt state. `rebuild`
explicitly initializes the supported schema but skips startup projection
verification so damaged read models can actually be repaired. Stop application
writers and make a verified backup before repair. Neither command needs a
provider key or media access.

## Additive Schema v3

Schema v3 adds durable `workflow_run` and `workflow_step` records and links the
private `job` execution queue to the active run/step. Workflow definitions stay
versioned in code. Public long-operation status is read from Workflow/Step;
Job has no HTTP or SSE representation.

Worker restart moves an interrupted step back to queued when retry budget
remains. Completed steps retain their hashes and terminal state; cancellation
and retry resume from the first incomplete step. Public summaries are bounded
and exclude payloads, paths, provider output and credentials.

## Additive Schema v4

Schema v4 adds disposable synchronous CQRS projections for deterministic
Factual Explore:

- `explore_film_read_model` stores visible Film sort/year/watched state;
- `explore_facet_read_model` stores Genre, Person, Country and derived Decade
  membership, eligibility, conflict state and a bounded public payload.

It does not migrate or reinterpret Canonical user facts. On an existing v3
database, startup first creates and verifies an online SQLite backup, applies
the additive DDL transactionally, then rebuilds all synchronous projections.
New or version-mismatched Explore projection state is not served during this
process. Rebuild reads only Canonical SQLite rows and does not access media,
network services, model providers or credentials.

The registered states are `explore_films=factual-explore-film.v1` and
`explore_facets=factual-explore-facet.v1`. Domain and Viewing mutations refresh
affected Explore rows in the same transaction; any projection failure rolls
back the originating write. Public Explore queries never fall back to live
Canonical joins and return `503 projection_unavailable` while state is absent,
failed or stale.

## Additive Schema v5

Schema v5 adds `cinema_dna_film_read_model`, a disposable profile/Film projection
for all-time confirmed viewing history. It includes active historical Films
without any visible LibraryItem. It is refreshed independently of Library and
Detail projection existence, using the same factual selector as Explore.

The registered state is `cinema_dna=cinema-dna-film.v1`. A v4 upgrade creates a
verified backup, applies only the new table DDL and rebuilds projections through
the existing bootstrap. Repeated startup does not change domain facts. Rating,
Viewing and metadata writes refresh the projection transactionally; failed
projection writes roll back the domain transaction. Missing, failed or stale
state returns `503 projection_unavailable` instead of an empty statistic.

The normal verify/rebuild/backup/restore commands cover this table. It is absent
from `library-export.v1`, which continues to export Canonical facts only.

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

Future changes start at version 6. Each migration must have a monotonically
increasing integer version, stable name, deterministic checksum and one
transactional upgrade.

- Never edit an applied migration; add the next version.
- Do not access network services, credentials or media files from migrations.
- Prefer additive schema changes and deterministic bounded data transforms.
- Do not log row content, secrets or paths in journal errors.
- Compare fresh baseline-plus-migrations with the registered current SQLModel schema.
- Test repeat execution, checksum mismatch, transactional failure and recovery.

The runner explicitly begins a SQLite transaction before migration DDL. The
schema/data changes and `applied` journal update commit together. DDL failures,
including a failed final journal write, roll back before recording a bounded
`failed` status; a retry must not encounter partially committed new tables.

## Backup and restore

Existing same-epoch databases with future pending migrations use SQLite's
online backup API before mutation. A backup is reopened, integrity-checked,
hashed and described by a path-free manifest. Copying only a live `.db` file is
not an acceptable backup when WAL may be active.

Offline verification:

Create an operator backup without booting, migrating or scanning the application
(run from `backend/`, substitute the actual database path):

```sh
uv run python -m app.backup --database data/library.db --backup-dir data/backups/manual
```

Keep the returned `.db` and `.manifest.json` together. The backup command exits
2 on integrity/storage errors and does not expose raw storage exceptions. A
full backup contains private settings, paths and personal data; keep it local
or in protected storage, not in a public issue or Git.

Verify the returned manifest before replacement:

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

Restore also checks destination space and revalidates the target after preparing
the copy. The copied database must match the originally verified manifest, even
if the backup changes during preparation. A non-empty target WAL is refused:
stop every writer, explicitly checkpoint offline, then calculate a new target
SHA-256. Never delete WAL/SHM files to bypass this guard. Online **backup** still
captures committed WAL rows through SQLite's backup API.

An exclusivity probe and repeated hashes do not replace the stopped-writer
requirement: keep all application instances and database tools stopped for the
entire replacement. Storage failure before replacement leaves the target and
verified safety backup available. For post-replacement verification failure,
leave the application stopped and recover from that safety backup.

See [the RC operator runbook](rc-operations.md) for the full release/recovery
sequence and [release readiness](release-readiness.md) for measured boundaries.

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
