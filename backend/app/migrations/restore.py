from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from app.migrations.backup import (
    BackupArtifact,
    BackupValidationError,
    create_verified_backup,
    inspect_database,
)


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class RestoreValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedBackup:
    artifact: BackupArtifact
    source_schema_version: int
    target_schema_version: int
    app_version: str


@dataclass(frozen=True)
class RestoreReport:
    target_path: Path
    restored_sha256: str
    restored_size_bytes: int
    restored_row_counts: dict[str, int]
    preserved_database_path: Path
    preserved_manifest_path: Path
    archived_sidecars: tuple[Path, ...]


def verify_backup_manifest(manifest_path: Path) -> VerifiedBackup:
    manifest_path = manifest_path.resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RestoreValidationError("Backup manifest cannot be read") from exc

    _validate_manifest(manifest)
    database_file = manifest["database_file"]
    database_path = (manifest_path.parent / database_file).resolve()
    if database_path.parent != manifest_path.parent:
        raise RestoreValidationError("Backup database must be beside its manifest")

    try:
        snapshot = inspect_database(database_path)
    except BackupValidationError as exc:
        raise RestoreValidationError(str(exc)) from exc

    if snapshot.sha256 != manifest["sha256"]:
        raise RestoreValidationError("Backup SHA-256 does not match its manifest")
    if snapshot.size_bytes != manifest["size_bytes"]:
        raise RestoreValidationError("Backup size does not match its manifest")
    if snapshot.row_counts != manifest["row_counts"]:
        raise RestoreValidationError("Backup row counts do not match its manifest")

    return VerifiedBackup(
        artifact=BackupArtifact(
            database_path=database_path,
            manifest_path=manifest_path,
            sha256=snapshot.sha256,
            size_bytes=snapshot.size_bytes,
            row_counts=snapshot.row_counts,
        ),
        source_schema_version=manifest["source_schema_version"],
        target_schema_version=manifest["target_schema_version"],
        app_version=manifest["app_version"],
    )


def restore_verified_backup(
    manifest_path: Path,
    target_path: Path,
    *,
    expected_target_sha256: str,
    preserve_dir: Path | None = None,
    app_version: str = "0.1.0",
) -> RestoreReport:
    verified = verify_backup_manifest(manifest_path)
    target_path = target_path.resolve()
    if target_path == verified.artifact.database_path:
        raise RestoreValidationError("Backup database cannot restore over itself")
    if not SHA256_PATTERN.fullmatch(expected_target_sha256):
        raise RestoreValidationError("Expected target SHA-256 is invalid")

    try:
        target_snapshot = inspect_database(target_path)
    except BackupValidationError as exc:
        raise RestoreValidationError(str(exc)) from exc
    if target_snapshot.sha256 != expected_target_sha256:
        raise RestoreValidationError("Target SHA-256 changed; refusing to replace database")

    preserve_dir = (preserve_dir or target_path.parent / "backups" / "pre-restore").resolve()
    schema_version = _current_schema_version(target_path)
    try:
        preserved = create_verified_backup(
            target_path,
            preserve_dir,
            app_version=f"{app_version}-pre-restore",
            source_schema_version=schema_version,
            target_schema_version=schema_version,
        )
    except BackupValidationError as exc:
        raise RestoreValidationError("Current database could not be preserved") from exc

    _require_offline_checkpoint(target_path)
    temporary_path = _copy_to_temporary(verified.artifact.database_path, target_path.parent)
    archived_sidecars: tuple[Path, ...] = ()
    try:
        temporary_snapshot = inspect_database(temporary_path)
        if temporary_snapshot != inspect_database(verified.artifact.database_path):
            raise RestoreValidationError("Temporary restore copy failed verification")

        archived_sidecars = _archive_sidecars(target_path, preserve_dir)
        os.replace(temporary_path, target_path)
        restored_snapshot = inspect_database(target_path)
        if restored_snapshot != temporary_snapshot:
            raise RestoreValidationError("Restored database failed post-replace verification")
    finally:
        temporary_path.unlink(missing_ok=True)

    return RestoreReport(
        target_path=target_path,
        restored_sha256=restored_snapshot.sha256,
        restored_size_bytes=restored_snapshot.size_bytes,
        restored_row_counts=restored_snapshot.row_counts,
        preserved_database_path=preserved.database_path,
        preserved_manifest_path=preserved.manifest_path,
        archived_sidecars=archived_sidecars,
    )


def _validate_manifest(manifest: Any) -> None:
    if not isinstance(manifest, dict) or manifest.get("format_version") != 1:
        raise RestoreValidationError("Unsupported backup manifest format")

    database_file = manifest.get("database_file")
    if (
        not isinstance(database_file, str)
        or not database_file
        or Path(database_file).name != database_file
        or "/" in database_file
        or "\\" in database_file
    ):
        raise RestoreValidationError("Backup database filename is unsafe")

    sha256 = manifest.get("sha256")
    if not isinstance(sha256, str) or not SHA256_PATTERN.fullmatch(sha256):
        raise RestoreValidationError("Backup manifest SHA-256 is invalid")

    size_bytes = manifest.get("size_bytes")
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes <= 0:
        raise RestoreValidationError("Backup manifest size is invalid")

    row_counts = manifest.get("row_counts")
    if not isinstance(row_counts, dict) or any(
        not isinstance(table, str)
        or not table
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
        for table, count in row_counts.items()
    ):
        raise RestoreValidationError("Backup manifest row counts are invalid")

    for field in ("source_schema_version", "target_schema_version"):
        value = manifest.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RestoreValidationError(f"Backup manifest {field} is invalid")

    if not isinstance(manifest.get("app_version"), str) or not manifest["app_version"]:
        raise RestoreValidationError("Backup manifest app version is invalid")
    if not isinstance(manifest.get("created_at"), str) or not manifest["created_at"]:
        raise RestoreValidationError("Backup manifest timestamp is invalid")
    if manifest.get("integrity_check") != "ok":
        raise RestoreValidationError("Backup manifest integrity status is invalid")


def _current_schema_version(path: Path) -> int:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        if not table:
            return 0
        row = connection.execute(
            "SELECT MAX(version) FROM schema_migrations WHERE status = 'applied'"
        ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _require_offline_checkpoint(path: Path) -> None:
    try:
        with closing(sqlite3.connect(path, timeout=0.1, isolation_level=None)) as connection:
            result = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if result and int(result[0]) != 0:
                raise RestoreValidationError("Target database is busy; stop the application first")
            connection.execute("BEGIN EXCLUSIVE")
            connection.execute("ROLLBACK")
    except sqlite3.Error as exc:
        raise RestoreValidationError("Target database is busy; stop the application first") from exc


def _copy_to_temporary(source: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    handle, filename = tempfile.mkstemp(
        prefix=".5x49-database-restore-",
        suffix=".tmp",
        dir=destination_dir,
    )
    os.close(handle)
    temporary_path = Path(filename)
    try:
        shutil.copyfile(source, temporary_path)
        with temporary_path.open("r+b") as file:
            os.fsync(file.fileno())
        return temporary_path
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _archive_sidecars(target_path: Path, preserve_dir: Path) -> tuple[Path, ...]:
    sidecars = [Path(f"{target_path}-wal"), Path(f"{target_path}-shm")]
    existing = [path for path in sidecars if path.exists()]
    if not existing:
        return ()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive_dir = preserve_dir / f"sidecars-{timestamp}"
    archive_dir.mkdir(parents=True, exist_ok=False)
    archived = []
    for sidecar in existing:
        destination = archive_dir / sidecar.name
        os.replace(sidecar, destination)
        archived.append(destination)
    return tuple(archived)


def _report_payload(report: RestoreReport) -> dict[str, Any]:
    return {
        "status": "restored",
        "target_file": report.target_path.name,
        "restored_sha256": report.restored_sha256,
        "restored_size_bytes": report.restored_size_bytes,
        "restored_row_counts": report.restored_row_counts,
        "preserved_database_file": report.preserved_database_path.name,
        "preserved_manifest_file": report.preserved_manifest_path.name,
        "archived_sidecar_files": [path.name for path in report.archived_sidecars],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify or restore a 5X49 SQLite backup")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--replace", action="store_true", help="Replace an offline target database")
    parser.add_argument("--target", type=Path)
    parser.add_argument("--confirm-current-sha256")
    parser.add_argument("--preserve-dir", type=Path)
    args = parser.parse_args(argv)

    try:
        if not args.replace:
            verified = verify_backup_manifest(args.manifest)
            payload = {
                "status": "verified",
                "database_file": verified.artifact.database_path.name,
                "sha256": verified.artifact.sha256,
                "size_bytes": verified.artifact.size_bytes,
                "row_counts": verified.artifact.row_counts,
                "source_schema_version": verified.source_schema_version,
                "target_schema_version": verified.target_schema_version,
            }
        else:
            if args.target is None or args.confirm_current_sha256 is None:
                parser.error("--replace requires --target and --confirm-current-sha256")
            payload = _report_payload(
                restore_verified_backup(
                    args.manifest,
                    args.target,
                    expected_target_sha256=args.confirm_current_sha256,
                    preserve_dir=args.preserve_dir,
                )
            )
    except RestoreValidationError as exc:
        print(f"Restore refused: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
