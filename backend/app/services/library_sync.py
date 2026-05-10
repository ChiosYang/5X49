from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

from app.services.library import library_manager
from app.services.scanner import NFOScanner
from app.services.settings import get_media_dir


class LibrarySyncService:
    """Coordinates folder scans, movie refreshes, and missing-file reconciliation."""

    def __init__(self):
        self._lock = Lock()
        self._status = {
            "state": "idle",
            "last_started_at": None,
            "last_finished_at": None,
            "last_error": None,
            "last_result": None,
        }

    def get_status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def reconcile(self, media_dir: Optional[str] = None) -> dict:
        """Scan the whole library and mark movies missing when they disappear."""
        target_dir = Path(media_dir or get_media_dir())
        started_at = datetime.now(timezone.utc).isoformat()
        self._set_status(state="running", last_started_at=started_at, last_error=None)

        try:
            if not target_dir.exists():
                raise FileNotFoundError(f"Directory not found: {target_dir}")

            scanner = NFOScanner(str(target_dir))
            movies = scanner.scan()
            added = library_manager.add_movies(movies)
            missing = library_manager.mark_missing_not_seen_since(started_at)

            result = {
                "scanned": len(movies),
                "added": added,
                "missing": missing,
                "media_dir": str(target_dir),
            }
            self._set_status(
                state="idle",
                last_finished_at=datetime.now(timezone.utc).isoformat(),
                last_result=result,
            )
            return result
        except Exception as exc:
            self._set_status(
                state="error",
                last_finished_at=datetime.now(timezone.utc).isoformat(),
                last_error=str(exc),
            )
            raise

    def refresh_movie(self, movie_id: str) -> dict:
        """Refresh one movie from its known folder while preserving its current ID."""
        movie = library_manager.get_movie(movie_id)
        if not movie:
            raise LookupError("Movie not found")

        folder_path = movie.get("folder_path")
        if not folder_path and movie.get("folder_name"):
            folder_path = str(Path(get_media_dir()) / movie["folder_name"])
        if not folder_path:
            raise ValueError("Movie does not have a folder path")

        updated_movie = self.scan_folder(folder_path, preserve_id=movie_id)
        if not updated_movie:
            raise FileNotFoundError("Movie folder or video file not found")

        return {
            "status": "success",
            "movie_id": movie_id,
            "updated": True,
            "movie": updated_movie,
        }

    def scan_folder(self, folder_path: str | Path, preserve_id: Optional[str] = None) -> Optional[dict]:
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            return None

        scanner = NFOScanner(str(folder.parent))
        movie_data = scanner.scan_folder(folder)
        if not movie_data:
            return None

        return library_manager.upsert_movie(movie_data, preserve_id=preserve_id)

    def mark_path_missing(self, path: str | Path) -> int:
        return library_manager.mark_path_missing(str(Path(path).resolve()))

    def _set_status(self, **updates):
        with self._lock:
            self._status.update(updates)


library_sync_service = LibrarySyncService()
