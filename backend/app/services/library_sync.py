from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

from app.services.event_bus import library_event_bus
from app.services.event_store import event_store
from app.services.library import library_manager
from app.services.scanner import NFOScanner
from app.services.settings import get_media_dirs
from sqlmodel import Session
from app import database
from app.canonical_models import Setting, canonical_utc_now_iso
from app.services.media_roots import configured_root, directory_status, root_id, explicitly_absent, safe_path


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
            current = dict(self._status)
        if current["last_started_at"] is None:
            try:
                with Session(database.engine) as session:
                    saved = session.get(Setting, "media_scan_status")
                    if saved and isinstance(saved.value, dict):
                        current = saved.value
                        if current.get("state") == "running":
                            current = {**current, "state": "interrupted", "last_error": "Scan interrupted by restart"}
            except Exception:
                pass
        return current

    def reconcile(self, media_dir: Optional[str] = None, *, ctx=None, roots: list[str] | None = None, enforce_config: bool = False) -> dict:
        """Persist positive observations; only complete coverage authorizes absence."""
        roots = roots if roots is not None else ([media_dir] if media_dir else get_media_dirs())
        enforce_config = enforce_config or media_dir is None
        started_at = datetime.now(timezone.utc).isoformat()
        self._set_status(state="running", last_started_at=started_at, last_error=None,
                         last_result=None)
        results = [{"id": root_id(root), "state": "not_scanned", "scanned": 0,
                    "added": 0, "errors": 0, "skipped_links": 0} for root in roots]
        total = {"scanned": 0, "added": 0, "missing": 0}
        try:
            self._progress(ctx, "discover", "Discovering configured media roots")
            cache = self._video_probe_cache()
            for root, row in zip(roots, results):
                self._progress(ctx, "inspect", "Inspecting media root")
                row["state"] = "running"
                accessibility = directory_status(root)["state"]
                if accessibility != "accessible":
                    row.update(state=accessibility, errors=1)
                    continue
                scanner = NFOScanner(root, video_probe_cache=cache)
                scanner.check_cancelled = lambda: self._check_scan(ctx, root, enforce_config)
                observed = scanner.scan_observed()
                self._progress(ctx, "resolve", "Resolving Film identities")
                self._check_scan(ctx, root, enforce_config)
                row.update(scanned=len(observed), errors=len(scanner.errors),
                           skipped_links=scanner.skipped_links)
                self._progress(ctx, "persist", "Persisting Canonical observations")
                row["added"] = library_manager.add_observations(
                    [item.film for item in observed],
                    structured_observations=[item.structured_metadata for item in observed],
                    check_observation=(lambda payload: self._validate_observation(payload, root, ctx)) if enforce_config else None)
                row["state"] = "partial" if scanner.errors else "complete"
                total["scanned"] += row["scanned"]
                total["added"] += row["added"]
            self._progress(ctx, "reconcile_missing", "Checking complete scan coverage")
            # Any incomplete root suppresses missing reconciliation for this run.
            if results and all(row["state"] == "complete" for row in results):
                for root in roots:
                    self._check_scan(ctx, root, enforce_config)
                total["missing"] = library_manager.mark_missing_not_seen_since(
                    started_at, roots=roots, check_cancelled=lambda: self._check_roots(ctx, roots, enforce_config))
            total["incomplete_roots"] = sum(row["state"] != "complete" for row in results)
            result = {**total, "roots": results,
                      "complete": bool(results) and all(row["state"] == "complete" for row in results)}
            if ctx is not None and hasattr(ctx, "progress"):
                ctx.progress(stage="finalize", message="Finalizing Library reconcile", counts=total)
            self._set_status(state="idle" if result["complete"] else "partial",
                last_finished_at=datetime.now(timezone.utc).isoformat(), last_result=result)
            library_event_bus.publish_library_changed("reconcile", result=result)
            event_store.safe_append("LibraryReconciled", "library", None, result)
            return result
        except Exception as exc:
            for row in results:
                if row["state"] == "running":
                    row["state"] = "interrupted"
            self._set_status(state="interrupted" if type(exc).__name__ == "JobCancelled" else "error",
                last_finished_at=datetime.now(timezone.utc).isoformat(),
                last_error=type(exc).__name__, last_result={**total, "roots": results, "complete": False})
            raise

    def _validate_observation(self, payload, root, ctx):
        self._check_scan(ctx, root, True)
        for key in ("media_path", "folder_path", "nfo_path"):
            if payload.get(key):
                configured_root(Path(payload[key]))

    def _check_scan(self, ctx, root, enforce_config):
        if ctx is not None and hasattr(ctx, "raise_if_cancelled"):
            ctx.raise_if_cancelled()
        if enforce_config and Path(root) != configured_root(Path(root)):
            raise ValueError("Media configuration changed during scan")
        safe_path(root, root)

    def _check_roots(self, ctx, roots, enforce_config):
        for root in roots:
            self._check_scan(ctx, root, enforce_config)

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
        configured_root(folder_path)
        updated = self.scan_folder(
            folder_path,
            media_root=str(configured_root(folder_path)),
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
        media_root: str | None = None,
    ) -> Optional[dict]:
        if include_resolution_stage:
            self._progress(ctx, "resolve_subject", "Resolving scan subject")
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            return None

        scanner = NFOScanner(media_root or str(folder.parent), video_probe_cache=self._video_probe_cache())
        self._progress(ctx, "inspect", "Inspecting media folder")
        locator = None
        if library_item_id:
            context = library_manager.get_item_operation_context(library_item_id)
            locator = (context.get("video") or {}).get("locator") if context else None
            if locator is None:
                return None
        observations = scanner.scan_folder_editions_observed(folder, video_path=locator)
        if not observations:
            return None

        self._progress(ctx, "persist", "Persisting media observations")
        upsert_result = None
        for observed_film in observations:
            if media_root:
                self._validate_observation(observed_film.film, media_root, ctx)
            result = library_manager.upsert_observation(
                observed_film.film,
                library_item_id=library_item_id,
                command_id=command_id,
                correlation_id=correlation_id,
                structured_metadata=observed_film.structured_metadata,
                preserve_scrape_state=True,
            )
            # The compatibility response is the first edition's Film; every
            # observation is persisted even if a later one needs relink review.
            if upsert_result is None:
                upsert_result = result
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
        root = configured_root(path)
        if not explicitly_absent(path, root):
            return 0
        # Directory events require descendant-aware, explicit absence checks too.
        return library_manager.mark_missing_not_seen_since(
            datetime.now(timezone.utc).isoformat(), roots=[str(root)], path_prefix=str(path))

    def _set_status(self, **updates):
        with self._lock:
            self._status.update(updates)
            snapshot = dict(self._status)
        try:
            with Session(database.engine) as session:
                row = session.get(Setting, "media_scan_status") or Setting(key="media_scan_status")
                row.value = snapshot
                row.updated_at = canonical_utc_now_iso()
                session.add(row)
                session.commit()
        except Exception:
            # A failed receipt must not alter scan identity or missing decisions.
            pass

    @staticmethod
    def _progress(ctx, stage: str, message: str, *, counts: dict | None = None) -> None:
        if ctx is not None and hasattr(ctx, "progress"):
            ctx.progress(stage=stage, message=message, **({"counts": counts} if counts is not None else {}))
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
