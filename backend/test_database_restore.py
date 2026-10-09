import tempfile
import sqlite3
import unittest
import errno
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import text
from sqlmodel import create_engine

from app.database import configure_sqlite_engine
from app.migrations.backup import create_verified_backup, inspect_database
from app.migrations.restore import RestoreValidationError, restore_verified_backup, verify_backup_manifest
from app.migrations.runner import run_migrations
import app.backup as backup_module
import app.migrations.restore as restore_module


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

    def test_backup_changed_after_verification_is_never_restored(self):
        backup = create_verified_backup(
            self.database_path, self.root / "backup", app_version="test",
            source_schema_version=6, target_schema_version=6,
        )
        before = self.database_path.read_bytes()
        copy = restore_module._copy_to_temporary

        def changed_copy(source, destination):
            with closing(sqlite3.connect(source)) as connection:
                connection.execute("UPDATE setting SET value='unverified' WHERE key='sentinel'")
                connection.commit()
            return copy(source, destination)

        with patch.object(restore_module, "_copy_to_temporary", side_effect=changed_copy):
            with self.assertRaisesRegex(RestoreValidationError, "verification"):
                restore_verified_backup(
                    backup.manifest_path, self.database_path,
                    expected_target_sha256=inspect_database(self.database_path).sha256,
                )
        self.assertEqual(self.database_path.read_bytes(), before)

    def test_target_changed_while_preparing_restore_is_not_overwritten(self):
        backup = create_verified_backup(
            self.database_path, self.root / "backup", app_version="test",
            source_schema_version=6, target_schema_version=6,
        )
        copy = restore_module._copy_to_temporary

        def changed_copy(source, destination):
            with closing(sqlite3.connect(self.database_path)) as connection:
                connection.execute("UPDATE setting SET value='new work' WHERE key='sentinel'")
                connection.commit()
            return copy(source, destination)

        with patch.object(restore_module, "_copy_to_temporary", side_effect=changed_copy):
            with self.assertRaisesRegex(RestoreValidationError, "changed"):
                restore_verified_backup(
                    backup.manifest_path, self.database_path,
                    expected_target_sha256=inspect_database(self.database_path).sha256,
                )
        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM setting WHERE key='sentinel'").fetchone()[0], "new work")

    def _backup(self):
        return create_verified_backup(
            self.database_path, self.root / "backup", app_version="test",
            source_schema_version=6, target_schema_version=6,
        )

    def test_preview_is_read_only_and_corrupt_manifest_is_refused(self):
        backup = self._backup()
        before = self.database_path.read_bytes()
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(restore_module.main(["--manifest", str(backup.manifest_path)]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "verified")
        self.assertEqual(self.database_path.read_bytes(), before)
        manifest = json.loads(backup.manifest_path.read_text())
        manifest["sha256"] = "0" * 64
        backup.manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(RestoreValidationError, "SHA-256"):
            verify_backup_manifest(backup.manifest_path)
        self.assertEqual(self.database_path.read_bytes(), before)

    def test_low_space_refuses_before_backup_or_target_mutation(self):
        backup = self._backup()
        before = self.database_path.read_bytes()
        with (
            patch.object(restore_module.shutil, "disk_usage", return_value=SimpleNamespace(free=0)),
            patch.object(restore_module, "create_verified_backup") as preserve,
        ):
            with self.assertRaisesRegex(RestoreValidationError, "Insufficient free space"):
                restore_verified_backup(backup.manifest_path, self.database_path,
                                        expected_target_sha256=inspect_database(self.database_path).sha256)
            preserve.assert_not_called()
        self.assertEqual(self.database_path.read_bytes(), before)

    def test_mid_copy_disk_full_keeps_current_data_and_safety_backup(self):
        backup = self._backup()
        before = self.database_path.read_bytes()
        with patch.object(restore_module.shutil, "copyfile", side_effect=OSError(errno.ENOSPC, "private-storage-canary")):
            with redirect_stderr(io.StringIO()) as errors:
                code = restore_module.main([
                    "--manifest", str(backup.manifest_path), "--replace", "--target", str(self.database_path),
                    "--confirm-current-sha256", inspect_database(self.database_path).sha256,
                ])
        self.assertEqual(code, 2)
        self.assertNotIn("private-storage-canary", errors.getvalue())
        self.assertEqual(self.database_path.read_bytes(), before)
        self.assertEqual(list(self.root.glob(".5x49-database-restore-*")), [])
        manifests = list((self.root / "backups" / "pre-restore").glob("*.manifest.json"))
        self.assertEqual(len(manifests), 1)
        verify_backup_manifest(manifests[0])

    def test_active_writer_blocks_restore_without_losing_committed_data(self):
        backup = self._backup()
        before = self.database_path.read_bytes()
        with closing(sqlite3.connect(self.database_path)) as writer:
            writer.execute("BEGIN IMMEDIATE")
            try:
                with self.assertRaisesRegex(RestoreValidationError, "busy"):
                    restore_verified_backup(backup.manifest_path, self.database_path,
                                            expected_target_sha256=inspect_database(self.database_path).sha256)
            finally:
                writer.rollback()
        self.assertEqual(self.database_path.read_bytes(), before)

    def test_online_backup_includes_committed_wal_rows(self):
        with closing(sqlite3.connect(self.database_path)) as writer:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("UPDATE setting SET value='committed in WAL' WHERE key='sentinel'")
            writer.commit()
            self.assertGreater(Path(f"{self.database_path}-wal").stat().st_size, 0)
            backup = self._backup()
            with closing(sqlite3.connect(backup.database_path)) as copy:
                self.assertEqual(copy.execute("SELECT value FROM setting WHERE key='sentinel'").fetchone()[0], "committed in WAL")
        verify_backup_manifest(backup.manifest_path)

    def test_restore_refuses_unconfirmed_wal_content_without_checkpointing_it(self):
        backup = self._backup()
        with closing(sqlite3.connect(self.database_path)) as writer:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("UPDATE setting SET value='new WAL work' WHERE key='sentinel'")
            writer.commit()
            wal_path = Path(f"{self.database_path}-wal")
            before = (self.database_path.read_bytes(), wal_path.read_bytes())
            with self.assertRaisesRegex(RestoreValidationError, "pending WAL"):
                restore_verified_backup(backup.manifest_path, self.database_path,
                                        expected_target_sha256=inspect_database(self.database_path).sha256)
            self.assertEqual((self.database_path.read_bytes(), wal_path.read_bytes()), before)

    def test_backup_cli_creates_verifiable_artifact_without_changing_source(self):
        before = self.database_path.read_bytes()
        destination = self.root / "manual-backup"
        with redirect_stdout(io.StringIO()) as output:
            code = backup_module.main(["--database", str(self.database_path), "--backup-dir", str(destination)])
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["schema_version"], 6)
        self.assertNotIn(str(self.root), output.getvalue())
        verify_backup_manifest(destination / payload["manifest_file"])
        self.assertEqual(self.database_path.read_bytes(), before)

    def test_backup_cli_missing_source_does_not_create_database_or_expose_path(self):
        missing = self.root / "private-canary.db"
        with redirect_stderr(io.StringIO()) as errors:
            code = backup_module.main(["--database", str(missing), "--backup-dir", str(self.root / "backup")])
        self.assertEqual(code, 2)
        self.assertFalse(missing.exists())
        self.assertNotIn("private-canary", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
