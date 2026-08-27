from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

from app.services.event_bus import library_event_bus
from app.services.event_store import event_store
from app.services.library import library_manager
from app.services.scanner import NFOScanner
from app.services.settings import get_media_dir


class LibrarySyncService:
    """Coordinates Film/LibraryItem scans and missing-file reconciliation."""

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

    def reconcile(self, media_dir: Optional[str] = None, *, ctx=None) -> dict:
        """Scan the whole library and mark missing local editions."""
        target_dir = Path(media_dir or get_media_dir())
        started_at = datetime.now(timezone.utc).isoformat()
        self._set_status(state="running", last_started_at=started_at, last_error=None)

        try:
            self._progress(ctx, "discover", "Discovering media observations")
            if not target_dir.exists():
                raise FileNotFoundError(f"Directory not found: {target_dir}")

            scanner = NFOScanner(str(target_dir), video_probe_cache=self._video_probe_cache())
            observed_films = scanner.scan_observed()
            self._progress(ctx, "inspect", "Inspecting discovered media")
            observations = [item.film for item in observed_films]
            self._progress(ctx, "resolve", "Resolving Film identities")
            self._progress(ctx, "persist", "Persisting Canonical observations")
            added = library_manager.add_observations(
                observations,
                structured_observations=[item.structured_metadata for item in observed_films],
            )
            self._progress(ctx, "reconcile_missing", "Reconciling missing editions")
            missing = library_manager.mark_missing_not_seen_since(started_at)

            result = {
                "scanned": len(observations),
                "added": added,
                "missing": missing,
            }
            self._progress(ctx, "finalize", "Finalizing Library reconcile")
            self._set_status(
                state="idle",
                last_finished_at=datetime.now(timezone.utc).isoformat(),
                last_result=result,
            )
            library_event_bus.publish_library_changed("reconcile", result=result)
            event_store.safe_append(
                "LibraryReconciled",
                "library",
                None,
                result,
            )
            return result
        except Exception as exc:
            self._set_status(
                state="error",
                last_finished_at=datetime.now(timezone.utc).isoformat(),
                last_error=str(exc),
            )
            raise

    def refresh_item(self, library_item_id: str, *, ctx=None) -> dict:
        """Refresh one local edition from its current video locator."""
        self._progress(ctx, "resolve_subject", "Resolving Library edition")
        item = library_manager.get_item_operation_context(library_item_id)
        if not item:
            raise LookupError("Library item not found")

        video = item.get("video") or {}
        video_path = video.get("locator")
        folder_path = str(Path(video_path).parent) if video_path else None
        if not folder_path:
            raise ValueError("Library item does not have a local video locator")

        self._progress(ctx, "inspect", "Inspecting Library edition")
        updated = self.scan_folder(
            folder_path,
            library_item_id=library_item_id,
            ctx=ctx,
            include_resolution_stage=False,
        )
        if not updated:
            raise FileNotFoundError("Library item folder or video file not found")
        if updated.get("status") == "pending_relink":
            return updated

        return {
            "status": "success",
            "library_item_id": library_item_id,
            "updated": True,
            "film": updated,
        }

    def scan_folder(
        self,
        folder_path: str | Path,
        library_item_id: Optional[str] = None,
        *,
        command_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        ctx=None,
        include_resolution_stage: bool = True,
    ) -> Optional[dict]:
        if include_resolution_stage:
            self._progress(ctx, "resolve_subject", "Resolving scan subject")
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            return None

        scanner = NFOScanner(str(folder.parent), video_probe_cache=self._video_probe_cache())
        self._progress(ctx, "inspect", "Inspecting media folder")
        observed_film = scanner.scan_folder_observed(folder)
        if not observed_film:
            return None
        film_data = observed_film.film

        self._progress(ctx, "persist", "Persisting media observation")
        upsert_result = library_manager.upsert_observation(
            film_data,
            library_item_id=library_item_id,
            command_id=command_id,
            correlation_id=correlation_id,
            structured_metadata=observed_film.structured_metadata,
        )
        if upsert_result and upsert_result.get("status") == "pending_relink":
            return {
                "status": "pending_relink",
                "pending_relink_job_id": upsert_result["job_id"],
            }
        film = library_manager.get_film(upsert_result["film_id"]) if upsert_result else None
        if film:
            library_event_bus.publish_library_changed(
                "folder_scanned",
                film_id=film.get("id"),
                library_item_id=upsert_result.get("library_item_id"),
            )
        self._progress(ctx, "finalize", "Finalizing media refresh")
        return film

    def mark_path_missing(self, path: str | Path) -> int:
        normalized_path = str(Path(path).resolve())
        updated = library_manager.mark_path_missing(normalized_path)
        if updated:
            library_event_bus.publish_library_changed(
                "path_missing",
                updated=updated,
            )
        return updated

    def _set_status(self, **updates):
        with self._lock:
            self._status.update(updates)

    @staticmethod
    def _progress(ctx, stage: str, message: str) -> None:
        if ctx is not None and hasattr(ctx, "progress"):
            ctx.progress(stage=stage, message=message)
        if ctx is not None and hasattr(ctx, "raise_if_cancelled"):
            ctx.raise_if_cancelled()

    def _video_probe_cache(self) -> dict[str, dict]:
        cache: dict[str, dict] = {}
        for film in library_manager.list_operation_contexts():
            locator = film.get("media_path")
            if locator:
                cache[locator] = {
                    "media_path": locator,
                    "file_size": film.get("file_size"),
                    "file_mtime": film.get("file_mtime"),
                    "video_width": film.get("video_width"),
                    "video_height": film.get("video_height"),
                    "video_codec": film.get("video_codec"),
                    "video_bitrate": film.get("video_bitrate"),
                    "video_duration": film.get("video_duration"),
                    "video_fps": film.get("video_fps"),
                    "video_dynamic_range": film.get("video_dynamic_range"),
                    "video_bit_depth": film.get("video_bit_depth"),
                    "audio_tracks": film.get("audio_tracks"),
                }
        return cache


library_sync_service = LibrarySyncService()
