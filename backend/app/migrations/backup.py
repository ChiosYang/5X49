from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MINIMUM_FREE_BYTES = 1024 * 1024


class BackupValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackupArtifact:
    database_path: Path
    manifest_path: Path
    sha256: str
    size_bytes: int
    row_counts: dict[str, int]


def create_verified_backup(
    source_path: Path,
    backup_dir: Path,
    *,
    app_version: str,
    source_schema_version: int,
    target_schema_version: int,
) -> BackupArtifact:
    source_path = source_path.resolve()
    backup_dir = backup_dir.resolve()

    if not source_path.is_file():
        raise BackupValidationError("SQLite source database does not exist")

    with closing(_open_read_only(source_path)) as source:
        _require_integrity(source, "source")
        source_counts = _row_counts(source)

        backup_dir.mkdir(parents=True, exist_ok=True)
        required_bytes = _estimated_backup_bytes(source_path) + MINIMUM_FREE_BYTES
        if shutil.disk_usage(backup_dir).free < required_bytes:
            raise BackupValidationError("Insufficient free space for database backup")

        temporary_path = _temporary_path(backup_dir)
        try:
            with closing(sqlite3.connect(temporary_path)) as target:
                source.backup(target)

            with closing(_open_read_only(temporary_path)) as backup:
                _require_integrity(backup, "backup")
                backup_counts = _row_counts(backup)

            if backup_counts != source_counts:
                raise BackupValidationError("Backup row counts do not match the source database")

            size_bytes = temporary_path.stat().st_size
            if size_bytes <= 0:
                raise BackupValidationError("Backup database is empty")

            sha256 = _sha256(temporary_path)
            created_at = datetime.now(timezone.utc)
            filename = _backup_filename(
                app_version=app_version,
                source_schema_version=source_schema_version,
                target_schema_version=target_schema_version,
                created_at=created_at,
                sha256=sha256,
            )
            database_path = backup_dir / filename
            if database_path.exists():
                raise BackupValidationError("Backup filename collision")
            os.replace(temporary_path, database_path)

            manifest = {
                "format_version": 1,
                "app_version": app_version,
                "created_at": created_at.isoformat(),
                "source_schema_version": source_schema_version,
                "target_schema_version": target_schema_version,
                "database_file": database_path.name,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "row_counts": backup_counts,
                "integrity_check": "ok",
            }
            manifest_path = database_path.with_suffix(".manifest.json")
            _write_manifest(manifest_path, manifest)
            return BackupArtifact(
                database_path=database_path,
                manifest_path=manifest_path,
                sha256=sha256,
                size_bytes=size_bytes,
                row_counts=backup_counts,
            )
        finally:
            temporary_path.unlink(missing_ok=True)


def _open_read_only(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=30)


def _require_integrity(connection: sqlite3.Connection, label: str) -> None:
    results = [row[0] for row in connection.execute("PRAGMA integrity_check")]
    if results != ["ok"]:
        raise BackupValidationError(f"SQLite {label} integrity check failed")


def _row_counts(connection: sqlite3.Connection) -> dict[str, int]:
    table_names = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    counts: dict[str, int] = {}
    for table_name in table_names:
        quoted_name = '"' + table_name.replace('"', '""') + '"'
        row = connection.execute(f"SELECT COUNT(*) FROM {quoted_name}").fetchone()
        counts[table_name] = int(row[0]) if row else 0
    return counts


def _temporary_path(backup_dir: Path) -> Path:
    handle, filename = tempfile.mkstemp(
        prefix=".5x49-database-backup-",
        suffix=".tmp",
        dir=backup_dir,
    )
    os.close(handle)
    return Path(filename)


def _estimated_backup_bytes(source_path: Path) -> int:
    estimated = source_path.stat().st_size
    wal_path = Path(f"{source_path}-wal")
    if wal_path.is_file():
        estimated += wal_path.stat().st_size
    return estimated


def _backup_filename(
    *,
    app_version: str,
    source_schema_version: int,
    target_schema_version: int,
    created_at: datetime,
    sha256: str,
) -> str:
    safe_version = re.sub(r"[^A-Za-z0-9._-]+", "-", app_version).strip("-") or "unknown"
    timestamp = created_at.strftime("%Y%m%dT%H%M%S%fZ")
    return (
        f"5x49-app-{safe_version}-schema-{source_schema_version:04d}"
        f"-to-{target_schema_version:04d}-{timestamp}-{sha256[:12]}.db"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    handle, filename = tempfile.mkstemp(
        prefix=f".{path.name}-",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(filename)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(manifest, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
