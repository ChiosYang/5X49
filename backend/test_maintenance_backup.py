import hashlib
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, nullcontext, redirect_stdout
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select
from app.api import backups as routes
from app.database import configure_sqlite_engine
from app.migrations import backup as backup_module
from app.migrations.backup import inspect_database
from app.migrations.restore import main as restore_cli
from app.migrations.runner import run_migrations
from app.models import (Film, GraphEntity, FilmMetadataOverride, FilmMetadataEdit, FilmProfileState,
                        Viewing, LocalProfile, Setting, Job, EventRecord, OperationSnapshot)
from app.services import maintenance_backup as module
from app.services.maintenance_backup import MaintenanceBackups, BackupError
from app.services.projections import projection_coordinator

CANARY = "SYNTHETIC-CONFIG-CREDENTIAL-DO-NOT-EXPORT-123"


class MaintenanceBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "library.db"
        self.engine = create_engine(f"sqlite:///{self.source}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, self.source, backup_required=False)
        self.film = "film_" + "a" * 32
        self.alias = "film_" + "b" * 32
        with Session(self.engine) as session:
            session.info["skip_projection_hook"] = True
            profile = session.exec(select(LocalProfile.id)).one()
            session.add(GraphEntity(id=self.film, entity_type="film"))
            session.flush()
            session.add(Film(id=self.film, canonical_title="Synthetic film"))
            session.flush()
            session.add(GraphEntity(id=self.alias, entity_type="film", lifecycle_status="merged", merged_into_id=self.film))
            session.flush()
            session.add(Film(id=self.alias, canonical_title="Alias", lifecycle_status="merged", merged_into_id=self.film))
            session.add(FilmMetadataOverride(film_id=self.film, values={"title": "人工修正", "year": None, "overview": "人工简介"}, revision=1))
            session.add(FilmMetadataEdit(id="fmed_" + "c"*32, film_id=self.film, idempotency_key="synthetic-edit-001", request_hash="d"*64,
                before_values={}, after_values={"title": "人工修正", "year": None}, automatic_snapshot={"title": "Synthetic film"}))
            session.add(FilmProfileState(profile_id=profile, film_id=self.film, favorite=True, rating=3, notes="影片总评"))
            for i, (date, precision) in enumerate([(None, "unknown"), ("2025", "year"), ("2026-10-01", "date"), ("2026-10-01T20:30:00+08:00", "timestamp")]):
                session.add(Viewing(id=f"view_{i:032x}", profile_id=profile, film_id=self.film, watched_at=date,
                    watched_at_precision=precision, source="diary", rating=i+1, notes=f"观看评价 {i}"))
            session.add(Setting(key="tmdb_api_key", value=CANARY))
            session.add(Setting(key="watch_library", value=True))
            session.add(Setting(key="media_dirs", value=[str(self.root / "first"), str(self.root / "second")]))
            session.add(Setting(key="media_scan_status", value={"state": "partial", "last_result": {"complete": False}}))
            event = EventRecord(type="Synthetic", aggregate_type="film", aggregate_id=self.film,
                payload={"scrape_error": f"Request failed https://example.test?api_key={CANARY}",
                         "source": "https://test-user:historical-credential@example.test?access_token=old-token"})
            session.add(event)
            session.flush()
            session.add(OperationSnapshot(event_id=event.id, aggregate_type="film", aggregate_id=self.film,
                operation_kind="file_organization", before_state={"scrape_error": CANARY}, after_state={},
                optimistic_hash="e"*64, backup_manifest_ref="private-external-manifest"))
            session.add(Job(id="job_done", type="organizer.organize", status="succeeded", error=CANARY,
                            payload={"Authorization": f"Bearer {CANARY}"}))
            session.commit()
        from app.services import library as library_module
        with patch.object(library_module, "engine", self.engine):
            library_module.library_manager.upsert_observation(dict(title="Basic Instinct", folder_name="Synthetic file",
                media_path=str(self.root / "synthetic.mkv"), scrape_error=f"https://example.test?token={CANARY}"))
        projection_coordinator.bootstrap(self.engine)
        self.engine.dispose()
        self.service = MaintenanceBackups(self.source)
        self.workers = {}
        generate = self.service._generate

        def track_worker(identifier, lease):
            self.workers[identifier] = threading.current_thread()
            generate(identifier, lease)

        self.worker_patch = patch.object(self.service, "_generate", track_worker)
        self.worker_patch.start()
        self.addCleanup(self.worker_patch.stop)
        self.patch = patch.object(routes, "maintenance_backups", self.service)
        self.patch.start()
        app = FastAPI()
        app.include_router(routes.router)
        self.client = TestClient(app)

    def tearDown(self):
        errors = []
        alive = []

        def cleanup(label, action):
            try:
                action()
            except Exception as exc:
                errors.append(f"{label}: {type(exc).__name__}")

        cleanup("stop service", self.service.stop)
        for identifier, worker in list(self.workers.items()):
            cleanup(f"join {identifier}", lambda: worker.join(15))
            try:
                if worker.is_alive():
                    alive.append(identifier)
            except Exception as exc:
                alive.append(identifier)  # Unknown completion must preserve the directory too.
                errors.append(f"worker state {identifier}: {type(exc).__name__}")
        cleanup("close client", self.client.close)
        cleanup("restore routes", self.patch.stop)
        cleanup("dispose engine", self.engine.dispose)
        if alive:
            errors.append("backup worker still owns the test directory: " + ", ".join(alive))
        else:
            cleanup("remove fixture", self.temp.cleanup)
        self.assertFalse(errors, "; ".join(errors))

    def wait(self, identifier):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            record = self.service.get(identifier)
            if record["status"] != "generating":
                # The receipt precedes staging cleanup and generation-lock release.
                # Sequential fixture operations need the actual worker to finish.
                worker = self.workers[identifier]
                worker.join(max(0, deadline - time.monotonic()))
                self.assertFalse(worker.is_alive(), "generation worker did not finish")
                return record
            time.sleep(.02)
        self.fail("generation did not finish")

    def generate(self):
        identifier = uuid4().hex
        response = self.client.post("/maintenance/backups", json={"request_id": identifier})
        self.assertEqual(response.status_code, 202, response.text)
        record = self.wait(identifier)
        self.assertEqual(record["status"], "succeeded", record)
        return identifier

    def download(self, identifier):
        response = self.client.get(f"/maintenance/backups/{identifier}/download")
        self.assertEqual(response.status_code, 200, response.text[:200] if response.status_code != 200 else "")
        self.assertEqual(response.headers["cache-control"], "no-store")
        return response.content

    def test_zip_existing_cli_restore_preserves_business_rows_and_no_automatic_tasks(self):
        before = self.source.read_bytes()
        identifier = self.generate()
        payload = self.download(identifier)
        extracted = self.root / "extracted"
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertEqual(len(archive.namelist()), 3)
            for name in archive.namelist():
                self.assertNotIn(CANARY.encode(), archive.read(name))
                self.assertNotIn(b"historical-credential", archive.read(name))
                self.assertNotIn(b"old-token", archive.read(name))
            archive.extractall(extracted)
        manifest = next(extracted.glob("*.manifest.json"))
        target = self.root / "new-environment.db"
        target_engine = create_engine(f"sqlite:///{target}")
        run_migrations(target_engine, target, backup_required=False)
        target_engine.dispose()
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(restore_cli(["--manifest", str(manifest)]), 0)
            self.assertEqual(restore_cli(["--manifest", str(manifest), "--replace", "--target", str(target),
                "--confirm-current-sha256", inspect_database(target).sha256]), 0)
        with closing(sqlite3.connect(self.source)) as source, closing(sqlite3.connect(target)) as restored:
            for table in ["film", "graph_entity", "film_metadata_override", "film_metadata_edit", "film_profile_state", "viewing"]:
                self.assertEqual(source.execute(f"SELECT * FROM {table}").fetchall(), restored.execute(f"SELECT * FROM {table}").fetchall())
            self.assertEqual(restored.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(restored.execute("SELECT COUNT(*) FROM setting").fetchone()[0], 0)
            self.assertEqual(restored.execute("SELECT status, backup_manifest_ref FROM operation_snapshot").fetchone(), ("expired", None))
        self.assertEqual(projection_coordinator.bootstrap(target_engine)["status"], "passed")
        self.assertEqual(projection_coordinator.bootstrap(target_engine)["status"], "passed")
        from app.jobs import store, runtime
        runtime_instance = runtime.JobRuntime()
        with patch.object(store, "engine", target_engine), patch.object(runtime.workflow_store, "recover_interrupted"), patch.dict(runtime.JOB_HANDLERS, {"organizer.organize": lambda *args: self.fail("restored job executed")}):
            runtime_instance.start()
            time.sleep(.1)
            runtime_instance.stop()
        target_engine.dispose()
        self.assertEqual(self.source.read_bytes(), before)
        self.assertIsNone(self.service.status()["last_success"]["download_triggered_at"])
        self.assertEqual(self.client.post(f"/maintenance/backups/{identifier}/download-triggered").status_code, 200)
        self.assertIsNotNone(MaintenanceBackups(self.source).status()["last_success"]["download_triggered_at"])

    def test_replay_concurrency_separate_instance_and_process_lock(self):
        gate = threading.Event()
        entered = threading.Event()
        original = module.sanitize_snapshot
        def hold(path):
            entered.set()
            gate.wait(10)
            return original(path)
        identifier = uuid4().hex
        with patch.object(module, "sanitize_snapshot", hold):
            self.service.create(identifier)
            self.assertTrue(entered.wait(5))
            try:
                other = MaintenanceBackups(self.source)
                self.assertEqual(other.create(identifier)["id"], identifier)
                with self.assertRaisesRegex(BackupError, "backup_busy"):
                    other.create(uuid4().hex)
                script = "from pathlib import Path; import sys; from app.services.maintenance_backup import file_lock, BackupError\ntry:\n with file_lock(Path(sys.argv[1]),wait=False): sys.exit(2)\nexcept BackupError: sys.exit(0)"
                result = subprocess.run([sys.executable, "-c", script, str(self.service.directory / "generation.lock")], capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(other.status()["last_attempt"]["status"], "generating")
            finally:
                gate.set()
            self.assertEqual(self.wait(identifier)["status"], "succeeded")
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertTrue(all(item["id"] == identifier for item in pool.map(self.service.create, [identifier]*4)))
        self.assertEqual(len(list(self.service.directory.glob("*.zip"))), 1)

    def test_failed_generation_keeps_previous_success_and_cleans_private_files(self):
        previous = self.generate()
        content = self.download(previous)
        original = module.create_verified_backup
        def fail_after_raw(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError("private credential-bearing diagnostic")
        with patch.object(module, "create_verified_backup", fail_after_raw):
            identifier = uuid4().hex
            self.service.create(identifier)
            self.assertEqual(self.wait(identifier)["error_code"], "backup_failed")
        self.assertEqual(self.service.status()["last_success"]["id"], previous)
        self.assertEqual(self.download(previous), content)
        self.assertEqual(list(self.service.directory.glob("stage-*")), [])
        self.assertNotIn("private credential", json.dumps(self.service.status()))

    def test_expiry_missing_and_corruption_are_not_reported_available(self):
        identifier = self.generate()
        with self.service.state() as db:
            db.execute("UPDATE attempt SET expires_at=? WHERE id=?", ((module.now()-timedelta(seconds=1)).isoformat(), identifier))
        self.assertFalse(self.service.status()["last_success"]["available"])
        self.assertFalse(self.service.archive(identifier).exists())
        self.assertEqual(self.client.get(f"/maintenance/backups/{identifier}/download").status_code, 410)
        self.assertEqual(self.service.create(identifier)["id"], identifier)  # Never silently regenerate expired retries.
        missing = self.generate()
        self.service.archive(missing).unlink()
        self.assertEqual(self.service.status()["last_success"]["artifact_state"], "missing")
        corrupt = self.generate()
        self.service.archive(corrupt).write_bytes(b"corrupt")
        self.assertEqual(self.client.get(f"/maintenance/backups/{corrupt}/download").status_code, 410)
        self.assertEqual(self.service.status()["last_success"]["artifact_state"], "corrupt")

    def test_restart_recovers_interrupted_without_losing_success(self):
        previous = self.generate()
        identifier = uuid4().hex
        with self.service.state() as db:
            db.execute("INSERT INTO attempt (id,status,created_at) VALUES (?,'generating',?)", (identifier, module.now().isoformat()))
        stage = self.service.directory / f"stage-{identifier}"
        stage.mkdir()
        (stage / "partial.db").write_bytes(b"synthetic private bytes")
        restarted = MaintenanceBackups(self.source)
        self.assertEqual(restarted.status()["last_attempt"]["status"], "interrupted")
        self.assertEqual(restarted.status()["last_success"]["id"], previous)
        self.assertFalse(stage.exists())
        self.assertEqual(restarted.create(identifier)["status"], "interrupted")

    def test_active_tasks_refused_and_personal_sensitive_content_never_rewritten(self):
        with closing(sqlite3.connect(self.source)) as db:
            db.execute("UPDATE job SET status='queued'")
            db.commit()
        identifier = uuid4().hex
        self.service.create(identifier)
        self.assertEqual(self.wait(identifier)["error_code"], "backup_tasks_active")
        with closing(sqlite3.connect(self.source)) as db:
            db.execute("UPDATE job SET status='succeeded'")
            db.execute("UPDATE film_profile_state SET notes=?", (CANARY,))
            db.commit()
        before = self.source.read_bytes()
        identifier = uuid4().hex
        self.service.create(identifier)
        self.assertEqual(self.wait(identifier)["error_code"], "backup_sensitive_content")
        self.assertEqual(before, self.source.read_bytes())
        self.assertEqual(list(self.service.directory.glob("*.zip")), [])

    def test_in_flight_download_survives_replacement_and_cleanup_retries(self):
        previous = self.generate()
        handle, record = self.service.download(previous)
        try:
            current = self.generate()
            self.assertEqual(hashlib.file_digest(handle, "sha256").hexdigest(), record["sha256"])
            self.assertFalse(self.service.get(previous)["available"])
        finally:
            handle.close()
        self.service.status()
        self.assertFalse(self.service.archive(previous).exists())
        self.assertTrue(self.service.archive(current).exists())

    def test_wait_includes_terminal_cleanup_before_next_generation(self):
        for outcome in ("succeeded", "failed"):
            with self.subTest(outcome=outcome):
                entered = threading.Event()
                release = threading.Event()
                joining = threading.Event()
                identifier = uuid4().hex
                stage = self.service.directory / f"stage-{identifier}"
                remove = module.shutil.rmtree

                def hold_cleanup(path, *args, **kwargs):
                    if Path(path) == stage:
                        entered.set()
                        if not release.wait(10):
                            raise RuntimeError("test did not release staging cleanup")
                    return remove(path, *args, **kwargs)

                failure = (patch.object(module, "sanitize_snapshot", side_effect=OSError("synthetic failure"))
                           if outcome == "failed" else nullcontext())
                with failure, patch.object(module.shutil, "rmtree", hold_cleanup):
                    try:
                        self.service.create(identifier)
                        self.assertTrue(entered.wait(5), "worker did not reach staging cleanup")
                        self.assertEqual(self.service.get(identifier)["status"], outcome)
                        self.assertEqual(self.service.create(identifier)["status"], outcome)
                        # A terminal receipt is replayable while a different ID is still busy.
                        busy = self.client.post("/maintenance/backups", json={"request_id": uuid4().hex})
                        self.assertEqual(busy.status_code, 409)
                        self.assertEqual(busy.json()["detail"]["code"], "backup_busy")
                        worker = self.workers[identifier]
                        join = worker.join

                        def observe_join(timeout=None):
                            joining.set()
                            return join(timeout)

                        with patch.object(worker, "join", observe_join), ThreadPoolExecutor(max_workers=1) as pool:
                            waiting = pool.submit(self.wait, identifier)
                            try:
                                self.assertTrue(joining.wait(5), "wait returned before worker completion")
                                self.assertFalse(waiting.done(), "cleanup gate is still held")
                            finally:
                                release.set()
                            self.assertEqual(waiting.result(timeout=5)["status"], outcome)
                    finally:
                        release.set()
                self.assertFalse(stage.exists())
                with module.file_lock(self.service.directory / "generation.lock", wait=False):
                    pass
                self.generate()  # No retry: a fresh generation must now be accepted.

    def test_wait_fails_when_terminal_worker_does_not_finish_within_original_deadline(self):
        identifier = uuid4().hex
        worker = Mock()
        worker.is_alive.return_value = True
        self.workers[identifier] = worker
        try:
            with patch.object(self.service, "get", return_value={"status": "succeeded"}), \
                    patch.object(time, "monotonic", side_effect=[100, 101, 115]):
                with self.assertRaisesRegex(AssertionError, "generation worker did not finish"):
                    self.wait(identifier)
            worker.join.assert_called_once_with(0)
        finally:
            del self.workers[identifier]

    def test_teardown_timeout_cleans_shared_resources_and_joins_every_worker(self):
        for close_fails in (False, True):
            with self.subTest(close_fails=close_fails), tempfile.TemporaryDirectory() as directory:
                original_service = routes.maintenance_backups
                case = MaintenanceBackupTests()
                case.service = Mock()
                case.client = Mock()
                if close_fails:
                    case.client.close.side_effect = RuntimeError("synthetic client failure")
                case.engine = Mock()
                case.temp = Mock()
                marker = Path(directory) / "worker-owned"
                marker.write_text("synthetic worker state", encoding="utf-8")
                case.temp.cleanup.side_effect = marker.unlink
                live, finished = Mock(), Mock()
                live.is_alive.return_value = True
                finished.is_alive.return_value = False
                case.workers = {"alive-fixture": live, "finished-fixture": finished}
                case.patch = patch.object(routes, "maintenance_backups", case.service)
                case.patch.start()
                try:
                    with self.assertRaisesRegex(AssertionError, "backup worker still owns the test directory") as failure:
                        case.tearDown()
                    self.assertIs(routes.maintenance_backups, original_service)
                    case.service.stop.assert_called_once_with()
                    case.client.close.assert_called_once_with()
                    case.engine.dispose.assert_called_once_with()
                    live.join.assert_called_once_with(15)
                    finished.join.assert_called_once_with(15)
                    case.temp.cleanup.assert_not_called()
                    self.assertTrue(marker.is_file())
                    if close_fails:
                        self.assertIn("close client: RuntimeError", str(failure.exception))
                finally:
                    case.patch.stop()

    def test_file_lock_releases_after_exception_and_wait_timeout_preserves_owner(self):
        path = self.root / "boundary.lock"
        with self.assertRaisesRegex(RuntimeError, "synthetic protected work"):
            with module.file_lock(path, wait=False):
                raise RuntimeError("synthetic protected work")
        with module.file_lock(path, wait=False):
            with self.assertRaisesRegex(BackupError, "backup_busy"):
                with module.file_lock(path, wait=False):
                    self.fail("a competing lock must not be acquired")
            with patch.object(time, "monotonic", side_effect=[100, 100, 105]), \
                    patch.object(time, "sleep") as sleep:
                with self.assertRaisesRegex(BackupError, "backup_busy"):
                    with module.file_lock(path):
                        self.fail("a timed-out contender must not acquire ownership")
                sleep.assert_called_once_with(.02)
            # A failed contender must not release the original owner's lock.
            with self.assertRaisesRegex(BackupError, "backup_busy"):
                with module.file_lock(path, wait=False):
                    self.fail("the original owner must remain locked")
        with module.file_lock(path, wait=False):
            pass

    def test_invalid_identifiers_unknown_receipts_and_status_storage_failure(self):
        self.assertEqual(self.client.post("/maintenance/backups", json={"request_id": "../private"}).status_code, 422)
        self.assertEqual(self.client.get("/maintenance/backups/not-an-id/download").status_code, 422)
        self.assertEqual(self.client.get(f"/maintenance/backups/{uuid4().hex}").status_code, 410)
        with patch.object(self.service, "status", side_effect=sqlite3.OperationalError(CANARY)):
            response = self.client.get("/maintenance/backups")
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(CANARY, response.text)

    def test_backup_store_failure_does_not_prevent_application_start(self):
        with patch.object(self.service, "status", side_effect=sqlite3.DatabaseError(CANARY)):
            self.service.start()
            self.assertTrue(self.service.janitor.is_alive())
            self.service.stop()

    def test_natural_language_and_credential_urls_have_distinct_boundaries(self):
        self.assertEqual(module._scrub("Basic Instinct", []), "Basic Instinct")
        self.assertEqual(module._scrub({"input_tokens": 123}, []), {"input_tokens": 123})
        self.assertNotIn("historical-secret", module._scrub("https://example.test/image?token=historical-secret", []))
        self.assertNotIn("historical-secret", module._scrub("https://example.test/image?secret=historical-secret", []))

    def test_online_snapshot_counts_share_transaction_with_concurrent_wal_write(self):
        original = backup_module._row_counts
        with closing(sqlite3.connect(self.source)) as writer:
            writer.execute("PRAGMA journal_mode=WAL")
            injected = False
            def count(connection):
                nonlocal injected
                counts = original(connection)
                if not injected:
                    injected = True
                    writer.execute("INSERT INTO setting VALUES ('concurrent','\"new\"','2026-10-12')")
                    writer.commit()
                return counts
            with patch.object(backup_module, "_row_counts", count):
                artifact = backup_module.create_verified_backup(self.source, self.root / "race", app_version="test", source_schema_version=11, target_schema_version=11)
            self.assertEqual(writer.execute("SELECT COUNT(*) FROM setting").fetchone()[0], artifact.row_counts["setting"]+1)


if __name__ == "__main__":
    unittest.main()
