"""Create a verified SQLite backup without booting or migrating the application."""

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Sequence

from app.migrations.backup import BackupValidationError, create_verified_backup


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--backup-dir", required=True, type=Path)
    parser.add_argument("--app-version", default="0.1.0")
    args = parser.parse_args(argv)
    try:
        uri = f"{args.database.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
            row = connection.execute("SELECT MAX(version) FROM schema_migrations WHERE status = 'applied'").fetchone()
            schema_version = int(row[0] or 0)
        artifact = create_verified_backup(
            args.database, args.backup_dir, app_version=args.app_version,
            source_schema_version=schema_version, target_schema_version=schema_version,
        )
    except (OSError, sqlite3.Error, BackupValidationError):
        print("Backup refused: check database integrity, permissions and available space", file=sys.stderr)
        return 2
    print(json.dumps({
        "status": "verified", "database_file": artifact.database_path.name,
        "manifest_file": artifact.manifest_path.name, "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes, "schema_version": schema_version,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
