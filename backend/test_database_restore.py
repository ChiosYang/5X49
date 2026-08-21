import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from sqlalchemy import text
from sqlmodel import create_engine

from app.migrations.backup import inspect_database
from app.migrations.restore import (
    RestoreValidationError,
    main,
    restore_verified_backup,
    verify_backup_manifest,
)
from app.migrations.runner import run_migrations
from app.migrations.versions import MIGRATIONS


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "database"
CURRENT_VERSION = MIGRATIONS[-1].version
ALL_VERSIONS = tuple(migration.version for migration in MIGRATIONS)


class DatabaseRestoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_manifest_verification_matches_created_backup(self):
        database_path = self._materialize("oldest-supported")
        engine = self._engine(database_path)
        try:
            migration = run_migrations(
                engine,
                database_path,
                app_version="test",
                backup_dir=self.tmp_path / "backups",
            )
        finally:
            engine.dispose()

        verified = verify_backup_manifest(migration.backup.manifest_path)

        self.assertEqual(verified.artifact.sha256, migration.backup.sha256)
        self.assertEqual(verified.artifact.row_counts, {"job": 1, "movie": 1})
        self.assertEqual(verified.source_schema_version, 0)
        self.assertEqual(verified.target_schema_version, CURRENT_VERSION)

    def test_verify_cli_reports_manifest_metadata_without_modifying_database(self):
        database_path = self._materialize("oldest-supported")
        engine = self._engine(database_path)
        try:
            migration = run_migrations(
                engine,
                database_path,
                app_version="test",
                backup_dir=self.tmp_path / "backups",
            )
        finally:
            engine.dispose()
        database_before = inspect_database(database_path)
        output = StringIO()

        with redirect_stdout(output):
            exit_code = main(["--manifest", str(migration.backup.manifest_path)])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "verified")
        self.assertEqual(payload["sha256"], migration.backup.sha256)
        self.assertNotIn("target_path", payload)
        self.assertEqual(inspect_database(database_path), database_before)

    def test_restore_cli_replaces_target_without_reporting_absolute_paths(self):
        database_path = self._materialize("oldest-supported")
        engine = self._engine(database_path)
        try:
            migration = run_migrations(
                engine,
                database_path,
                app_version="test",
                backup_dir=self.tmp_path / "backups",
            )
        finally:
            engine.dispose()
        current = inspect_database(database_path)
        output = StringIO()

        with redirect_stdout(output):
            exit_code = main([
                "--manifest",
                str(migration.backup.manifest_path),
                "--replace",
                "--target",
                str(database_path),
                "--confirm-current-sha256",
                current.sha256,
                "--preserve-dir",
                str(self.tmp_path / "pre-restore"),
            ])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "restored")
        self.assertEqual(payload["target_file"], database_path.name)
        self.assertEqual(payload["restored_sha256"], migration.backup.sha256)
        self.assertNotIn(str(self.tmp_path), output.getvalue())
        self.assertEqual(inspect_database(database_path).sha256, migration.backup.sha256)

    def test_full_restore_preserves_upgraded_database_and_restores_legacy_content(self):
        database_path = self._materialize("legacy-user-state-events")
        engine = self._engine(database_path)
        try:
            migration = run_migrations(
                engine,
                database_path,
                app_version="test",
                backup_dir=self.tmp_path / "upgrade-backups",
            )
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE movie SET title = 'Mutated After Upgrade' "
                        "WHERE id = 'state_movie_watched'"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO events ("
                        "id, aggregate_type, aggregate_id, type, actor_type, "
                        "schema_version, occurred_at"
                        ") VALUES ("
                        "'evt_after_upgrade', 'movie', 'state_movie_watched', "
                        "'MovieStateBackfilled', 'migration', 1, "
                        "'2026-08-21T00:00:00+00:00'"
                        ")"
                    )
                )
        finally:
            engine.dispose()

        mutated_snapshot = inspect_database(database_path)
        report = restore_verified_backup(
            migration.backup.manifest_path,
            database_path,
            expected_target_sha256=mutated_snapshot.sha256,
            preserve_dir=self.tmp_path / "pre-restore",
            app_version="test",
        )

        self.assertEqual(report.restored_sha256, migration.backup.sha256)
        self.assertEqual(report.restored_row_counts, migration.backup.row_counts)
        with closing(sqlite3.connect(database_path)) as restored:
            title = restored.execute(
                "SELECT title FROM movie WHERE id = 'state_movie_watched'"
            ).fetchone()[0]
            event_count = restored.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            journal = restored.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
            ).fetchone()
        self.assertEqual(title, "Watched Legacy Movie")
        self.assertEqual(event_count, 2)
        self.assertIsNone(journal)

        preserved = verify_backup_manifest(report.preserved_manifest_path)
        self.assertEqual(preserved.artifact.row_counts["events"], 3)
        self.assertEqual(preserved.artifact.row_counts["schema_migrations"], len(MIGRATIONS))
        with closing(sqlite3.connect(report.preserved_database_path)) as current_backup:
            preserved_title = current_backup.execute(
                "SELECT title FROM movie WHERE id = 'state_movie_watched'"
            ).fetchone()[0]
        self.assertEqual(preserved_title, "Mutated After Upgrade")

        retry_engine = self._engine(database_path)
        try:
            retry = run_migrations(
                retry_engine,
                database_path,
                app_version="test",
                backup_dir=self.tmp_path / "retry-backups",
            )
            self.assertEqual(retry.applied_versions, ALL_VERSIONS)
        finally:
            retry_engine.dispose()

    def test_wrong_target_confirmation_refuses_without_preserving_or_replacing(self):
        database_path = self._materialize("oldest-supported")
        engine = self._engine(database_path)
        try:
            migration = run_migrations(
                engine,
                database_path,
                app_version="test",
                backup_dir=self.tmp_path / "backups",
            )
        finally:
            engine.dispose()
        before = inspect_database(database_path)
        preserve_dir = self.tmp_path / "pre-restore"

        with self.assertRaisesRegex(RestoreValidationError, "Target SHA-256 changed"):
            restore_verified_backup(
                migration.backup.manifest_path,
                database_path,
                expected_target_sha256="0" * 64,
                preserve_dir=preserve_dir,
            )

        self.assertEqual(inspect_database(database_path), before)
        self.assertFalse(preserve_dir.exists())

    def test_active_write_transaction_refuses_restore_without_replacing_target(self):
        database_path = self._materialize("oldest-supported")
        engine = self._engine(database_path)
        try:
            migration = run_migrations(
                engine,
                database_path,
                app_version="test",
                backup_dir=self.tmp_path / "backups",
            )
        finally:
            engine.dispose()

        with closing(sqlite3.connect(database_path)) as writer:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute(
                "UPDATE movie SET title = 'Current Title' WHERE id = 'legacy_movie_001'"
            )
            writer.commit()
            current = inspect_database(database_path)
            writer.execute("BEGIN IMMEDIATE")
            writer.execute(
                "UPDATE movie SET title = 'Uncommitted Title' WHERE id = 'legacy_movie_001'"
            )

            with self.assertRaisesRegex(RestoreValidationError, "busy"):
                restore_verified_backup(
                    migration.backup.manifest_path,
                    database_path,
                    expected_target_sha256=current.sha256,
                    preserve_dir=self.tmp_path / "pre-restore",
                )
            writer.rollback()

        with closing(sqlite3.connect(database_path)) as current_database:
            title = current_database.execute(
                "SELECT title FROM movie WHERE id = 'legacy_movie_001'"
            ).fetchone()[0]
        self.assertEqual(title, "Current Title")

    def test_manifest_path_traversal_is_rejected(self):
        manifest_path = self.tmp_path / "unsafe.manifest.json"
        manifest_path.write_text(
            json.dumps({
                "format_version": 1,
                "app_version": "test",
                "created_at": "2026-08-21T00:00:00+00:00",
                "source_schema_version": 0,
                "target_schema_version": 1,
                "database_file": "../outside.db",
                "sha256": "0" * 64,
                "size_bytes": 1,
                "row_counts": {},
                "integrity_check": "ok",
            }),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(RestoreValidationError, "filename is unsafe"):
            verify_backup_manifest(manifest_path)

    def test_tampered_manifest_hash_is_rejected(self):
        database_path = self._materialize("oldest-supported")
        engine = self._engine(database_path)
        try:
            migration = run_migrations(
                engine,
                database_path,
                app_version="test",
                backup_dir=self.tmp_path / "backups",
            )
        finally:
            engine.dispose()
        manifest = json.loads(migration.backup.manifest_path.read_text(encoding="utf-8"))
        manifest["sha256"] = "0" * 64
        migration.backup.manifest_path.write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(RestoreValidationError, "SHA-256 does not match"):
            verify_backup_manifest(migration.backup.manifest_path)

    def _materialize(self, name: str) -> Path:
        fixture_dir = FIXTURES_DIR / name
        database_path = self.tmp_path / f"{name}.db"
        with closing(sqlite3.connect(database_path)) as connection:
            connection.executescript((fixture_dir / "schema.sql").read_text(encoding="utf-8"))
            connection.commit()
        return database_path

    @staticmethod
    def _engine(database_path: Path):
        return create_engine(f"sqlite:///{database_path}", connect_args={"timeout": 30})


if __name__ == "__main__":
    unittest.main()
