import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel, create_engine

import app.database as database_module
import app.models  # noqa: F401
from app.database import configure_sqlite_engine
from app.migrations.runner import Migration, MigrationError, run_migrations
from app.migrations.versions import MIGRATIONS
from app.migrations.versions.v0001_fresh_canonical_baseline import BASELINE_SQL_SHA256


class FreshCanonicalMigrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _engine(self, name: str):
        path = self.root / name
        engine = create_engine(f"sqlite:///{path}", poolclass=NullPool)
        configure_sqlite_engine(engine)
        return path, engine

    def test_fresh_v1_is_static_idempotent_and_has_fixed_reference_rows(self):
        path, engine = self._engine("fresh.db")
        try:
            first = run_migrations(engine, path, app_version="test", backup_required=False)
            before = self._digest(engine)
            second = run_migrations(engine, path, app_version="test", backup_required=False)
            self.assertEqual(first.current_version, 1)
            self.assertEqual(first.applied_versions, (1,))
            self.assertEqual(second.applied_versions, ())
            self.assertIsNone(second.backup)
            self.assertEqual(before, self._digest(engine))
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text("SELECT epoch FROM schema_metadata")).scalar_one(), "fresh-canonical-v1")
                self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM assertion_predicate")).scalar_one(), 9)
                self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM concept WHERE kind='genre'")).scalar_one(), 19)
                self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM local_profile")).scalar_one(), 1)
        finally:
            engine.dispose()

    def test_baseline_ddl_matches_registered_sqlmodel_schema(self):
        migrated_path, migrated = self._engine("migrated.db")
        model_path, model = self._engine("model.db")
        try:
            run_migrations(migrated, migrated_path, app_version="test", backup_required=False)
            SQLModel.metadata.create_all(model)
            migrated_tables = set(inspect(migrated).get_table_names()) - {"schema_migrations"}
            model_tables = set(inspect(model).get_table_names())
            self.assertEqual(migrated_tables, model_tables)
            for table in sorted(model_tables):
                self.assertEqual(self._table_signature(migrated, table), self._table_signature(model, table), table)
            self.assertRegex(BASELINE_SQL_SHA256, r"^[0-9a-f]{64}$")
        finally:
            migrated.dispose()
            model.dispose()

    def test_database_entrypoint_rejects_pre_epoch_database_without_mutation(self):
        path, engine = self._engine("old.db")
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE movie (id TEXT PRIMARY KEY, title TEXT NOT NULL)")
            connection.execute("INSERT INTO movie VALUES ('old', 'sentinel')")
            connection.commit()
        before = path.read_bytes()
        original_engine = database_module.engine
        try:
            database_module.engine = engine
            with self.assertRaisesRegex(MigrationError, "predates the fresh Canonical baseline"):
                database_module._assert_fresh_schema_epoch()
        finally:
            database_module.engine = original_engine
            engine.dispose()
        self.assertEqual(before, path.read_bytes())

    def test_migration_checksum_mismatch_is_rejected(self):
        path, engine = self._engine("checksum.db")
        try:
            run_migrations(engine, path, app_version="test", backup_required=False)
            changed = Migration(
                version=1,
                name=MIGRATIONS[0].name,
                checksum_material="changed",
                upgrade=lambda _connection: None,
            )
            with self.assertRaisesRegex(MigrationError, "checksum"):
                run_migrations(engine, path, migrations=(changed,), app_version="test", backup_required=False)
        finally:
            engine.dispose()

    def test_failed_additive_migration_rolls_back_and_can_retry(self):
        path, engine = self._engine("retry.db")
        base = Migration(1, "base", "v1", lambda connection: connection.execute(text("CREATE TABLE sentinel (value TEXT)")))

        def fail(connection):
            connection.execute(text("INSERT INTO sentinel VALUES ('must rollback')"))
            raise RuntimeError("boom")

        failing = Migration(2, "next", "v2", fail)
        fixed = Migration(2, "next", "v2", lambda connection: connection.execute(text("INSERT INTO sentinel VALUES ('ok')")))
        try:
            run_migrations(engine, path, migrations=(base,), app_version="test", backup_required=False)
            with self.assertRaises(MigrationError):
                run_migrations(engine, path, migrations=(base, failing), app_version="test", backup_required=False)
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM sentinel")).scalar_one(), 0)
            report = run_migrations(engine, path, migrations=(base, fixed), app_version="test", backup_required=False)
            self.assertEqual(report.applied_versions, (2,))
        finally:
            engine.dispose()

    @staticmethod
    def _table_signature(engine, table: str):
        inspector = inspect(engine)
        columns = tuple(
            (item["name"], str(item["type"]), bool(item["nullable"]), item.get("default"))
            for item in inspector.get_columns(table)
        )
        indexes = tuple(sorted((item["name"], tuple(item["column_names"]), bool(item["unique"])) for item in inspector.get_indexes(table)))
        uniques = tuple(sorted(tuple(item["column_names"]) for item in inspector.get_unique_constraints(table)))
        fks = tuple(sorted((tuple(item["constrained_columns"]), item["referred_table"], tuple(item["referred_columns"])) for item in inspector.get_foreign_keys(table)))
        return columns, indexes, uniques, fks

    @staticmethod
    def _digest(engine):
        with engine.connect() as connection:
            return tuple(
                connection.execute(text("SELECT name, type, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name")).all()
            )


if __name__ == "__main__":
    unittest.main()
