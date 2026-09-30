# RC operator runbook

Updated: 2026-10-01

## Supported boundary

This runbook covers Fresh Canonical schema v1–v5 in epoch
`fresh-canonical-v1`. Pre-epoch development databases are not upgraded or
imported; archive them with their matching older application. Never point a new
build at an old database to experiment. A portable export is not a restorable
database backup.

Run source commands from `backend/` with `uv`; use the actual database path if
`SQLITE_DB_PATH` differs from `data/library.db`. For Docker, paths are inside the
backend container (`/app/data/library.db`, media `/media`). A Docker installation
uses the published image in Compose, not the checked-out source. Record the
image ID/digest and source commit for the build actually being tested.

## Before an upgrade

1. Record the current application commit/image ID and database schema version.
2. Stop frontend/backend writers and watcher jobs. For Docker use
   `docker compose stop`; preserve the data volume. Do not use `down -v`.
3. Back up using the current compatible application environment:

   ```sh
   uv run python -m app.backup --database data/library.db --backup-dir data/backups/manual
   ```

   In Docker, while services are stopped, run the same module in a temporary
   container using the existing data volume:

   ```sh
   docker compose run --rm --no-deps backend python -m app.backup --database data/library.db --backup-dir data/backups/manual
   ```

4. Verify the returned manifest and save the database/manifest pair to protected
   storage outside the upgrade's failure domain:

   ```sh
   uv run python -m app.migrations.restore --manifest <backup.manifest.json>
   ```

5. Start the candidate build. It validates epoch/checksums, makes a verified
   backup before pending migrations, applies additive migrations and initializes
   projections before serving requests. Do not edit an applied migration or its
   checksum to bypass refusal.
6. Check `/health`, Library, a Film detail, Diary, Explore and a confirmed Ask
   form query. Record counts/IDs and a personal record before and after restart.
   `/health` is liveness, not a complete database or user-journey diagnosis.

## Diagnose and repair projections

```sh
uv run python -m app.projections verify
```

Exit 0 means current projection versions, row hashes and stored digests agree.
Exit 2 is a failed check, including an absent database. Verification is read-only
and never repairs or silently returns an empty successful result. It does not
certify provider quality or compare every projection with freshly derived facts.

For missing/stale/corrupt projections, stop writers, create and verify a backup,
then run:

```sh
uv run python -m app.projections rebuild --all
uv run python -m app.projections verify
```

The rebuild is transactional and reads canonical data without contacting media
or external providers. A failed rebuild must be investigated while the service
is stopped; keep the original database and safety backup. Do not delete
canonical rows to get an empty successful report.

For a support record include application commit/image ID, OS/architecture,
schema version, command exit codes, sanitized projection report, workflow ID
and public error code. Inspect logs locally before sharing. Do not attach the
database, settings, raw provider responses, notes, media paths or credentials.

## Full offline restore

1. Stop **all** writers, including other application instances and database
   tools, for the entire operation. Verify the desired backup manifest first.
2. If restore reports pending WAL, keep writers stopped. Use a local SQLite
   connection to checkpoint explicitly; this folds committed WAL data into the
   database, so calculate the confirmation hash afterwards:

   ```sh
   uv run python -c 'import sqlite3; from contextlib import closing; c=sqlite3.connect("data/library.db", timeout=1); print(c.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()); c.close()'
   ```

   A busy checkpoint must be resolved before proceeding. Never delete a WAL or
   SHM file to make a refusal disappear. Take another verified backup if the
   current state must be retained independently.
3. Calculate the exact offline target's SHA-256:

   ```sh
   uv run python -c 'import hashlib; from pathlib import Path; print(hashlib.file_digest(Path("data/library.db").open("rb"), "sha256").hexdigest())'
   ```

4. Replace only after reviewing the backup and target:

   ```sh
   uv run python -m app.migrations.restore --manifest <backup.manifest.json> --replace --target data/library.db --confirm-current-sha256 <current-sha256>
   ```

5. Retain the returned pre-restore safety backup. Restart the application version
   that matches the restored schema. Recheck projections and the same Library,
   Diary and Ask facts. Restoring an older backup and immediately starting the
   new build will run its forward migrations again; this is not a rollback.

The database backup does not contain media/NFO/artwork files. Full database
restore cannot undo arbitrary media changes. Supported file-organization
recovery uses the operation's preview and bounded restore contract separately.

## Failure handling

| Trigger | Expected response and next step |
| --- | --- |
| No provider keys | Local NFO scanning, Library, Diary, factual Explore and Ask form remain usable. Natural-language interpretation and remote enrichment are unavailable. |
| Read-only media | Scan/read existing files; keep application database/cache writable. File organization and NFO/artwork writes require writable media and may fail. |
| Low backup/restore space | Refuse before replacement; release space or choose another protected backup destination, then retry. Never remove the only valid backup. |
| Space runs out during restore copy | Remove the incomplete temporary copy; keep target and safety backup. Reverify both before retry. |
| Failed migration | Stop serving; retain backup and bounded journal error. Transactional schema/data changes are rolled back. Retry only with the cause corrected. |
| Provider timeout/429/5xx | Observe bounded workflow/Ask errors. Retry according to the workflow policy or use the local form; never broaden filters silently. |
| Target changed / pending WAL / active writer | Stop all writers, checkpoint if necessary, verify the new state and obtain a fresh confirmation hash. |
| Restore post-check fails | Keep service stopped. Verify and recover using the pre-restore safety backup. |

## Privacy and exposure

This is a single-user local/self-hosted application. The API has no user-account
authentication boundary; keep it on a trusted host/network or behind separately
configured access control. Do not expose the default backend directly to the
public internet. CORS is not authentication.

Full backups can contain keys, local paths and personal records. Portable
exports intentionally include personal ratings/notes/viewings. Treat both as
private. Ask sends only the typed question and static schema for interpretation;
the no-key form stays local. Analysis/TMDB integrations have their own provider
inputs and must not be described as entirely offline.

See [release readiness](release-readiness.md) for known issues and
[Beta validation](beta-validation.md) for the human evidence still required.
