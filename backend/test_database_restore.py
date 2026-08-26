import tempfile
import unittest
from pathlib import Path

from sqlalchemy import text
from sqlmodel import create_engine

from app.database import configure_sqlite_engine
from app.migrations.backup import create_verified_backup, inspect_database
from app.migrations.restore import RestoreValidationError, restore_verified_backup, verify_backup_manifest
from app.migrations.runner import run_migrations


class FreshCanonicalRestoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.database_path = self.root / "library.db"
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, self.database_path, app_version="test", backup_required=False)
        with self.engine.begin() as connection:
            connection.execute(text("INSERT INTO setting (key, value, updated_at) VALUES ('sentinel', 'before', '2026-08-26T00:00:00Z')"))
        self.engine.dispose()

    def tearDown(self):
        self._tmp.cleanup()

    def test_verified_backup_restore_round_trip_preserves_v1_epoch(self):
        backup = create_verified_backup(
            self.database_path,
            self.root / "backup",
            app_version="test",
            source_schema_version=1,
            target_schema_version=1,
        )
        verified = verify_backup_manifest(backup.manifest_path)
        self.assertEqual(verified.artifact.sha256, backup.sha256)

        engine = create_engine(f"sqlite:///{self.database_path}")
        with engine.begin() as connection:
            connection.execute(text("UPDATE setting SET value='after' WHERE key='sentinel'"))
        engine.dispose()
        current_sha = inspect_database(self.database_path).sha256
        report = restore_verified_backup(
            backup.manifest_path,
            self.database_path,
            expected_target_sha256=current_sha,
            preserve_dir=self.root / "pre-restore",
            app_version="test",
        )
        self.assertEqual(report.restored_sha256, backup.sha256)
        engine = create_engine(f"sqlite:///{self.database_path}")
        try:
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text("SELECT value FROM setting WHERE key='sentinel'")).scalar_one(), "before")
                self.assertEqual(connection.execute(text("SELECT epoch FROM schema_metadata")).scalar_one(), "fresh-canonical-v1")
        finally:
            engine.dispose()

    def test_restore_rejects_stale_target_hash_without_modifying_database(self):
        backup = create_verified_backup(
            self.database_path,
            self.root / "backup",
            app_version="test",
            source_schema_version=1,
            target_schema_version=1,
        )
        before = self.database_path.read_bytes()
        with self.assertRaisesRegex(RestoreValidationError, "Target SHA-256 changed"):
            restore_verified_backup(
                backup.manifest_path,
                self.database_path,
                expected_target_sha256="0" * 64,
                preserve_dir=self.root / "pre-restore",
            )
        self.assertEqual(self.database_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
