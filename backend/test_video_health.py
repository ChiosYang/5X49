"""Disposable SQLite and generated audio/video only; never access an existing library."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import sys
import psutil
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select
from app import database
from app.database import configure_sqlite_engine
from app.main import app
from app.migrations.runner import run_migrations
from app.models import Job, MediaAsset, Setting
from app.health_models import VideoHealth
from app.services import event_store, library, settings, video_health_views
from app.services.video_health import VideoHealthService, file_version, digest, in_window
from app.services.video_health_decoder import ToolProcess, container_arguments, decode_arguments, classify
from app.services.maintenance_backup import sanitize_snapshot, file_lock, BackupError
from datetime import datetime, timezone


class HealthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples = tempfile.TemporaryDirectory(prefix="health-synthetic-")
        cls.normal = Path(cls.samples.name) / "normal.mp4"
        cls.ffmpeg = shutil.which("ffmpeg")
        cls.ffprobe = shutil.which("ffprobe")
        if not cls.ffmpeg or not cls.ffprobe:
            raise unittest.SkipTest("Real health integration requires ffmpeg and ffprobe")
        subprocess.run([cls.ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=144x96:rate=8",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000", "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=16000",
            "-map", "0:v", "-map", "1:a", "-map", "2:a", "-t", "6", "-c:v", "mpeg4", "-g", "8",
            "-c:a", "aac", "-movflags", "+faststart", str(cls.normal)], check=True, capture_output=True, timeout=30)
        payload = subprocess.run([cls.ffprobe, "-v", "error", "-show_packets", "-select_streams", "v", "-of", "json", str(cls.normal)],
            check=True, capture_output=True, timeout=20)
        packets = json.loads(payload.stdout)["packets"]
        packet = next(packet for packet in packets if float(packet.get("pts_time", 0)) > 3 and int(packet["size"]) > 1000)
        data = bytearray(cls.normal.read_bytes())
        pos, size = int(packet["pos"]), int(packet["size"])
        data[pos:pos+size] = b"\xff" * size
        cls.corrupt = Path(cls.samples.name) / "corrupt.mp4"
        cls.corrupt.write_bytes(data)
        cls.truncated = Path(cls.samples.name) / "truncated.mp4"
        cls.truncated.write_bytes(cls.normal.read_bytes()[:len(data)*2//3])

    @classmethod
    def tearDownClass(cls):
        cls.samples.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="health-isolated-")
        self.root = Path(self.temp.name).resolve()
        self.media = self.root / "media"; self.media.mkdir()
        self.db_path = self.root / "library.db"
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, self.db_path, backup_required=False)
        for module in (database, library, event_store):
            guard = patch.object(module, "engine", self.engine)
            guard.start(); self.addCleanup(guard.stop)
        guard = patch.object(database, "sqlite_path", self.db_path)
        guard.start(); self.addCleanup(guard.stop)
        guard = patch.object(settings, "get_available_models", return_value=[])
        guard.start(); self.addCleanup(guard.stop)
        settings.set_media_dirs([str(self.media)])
        self.observer = Mock(sample=Mock(return_value={"observable": True, "cpu": 0, "disk": 0}))
        self.service = VideoHealthService(observer=self.observer)
        self.service.configure({"idle_seconds": 0, "stable_seconds": 0})
        for target in ("app.api.video_health.video_health", "app.services.video_health_views.video_health"):
            guard = patch(target, self.service); guard.start(); self.addCleanup(guard.stop)
        self.client = TestClient(app)
        self.inspect_threads = []

    def tearDown(self):
        self.service.stop()
        for thread in self.inspect_threads:
            thread.join(timeout=8)
        self.client.close(); self.engine.dispose(); self.temp.cleanup()

    def add(self, source=None, name="Sample.mp4"):
        path = self.media / name
        shutil.copyfile(source or self.normal, path)
        with path.open('ab') as handle:
            handle.write(name.encode())
        result = library.library_manager.upsert_observation({"title": name, "folder_name": "Sample",
            "media_path": str(path), "file_size": path.stat().st_size, "file_mtime": path.stat().st_mtime})
        return path, result

    def rows(self):
        with Session(self.engine) as session:
            return session.exec(select(VideoHealth).order_by(VideoHealth.observed_at)).all()

    def queued(self):
        self.service.discover(); self.service.discover()
        return self.rows()[-1]

    def inspect(self, source=None):
        path, _ = self.add(source)
        row = self.queued()
        self.service.inspect(row.id)
        return path, self.rows()[-1]

    def test_normal_continuous_multitrack_decode_and_read_only(self):
        path, _ = self.add()
        before = hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns
        row = self.queued(); self.service.inspect(row.id)
        current = self.rows()[-1]
        self.assertEqual((current.container_status, current.status), ("passed", "passed"))
        self.assertGreater(current.decoded_seconds, 5)
        self.assertEqual(before, (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns))
        args = decode_arguments(path, [{"index": 0}, {"index": 1}, {"index": 2}])
        self.assertEqual(args.count("-map"), 3)
        self.assertNotIn("copy", args)
        self.assertIn("explode", args)

    def test_real_midstream_corruption_passes_container_but_fails_decode(self):
        _, row = self.inspect(self.corrupt)
        self.assertEqual(row.container_status, "passed")
        self.assertEqual(row.status, "abnormal")
        self.assertEqual(row.error_code, "media_decode_error")
        public = self.client.get(f"/maintenance/video-health/files/{row.id}").json()
        self.assertIsNone(public["error_position_seconds"])
        self.assertEqual(public["position_kind"], "unknown")
        self.assertNotIn(str(self.media), json.dumps(public))

    def test_real_truncation_is_not_a_full_pass(self):
        _, row = self.inspect(self.truncated)
        self.assertEqual(row.status, "abnormal")

    def test_new_files_wait_for_two_stable_observations(self):
        self.service.configure({"stable_seconds": 60})
        path, _ = self.add()
        stamp = time.time()
        self.service.clock = lambda: stamp
        self.service.discover(); self.assertEqual(self.rows()[0].status, "unchecked")
        self.service.clock = lambda: stamp + 59
        self.service.discover(); self.assertEqual(self.rows()[0].status, "unchecked")
        path.write_bytes(path.read_bytes() + b"change")
        self.service.clock = lambda: stamp + 61
        self.service.discover(); self.assertEqual(self.rows()[-1].status, "unchecked")
        self.service.clock = lambda: stamp + 122
        self.service.discover(); self.assertEqual(self.rows()[-1].status, "queued")

    def test_passed_unchanged_file_never_redecodes(self):
        _, row = self.inspect()
        for _ in range(3): self.service.discover()
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0].status, "passed")
        with patch.object(self.service, "inspect") as check:
            self.service.tick(); check.assert_not_called()
        self.service.queue_all(); self.service.discover()
        self.assertEqual(self.rows()[0].attempts, 1)

    def test_scan_version_change_invalidates_previous_pass_without_bulk_stat(self):
        path, row = self.inspect()
        path.write_bytes(path.read_bytes() + b"changed")
        with Session(self.engine) as session:
            asset = session.get(MediaAsset, row.asset_id)
            asset.file_size = path.stat().st_size; asset.file_mtime = path.stat().st_mtime
            session.add(asset); session.commit()
        with patch("app.services.video_health.file_version", side_effect=AssertionError("Summary must not stat every disk")):
            state = self.client.get("/maintenance/video-health").json()
        self.assertEqual(state["counts"]["passed"], 0)
        self.assertEqual(state["counts"]["unchecked"], 1)

    def test_persistent_queue_and_restart_incomplete_require_explicit_retry(self):
        self.add(); row = self.queued()
        self.service.queue_all()
        fresh = VideoHealthService(observer=self.observer)
        fresh.recover()
        self.assertEqual(self.rows()[0].status, "queued")
        with Session(self.engine) as session:
            current = session.get(VideoHealth, row.id); current.status = "checking"
            session.add(current); session.commit()
        fresh.recover(); fresh.discover()
        self.assertEqual(self.rows()[0].status, "incomplete")
        self.assertEqual(self.rows()[0].error_code, "interrupted")
        self.service.control(row.id, "retry")
        self.service.discover()
        self.assertEqual(self.rows()[0].status, "queued")

    def test_offline_permission_and_tool_failure_never_claim_damage(self):
        path, _ = self.add(); row = self.queued(); path.unlink()
        self.service.inspect(row.id)
        self.assertEqual((self.rows()[0].status, self.rows()[0].error_code), ("incomplete", "offline"))
        self.assertGreater(self.rows()[0].next_attempt_at, time.time())
        with patch("app.services.video_health.file_version", side_effect=AssertionError("Backoff must skip read")):
            self.service.discover()
        shutil.copyfile(self.normal, path)
        self.service.discover(); row = self.rows()[-1]
        with patch("app.services.video_health.file_version", side_effect=PermissionError()):
            self.service.inspect(row.id)
        self.assertNotEqual(self.rows()[-1].status, "abnormal")
        for errors in ["Permission denied", "Input/output error", "No such file", "Error opening input"]:
            self.assertEqual(classify(errors)[0], "incomplete")
        self.assertEqual(classify("Unknown decoder 'not-a-codec'")[0], "unsupported")

    def test_missing_tools_are_unsupported(self):
        self.add(); row = self.queued()
        with patch("app.services.video_health.container_arguments", return_value=None):
            self.service.inspect(row.id)
        self.assertEqual((self.rows()[0].status, self.rows()[0].error_code), ("unsupported", "tool_missing"))

    def test_unchanged_pass_survives_offline_backoff_without_redecoding(self):
        _, row = self.inspect()
        passed = self.rows()[0].passed_at
        future = time.time() + 86401
        self.service.clock = lambda: future
        parked = self.root / 'parked-media'
        self.media.rename(parked)
        try:
            self.service.discover()
            self.assertEqual(self.rows()[0].status, 'incomplete')
            self.assertEqual(self.rows()[0].passed_at, passed)
        finally:
            parked.rename(self.media)
        self.service.clock = lambda: future + 500
        self.service.discover()
        self.assertEqual(self.rows()[0].status, 'passed')
        self.assertEqual(self.rows()[0].passed_at, passed)
        with patch.object(self.service, 'inspect') as decode:
            self.service.tick(); decode.assert_not_called()

    def test_removed_roots_are_not_discovered_or_requeued(self):
        self.add(); settings.set_media_dirs([])
        self.service.queue_all()
        with patch('app.services.video_health.file_version', side_effect=AssertionError('Revoked root must not be sampled')):
            self.service.discover()
        self.assertEqual(self.rows(), [])

    def test_boundaries_revocation_identity_change_and_cancel(self):
        self.add(); row = self.queued()
        settings.set_media_dirs([])
        self.service.inspect(row.id)
        self.assertEqual(self.rows()[0].error_code, "boundary_changed")
        self.assertEqual(self.client.get("/maintenance/video-health").json()["total"], 0)
        settings.set_media_dirs([str(self.media)])
        self.service.control(row.id, "retry"); self.service.discover()
        self.service.control(row.id, "cancel"); self.service.inspect(row.id)
        self.assertEqual((self.rows()[0].status, self.rows()[0].error_code), ("incomplete", "cancelled"))
        with Session(self.engine) as session:
            asset = session.get(MediaAsset, row.asset_id); asset.availability_status = "retired"
            session.add(asset); session.commit()
        response = self.client.post(f"/maintenance/video-health/files/{row.id}", json={"action": "retry"})
        self.assertEqual(response.status_code, 409)

    def test_write_during_decoder_invalidates_result(self):
        path, _ = self.add(); row = self.queued()
        original = self.service.run_tool
        def mutate(identifier, arguments, **kwargs):
            result = original(identifier, arguments, **kwargs)
            if not kwargs.get("probe"):
                path.write_bytes(path.read_bytes() + b"concurrent write")
            return result
        with patch.object(self.service, "run_tool", side_effect=mutate):
            self.service.inspect(row.id)
        self.assertEqual((self.rows()[0].status, self.rows()[0].error_code), ("incomplete", "file_changed"))

    def test_load_hysteresis_budget_and_unknown_environment_are_conservative(self):
        stamp = time.time(); self.service.clock = lambda: stamp
        self.service.configure({"idle_seconds": 60})
        self.assertEqual(self.service.scheduling_reason(), "waiting_idle")
        self.service.clock = lambda: stamp + 61
        self.assertIsNone(self.service.scheduling_reason())
        self.service.active_tool = Mock(suspended=False, process=Mock(pid=123))
        self.observer.sample.return_value = {"observable": True, "cpu": 50, "disk": 30}
        self.assertIsNone(self.service.scheduling_reason(active=True))
        self.assertEqual(self.service.scheduling_reason(), "host_busy")
        self.observer.sample.return_value = {"observable": True, "cpu": 90, "disk": 0}
        self.assertEqual(self.service.scheduling_reason(active=True), "host_busy")
        self.service.active_tool.suspended = True
        self.observer.sample.return_value = {"observable": True, "cpu": 50, "disk": 30}
        self.assertEqual(self.service.scheduling_reason(active=True), "host_busy")
        self.observer.sample.return_value = {"observable": True, "cpu": 0, "disk": 0}
        self.assertEqual(self.service.scheduling_reason(active=True), "waiting_idle")
        self.service.clock = lambda: stamp + 122
        self.assertIsNone(self.service.scheduling_reason(active=True))
        self.service.active_tool = None
        self.service.clock = lambda: stamp + 61
        self.observer.sample.return_value = {"observable": False, "cpu": None, "disk": None}
        self.assertEqual(self.service.scheduling_reason(), "load_unobservable")
        minute = datetime.fromtimestamp(stamp+61, timezone.utc).hour * 60 + datetime.fromtimestamp(stamp+61, timezone.utc).minute
        self.service.configure({"start_minute": minute, "end_minute": (minute + 30) % 1440, "idle_seconds": 0})
        self.assertIsNone(self.service.scheduling_reason())
        with Session(self.engine) as session:
            state = self.service.runtime(session)
            state.update(day=datetime.fromtimestamp(stamp+61, timezone.utc).date().isoformat(), used_seconds=3600)
            self.service._save_setting(session, "video_health_runtime", state); session.commit()
        self.assertEqual(self.service.scheduling_reason(), "budget_used")
        self.assertIsNone(self.service.scheduling_reason(active=True))

    def test_application_tasks_and_manual_pause_preempt_checks(self):
        with Session(self.engine) as session:
            session.add(Job(id="job_synthetic", type="library.reconcile", status="queued")); session.commit()
        self.assertEqual(self.service.scheduling_reason(), "application_busy")
        self.service.configure({"paused": True})
        self.assertEqual(self.service.scheduling_reason(), "paused")
        self.service.configure({"paused": False})
        fake = Mock()
        self.service.active_tool = fake
        with self.service.foreground():
            fake.pause.assert_called_once_with(True)
            self.assertEqual(self.service.foreground_count, 1)
        self.assertEqual(self.service.foreground_count, 0)
        self.service.active_tool = None

    def test_batch_discovery_never_touches_all_disks_and_cursor_persists(self):
        for index in range(9): self.add(name=f"Video {index}.mp4")
        with patch("app.services.video_health.file_version", wraps=file_version) as observe:
            self.service.discover(batch=2)
            self.assertLessEqual(observe.call_count, 4)
        with Session(self.engine) as session:
            cursor = self.service.runtime(session)["cursor"]
        self.assertTrue(cursor)
        fresh = VideoHealthService(observer=self.observer)
        for _ in range(6): fresh.discover(batch=2)
        self.assertEqual(len(self.rows()), 9)

    def test_new_priority_over_backlog_and_manual_sweep_when_auto_off(self):
        self.add(); self.service.configure({"enabled": False})
        self.assertEqual(self.service.scheduling_reason(), "disabled")
        self.service.queue_all(); self.assertIsNone(self.service.scheduling_reason())
        self.service.discover(); self.service.discover()
        self.assertEqual(self.rows()[0].priority, 20)
        self.service.inspect(self.rows()[0].id)
        self.service.discover()
        self.assertEqual(self.service.scheduling_reason(), "disabled")

    def test_notification_is_durable_deduplicated_and_stale_version_is_hidden(self):
        path, row = self.inspect(self.corrupt)
        with patch("app.services.video_health.library_event_bus.publish") as notify:
            self.service.finish(row.id, "abnormal", "media_decode_error")
            notify.assert_not_called()
        self.assertEqual(self.client.get("/maintenance/video-health").json()["unread"], 1)
        self.service.control(row.id, "acknowledge")
        self.assertEqual(self.client.get("/maintenance/video-health").json()["unread"], 0)
        shutil.copyfile(self.normal, path)
        self.service.discover()
        self.assertFalse(self.client.get(f"/maintenance/video-health/files/{row.id}").json()["current"])

    def test_backup_drops_health_queue_and_reset_cascades_with_fk_on(self):
        self.add(); self.queued()
        snapshot = self.root / "backup.db"
        shutil.copyfile(self.db_path, snapshot)
        sanitize_snapshot(snapshot)
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(snapshot)) as connection:
            self.assertEqual(connection.execute("select count(*) from video_health").fetchone()[0], 0)
        self.assertEqual(len(self.rows()), 1)
        library.library_manager.clear_all_data()
        self.assertEqual(self.rows(), [])
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_key_check").all(), [])

    def test_api_validation_pagination_cancel_and_no_path_payloads(self):
        self.add(); self.queued()
        for body in [{"start_minute": 1440}, {"daily_budget_minutes": 0}, {"enabled": "true"}, {"paused": None}, {}]:
            self.assertEqual(self.client.put("/maintenance/video-health/config", json=body).status_code, 422)
        self.assertEqual(self.client.get("/maintenance/video-health/files?status=unknown").status_code, 422)
        response = self.client.get("/maintenance/video-health/files?status=all&limit=1").json()
        self.assertEqual(response["total"], 1)
        self.assertNotIn(str(self.media), json.dumps(response))
        self.assertEqual(self.client.post("/maintenance/video-health/cancel").json()["cancelled"], 1)
        self.assertEqual(self.rows()[0].error_code, "cancelled")

    def test_general_settings_cannot_overwrite_concurrent_health_control_or_budget(self):
        stale = settings.load_settings()
        self.service.configure({'paused': True})
        self.service.queue_all()
        with Session(self.engine) as session:
            state = self.service.runtime(session); state['used_seconds'] = 1200
            self.service._save_setting(session, 'video_health_runtime', state); session.commit()
        stale['language'] = 'en'
        self.assertTrue(settings.save_settings(stale))
        self.assertTrue(self.service.config()['paused'])
        with Session(self.engine) as session:
            state = self.service.runtime(session)
            self.assertTrue(state['sweep'])
            self.assertEqual(state['used_seconds'], 1200)

    def test_os_lock_rejects_second_worker_owner(self):
        with file_lock(self.root / "health.lock", wait=False):
            with self.assertRaises(BackupError):
                with file_lock(self.root / "health.lock", wait=False): pass

    def test_real_owned_process_pause_resume_retains_decoder_to_eof(self):
        arguments = decode_arguments(self.normal, [{"index": 0}, {"index": 1}, {"index": 2}])
        arguments[arguments.index("-i"):arguments.index("-i")] = ["-readrate", "1"]
        tool = ToolProcess(arguments)
        try:
            time.sleep(.7)
            tool.pause(True)
            self.settle_progress(tool)
            seconds = tool.seconds
            time.sleep(.7)
            self.assertEqual(tool.seconds, seconds)
            self.assertIsNone(tool.process.poll())
            tool.pause(False)
            tool.process.wait(timeout=12)
            self.assertEqual(tool.result(), ("passed", None))
            self.assertTrue(tool.ended)
            self.assertGreater(tool.seconds, 5)
        finally:
            tool.close()

    @staticmethod
    def settle_progress(tool):
        # Already-written pipe data can arrive after the process is suspended.
        # Wait for the reader to drain before asserting decoder progress stops.
        deadline = time.monotonic() + 3
        last, settled = tool.seconds, time.monotonic()
        while time.monotonic() < deadline:
            if tool.seconds != last:
                last, settled = tool.seconds, time.monotonic()
            elif time.monotonic() - settled > .75:
                return
            time.sleep(.05)

    def slow_decode(self, path, streams):
        arguments = decode_arguments(path, streams)
        if arguments:
            position = arguments.index('-i')
            arguments[position:position] = ['-readrate', '1']
        return arguments

    def test_cancel_running_real_decoder_is_incomplete_and_process_is_reaped(self):
        self.add(); row = self.queued()
        with patch('app.services.video_health.decode_arguments', side_effect=self.slow_decode):
            worker = threading.Thread(target=self.service.inspect, args=(row.id,)); worker.start()
            self.inspect_threads.append(worker)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and self.rows()[0].decoded_seconds < .5:
                time.sleep(.1)
            self.assertGreater(self.rows()[0].decoded_seconds, 0)
            pid = self.service.active_tool.process.pid
            self.service.control(row.id, 'cancel')
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
        self.assertEqual((self.rows()[0].status, self.rows()[0].error_code), ('incomplete', 'cancelled'))
        self.assertFalse(psutil.pid_exists(pid))

    def test_pause_resume_in_service_and_soft_budget_complete_same_process(self):
        self.add(); row = self.queued()
        with patch('app.services.video_health.decode_arguments', side_effect=self.slow_decode):
            worker = threading.Thread(target=self.service.inspect, args=(row.id,)); worker.start()
            self.inspect_threads.append(worker)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and self.rows()[0].decoded_seconds < .5:
                time.sleep(.1)
            self.service.configure({'paused': True})
            time.sleep(.8)
            tool = self.service.active_tool
            self.assertTrue(tool.suspended)
            self.settle_progress(tool)
            pid, seconds = tool.process.pid, tool.seconds
            time.sleep(.8)
            self.assertEqual(tool.seconds, seconds)
            self.assertLessEqual(self.rows()[0].decoded_seconds, seconds)
            with Session(self.engine) as session:
                state = self.service.runtime(session)
                state.update(day=datetime.now(timezone.utc).date().isoformat(), used_seconds=86400)
                self.service._save_setting(session, 'video_health_runtime', state); session.commit()
            self.service.configure({'paused': False})
            worker.join(timeout=12)
            self.assertFalse(worker.is_alive())
            self.assertEqual(tool.process.pid, pid)
        self.assertEqual(self.rows()[0].status, 'passed')

    def test_abrupt_owner_exit_reaps_decoder_without_restart_overlap(self):
        code = '''import os, sys, time
from pathlib import Path
from app.services.video_health_decoder import ToolProcess, decode_arguments
args = decode_arguments(Path(sys.argv[1]), [{'index': 0}, {'index': 1}, {'index': 2}])
position = args.index('-i'); args[position:position] = ['-readrate', '0.1']
tool = ToolProcess(args)
print(tool.process.pid, flush=True)
time.sleep(.5)
os._exit(0)
'''
        completed = subprocess.run([sys.executable, '-c', code, str(self.normal)], capture_output=True, text=True, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        pid = int(completed.stdout.strip())
        def living():
            try: return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
            except psutil.NoSuchProcess: return False
        deadline = time.monotonic() + 3
        while living() and time.monotonic() < deadline: time.sleep(.05)
        self.assertFalse(living(), 'Decoder outlived abruptly terminated owner')

    def test_overnight_and_all_day_windows(self):
        self.assertTrue(in_window({"start_minute": 1320, "end_minute": 360}, datetime(2026, 1, 1, 23, tzinfo=timezone.utc)))
        self.assertTrue(in_window({"start_minute": 1320, "end_minute": 360}, datetime(2026, 1, 1, 2, tzinfo=timezone.utc)))
        self.assertFalse(in_window({"start_minute": 1320, "end_minute": 360}, datetime(2026, 1, 1, 12, tzinfo=timezone.utc)))


if __name__ == "__main__": unittest.main()
