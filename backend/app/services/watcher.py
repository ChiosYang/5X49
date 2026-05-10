import threading
import time
from pathlib import Path
from typing import Optional

from app.services.library_sync import library_sync_service
from app.services.settings import get_media_dir, get_watch_debounce_seconds, get_watch_interval_seconds


class LibraryWatcher:
    """Polling-based media watcher.

    Filesystem event backends can be unreliable across Docker volumes and NAS
    mounts. This watcher favors eventual consistency: detect path changes,
    debounce noisy writes, and delegate actual database updates to sync service.
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
        self._pending_folders: dict[str, float] = {}
        self._status = {
            "running": False,
            "media_dir": None,
            "last_event_at": None,
            "last_error": None,
            "pending": 0,
        }

    def start(self, media_dir: Optional[str] = None) -> dict:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return {**self._status, "pending": len(self._pending_folders)}

            target_dir = Path(media_dir or get_media_dir())
            self._stop_event.clear()
            self._snapshot = self._build_snapshot(target_dir)
            self._status.update({
                "running": True,
                "media_dir": str(target_dir),
                "last_error": None,
                "pending": 0,
            })
            self._thread = threading.Thread(
                target=self._run,
                args=(target_dir,),
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

    def _run(self, media_dir: Path):
        while not self._stop_event.is_set():
            try:
                next_snapshot = self._build_snapshot(media_dir)
                self._handle_snapshot_changes(self._snapshot, next_snapshot)
                self._snapshot = next_snapshot
                self._flush_ready_folders()
            except Exception as exc:
                with self._lock:
                    self._status["last_error"] = str(exc)

            self._stop_event.wait(get_watch_interval_seconds())

        with self._lock:
            self._status["running"] = False

    def _build_snapshot(self, media_dir: Path) -> dict[str, tuple[float, int, bool]]:
        snapshot = {}
        if not media_dir.exists():
            return snapshot

        for path in media_dir.rglob("*"):
            try:
                if path.name.startswith("."):
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
            if Path(folder).exists():
                library_sync_service.scan_folder(folder)


library_watcher = LibraryWatcher()
