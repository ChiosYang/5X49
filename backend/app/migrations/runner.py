from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from sqlalchemy import Connection, Engine, inspect, text

from app.migrations.backup import BackupArtifact, create_verified_backup


JOURNAL_TABLE = "schema_migrations"


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    checksum_material: str
    upgrade: Callable[[Connection], None]

    @property
    def checksum(self) -> str:
        value = f"{self.version}\0{self.name}\0{self.checksum_material}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MigrationReport:
    current_version: int
    applied_versions: tuple[int, ...]
    backup: BackupArtifact | None


@dataclass(frozen=True)
class _JournalEntry:
    version: int
    name: str
    checksum: str
    status: str


def run_migrations(
    engine: Engine,
    sqlite_path: Path,
    *,
    migrations: Sequence[Migration] | None = None,
    app_version: str = "0.1.0",
    backup_required: bool = True,
    backup_dir: Path | None = None,
) -> MigrationReport:
    if migrations is None:
        from app.migrations.versions import MIGRATIONS

        migrations = MIGRATIONS

    ordered = _validate_registry(migrations)
    journal = _read_journal(engine)
    applied_versions = _validate_journal(journal, ordered)
    pending = [item for item in ordered if item.version not in applied_versions]
    current_version = max(applied_versions, default=0)

    if not pending:
        return MigrationReport(
            current_version=current_version,
            applied_versions=(),
            backup=None,
        )

    backup = None
    if backup_required:
        destination = backup_dir or sqlite_path.parent / "backups" / "database"
        backup = create_verified_backup(
            sqlite_path,
            destination,
            app_version=app_version,
            source_schema_version=current_version,
            target_schema_version=ordered[-1].version,
        )

    _ensure_journal(engine)
    newly_applied: list[int] = []
    for migration in pending:
        _set_journal_status(engine, migration, "running")
        try:
            with engine.begin() as connection:
                migration.upgrade(connection)
        except Exception as exc:
            try:
                _set_journal_status(
                    engine,
                    migration,
                    "failed",
                    error_summary=f"{type(exc).__name__}: migration operation failed",
                )
            except Exception:
                pass
            raise MigrationError(
                f"Database migration {migration.version} ({migration.name}) failed"
            ) from exc

        _set_journal_status(engine, migration, "applied")
        newly_applied.append(migration.version)

    return MigrationReport(
        current_version=ordered[-1].version,
        applied_versions=tuple(newly_applied),
        backup=backup,
    )


def database_has_user_tables(sqlite_path: Path) -> bool:
    if not sqlite_path.is_file() or sqlite_path.stat().st_size == 0:
        return False

    uri = f"{sqlite_path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "AND name != ? LIMIT 1",
            (JOURNAL_TABLE,),
        ).fetchone()
    return row is not None


def _validate_registry(migrations: Sequence[Migration]) -> tuple[Migration, ...]:
    ordered = tuple(migrations)
    versions = [item.version for item in ordered]
    if any(version <= 0 for version in versions):
        raise MigrationError("Migration versions must be positive integers")
    if versions != sorted(set(versions)):
        raise MigrationError("Migration versions must be unique and increasing")
    if any(not item.name.strip() for item in ordered):
        raise MigrationError("Migration names must not be empty")
    return ordered


def _read_journal(engine: Engine) -> dict[int, _JournalEntry]:
    with engine.connect() as connection:
        if JOURNAL_TABLE not in inspect(connection).get_table_names():
            return {}
        rows = connection.execute(
            text(
                "SELECT version, name, checksum, status "
                f"FROM {JOURNAL_TABLE} ORDER BY version"
            )
        ).mappings()
        return {
            int(row["version"]): _JournalEntry(
                version=int(row["version"]),
                name=str(row["name"]),
                checksum=str(row["checksum"]),
                status=str(row["status"]),
            )
            for row in rows
        }


def _validate_journal(
    journal: dict[int, _JournalEntry],
    migrations: Sequence[Migration],
) -> set[int]:
    registered = {item.version: item for item in migrations}
    valid_statuses = {"running", "applied", "failed"}
    for version, entry in journal.items():
        migration = registered.get(version)
        if migration is None:
            raise MigrationError(
                f"Database schema version {version} is not supported by this application"
            )
        if entry.name != migration.name or entry.checksum != migration.checksum:
            raise MigrationError(f"Database migration {version} checksum does not match")
        if entry.status not in valid_statuses:
            raise MigrationError(f"Database migration {version} has invalid status")

    applied = {version for version, entry in journal.items() if entry.status == "applied"}
    expected_prefix = {item.version for item in migrations[: len(applied)]}
    if applied != expected_prefix:
        raise MigrationError("Applied database migrations are not a contiguous prefix")
    return applied


def _ensure_journal(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {JOURNAL_TABLE} ("
                "version INTEGER PRIMARY KEY, "
                "name VARCHAR NOT NULL, "
                "checksum VARCHAR NOT NULL, "
                "started_at VARCHAR NOT NULL, "
                "finished_at VARCHAR, "
                "status VARCHAR NOT NULL, "
                "error_summary VARCHAR"
                ")"
            )
        )


def _set_journal_status(
    engine: Engine,
    migration: Migration,
    status: str,
    *,
    error_summary: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    finished_at = now if status in {"applied", "failed"} else None
    with engine.begin() as connection:
        connection.execute(
            text(
                f"INSERT INTO {JOURNAL_TABLE} "
                "(version, name, checksum, started_at, finished_at, status, error_summary) "
                "VALUES (:version, :name, :checksum, :started_at, :finished_at, :status, :error_summary) "
                "ON CONFLICT(version) DO UPDATE SET "
                "name = excluded.name, checksum = excluded.checksum, "
                "started_at = excluded.started_at, finished_at = excluded.finished_at, "
                "status = excluded.status, error_summary = excluded.error_summary"
            ),
            {
                "version": migration.version,
                "name": migration.name,
                "checksum": migration.checksum,
                "started_at": now,
                "finished_at": finished_at,
                "status": status,
                "error_summary": error_summary[:500] if error_summary else None,
            },
        )
