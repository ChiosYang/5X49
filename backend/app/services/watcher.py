import threading
import time
from pathlib import Path
from typing import Optional

from app.services.library_sync import library_sync_service
from app.services.settings import (
    get_auto_organize_root_videos,
    get_media_dir,
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


class LibraryWatcher:
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
                self._snapshot = self._build_snapshot(target_dir)
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
                    media_dir,
                    watch_filter=self._watch_filter,
                    stop_event=self._stop_event,
                    debounce=1000,
                    rust_timeout=1000,
                    yield_on_timeout=True,
                    recursive=True,
                ):
                    if self._stop_event.is_set():
                        break

                    for change, path in changes:
                        self._handle_event_change(change, path)
                    self._flush_ready_folders()
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
        if not media_dir.exists():
            return snapshot

        for path in media_dir.rglob("*"):
            try:
                if self._is_ignored_path(path):
                    continue
                if path.is_dir():
                    stat = path.stat()
                    snapshot[str(path.resolve())] = (stat.st_mtime, 0, True)
                    continue

                if path.suffix.lower() not in self.tracked_extensions:
                    continue
                stat = path.stat()
                snapshot[str(path.resolve())] = (stat.st_mtime, stat.st_size, False)
            except OSError:
                continue

        return snapshot

    def _build_path_type_index(self, media_dir: Path) -> dict[str, bool]:
        path_types = {}
        if not media_dir.exists():
            return path_types

        for path in media_dir.rglob("*"):
            try:
                if self._is_ignored_path(path):
                    continue
                if path.is_dir():
                    path_types[str(path.resolve())] = True
                elif path.suffix.lower() in self.tracked_extensions:
                    path_types[str(path.resolve())] = False
            except OSError:
                continue

        return path_types

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
                library_sync_service.mark_path_missing(path)
            elif Path(path).suffix.lower() in self.video_extensions:
                library_sync_service.mark_path_missing(path)
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
                library_sync_service.mark_path_missing(normalized)
            elif path_obj.suffix.lower() in self.video_extensions:
                library_sync_service.mark_path_missing(normalized)
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
            if folder_path.exists():
                if self._has_recent_video(folder):
                    self._queue_folder(folder)
                    continue
                if self._is_media_root(folder_path):
                    if get_auto_organize_root_videos():
                        try:
                            from app.services.metadata.organizer import root_video_organizer

                            root_video_organizer.organize_root(str(folder_path))
                        except Exception as exc:
                            self._record_error(str(exc))
                    continue
                library_sync_service.scan_folder(folder)

    def _watch_filter(self, change, path: str) -> bool:
        path_obj = Path(path)
        if self._is_ignored_path(path_obj):
            return False
        if path_obj.exists() and path_obj.is_dir():
            return True
        if change == Change.deleted:
            return True
        return path_obj.suffix == "" or path_obj.suffix.lower() in self.tracked_extensions

    def _is_ignored_path(self, path: Path) -> bool:
        return any(part.startswith(".") for part in path.parts)

    def _normalize_event_path(self, path: Path) -> Optional[str]:
        if path.exists():
            try:
                return str(path.resolve())
            except OSError:
                return None
        return str(path.absolute())

    def _has_recent_video(self, folder: str) -> bool:
        stable_seconds = get_media_file_stable_seconds()
        if stable_seconds <= 0:
            return False

        cutoff = time.time() - stable_seconds
        try:
            for path in Path(folder).iterdir():
                if path.is_file() and path.suffix.lower() in self.video_extensions:
                    if path.stat().st_mtime > cutoff:
                        return True
        except OSError:
            return False
        return False

    def _is_media_root(self, folder: Path) -> bool:
        try:
            return folder.resolve() == Path(get_media_dir()).resolve()
        except OSError:
            return False

    def _record_error(self, error: Optional[str]):
        with self._lock:
            self._status["last_error"] = error


library_watcher = LibraryWatcher()
