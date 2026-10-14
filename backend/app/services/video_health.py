"""Durable, conservative background health checks over known local video assets."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import os
import stat
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import psutil
from sqlalchemy import and_, or_
from sqlalchemy.orm import aliased
from sqlmodel import Session, select

from app import database
from app.health_models import VideoHealth
from app.models import Film, Job, LibraryItem, MediaAsset, Setting
from app.services.event_bus import library_event_bus
from app.services.media_roots import configured_root, MediaBoundaryError, safe_path
from app.services.settings import get_media_dirs
from app.services.maintenance_backup import file_lock, BackupError
from app.services.video_health_decoder import ToolProcess, container_arguments, decode_arguments, probe_payload

logger = logging.getLogger(__name__)
DEFAULT_CONFIG = {"enabled": True, "paused": False, "start_minute": 0, "end_minute": 0,
                  "daily_budget_minutes": 30, "idle_seconds": 60, "stable_seconds": 60}
RETRYABLE = {"offline", "permission_denied", "read_unavailable"}
SUMMARIES = {
    "media_decode_error": "Container or audio/video decoding reported invalid media data.",
    "duration_short": "Decoded output ended substantially before the container's declared duration.",
    "file_changed": "File changed during inspection; no valid result was retained.",
    "offline": "File is offline or absent; this is not evidence of damage.",
    "permission_denied": "Read access was denied; this is not evidence of damage.",
    "boundary_changed": "Media access or edition ownership changed; inspection stopped.",
    "read_unavailable": "Read operation was unavailable; this is not evidence of damage.",
    "tool_missing": "FFmpeg or ffprobe is not installed.",
    "codec_or_tool_unsupported": "This codec, container or tool option is unsupported.",
    "tool_failed": "The tool did not complete; damage could not be established.",
    "metadata_invalid": "The container metadata could not be interpreted safely.",
    "cancelled": "Inspection cancelled; a full decode was not completed.",
    "interrupted": "Backend stopped or restarted. Retry explicitly to decode from the beginning.",
    "suspend_unsupported": "The environment could not suspend the decoder safely; retry explicitly.",
    "timeout": "The tool stopped making progress; a full decode was not completed.",
}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def asset_snapshot(asset: MediaAsset) -> str:
    return digest([asset.library_item_id, asset.locator, asset.availability_status,
                   asset.file_size, asset.file_mtime, asset.platform_file_id, asset.content_fingerprint])


def file_version(asset: MediaAsset) -> dict:
    root = configured_root(asset.locator)
    path = safe_path(asset.locator, root)
    observed = path.stat()
    if not stat.S_ISREG(observed.st_mode):
        raise MediaBoundaryError("Not a regular local file")
    return {"locator_hash": asset.normalized_locator_hash, "device": observed.st_dev,
            "inode": observed.st_ino, "size": observed.st_size,
            "mtime_ns": observed.st_mtime_ns, "ctime_ns": observed.st_ctime_ns}


def in_window(config: dict, now: datetime) -> bool:
    minute = now.hour * 60 + now.minute
    start, end = config["start_minute"], config["end_minute"]
    return start == end or (start <= minute < end if start < end else minute >= start or minute < end)


class LoadObserver:
    def __init__(self):
        self.previous = None

    def sample(self, decoder_pid: int | None = None) -> dict:
        try:
            cpu = psutil.cpu_times()
            total = sum(cpu) - getattr(cpu, "guest", 0) - getattr(cpu, "guest_nice", 0)
            idle = cpu.idle + getattr(cpu, "iowait", 0)
            disks = psutil.disk_io_counters(perdisk=True)
            ticks = {key: value.busy_time for key, value in disks.items() if hasattr(value, "busy_time")}
            stamp = time.monotonic()
            decoder_cpu = 0
            if decoder_pid:
                try:
                    owned = psutil.Process(decoder_pid).cpu_times()
                    decoder_cpu = owned.user + owned.system
                except psutil.Error:
                    pass
            previous, self.previous = self.previous, (total, idle, ticks, stamp, decoder_pid, decoder_cpu)
            if not previous or total <= previous[0]:
                return {"observable": False, "cpu": None, "disk": None}
            cpu_load = max(0, min(100, 100 * (1 - (idle - previous[1]) / (total - previous[0]))))
            if decoder_pid and previous[4] == decoder_pid:
                cpu_load = max(0, cpu_load - 100 * max(0, decoder_cpu - previous[5]) / (total - previous[0]))
            disk_load = max((100 * (value - previous[2].get(key, value)) / ((stamp - previous[3]) * 1000)
                             for key, value in ticks.items()), default=None)
            return {"observable": disk_load is not None, "cpu": cpu_load,
                    "disk": min(100, max(0, disk_load)) if disk_load is not None else None}
        except (psutil.Error, OSError, AttributeError, ZeroDivisionError):
            return {"observable": False, "cpu": None, "disk": None}


class VideoHealthService:
    def __init__(self, *, observer=None, clock=time.time):
        self.observer = observer or LoadObserver()
        self.clock = clock
        self.stop_event = threading.Event()
        self.thread = None
        self.foreground_count = 0
        self.guard = threading.RLock()
        self.active_tool = None
        self.active_id = None
        self.reason = "starting"
        self.load = {"observable": False, "cpu": None, "disk": None}
        self.idle_since = None

    def config(self, session: Session | None = None) -> dict:
        if session is None:
            with Session(database.engine) as local:
                return self.config(local)
        row = session.get(Setting, "video_health_config")
        return {**DEFAULT_CONFIG, **(row.value if row and isinstance(row.value, dict) else {})}

    def configure(self, values: dict) -> dict:
        with self.guard, Session(database.engine) as session:
            config = {**self.config(session), **values}
            self._save_setting(session, "video_health_config", config)
            session.commit()
        return config

    @staticmethod
    def _save_setting(session, key, value):
        row = session.get(Setting, key) or Setting(key=key)
        row.value = value
        session.add(row)

    def runtime(self, session):
        row = session.get(Setting, "video_health_runtime")
        return {"cursor": "", "recent_since": "", "sweep": False, "manual": False,
                "next_sample_at": 0, "day": "", "used_seconds": 0,
                **(row.value if row and isinstance(row.value, dict) else {})}

    def queue_all(self):
        with self.guard, Session(database.engine) as session:
            state = self.runtime(session)
            state.update(cursor="", sweep=True, manual=True, next_sample_at=0)
            self._save_setting(session, "video_health_runtime", state)
            session.commit()
        return {"status": "queued", "batched": True}

    def scoped_receipts(self, statement):
        """Latest receipts in currently configured, active edition boundaries."""
        receipt = aliased(VideoHealth)
        latest = select(receipt.id).where(receipt.asset_id == VideoHealth.asset_id).order_by(
            receipt.observed_at.desc(), receipt.id.desc()).limit(1).correlate(VideoHealth).scalar_subquery()
        statement = statement.join(MediaAsset, MediaAsset.id == VideoHealth.asset_id).join(
            LibraryItem, LibraryItem.id == MediaAsset.library_item_id).where(
                VideoHealth.id == latest, MediaAsset.availability_status == "present",
                LibraryItem.availability_status == "available")
        prefixes = [str(Path(root)).rstrip('/\\') + os.sep for root in get_media_dirs()]
        return statement.where(or_(*(MediaAsset.locator.startswith(prefix, autoescape=True)
                                     for prefix in prefixes))) if prefixes else statement.where(False)

    def has_manual_work(self, session):
        statement = self.scoped_receipts(select(VideoHealth.id)).where(
            VideoHealth.priority == 20, VideoHealth.cancel_requested == False,
            or_(VideoHealth.status.in_(["unchecked", "queued", "checking"]),
                and_(VideoHealth.status == "incomplete", VideoHealth.error_code.in_(RETRYABLE))))
        return session.exec(statement.limit(1)).first() is not None

    def recover(self):
        with Session(database.engine) as session:
            for row in session.exec(select(VideoHealth).where(VideoHealth.status == "checking")).all():
                self._finish_row(row, "incomplete", "interrupted")
                session.add(row)
            session.commit()

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, name="video-health", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=10)

    def _run(self):
        # Only the owner may recover interrupted receipts or run a decoder.
        try:
            with file_lock(database.sqlite_path.with_suffix(".video-health.lock"), wait=False):
                self.recover()
                while not self.stop_event.is_set():
                    try:
                        self.tick()
                    except Exception:
                        logger.exception("Video health scheduling failed")
                        self.reason = "storage_unavailable"
                    self.stop_event.wait(2)
        except (BackupError, OSError):
            self.reason = "worker_owned_elsewhere"
        except Exception as exc:
            # Queue failure must not take down the library. Startup fixtures or
            # unavailable storage cannot safely recover or schedule work.
            self.reason = "storage_unavailable"
            logger.warning("Video health worker unavailable: %s", type(exc).__name__)

    @contextmanager
    def foreground(self):
        # Foreground jobs do not wait for a long video to finish. Suspension is
        # synchronous under the same lock used for launch and resume.
        with self.guard:
            self.foreground_count += 1
            if self.active_tool:
                try:
                    self.active_tool.pause(True)
                except (psutil.Error, OSError):
                    self.active_tool.pause_failed = True
                    self.active_tool.close()
        try:
            yield
        finally:
            with self.guard:
                self.foreground_count -= 1

    def scheduling_reason(self, *, active=False) -> str | None:
        config = self.config()
        now = datetime.fromtimestamp(self.clock(), timezone.utc)
        if config["paused"]:
            self.idle_since = None
            return "paused"
        if not config["enabled"]:
            with Session(database.engine) as session:
                if not self.runtime(session)["manual"] and not self.has_manual_work(session):
                    return "disabled"
        if not in_window(config, now):
            self.idle_since = None
            return "outside_window"
        with Session(database.engine) as session:
            jobs = session.exec(select(Job.id).where(Job.status.in_(["queued", "running", "cancelling"])).limit(1)).first()
            state = self.runtime(session)
        if self.foreground_count or jobs:
            self.idle_since = None
            return "application_busy"
        if not active and state["day"] == now.date().isoformat() and state["used_seconds"] >= config["daily_budget_minutes"] * 60:
            return "budget_used"
        self.load = self.observer.sample(self.active_tool.process.pid if self.active_tool else None)
        if not self.load["observable"]:
            # Explicitly narrowing the allowed window is the conservative fallback.
            if config["start_minute"] == config["end_minute"]:
                self.idle_since = None
                return "load_unobservable"
        running = active and self.active_tool is not None and not self.active_tool.suspended
        # Hysteresis: an already-running decoder may tolerate moderate load,
        # but a suspended decoder resumes only after the low idle thresholds.
        high = (self.load["cpu"] or 0) >= (75 if running else 30) or (self.load["disk"] or 0) >= (65 if running else 20)
        if high:
            self.idle_since = None
            return "host_busy"
        if self.idle_since is None:
            self.idle_since = self.clock()
        if self.clock() - self.idle_since < config["idle_seconds"]:
            return "waiting_idle"
        return None

    def tick(self):
        with self.guard:
            reason = self.scheduling_reason()
            self.reason = reason or "idle"
            if reason:
                return
            with Session(database.engine) as session:
                due = self.runtime(session)["next_sample_at"] <= self.clock()
            if due:
                self.discover(batch=4)
            with Session(database.engine) as session:
                statement = self.scoped_receipts(select(VideoHealth)).where(VideoHealth.status == "queued")
                if not self.config(session)["enabled"] and not self.runtime(session)["manual"]:
                    statement = statement.where(VideoHealth.priority == 20)
                row = session.exec(statement
                    .where(VideoHealth.next_attempt_at <= self.clock())
                    .order_by(VideoHealth.priority.desc(), VideoHealth.observed_at).limit(1)).first()
                identifier = row.id if row else None
        if identifier:
            self.inspect(identifier)

    def discover(self, batch=12):
        """Bounded stat samples over DB-known assets; no recursive filesystem walk."""
        with Session(database.engine) as session:
            state = self.runtime(session)
            state["next_sample_at"] = self.clock() + 30
            config = self.config(session)
            cutoff = datetime.fromtimestamp(self.clock(), timezone.utc).isoformat()
            base = select(MediaAsset).join(LibraryItem, LibraryItem.id == MediaAsset.library_item_id).where(
                MediaAsset.asset_kind.in_(["video", "video_part"]), MediaAsset.availability_status == "present",
                LibraryItem.availability_status == "available")
            roots = get_media_dirs()
            prefixes = [str(Path(root)).rstrip('/\\') + os.sep for root in roots]
            base = base.where(or_(*(MediaAsset.locator.startswith(prefix, autoescape=True) for prefix in prefixes))) if prefixes else base.where(False)
            recent = session.exec(base.where(MediaAsset.updated_at > state["recent_since"])
                .order_by(MediaAsset.updated_at, MediaAsset.id).limit(batch)).all() if config["enabled"] else []
            older = session.exec(base.where(MediaAsset.id > state["cursor"])
                .order_by(MediaAsset.id).limit(batch)).all() if config["enabled"] or state["sweep"] else []
            receipt = aliased(VideoHealth)
            latest_id = select(receipt.id).where(receipt.asset_id == MediaAsset.id).order_by(
                receipt.observed_at.desc(), receipt.id.desc()).limit(1).correlate(MediaAsset).scalar_subquery()
            pending_statement = base.join(VideoHealth, VideoHealth.asset_id == MediaAsset.id)
            if not config["enabled"] and not state["manual"]:
                pending_statement = pending_statement.where(VideoHealth.priority == 20)
            pending = session.exec(pending_statement
                .where(VideoHealth.id == latest_id)
                .where(or_(VideoHealth.status.in_(["unchecked", "queued"]),
                    and_(VideoHealth.status == "incomplete", VideoHealth.error_code.in_(RETRYABLE),
                         VideoHealth.next_attempt_at <= self.clock())))
                .order_by(VideoHealth.priority.desc(), VideoHealth.observed_at).limit(batch)).all()
            if older:
                state["cursor"] = older[-1].id
            else:
                state.update(cursor="", sweep=False)
            if recent:
                # Keep scanning a large burst across ticks; equal timestamps are
                # also covered by the persistent older cursor without starvation.
                state["recent_since"] = recent[-1].updated_at if len(recent) == batch else cutoff
            else:
                state["recent_since"] = cutoff
            for asset in {a.id: a for a in [*recent, *older, *pending]}.values():
                snapshot = asset_snapshot(asset)
                previous = session.exec(select(VideoHealth).where(VideoHealth.asset_id == asset.id)
                    .order_by(VideoHealth.observed_at.desc()).limit(1)).first()
                if previous and previous.next_attempt_at > self.clock() and previous.asset_snapshot == snapshot:
                    continue
                if (previous and previous.status == "passed" and previous.asset_snapshot == snapshot
                        and not state["manual"] and previous.checked_at
                        and self.clock() - previous.checked_at < 86400):
                    # Passing unchanged scan metadata needs no repeated disk
                    # read. A manual sweep or a later daily sample can detect
                    # additional out-of-band changes; live detail checks now.
                    continue
                try:
                    version = file_version(asset)
                except (OSError, ValueError) as exc:
                    if previous is None:
                        version = {"locator_hash": asset.normalized_locator_hash, "size": asset.file_size,
                                   "mtime": asset.file_mtime, "unobserved": True}
                        previous = VideoHealth(id="vh_" + digest([asset.id, version])[:32], asset_id=asset.id,
                            version_key=digest(version), version=version, asset_snapshot=snapshot,
                            observed_at=self.clock())
                    if previous:
                        code = "permission_denied" if isinstance(exc, PermissionError) else "boundary_changed" if isinstance(exc, MediaBoundaryError) else "offline"
                        self._finish_row(previous, "incomplete", code)
                        previous.attempts += 1
                        previous.next_attempt_at = self.clock() + min(86400, 60 * 2 ** min(previous.attempts, 10))
                        session.add(previous)
                    continue
                key = digest(version)
                if previous and previous.version_key != key:
                    if previous.status in {"unchecked", "queued"}:
                        self._finish_row(previous, "incomplete", "file_changed")
                        session.add(previous)
                    if not config["enabled"] and not state["manual"]:
                        # A single retry grants no authority to a newer version.
                        continue
                identifier = "vh_" + digest([asset.id, key])[:32]
                row = session.get(VideoHealth, identifier)
                if row is None:
                    if previous and previous.version_key != key:
                        # A retained historical pass is never the current pass.
                        previous.acknowledged = True
                        session.add(previous)
                    row = VideoHealth(id=identifier, asset_id=asset.id, version_key=key, version=version,
                        asset_snapshot=snapshot, observed_at=self.clock(),
                        priority=15 if previous and previous.version_key != key else 10 if asset in recent else 0)
                elif row.asset_snapshot != snapshot:
                    row.asset_snapshot = snapshot
                    # Same physical file after an identity move gets a fresh
                    # stability observation; no old owner notification transfers.
                    row.observed_at = self.clock()
                    row.status = "unchecked"
                    row.acknowledged = True
                if state["manual"] and asset in older and row.status in {"unchecked", "queued"}:
                    row.priority = 20
                if row.status == "unchecked" and self.clock() - row.observed_at >= config["stable_seconds"]:
                    row.status = "queued"
                elif row.status == "incomplete" and row.error_code in RETRYABLE and row.next_attempt_at <= self.clock():
                    if row.passed_at is not None:
                        # A temporary offline/access failure must not erase an
                        # unchanged version's successful continuous decode.
                        row.status = "passed"
                        row.error_code = None
                        row.error_summary = None
                    else:
                        row.status = "unchecked"
                        row.observed_at = self.clock()
                session.add(row)
            session.flush()
            if state["manual"] and not state["sweep"]:
                if not self.has_manual_work(session):
                    state["manual"] = False
            self._save_setting(session, "video_health_runtime", state)
            session.commit()

    def _context(self, session, row):
        asset = session.get(MediaAsset, row.asset_id)
        item = session.get(LibraryItem, asset.library_item_id) if asset else None
        if not asset or not item or asset.availability_status != "present" or item.availability_status != "available":
            raise MediaBoundaryError("Edition is no longer available")
        if asset_snapshot(asset) != row.asset_snapshot:
            raise MediaBoundaryError("Edition changed")
        if digest(file_version(asset)) != row.version_key:
            raise RuntimeError("file_changed")
        return asset, item

    def inspect(self, identifier):
        with self.guard, Session(database.engine) as session:
            row = session.get(VideoHealth, identifier)
            if not row or row.status != "queued" or row.cancel_requested:
                return
            try:
                asset, _ = self._context(session, row)
                path = Path(asset.locator)
                with path.open("rb") as handle:
                    handle.read(1)  # Read-only access check, not a hash or probe.
            except (OSError, ValueError, RuntimeError) as exc:
                self._finish_row(row, "incomplete", self._access_code(exc))
                row.attempts += 1
                row.next_attempt_at = self.clock() + min(86400, 60 * 2 ** min(row.attempts, 10))
                session.add(row); session.commit()
                return
            row.status = "checking"
            row.container_status = "unchecked"
            row.decoded_seconds = 0
            row.passed_at = None  # A newly started decode supersedes an old certificate.
            row.attempts += 1
            session.add(row); session.commit()
            self.active_id = identifier
        try:
            probe = container_arguments(path)
            if probe is None or decode_arguments(path, []) is None:
                self.finish(identifier, "unsupported", "tool_missing")
                return
            result, code, tool = self.run_tool(identifier, probe, probe=True)
            if result != "passed":
                self.finish(identifier, result, code, container_status=result)
                return
            try:
                streams, duration = probe_payload(tool)
            except (ValueError, TypeError, KeyError):
                self.finish(identifier, "incomplete", "metadata_invalid", container_status="incomplete")
                return
            with Session(database.engine) as session:
                row = session.get(VideoHealth, identifier)
                if row:
                    row.container_status = "passed"
                    row.duration_seconds = duration
                    session.add(row); session.commit()
            result, code, tool = self.run_tool(identifier, decode_arguments(path, streams))
            if result == "passed" and (not tool.ended or tool.seconds <= 0):
                result, code = "incomplete", "tool_failed"
            if result == "passed" and duration and duration - tool.seconds > max(2, duration * .02):
                result, code = "abnormal", "duration_short"
            self.finish(identifier, result, code)
        except Exception:
            logger.exception("Video inspection could not complete")
            self.finish(identifier, "incomplete", "tool_failed")
        finally:
            with self.guard:
                self.active_id = None
                self.active_tool = None

    @staticmethod
    def _access_code(exc):
        return ("permission_denied" if isinstance(exc, PermissionError) else
                "boundary_changed" if isinstance(exc, MediaBoundaryError) else
                "file_changed" if isinstance(exc, RuntimeError) else "offline")

    def run_tool(self, identifier, arguments, *, probe=False):
        tool = None
        code = None
        try:
            while tool is None:
                with self.guard:
                    if self.stop_event.is_set():
                        return "incomplete", "interrupted", None
                    with Session(database.engine) as session:
                        row = session.get(VideoHealth, identifier)
                        if row is None or row.cancel_requested:
                            return "incomplete", "cancelled", None
                        try:
                            self._context(session, row)
                        except (OSError, ValueError, RuntimeError) as exc:
                            return "incomplete", self._access_code(exc), None
                    # Foreground work or pause between probe and decode must not
                    # abandon a long file, nor launch a tool during that work.
                    reason = self.scheduling_reason(active=True)
                    self.reason = reason or "checking"
                    if reason is None:
                        tool = ToolProcess(arguments)
                        self.active_tool = tool
                if tool is None:
                    self.stop_event.wait(.5)
            last_tick, last_progress, last_seconds = self.clock(), self.clock(), 0
            while True:
                with self.guard:
                    if self.stop_event.is_set():
                        code = "interrupted"
                        break
                    if tool.pause_failed:
                        code = "suspend_unsupported"
                        break
                    with Session(database.engine) as session:
                        row = session.get(VideoHealth, identifier)
                        if row is None or row.cancel_requested:
                            code = "cancelled"; break
                        try:
                            self._context(session, row)
                        except (OSError, ValueError, RuntimeError) as exc:
                            code = self._access_code(exc); break
                        row.decoded_seconds = tool.seconds if not probe else row.decoded_seconds
                        session.add(row)
                        state = self.runtime(session)
                        today = datetime.fromtimestamp(self.clock(), timezone.utc).date().isoformat()
                        if state["day"] != today:
                            state.update(day=today, used_seconds=0)
                        if not tool.suspended:
                            state["used_seconds"] += max(0, self.clock() - last_tick)
                        self._save_setting(session, "video_health_runtime", state)
                        session.commit()
                    last_tick = self.clock()
                    if tool.process.poll() is not None:
                        result = tool.result()
                        if not probe:
                            with Session(database.engine) as session:
                                row = session.get(VideoHealth, identifier)
                                if row:
                                    row.decoded_seconds = tool.seconds
                                    session.add(row); session.commit()
                        return *result, tool
                    reason = self.scheduling_reason(active=True)
                    self.reason = reason or "checking"
                    try:
                        tool.pause(bool(reason))
                    except (psutil.Error, OSError):
                        code = "suspend_unsupported"; break
                    if tool.seconds != last_seconds or tool.suspended:
                        last_progress, last_seconds = self.clock(), tool.seconds
                    if self.clock() - last_progress > (30 if probe else 180):
                        code = "timeout"; break
                self.stop_event.wait(.5)
            return "incomplete", code, tool
        except (OSError, psutil.Error):
            return "incomplete", "read_unavailable", tool
        finally:
            if tool:
                tool.close()
            with self.guard:
                self.active_tool = None

    def _finish_row(self, row, status, code):
        row.status = status
        row.error_code = code
        row.error_summary = SUMMARIES.get(code) if code else None
        row.checked_at = self.clock()
        if status == "passed":
            row.passed_at = self.clock()
        elif status == "abnormal" or code not in RETRYABLE:
            row.passed_at = None

    def finish(self, identifier, status, code, *, container_status=None):
        notify = False
        with Session(database.engine) as session:
            row = session.get(VideoHealth, identifier)
            if not row:
                return
            try:
                self._context(session, row)
            except (OSError, ValueError, RuntimeError) as exc:
                status, code = "incomplete", self._access_code(exc)
            if row.cancel_requested:
                status, code = "incomplete", "cancelled"
            self._finish_row(row, status, code)
            if container_status:
                row.container_status = container_status
            if code in RETRYABLE:
                row.next_attempt_at = self.clock() + min(86400, 60 * 2 ** min(row.attempts, 10))
            if status == "abnormal" and not row.notified:
                row.notified = True
                row.acknowledged = False
                notify = True
            session.add(row); session.commit()
        if notify:
            library_event_bus.publish("video_health_attention", {"id": identifier})

    def control(self, identifier, action):
        with self.guard, Session(database.engine) as session:
            row = session.get(VideoHealth, identifier)
            if row is None:
                raise LookupError("Inspection not found")
            if action == "acknowledge":
                row.acknowledged = True
            elif action == "cancel":
                row.cancel_requested = True
                if row.status in {"queued", "unchecked"}:
                    self._finish_row(row, "incomplete", "cancelled")
            elif action == "retry":
                self._context(session, row)
                if row.status != "checking":
                    row.status = "unchecked"
                    row.observed_at = self.clock()
                    row.cancel_requested = False
                    row.error_code = None
                    row.error_summary = None
                    row.next_attempt_at = 0
                    row.priority = 20
                    state = self.runtime(session)
                    state["next_sample_at"] = 0
                    self._save_setting(session, "video_health_runtime", state)
            session.add(row); session.commit()


video_health = VideoHealthService()
