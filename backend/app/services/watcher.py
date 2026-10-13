import threading
import os
import time
import hashlib
from pathlib import Path
from typing import Optional

from app.services.event_bus import library_event_bus
from app.services.operation_manifests import operation_manifest_store
from app.services.settings import (
    get_auto_organize_root_videos,
    get_media_dir,
    get_media_dirs,
    get_media_file_stable_seconds,
    get_watch_debounce_seconds,
    get_watch_interval_seconds,
    get_watch_mode,
)

try:
    from watchfiles import Change, watch
except ImportError:
    Change = None
    watch = None


from app.services.media_roots import configured_root, safe_path, is_link, directory_status, root_id


class _RootWatcher:
    """Media watcher with native events and a polling fallback.

    The default path uses watchfiles so the media tree is not traversed every
    few seconds. Polling remains available for mounts where native events are
    unavailable or unreliable.
    """

    tracked_extensions = {
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv",
        ".m4v",
        ".ts",
        ".iso",
        ".nfo",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    }
    video_extensions = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".ts", ".iso"}

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._snapshot: dict[str, tuple[float, int, bool]] = {}
        self._path_types: dict[str, bool] = {}
        self._pending_folders: dict[str, float] = {}
        self._status = {
            "running": False,
            "media_dir": None,
            "mode": None,
            "last_event_at": None,
            "last_error": None,
            "pending": 0,
        }

    def start(self, media_dir: Optional[str] = None) -> dict:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return {**self._status, "pending": len(self._pending_folders)}

            target_dir = Path(media_dir or get_media_dir())
            mode = get_watch_mode()
            if mode == "events" and watch is None:
                mode = "polling"

            self._stop_event.clear()
            self._pending_folders = {}
            self._snapshot = {}
            self._path_types = {}
            if mode == "polling":
                try:
                    self._snapshot = self._build_snapshot(target_dir)
                except (OSError, ValueError):
                    self._snapshot = {}
            else:
                self._path_types = self._build_path_type_index(target_dir)

            self._status.update({
                "running": True,
                "media_dir": str(target_dir),
                "mode": mode,
                "last_error": None,
                "pending": 0,
            })
            self._thread = threading.Thread(
                target=self._run,
                args=(target_dir, mode),
                name="library-watcher",
                daemon=True,
            )
            self._thread.start()
            return {**self._status, "pending": len(self._pending_folders)}

    def stop(self) -> dict:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2)

        with self._lock:
            self._status["running"] = False
            self._status["pending"] = len(self._pending_folders)
        return self.status()

    def status(self) -> dict:
        with self._lock:
            status = dict(self._status)
            status["pending"] = len(self._pending_folders)
            return status

    def _run(self, media_dir: Path, mode: str):
        if mode == "polling":
            self._run_polling(media_dir)
        else:
            self._run_events(media_dir)

        with self._lock:
            self._status["running"] = False

    def _run_events(self, media_dir: Path):
        if watch is None:
            self._record_error("watchfiles is not installed")
            return

        while not self._stop_event.is_set():
            if not media_dir.exists():
                self._record_error(f"Directory not found: {media_dir}")
                self._stop_event.wait(get_watch_interval_seconds())
                continue

            self._record_error(None)
            try:
                for changes in watch(
                    *self._watch_directories(media_dir),
                    watch_filter=self._watch_filter,
                    stop_event=self._stop_event,
                    debounce=1000,
                    rust_timeout=1000,
                    yield_on_timeout=True,
                    recursive=False,
                ):
                    if self._stop_event.is_set():
                        break

                    for change, path in changes:
                        self._handle_event_change(change, path)
                    self._flush_ready_folders()
                    if time.time() - getattr(self, "_indexed_at", 0) >= get_watch_interval_seconds():
                        break
            except Exception as exc:
                self._record_error(str(exc))
                self._stop_event.wait(get_watch_interval_seconds())

    def _run_polling(self, media_dir: Path):
        while not self._stop_event.is_set():
            try:
                next_snapshot = self._build_snapshot(media_dir)
                self._handle_snapshot_changes(self._snapshot, next_snapshot)
                self._snapshot = next_snapshot
                self._flush_ready_folders()
            except Exception as exc:
                self._record_error(str(exc))

            self._stop_event.wait(get_watch_interval_seconds())

    def _build_snapshot(self, media_dir: Path) -> dict[str, tuple[float, int, bool]]:
        snapshot = {}
        pending = [media_dir]
        safe_path(media_dir.absolute(), media_dir.absolute())
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path).absolute()
                    if entry.name.startswith('.') or is_link(path):
                        continue
                    safe_path(path, media_dir.absolute())
                    is_directory = entry.is_dir(follow_symlinks=False)
                    if is_directory:
                        pending.append(path)
                    if is_directory or path.suffix.lower() in self.tracked_extensions:
                        stat = entry.stat(follow_symlinks=False)
                        snapshot[str(path)] = (stat.st_mtime, stat.st_size, is_directory)
        return snapshot

    def _build_path_type_index(self, media_dir: Path) -> dict[str, bool]:
        try:
            return {path: value[2] for path, value in self._build_snapshot(media_dir).items()}
        except (OSError, ValueError):
            return {}

    def _watch_directories(self, media_dir: Path):
        self._indexed_at = time.time()
        snapshot = self._build_snapshot(media_dir)
        # Nonrecursive watches never descend into links or junctions. A periodic
        # refresh catches newly mounted roots and whole trees moved into a root.
        self._handle_snapshot_changes(self._snapshot, snapshot)
        self._snapshot = snapshot
        self._path_types = {path: value[2] for path, value in snapshot.items()}
        return [media_dir, *(Path(path) for path, value in snapshot.items() if value[2])]

    def _handle_snapshot_changes(self, previous: dict, current: dict):
        previous_paths = set(previous)
        current_paths = set(current)

        for path in current_paths - previous_paths:
            self._queue_path(path, current[path][2])

        for path in previous_paths & current_paths:
            if previous[path] != current[path]:
                self._queue_path(path, current[path][2])

        for path in previous_paths - current_paths:
            was_directory = previous[path][2]
            if was_directory:
                self._enqueue_job("library.mark_path_missing", {"path": path})
            elif Path(path).suffix.lower() in self.video_extensions:
                self._enqueue_job("library.mark_path_missing", {"path": path})
            else:
                self._queue_folder(str(Path(path).parent))

    def _handle_event_change(self, change, path: str):
        path_obj = Path(path)
        normalized = self._normalize_event_path(path_obj)
        if not normalized:
            return

        if change == Change.deleted:
            was_directory = self._path_types.pop(normalized, None)
            if was_directory is None:
                was_directory = path_obj.suffix == ""

            if was_directory:
                self._enqueue_job("library.mark_path_missing", {"path": normalized})
            elif path_obj.suffix.lower() in self.video_extensions:
                self._enqueue_job("library.mark_path_missing", {"path": normalized})
                if self._is_direct_media_root_child(path_obj):
                    library_event_bus.publish_library_changed("root_videos_changed")
            else:
                self._queue_folder(str(path_obj.parent))
            return

        is_directory = path_obj.is_dir()
        self._path_types[normalized] = is_directory
        self._queue_path(normalized, is_directory)

    def _queue_path(self, path: str, is_directory: bool):
        folder = path if is_directory else str(Path(path).parent)
        self._queue_folder(folder)

    def _queue_folder(self, folder: str):
        now = time.time()
        with self._lock:
            self._pending_folders[folder] = now
            self._status["last_event_at"] = now
            self._status["pending"] = len(self._pending_folders)

    def _flush_ready_folders(self):
        debounce_seconds = get_watch_debounce_seconds()
        now = time.time()

        with self._lock:
            ready = [
                folder
                for folder, changed_at in self._pending_folders.items()
                if now - changed_at >= debounce_seconds
            ]
            for folder in ready:
                self._pending_folders.pop(folder, None)
            self._status["pending"] = len(self._pending_folders)

        for folder in ready:
            folder_path = Path(folder)
            try:
                configured_root(folder_path)
            except (ValueError, OSError):
                continue
            if folder_path.exists():
                if self._has_recent_video(folder):
                    self._queue_folder(folder)
                    continue
                if self._is_media_root(folder_path):
                    if get_auto_organize_root_videos():
                        self._enqueue_job("organizer.organize_root", {"media_dir": str(folder_path)})
                    else:
                        library_event_bus.publish_library_changed("root_videos_changed")
                self._enqueue_job("library.scan_folder", {"folder_path": folder})

    def _enqueue_job(self, job_type: str, payload: dict):
        try:
            from app.workflows import workflow_runtime

            dedupe_key = None
            root = configured_root(Path(self._status.get("media_dir") or get_media_dir()).absolute())
            if job_type == "library.scan_folder":
                raw_path = safe_path(Path(payload["folder_path"]).absolute(), root)
                path_hash = hashlib.sha256(str(raw_path).encode("utf-8")).hexdigest()[:16]
                payload = {
                    "path_ref": operation_manifest_store.create_path_reference(root, raw_path)
                }
                dedupe_key = f"{job_type}:{path_hash}"
            elif job_type == "library.mark_path_missing":
                raw_path = safe_path(Path(payload["path"]).absolute(), root)
                path_hash = hashlib.sha256(str(raw_path).encode("utf-8")).hexdigest()[:16]
                payload = {
                    "path_ref": operation_manifest_store.create_path_reference(
                        root,
                        raw_path,
                        allow_missing=True,
                    )
                }
                dedupe_key = f"{job_type}:{path_hash}"
            elif job_type == "organizer.organize_root":
                payload = {"media_root_ref": operation_manifest_store.create_path_reference(root, root)}
                dedupe_key = f"{job_type}:{root_id(root)}"
            workflow_runtime.enqueue(job_type, payload, dedupe_key=dedupe_key)
        except Exception as exc:
            self._record_error(str(exc))

    def _watch_filter(self, change, path: str) -> bool:
        path_obj = Path(path)
        try:
            configured_root(path_obj.absolute())
        except (ValueError, OSError):
            return False
        if self._is_ignored_path(path_obj):
            return False
        if path_obj.exists() and path_obj.is_dir():
            return True
        if change == Change.deleted:
            return True
        return path_obj.suffix == "" or path_obj.suffix.lower() in self.tracked_extensions

    def _is_ignored_path(self, path: Path) -> bool:
        try:
            root = configured_root(path.absolute())
            return any(part.startswith(".") for part in path.absolute().relative_to(root).parts)
        except (ValueError, OSError):
            return True

    def _normalize_event_path(self, path: Path) -> Optional[str]:
        try:
            configured_root(path.absolute())
            return str(path.absolute())
        except (ValueError, OSError):
            return None

    def _has_recent_video(self, folder: str) -> bool:
        stable_seconds = get_media_file_stable_seconds()
        if stable_seconds <= 0:
            return False

        cutoff = time.time() - stable_seconds
        try:
            root = configured_root(Path(folder))
            for path in Path(folder).iterdir():
                if not is_link(path) and safe_path(path, root).is_file() and path.suffix.lower() in self.video_extensions:
                    if path.stat().st_mtime > cutoff:
                        return True
        except (OSError, ValueError):
            return False
        return False

    def _is_media_root(self, folder: Path) -> bool:
        try:
            return folder.resolve() == Path(self._status.get("media_dir") or get_media_dir()).resolve()
        except OSError:
            return False

    def _is_direct_media_root_child(self, path: Path) -> bool:
        try:
            return path.parent.resolve() == Path(self._status.get("media_dir") or get_media_dir()).resolve()
        except OSError:
            return False

    def _record_error(self, error: Optional[str]):
        with self._lock:
            self._status["last_error"] = error


class LibraryWatcher:
    """One independent observer per configured root; offline roots do not stop peers."""
    def __init__(self):
        self._children = []
        self._lock = threading.RLock()

    def start(self, media_dir=None):
        with self._lock:
            if self._children:
                return self.status()
            for root in ([media_dir] if media_dir else get_media_dirs()):
                child = _RootWatcher()
                child.start(root)
                self._children.append(child)
            return self.status()

    def stop(self):
        with self._lock:
            for child in self._children:
                child.stop()
            self._children = []
            return self.status()

    def status(self):
        with self._lock:
            statuses = [child.status() for child in self._children]
        roots = [{**directory_status(row["media_dir"]), "running": row["running"],
                  "last_error": "watch_failed" if row["last_error"] else None} for row in statuses]
        return {"running": any(row["running"] for row in statuses),
                "media_dir": get_media_dir(), "roots": roots,
                "pending": sum(row["pending"] for row in statuses),
                "last_event_at": max((row["last_event_at"] or 0 for row in statuses), default=0) or None,
                "last_error": "watch_failed" if any(row["last_error"] for row in statuses) else None}


library_watcher = LibraryWatcher()
