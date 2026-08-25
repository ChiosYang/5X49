import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import inspect, text
from sqlmodel import SQLModel, create_engine

from app.migrations.runner import Migration, MigrationError, run_migrations
from app.migrations.versions import MIGRATIONS


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "database"
ADDITIONAL_FIXTURES = (
    "partial-legacy-columns",
    "movie-only",
    "job-only",
    "legacy-user-state-events",
    "canonical-identities",
    "viewing-migration",
)
CURRENT_VERSION = MIGRATIONS[-1].version
ALL_VERSIONS = tuple(migration.version for migration in MIGRATIONS)


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
            self.assertEqual(report.current_version, CURRENT_VERSION)
            self.assertEqual(report.applied_versions, ALL_VERSIONS)
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

            self.assertEqual(report.current_version, CURRENT_VERSION)
            self.assertEqual(report.applied_versions, ALL_VERSIONS)
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

            self.assertEqual(report.applied_versions, ALL_VERSIONS)
            self._assert_backup(report.backup, expected["row_counts"])
            self._assert_sentinels(engine, expected)
            for table, columns in before_columns.items():
                self.assertEqual(self._columns(engine, table), columns)
        finally:
            engine.dispose()

    def test_additional_legacy_fixture_matrix_preserves_declared_data(self):
        for fixture_name in ADDITIONAL_FIXTURES:
            with self.subTest(fixture=fixture_name):
                database_path, expected = self._materialize(fixture_name)
                engine = self._engine(database_path)
                backup_dir = self.tmp_path / f"{fixture_name}-backups"
                try:
                    report = run_migrations(
                        engine,
                        database_path,
                        app_version="test",
                        backup_dir=backup_dir,
                    )

                    self.assertEqual(report.applied_versions, ALL_VERSIONS)
                    self._assert_backup(report.backup, expected["row_counts"])
                    self._assert_declared_sentinels(engine, expected)

                    second = run_migrations(
                        engine,
                        database_path,
                        app_version="test",
                        backup_dir=backup_dir,
                    )
                    self.assertEqual(second.applied_versions, ())
                    self.assertIsNone(second.backup)
                    self.assertEqual(len(list(backup_dir.glob("*.db"))), 1)
                    self._assert_declared_sentinels(engine, expected)
                finally:
                    engine.dispose()

    def test_schema_v5_upgrades_to_v6_without_changing_existing_domain_rows(self):
        database_path, _ = self._materialize("current-unversioned")
        engine = self._engine(database_path)
        try:
            initial = run_migrations(
                engine,
                database_path,
                migrations=MIGRATIONS[:5],
                app_version="test-v5",
                backup_required=False,
            )
            self.assertEqual(initial.current_version, 5)
            existing_tables = set(inspect(engine).get_table_names()) - {"schema_migrations"}
            with engine.connect() as connection:
                counts_before = {
                    table: connection.execute(
                        text(f'SELECT COUNT(*) FROM "{table}"')
                    ).scalar_one()
                    for table in existing_tables
                }

            upgraded = run_migrations(
                engine,
                database_path,
                migrations=MIGRATIONS[:6],
                app_version="test-v6",
                backup_dir=self.tmp_path / "v6-backups",
            )

            self.assertEqual(upgraded.applied_versions, (6,))
            self.assertEqual(upgraded.current_version, 6)
            self.assertIsNotNone(upgraded.backup)
            with engine.connect() as connection:
                counts_after = {
                    table: connection.execute(
                        text(f'SELECT COUNT(*) FROM "{table}"')
                    ).scalar_one()
                    for table in existing_tables
                }
                for table in (
                    "person",
                    "credit",
                    "credit_provenance",
                    "concept",
                    "concept_alias",
                    "film_title",
                    "film_country",
                    "film_country_provenance",
                    "structured_metadata_review",
                ):
                    self.assertEqual(
                        connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one(),
                        0,
                    )
            self.assertEqual(counts_after, counts_before)

            second = run_migrations(
                engine,
                database_path,
                migrations=MIGRATIONS[:6],
                app_version="test-v6",
                backup_dir=self.tmp_path / "v6-backups",
            )
            self.assertEqual(second.applied_versions, ())
            self.assertIsNone(second.backup)
            self.assertEqual(len(list((self.tmp_path / "v6-backups").glob("*.db"))), 1)
        finally:
            engine.dispose()

    def test_schema_v6_upgrades_to_v7_with_idempotent_structured_backfill(self):
        database_path, expected = self._materialize("current-unversioned")
        engine = self._engine(database_path)
        try:
            initial = run_migrations(
                engine,
                database_path,
                migrations=MIGRATIONS[:6],
                app_version="test-v6",
                backup_required=False,
            )
            self.assertEqual(initial.current_version, 6)
            with engine.connect() as connection:
                canonical_counts_before = {
                    table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                    for table in ("movie", "film", "library_item", "legacy_movie_alias", "viewing")
                }

            upgraded = run_migrations(
                engine,
                database_path,
                migrations=MIGRATIONS[:7],
                app_version="test-v7",
                backup_dir=self.tmp_path / "v7-backups",
            )
            self.assertEqual(upgraded.applied_versions, (7,))
            self.assertEqual(upgraded.current_version, 7)
            self.assertIsNotNone(upgraded.backup)
            with engine.connect() as connection:
                canonical_counts_after = {
                    table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                    for table in canonical_counts_before
                }
                self.assertEqual(
                    connection.execute(
                        text(
                            "SELECT status FROM canonical_backfill_run "
                            "WHERE run_key='legacy_structured_metadata.v1'"
                        )
                    ).scalar_one(),
                    "succeeded",
                )
                self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM concept")).scalar_one(), 19)
                title_count = connection.execute(
                    text("SELECT COUNT(*) FROM film_title")
                ).scalar_one()
                movie_count = expected["row_counts"].get("movie", 0)
                self.assertGreaterEqual(title_count, movie_count * 2)
                self.assertLessEqual(title_count, movie_count * 3)
            self.assertEqual(canonical_counts_after, canonical_counts_before)

            second = run_migrations(
                engine,
                database_path,
                migrations=MIGRATIONS[:7],
                app_version="test-v7",
                backup_dir=self.tmp_path / "v7-backups",
            )
            self.assertEqual(second.applied_versions, ())
            self.assertIsNone(second.backup)
            self.assertEqual(len(list((self.tmp_path / "v7-backups").glob("*.db"))), 1)
        finally:
            engine.dispose()

    def test_schema_v7_backfill_failure_rolls_back_and_retries(self):
        database_path, expected = self._materialize("current-unversioned")
        engine = self._engine(database_path)
        try:
            run_migrations(
                engine,
                database_path,
                migrations=MIGRATIONS[:6],
                app_version="test-v6",
                backup_required=False,
            )
            with patch(
                "app.services.structured_metadata_sync."
                "structured_metadata_synchronizer.sync",
                side_effect=RuntimeError("synthetic structured backfill failure"),
            ):
                with self.assertRaises(MigrationError):
                    run_migrations(
                        engine,
                        database_path,
                        migrations=MIGRATIONS[:7],
                        app_version="test-v7-failure",
                        backup_required=False,
                    )

            with engine.connect() as connection:
                self.assertEqual(self._journal_status(engine, 7), "failed")
                for table in (
                    "person",
                    "credit",
                    "credit_provenance",
                    "concept",
                    "concept_alias",
                    "film_title",
                    "film_country",
                    "film_country_provenance",
                    "structured_metadata_review",
                ):
                    self.assertEqual(
                        connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one(),
                        0,
                        table,
                    )
                self.assertEqual(
                    connection.execute(text("SELECT COUNT(*) FROM movie")).scalar_one(),
                    expected["row_counts"]["movie"],
                )

            retried = run_migrations(
                engine,
                database_path,
                migrations=MIGRATIONS[:7],
                app_version="test-v7-retry",
                backup_required=False,
            )
            self.assertEqual(retried.applied_versions, (7,))
            self.assertEqual(self._journal_status(engine, 7), "applied")
        finally:
            engine.dispose()

    def test_schema_v7_upgrades_to_v8_without_changing_existing_domain_rows(self):
        database_path, _ = self._materialize("current-unversioned")
        engine = self._engine(database_path)
        backup_dir = self.tmp_path / "v8-backups"
        preserved_tables = (
            "movie",
            "film",
            "library_item",
            "legacy_movie_alias",
            "viewing",
            "person",
            "credit",
            "concept",
            "structured_metadata_review",
        )
        try:
            initial = run_migrations(
                engine,
                database_path,
                migrations=MIGRATIONS[:7],
                app_version="test-v7",
                backup_required=False,
            )
            self.assertEqual(initial.current_version, 7)
            with engine.connect() as connection:
                before = {
                    table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                    for table in preserved_tables
                }

            upgraded = run_migrations(
                engine,
                database_path,
                migrations=MIGRATIONS[:8],
                app_version="test-v8",
                backup_dir=backup_dir,
            )

            self.assertEqual(upgraded.applied_versions, (8,))
            self.assertEqual(upgraded.current_version, 8)
            self.assertIsNotNone(upgraded.backup)
            with engine.connect() as connection:
                after = {
                    table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
                    for table in preserved_tables
                }
                self.assertEqual(
                    connection.execute(text("SELECT COUNT(*) FROM assertion_predicate")).scalar_one(),
                    9,
                )
                for table in (
                    "analysis_run",
                    "assertion",
                    "evidence",
                    "assertion_evidence",
                    "assertion_provenance",
                    "analysis_resolution_review",
                ):
                    self.assertEqual(
                        connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one(),
                        0,
                    )
            self.assertEqual(after, before)

            second = run_migrations(
                engine,
                database_path,
                migrations=MIGRATIONS[:8],
                app_version="test-v8",
                backup_dir=backup_dir,
            )
            self.assertEqual(second.applied_versions, ())
            self.assertIsNone(second.backup)
            self.assertEqual(len(list(backup_dir.glob("*.db"))), 1)
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

    def _assert_declared_sentinels(self, engine, expected: dict) -> None:
        with engine.connect() as connection:
            for sentinel in expected.get("sentinels", []):
                table = self._quoted_identifier(sentinel["table"])
                predicates = []
                parameters = {}
                for index, (column, value) in enumerate(sentinel["key"].items()):
                    parameter = f"key_{index}"
                    predicates.append(f"{self._quoted_identifier(column)} = :{parameter}")
                    parameters[parameter] = value
                row = connection.execute(
                    text(f"SELECT * FROM {table} WHERE {' AND '.join(predicates)}"),
                    parameters,
                ).mappings().one()
                for column, value in sentinel["values"].items():
                    self.assertEqual(row[column], value)

    @staticmethod
    def _quoted_identifier(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

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
