import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from sqlalchemy import inspect, text
from sqlmodel import SQLModel, create_engine

from app.migrations.runner import Migration, MigrationError, run_migrations


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "database"


class DatabaseMigrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_empty_fixture_bootstraps_current_schema_without_backup(self):
        database_path, expected = self._materialize("empty")
        engine = self._engine(database_path)
        try:
            import app.models  # noqa: F401

            SQLModel.metadata.create_all(engine)
            report = run_migrations(
                engine,
                database_path,
                app_version="test",
                backup_required=False,
            )

            self.assertEqual(expected["row_counts"], {})
            self.assertEqual(report.current_version, 1)
            self.assertEqual(report.applied_versions, (1,))
            self.assertIsNone(report.backup)
            self.assertEqual(self._journal_status(engine, 1), "applied")
            self.assertIn("movie", inspect(engine).get_table_names())
        finally:
            engine.dispose()

    def test_oldest_fixture_upgrades_with_verified_backup_and_is_idempotent(self):
        database_path, expected = self._materialize("oldest-supported")
        engine = self._engine(database_path)
        backup_dir = self.tmp_path / "backups"
        try:
            report = run_migrations(
                engine,
                database_path,
                app_version="test",
                backup_dir=backup_dir,
            )

            self.assertEqual(report.current_version, 1)
            self.assertEqual(report.applied_versions, (1,))
            self.assertIsNotNone(report.backup)
            self._assert_backup(report.backup, expected["row_counts"])
            self._assert_sentinels(engine, expected)
            self.assertEqual(self._journal_status(engine, 1), "applied")

            before_columns = self._columns(engine, "movie")
            second = run_migrations(
                engine,
                database_path,
                app_version="test",
                backup_dir=backup_dir,
            )
            self.assertEqual(second.applied_versions, ())
            self.assertIsNone(second.backup)
            self.assertEqual(self._columns(engine, "movie"), before_columns)
            self.assertEqual(len(list(backup_dir.glob("*.db"))), 1)
            self._assert_sentinels(engine, expected)
        finally:
            engine.dispose()

    def test_current_unversioned_fixture_is_stamped_without_rewriting_data(self):
        database_path, expected = self._materialize("current-unversioned")
        engine = self._engine(database_path)
        try:
            before_columns = {
                table: self._columns(engine, table)
                for table in expected["row_counts"]
            }
            report = run_migrations(
                engine,
                database_path,
                app_version="test",
                backup_dir=self.tmp_path / "backups",
            )

            self.assertEqual(report.applied_versions, (1,))
            self._assert_backup(report.backup, expected["row_counts"])
            self._assert_sentinels(engine, expected)
            for table, columns in before_columns.items():
                self.assertEqual(self._columns(engine, table), columns)
        finally:
            engine.dispose()

    def test_backup_includes_committed_rows_from_an_open_wal(self):
        database_path, expected = self._materialize("current-unversioned")
        wal_path = Path(f"{database_path}-wal")

        with closing(sqlite3.connect(database_path)) as writer:
            self.assertEqual(writer.execute("PRAGMA journal_mode = WAL").fetchone()[0], "wal")
            writer.execute("PRAGMA wal_autocheckpoint = 0")
            writer.execute(
                "INSERT INTO job ("
                "id, type, status, attempts, max_attempts, priority, cancel_requested, "
                "created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "current_job_wal_002",
                    "scan",
                    "queued",
                    0,
                    1,
                    0,
                    0,
                    "2025-05-08T07:08:09+00:00",
                    "2025-05-08T07:08:09+00:00",
                ),
            )
            writer.commit()
            self.assertTrue(wal_path.is_file())

            engine = self._engine(database_path)
            try:
                report = run_migrations(
                    engine,
                    database_path,
                    app_version="test",
                    backup_dir=self.tmp_path / "backups",
                )
            finally:
                engine.dispose()

            expected_counts = {**expected["row_counts"], "job": 2}
            self._assert_backup(report.backup, expected_counts)
            with closing(sqlite3.connect(report.backup.database_path)) as backup:
                self.assertEqual(backup.execute("SELECT COUNT(*) FROM job").fetchone()[0], 2)

    def test_failed_migration_rolls_back_and_can_be_retried(self):
        database_path, _ = self._materialize("oldest-supported")
        engine = self._engine(database_path)
        backup_dir = self.tmp_path / "backups"

        def fail_after_write(connection):
            connection.execute(
                text("UPDATE movie SET title = 'must roll back' WHERE id = 'legacy_movie_001'")
            )
            raise RuntimeError("synthetic failure")

        failing = Migration(1, "synthetic_failure", "stable-operation", fail_after_write)
        try:
            with self.assertRaises(MigrationError):
                run_migrations(
                    engine,
                    database_path,
                    migrations=(failing,),
                    app_version="test",
                    backup_dir=backup_dir,
                )

            self.assertEqual(self._movie_title(engine), "Legacy Sentinel")
            self.assertEqual(self._journal_status(engine, 1), "failed")
            self.assertEqual(len(list(backup_dir.glob("*.db"))), 1)

            fixed = Migration(1, "synthetic_failure", "stable-operation", lambda connection: None)
            report = run_migrations(
                engine,
                database_path,
                migrations=(fixed,),
                app_version="test",
                backup_dir=backup_dir,
            )
            self.assertEqual(report.applied_versions, (1,))
            self.assertEqual(self._journal_status(engine, 1), "applied")
            self.assertEqual(self._movie_title(engine), "Legacy Sentinel")
        finally:
            engine.dispose()

    def test_checksum_mismatch_fails_before_backup_or_schema_change(self):
        database_path, _ = self._materialize("oldest-supported")
        engine = self._engine(database_path)
        initial = Migration(1, "checksum_test", "original", lambda connection: None)
        try:
            run_migrations(
                engine,
                database_path,
                migrations=(initial,),
                app_version="test",
                backup_required=False,
            )
            changed = Migration(1, "checksum_test", "changed", lambda connection: None)
            backup_dir = self.tmp_path / "backups"

            with self.assertRaisesRegex(MigrationError, "checksum"):
                run_migrations(
                    engine,
                    database_path,
                    migrations=(changed,),
                    app_version="test",
                    backup_dir=backup_dir,
                )

            self.assertFalse(backup_dir.exists())
            self.assertEqual(self._journal_status(engine, 1), "applied")
        finally:
            engine.dispose()

    def _materialize(self, name: str) -> tuple[Path, dict]:
        fixture_dir = FIXTURES_DIR / name
        database_path = self.tmp_path / f"{name}.db"
        with closing(sqlite3.connect(database_path)) as connection:
            connection.executescript((fixture_dir / "schema.sql").read_text(encoding="utf-8"))
            connection.commit()
        expected = json.loads((fixture_dir / "expected.json").read_text(encoding="utf-8"))
        return database_path, expected

    @staticmethod
    def _engine(database_path: Path):
        return create_engine(f"sqlite:///{database_path}", connect_args={"timeout": 30})

    @staticmethod
    def _columns(engine, table_name: str) -> set[str]:
        return {column["name"] for column in inspect(engine).get_columns(table_name)}

    @staticmethod
    def _journal_status(engine, version: int) -> str:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT status FROM schema_migrations WHERE version = :version"),
                {"version": version},
            ).scalar_one()

    @staticmethod
    def _movie_title(engine) -> str:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT title FROM movie WHERE id = 'legacy_movie_001'")
            ).scalar_one()

    def _assert_sentinels(self, engine, expected: dict) -> None:
        with engine.connect() as connection:
            movie = connection.execute(
                text("SELECT * FROM movie WHERE id = :id"),
                {"id": expected["movie"]["id"]},
            ).mappings().one()
            job = connection.execute(
                text("SELECT * FROM job WHERE id = :id"),
                {"id": expected["job"]["id"]},
            ).mappings().one()
        for key, value in expected["movie"].items():
            self.assertEqual(movie[key], value)
        for key, value in expected["job"].items():
            self.assertEqual(job[key], value)

    def _assert_backup(self, artifact, expected_counts: dict[str, int]) -> None:
        self.assertIsNotNone(artifact)
        manifest = json.loads(artifact.manifest_path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(artifact.database_path.read_bytes()).hexdigest()
        self.assertEqual(manifest["sha256"], digest)
        self.assertEqual(manifest["size_bytes"], artifact.database_path.stat().st_size)
        self.assertEqual(manifest["row_counts"], expected_counts)
        self.assertEqual(manifest["integrity_check"], "ok")
        self.assertNotIn("source_path", manifest)
        with closing(sqlite3.connect(artifact.database_path)) as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
