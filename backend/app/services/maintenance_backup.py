"""Downloadable, configuration-free database backups. Never writes to the source."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import threading
import time
import zipfile
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, quote_plus

from app import database
from app.migrations.backup import create_verified_backup
from app.migrations.restore import verify_backup_manifest

logger = logging.getLogger(__name__)
ID = re.compile(r"[0-9a-f]{32}")
SECRET_KEY = re.compile(r"(?:api[_-]?key|token|password|secret|authorization|credential|signature)", re.I)
JSON_SECRET_KEY = re.compile(r"^(?:(?:tmdb[_-]|openrouter[_-])?api[_-]?key|(?:access[_-]|refresh[_-]|auth[_-])?token|password|(?:client[_-])?secret|authorization|credential|signature)$", re.I)
ASSIGNMENT = re.compile(r"(?i)((?:[?&](?:api[_-]?key|(?:access[_-]|refresh[_-]|auth[_-])?token|password|(?:client[_-])?secret|signature|x-amz-signature|x-goog-signature))=)[^\s&\"'<>;,]+")
AUTH = re.compile(r"(?i)(authorization\s*[:=]\s*(?:Bearer|Basic))\s+[A-Za-z0-9+/=._~-]+")
URL_AUTH = re.compile(r"(?i)(https?://)[^\s/@]+@")
DIAGNOSTICS = {"scrape_error", "error", "error_message"}
# All other tables are protected, including user-reviewed assertions and evidence.
AUTOMATIC_TABLES = {"job", "workflow_run", "workflow_step", "events", "operation_snapshot", "library_item"}

README = """5X49 library database backup / 片库数据库备份

Includes SQLite library data, manual metadata and edit history, personal Film
reviews and Viewing reviews, identities and analysis. This is NOT library-export.v1.
Configuration (the entire Setting table), API keys, artwork files, video, NFO,
environment files, external operation manifests and host-specific video health
receipts/queues are NOT included. Diagnostic
errors and credential-bearing automatic fields are sanitized. Filesystem undo
snapshots are expired: database history does not restore file undo capability.
Reconfigure media directories and API keys after recovery. Paths stored in library
records remain, so keep this personal backup private. Arbitrary secrets typed in
personal content cannot be identified semantically.

Recovery uses the existing offline CLI; there is no web restore endpoint:
1. Extract this ZIP to a private directory, keeping the .db and .manifest.json together.
2. python -m app.migrations.restore --manifest <extracted.manifest.json>
3. In a NEW temporary environment initialize an empty database with the same app
   version, with WATCH_LIBRARY=false, no credentials and no media configured.
   Stop the backend/writers. Checkpoint the target SQLite WAL, then independently
   calculate the current target database SHA-256.
4. python -m app.migrations.restore --manifest <extracted.manifest.json> --replace
   --target <offline-target.db> --confirm-current-sha256 <current-target-sha256>
   (Run the command on one line.) The existing CLI preserves the previous target.
5. Start with WATCH_LIBRARY=false and review the restored library before configuring
   media paths, credentials or automation. No active database tasks are packaged.

包含影片、人工资料、编辑历史、观看记录和评价；不包含配置/密钥、海报文件、视频、
NFO 或外部操作清单。恢复后需重新配置目录与密钥；文件操作撤销不可用。
生成成功和浏览器触发下载都不能证明文件已保存到用户磁盘，请自行确认并保管下载文件。
"""


class BackupError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def now():
    return datetime.now(timezone.utc)


@contextmanager
def file_lock(path: Path, *, wait: bool = True):
    """OS-owned lock: process death releases it; no stale PID/lease guessing."""
    with path.open("a+b") as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + (5 if wait else 0)
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise BackupError("backup_busy") from None
                time.sleep(0.02)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _scrub(value, secrets):
    if isinstance(value, dict):
        return {key: None if key.lower() in DIAGNOSTICS else "[redacted]" if JSON_SECRET_KEY.fullmatch(key) else _scrub(item, secrets)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item, secrets) for item in value]
    if not isinstance(value, str):
        return value
    for secret in secrets:
        value = value.replace(secret, "[redacted]")
    value = URL_AUTH.sub(r"\1[redacted]@", value)
    value = AUTH.sub(r"\1 [redacted]", value)
    return ASSIGNMENT.sub(r"\1[redacted]", value)


def sanitize_snapshot(path: Path) -> int:
    """Only the private snapshot is changed; user-authored content is never redacted."""
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        for table, statuses in (("job", ("queued", "running", "cancelling")),
                                ("workflow_run", ("queued", "running")),
                                ("workflow_step", ("queued", "running")),
                                ("analysis_run", ("queued", "running"))):
            marks = ",".join("?" for _ in statuses)
            if db.execute(f'SELECT 1 FROM "{table}" WHERE status IN ({marks}) LIMIT 1', statuses).fetchone():
                raise BackupError("backup_tasks_active")
        # Host-specific receipts and queued work never replay after restoring.
        db.execute("DELETE FROM video_health")
        secrets = {os.environ.get(key, "") for key in ("TMDB_API_KEY", "OPENROUTER_API_KEY")}
        for key, raw in db.execute("SELECT key, value FROM setting"):
            if SECRET_KEY.search(key):
                value = json.loads(raw)
                if isinstance(value, str):
                    secrets.add(value)
        secrets.discard("")
        # An invalid short credential would also match ordinary words and hashes.
        if any(len(value) < 8 for value in secrets):
            raise BackupError("backup_sensitive_content")
        variants = {encoded for value in secrets for encoded in (value, quote(value, safe=""), quote_plus(value), json.dumps(value)[1:-1])}
        variants = sorted(variants, key=len, reverse=True)
        db.execute("PRAGMA secure_delete=ON")
        db.execute("DELETE FROM setting")
        db.execute("UPDATE operation_snapshot SET status='expired', backup_manifest_ref=NULL WHERE operation_kind='file_organization'")
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        # Derived caches can embed old diagnostic text. Rebuild from preserved facts
        # on startup; retaining their old hashes after sanitization would fail boot.
        for table in tables:
            if table.endswith("_read_model") or table == "projection_state":
                quoted = '"' + table.replace('"', '""') + '"'
                db.execute(f"DELETE FROM {quoted}")
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            columns = [row[1] for row in db.execute(f"PRAGMA table_info({quoted})")]
            for row in db.execute(f"SELECT rowid, * FROM {quoted}").fetchall():
                updates = {}
                for column, value in zip(columns, row[1:]):
                    if not isinstance(value, str):
                        continue
                    parsed = value
                    if value.startswith(("{", "[")):
                        try:
                            parsed = json.loads(value)
                        except ValueError:
                            pass
                    clean = None if column.lower() in DIAGNOSTICS else _scrub(parsed, variants)
                    if clean == parsed:
                        continue
                    if (table not in AUTOMATIC_TABLES and not table.endswith("_read_model")) and column.lower() not in DIAGNOSTICS:
                        raise BackupError("backup_sensitive_content")
                    updates[column] = json.dumps(clean, ensure_ascii=False) if not isinstance(parsed, str) else clean
                if updates:
                    assignments = ",".join('"' + col.replace('"', '""') + '"=?' for col in updates)
                    db.execute(f"UPDATE {quoted} SET {assignments} WHERE rowid=?", (*updates.values(), row[0]))
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise BackupError("backup_failed")
        version = db.execute("SELECT MAX(version) FROM schema_migrations WHERE status='applied'").fetchone()[0]
        db.commit()
        # Discard free pages/old string content; switch off copied WAL mode before packaging.
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("VACUUM")
    with path.open("rb") as handle:
        overlap = b""
        needles = [value.encode() for value in variants]
        keep = max(map(len, needles), default=1)
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            data = overlap + chunk
            if any(needle in data for needle in needles):
                raise BackupError("backup_sensitive_content")
            overlap = data[-keep:]
    return int(version)


class MaintenanceBackups:
    def __init__(self, source: Path, directory: Path | None = None):
        self.source = source
        self.directory = directory or source.parent / "maintenance-backups"
        self.stopping = threading.Event()
        self.janitor = None

    @contextmanager
    def state(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with file_lock(self.directory / "state.lock"), closing(sqlite3.connect(self.directory / "state.sqlite3", timeout=5)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("""CREATE TABLE IF NOT EXISTS attempt (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL,
                finished_at TEXT, expires_at TEXT, size_bytes INTEGER, sha256 TEXT,
                schema_version INTEGER, error_code TEXT, download_triggered_at TEXT,
                artifact_state TEXT)""")
            yield db

    def archive(self, identifier):
        if not ID.fullmatch(identifier):
            raise BackupError("backup_not_found")
        return self.directory / f"5x49-backup-{identifier}.zip"

    def _latest(self, db, success=False):
        return db.execute("SELECT * FROM attempt " + ("WHERE status='succeeded' " if success else "") + "ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()

    def _view(self, row):
        if row is None:
            return None
        result = dict(row)
        result["available"] = row["artifact_state"] == "available"
        result["filename"] = self.archive(row["id"]).name if row["status"] == "succeeded" else None
        return result

    def _cleanup(self, db):
        success = self._latest(db, True)
        keep = None
        if success and success["artifact_state"] == "available":
            path = self.archive(success["id"])
            reason = "expired" if success["expires_at"] <= now().isoformat() else "missing" if not path.is_file() else None
            if reason:
                db.execute("UPDATE attempt SET artifact_state=? WHERE id=?", (reason, success["id"]))
            else:
                keep = path
        for path in self.directory.glob("5x49-backup-*.zip"):
            if path != keep and ID.fullmatch(path.stem.removeprefix("5x49-backup-")):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass  # An open Windows download owns the file until its stream closes.

    def _recover(self, db):
        try:
            with file_lock(self.directory / "generation.lock", wait=False):
                db.execute("UPDATE attempt SET status='interrupted', finished_at=?, error_code='backup_interrupted' WHERE status='generating'", (now().isoformat(),))
                for path in self.directory.glob("stage-*"):
                    if ID.fullmatch(path.name.removeprefix("stage-")) and not path.is_symlink():
                        shutil.rmtree(path, ignore_errors=True)
        except BackupError:
            pass  # Another worker owns the generation, including in another process.

    def status(self):
        with self.state() as db:
            self._recover(db)
            self._cleanup(db)
            return {"last_attempt": self._view(self._latest(db)), "last_success": self._view(self._latest(db, True)), "retention_hours": 24}

    def get(self, identifier):
        with self.state() as db:
            self._recover(db)
            self._cleanup(db)
            row = db.execute("SELECT * FROM attempt WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise BackupError("backup_not_found")
            return self._view(row)

    def create(self, identifier):
        with self.state() as db:
            self._recover(db)
            self._cleanup(db)
            prior = db.execute("SELECT * FROM attempt WHERE id=?", (identifier,)).fetchone()
            if prior:
                return self._view(prior)
            lease = file_lock(self.directory / "generation.lock", wait=False)
            lease.__enter__()
            try:
                db.execute("INSERT INTO attempt (id,status,created_at) VALUES (?,'generating',?)", (identifier, now().isoformat()))
                db.commit()  # Publish the claim before the worker or response can observe it.
                worker = threading.Thread(target=self._generate, args=(identifier, lease), daemon=True)
                worker.start()
            except BaseException:
                lease.__exit__(None, None, None)
                raise
            return self._view(db.execute("SELECT * FROM attempt WHERE id=?", (identifier,)).fetchone())

    def _generate(self, identifier, lease):
        stage = self.directory / f"stage-{identifier}"
        published = False
        try:
            stage.mkdir(mode=0o700)
            from app.services.video_health import video_health
            with video_health.foreground():
                raw = create_verified_backup(self.source, stage / "raw", app_version=database._app_version(), source_schema_version=0, target_schema_version=0)
            schema = sanitize_snapshot(raw.database_path)
            artifact = create_verified_backup(raw.database_path, stage / "clean", app_version=database._app_version(), source_schema_version=schema, target_schema_version=schema)
            verify_backup_manifest(artifact.manifest_path)
            package = stage / "package.zip"
            with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(artifact.database_path, artifact.database_path.name)
                archive.write(artifact.manifest_path, artifact.manifest_path.name)
                archive.writestr("RESTORE.txt", README)
            with package.open("r+b") as handle:
                os.fsync(handle.fileno())
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            size = package.stat().st_size
            if self.stopping.is_set():
                raise BackupError("backup_interrupted")
            with self.state() as db:
                os.replace(package, self.archive(identifier))
                finished = now()
                db.execute("UPDATE attempt SET artifact_state='superseded' WHERE artifact_state='available'")
                db.execute("UPDATE attempt SET status='succeeded',finished_at=?,expires_at=?,size_bytes=?,sha256=?,schema_version=?,artifact_state='available' WHERE id=?",
                           (finished.isoformat(), (finished + timedelta(hours=24)).isoformat(), size, digest, schema, identifier))
                db.commit()
                published = True
                self._cleanup(db)
        except Exception as exc:
            code = exc.code if isinstance(exc, BackupError) else "backup_failed"
            try:
                with self.state() as db:
                    db.execute("UPDATE attempt SET status=?,finished_at=?,error_code=? WHERE id=? AND status='generating'",
                               ("interrupted" if code == "backup_interrupted" else "failed", now().isoformat(), code, identifier))
            except Exception:
                logger.error("Backup status storage unavailable")
        finally:
            try:
                if not published:
                    try:
                        self.archive(identifier).unlink(missing_ok=True)
                    except OSError:
                        pass
                shutil.rmtree(stage, ignore_errors=True)
            finally:
                lease.__exit__(None, None, None)

    def download(self, identifier):
        with self.state() as db:
            self._cleanup(db)
            row = db.execute("SELECT * FROM attempt WHERE id=?", (identifier,)).fetchone()
            if not row or row["artifact_state"] != "available":
                raise BackupError("backup_unavailable")
            handle = self.archive(identifier).open("rb")
            try:
                if hashlib.file_digest(handle, "sha256").hexdigest() != row["sha256"]:
                    db.execute("UPDATE attempt SET artifact_state='corrupt' WHERE id=?", (identifier,))
                    db.commit()
                    raise BackupError("backup_unavailable")
                handle.seek(0)
                return handle, self._view(row)
            except BaseException:
                handle.close()
                raise

    def acknowledge(self, identifier):
        with self.state() as db:
            row = db.execute("SELECT * FROM attempt WHERE id=? AND status='succeeded'", (identifier,)).fetchone()
            if not row:
                raise BackupError("backup_not_found")
            db.execute("UPDATE attempt SET download_triggered_at=COALESCE(download_triggered_at,?) WHERE id=?", (now().isoformat(), identifier))
            return self._view(db.execute("SELECT * FROM attempt WHERE id=?", (identifier,)).fetchone())

    def start(self):
        self.stopping.clear()
        try:
            self.status()
        except Exception:
            # A damaged/unwritable backup store must not prevent library startup.
            logger.error("Backup status storage unavailable")
        def sweep():
            while not self.stopping.wait(60):
                try:
                    self.status()
                except Exception:
                    logger.error("Backup cleanup unavailable")
        self.janitor = threading.Thread(target=sweep, daemon=True)
        self.janitor.start()

    def stop(self):
        self.stopping.set()
        if self.janitor:
            self.janitor.join(timeout=2)


maintenance_backups = MaintenanceBackups(database.sqlite_path)
