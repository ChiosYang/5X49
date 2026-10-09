import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import event, inspect, text
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel, Session, create_engine, select

import app.database as database_module
import app.models  # noqa: F401
from app.database import configure_sqlite_engine
from app.migrations.runner import Migration, MigrationError, run_migrations
from app.migrations.versions import MIGRATIONS
from app.migrations.versions.v0001_fresh_canonical_baseline import BASELINE_SQL_SHA256
from app.migrations.backup import BackupValidationError
from app.migrations.restore import verify_backup_manifest
from app.canonical_models import Film, FilmProfileState, GraphEntity, LocalProfile, Viewing, LibraryItem, LibraryFilmReadModel
from app.services.projections import projection_coordinator


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

    def test_fresh_schema_is_static_idempotent_and_has_fixed_reference_rows(self):
        path, engine = self._engine("fresh.db")
        try:
            first = run_migrations(engine, path, app_version="test", backup_required=False)
            before = self._digest(engine)
            second = run_migrations(engine, path, app_version="test", backup_required=False)
            self.assertEqual(first.current_version, 6)
            self.assertEqual(first.applied_versions, (1, 2, 3, 4, 5, 6))
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
        with closing(sqlite3.connect(path)) as connection:
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

    def test_v3_to_v4_upgrade_creates_verified_backup_and_explore_tables(self):
        path, engine = self._engine("v3-upgrade.db")
        backup_dir = self.root / "backups"
        try:
            first = run_migrations(
                engine,
                path,
                migrations=MIGRATIONS[:3],
                app_version="test",
                backup_required=False,
            )
            self.assertEqual(first.current_version, 3)
            report = run_migrations(
                engine,
                path,
                migrations=MIGRATIONS[:4],
                app_version="test",
                backup_required=True,
                backup_dir=backup_dir,
            )
            self.assertEqual(report.current_version, 4)
            self.assertEqual(report.applied_versions, (4,))
            self.assertIsNotNone(report.backup)
            self.assertTrue(report.backup.database_path.is_file())
            self.assertTrue(report.backup.manifest_path.is_file())
            tables = set(inspect(engine).get_table_names())
            self.assertIn("explore_film_read_model", tables)
            self.assertIn("explore_facet_read_model", tables)
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

    def test_failed_ddl_migration_leaves_no_partial_schema_and_can_retry(self):
        path, engine = self._engine("ddl-failure.db")
        base = Migration(1, "base", "v1", lambda connection: connection.execute(text("CREATE TABLE sentinel (value TEXT)")))

        def fail(connection):
            connection.execute(text("CREATE TABLE added (value TEXT)"))
            connection.execute(text("INSERT INTO sentinel VALUES ('must rollback')"))
            raise RuntimeError("simulated disk failure")

        failing = Migration(2, "next", "v2", fail)
        fixed = Migration(2, "next", "v2", lambda connection: connection.execute(text("CREATE TABLE added (value TEXT)")))
        try:
            run_migrations(engine, path, migrations=(base,), backup_required=False)
            with self.assertRaises(MigrationError):
                run_migrations(engine, path, migrations=(base, failing), backup_required=False)
            self.assertNotIn("added", inspect(engine).get_table_names())
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM sentinel")).scalar_one(), 0)
            self.assertEqual(run_migrations(engine, path, migrations=(base, fixed), backup_required=False).applied_versions, (2,))
        finally:
            engine.dispose()

    def test_journal_write_failure_rolls_back_migration_data_and_schema(self):
        path, engine = self._engine("journal-failure.db")
        base = Migration(1, "base", "v1", lambda connection: connection.execute(text("CREATE TABLE sentinel (value TEXT)")))

        def upgrade(connection):
            connection.execute(text("CREATE TABLE added (value TEXT)"))
            connection.execute(text("INSERT INTO sentinel VALUES ('once')"))

        next_migration = Migration(2, "next", "v2", upgrade)

        def fail_applied(_connection, _cursor, statement, _parameters, context, _many):
            compiled = getattr(context, "compiled_parameters", None)
            values = compiled[0] if compiled else {}
            if "INSERT INTO schema_migrations" in statement and values.get("status") == "applied":
                raise sqlite3.OperationalError("simulated journal disk failure")

        try:
            run_migrations(engine, path, migrations=(base,), backup_required=False)
            event.listen(engine, "before_cursor_execute", fail_applied)
            with self.assertRaises((MigrationError, sqlite3.OperationalError)):
                run_migrations(engine, path, migrations=(base, next_migration), backup_required=False)
            event.remove(engine, "before_cursor_execute", fail_applied)
            self.assertNotIn("added", inspect(engine).get_table_names())
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM sentinel")).scalar_one(), 0)
            run_migrations(engine, path, migrations=(base, next_migration), backup_required=False)
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM sentinel")).scalar_one(), 1)
        finally:
            engine.dispose()

    def test_all_supported_upgrade_versions_preserve_personal_facts_and_rebuild(self):
        for version in range(1, 6):
            with self.subTest(version=version):
                path, engine = self._engine(f"upgrade-{version}.db")
                try:
                    run_migrations(engine, path, migrations=MIGRATIONS[:version], backup_required=False)
                    film_id = "film_" + "a" * 32
                    with Session(engine) as session:
                        session.info["skip_projection_hook"] = True
                        profile_id = session.exec(select(LocalProfile.id)).one()
                        session.add(GraphEntity(id=film_id, entity_type="film"))
                        session.flush()
                        session.add(Film(id=film_id, canonical_title="Upgrade fixture", release_year=1999))
                        session.flush()
                        session.execute(text("INSERT INTO film_profile_state (profile_id,film_id,favorite,rating,notes,created_at,updated_at) VALUES (:profile,:film,0,4,'preserve me','2026-01-01','2026-01-01')"), {"profile":profile_id,"film":film_id})
                        session.add(Viewing(id="view_" + "b" * 32, profile_id=profile_id, film_id=film_id,
                                           source="diary", source_record_id="fixture"))
                        session.commit()
                    report = run_migrations(engine, path, backup_dir=self.root / f"backup-{version}")
                    self.assertEqual(report.applied_versions, tuple(range(version + 1, 7)))
                    self.assertEqual(verify_backup_manifest(report.backup.manifest_path).source_schema_version, version)
                    projection_coordinator.bootstrap(engine)
                    with Session(engine) as session:
                        self.assertEqual(session.get(Film, film_id).canonical_title, "Upgrade fixture")
                        state = session.exec(select(FilmProfileState)).one()
                        self.assertEqual((state.rating, state.notes), (4, "preserve me"))
                        self.assertEqual(len(session.exec(select(Viewing)).all()), 1)
                        self.assertEqual(projection_coordinator.verify_session(session)["status"], "passed")
                    self.assertEqual(run_migrations(engine, path).applied_versions, ())
                finally:
                    engine.dispose()

    def test_insufficient_backup_space_prevents_any_upgrade(self):
        path, engine = self._engine("low-space.db")
        try:
            run_migrations(engine, path, migrations=MIGRATIONS[:4], backup_required=False)
            before = path.read_bytes()
            with patch("app.migrations.backup.shutil.disk_usage", return_value=SimpleNamespace(free=0)):
                with self.assertRaisesRegex(BackupValidationError, "Insufficient free space"):
                    run_migrations(engine, path, backup_dir=self.root / "low-space-backups")
            self.assertEqual(path.read_bytes(), before)
            self.assertNotIn("cinema_dna_film_read_model", inspect(engine).get_table_names())
        finally:
            engine.dispose()

    def test_v5_upgrade_preserves_displayed_default_and_personal_state(self):
        path, engine = self._engine("primary-upgrade.db")
        try:
            run_migrations(engine,path,migrations=MIGRATIONS[:5],backup_required=False)
            film_id="film_"+"a"*32
            second="lib_"+"c"*32
            with Session(engine) as session:
                session.info["skip_projection_hook"]=True
                profile=session.exec(select(LocalProfile.id)).one()
                session.add(GraphEntity(id=film_id,entity_type="film"));session.flush()
                session.add(Film(id=film_id,canonical_title="Upgrade editions"));session.flush()
                for id,added in [("lib_"+"b"*32,"2026-01-01"),(second,"2026-01-02")]:
                    session.add(LibraryItem(id=id,film_id=film_id,profile_id=profile,source_type="local_folder",
                        source_instance_id="local",source_item_key=id,added_at=added))
                session.flush()
                session.add(LibraryFilmReadModel(film_id=film_id,sort_title="upgrade editions",primary_item_id=second,
                    payload={},source_hash="a"*64,projection_version="library-film.v1"))
                session.execute(text("INSERT INTO film_profile_state (profile_id,film_id,favorite,rating,notes,created_at,updated_at) VALUES (:profile,:film,1,4,'keep notes','2026-01-01','2026-01-01')"),{"profile":profile,"film":film_id})
                session.commit()
            report=run_migrations(engine,path,backup_dir=self.root/"primary-backups")
            self.assertEqual(report.applied_versions,(6,))
            self.assertEqual(verify_backup_manifest(report.backup.manifest_path).source_schema_version,5)
            projection_coordinator.bootstrap(engine)
            with Session(engine) as session:
                state=session.get(FilmProfileState,(profile,film_id))
                self.assertEqual((state.primary_item_id,state.favorite,state.rating,state.notes),(second,True,4,"keep notes"))
                projected=session.get(LibraryFilmReadModel,film_id)
                self.assertEqual(projected.primary_item_id,second)
                self.assertEqual(projected.projection_version,"library-film.v2")
        finally:engine.dispose()

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
