import os
import shutil
from pathlib import Path
from typing import Optional
from uuid import uuid4

from sqlmodel import Session

from app.database import engine
from app.models import EventRecord, Movie
from app.services.event_store import event_store
from app.services.projections.movie_projection import movie_projector
from app.services.projections.movie_timeline import movie_timeline_dry_run
from app.services.settings import get_media_dir


RESTORE_FILE_TYPES = {"poster", "backdrop", "nfo"}


class TimelineRestoreBlocked(ValueError):
    def __init__(self, report: dict):
        super().__init__("Timeline restore is not fully safe")
        self.report = report


class MovieTimelineRestore:
    """Execute historical movie restore through compensation events."""

    def run(
        self,
        *,
        movie_id: str,
        before_event_id: Optional[str] = None,
        at: Optional[str] = None,
        restore_fields: Optional[list[str]] = None,
        restore_files: Optional[list[str]] = None,
        allow_partial: bool = False,
    ) -> dict:
        self._validate_selector(before_event_id=before_event_id, at=at)
        preview = movie_timeline_dry_run.restore_preview(
            movie_id=movie_id,
            before_event_id=before_event_id,
            at=at,
        )
        requested_fields = self._requested_fields(preview, restore_fields)
        requested_files = self._requested_files(preview, restore_files)
        actions_requested = {
            "restore_fields": requested_fields,
            "restore_files": requested_files,
            "allow_partial": allow_partial,
        }
        restore_command_id = f"cmd_timeline_restore_{uuid4().hex}"
        restore_correlation_id = f"corr_timeline_restore_{uuid4().hex}"

        field_plan = self._field_plan(movie_id, preview, requested_fields)
        file_plan = self._file_plan(preview, requested_files)
        conflicts = [*field_plan["conflicts"]]
        skipped = [*field_plan["skipped"], *file_plan["skipped"]]
        preflight_report = self._report(
            movie_id=movie_id,
            restore_command_id=restore_command_id,
            restore_correlation_id=restore_correlation_id,
            actions_requested=actions_requested,
            restored=[],
            skipped=skipped,
            conflicts=conflicts,
            dry_run=preview,
        )

        if (conflicts or skipped) and not allow_partial:
            raise TimelineRestoreBlocked(preflight_report)

        restored = []
        if field_plan["fields"]:
            restored.append(self._restore_fields(
                movie_id=movie_id,
                preview=preview,
                restore_command_id=restore_command_id,
                restore_correlation_id=restore_correlation_id,
                fields=field_plan["fields"],
                conflicts=conflicts,
                skipped_fields=field_plan["skipped"],
            ))
        for file_item in file_plan["files"]:
            restored.append(self._restore_file(
                file_item,
                restore_command_id=restore_command_id,
                restore_correlation_id=restore_correlation_id,
            ))

        return self._report(
            movie_id=movie_id,
            restore_command_id=restore_command_id if restored else None,
            restore_correlation_id=restore_correlation_id if restored else None,
            actions_requested=actions_requested,
            restored=restored,
            skipped=skipped,
            conflicts=conflicts,
            dry_run=preview,
        )

    def _validate_selector(self, *, before_event_id: Optional[str], at: Optional[str]):
        if bool(before_event_id) == bool(at):
            raise ValueError("Exactly one of before_event_id or at is required")

    def _requested_fields(self, preview: dict, restore_fields: Optional[list[str]]) -> list[str]:
        if restore_fields is None:
            return [
                item["field"]
                for item in preview.get("field_restore", [])
                if isinstance(item, dict) and isinstance(item.get("field"), str)
            ]
        return [field for field in restore_fields if isinstance(field, str)]

    def _requested_files(self, preview: dict, restore_files: Optional[list[str]]) -> list[str]:
        if restore_files is None:
            return list(dict.fromkeys(
                item.get("file_type")
                for item in preview.get("restorable_files", [])
                if item.get("file_type") in RESTORE_FILE_TYPES
            ))
        unknown = sorted({item for item in restore_files if item not in RESTORE_FILE_TYPES})
        if unknown:
            raise ValueError(f"Unsupported restore_files: {', '.join(unknown)}")
        return list(dict.fromkeys(restore_files))

    def _field_plan(self, movie_id: str, preview: dict, requested_fields: list[str]) -> dict:
        if not requested_fields:
            return {"fields": [], "conflicts": [], "skipped": []}
        target_state = preview.get("target_state")
        if not isinstance(target_state, dict):
            return {
                "fields": [],
                "conflicts": [],
                "skipped": [
                    {
                        "action": "restore_fields",
                        "field": field,
                        "reason": "Target state could not be rebuilt",
                    }
                    for field in requested_fields
                ],
            }

        diff_by_field = {
            item.get("field"): item
            for item in preview.get("field_restore", [])
            if isinstance(item, dict) and isinstance(item.get("field"), str)
        }
        with Session(engine) as session:
            movie = session.get(Movie, movie_id)
            if not movie:
                raise LookupError("Movie not found")
            fields = []
            conflicts = []
            skipped = []
            for field in requested_fields:
                diff = diff_by_field.get(field)
                if not diff:
                    skipped.append({
                        "action": "restore_field",
                        "field": field,
                        "reason": "Field is not available in restore preview",
                    })
                    continue
                if field not in Movie.model_fields:
                    skipped.append({
                        "action": "restore_field",
                        "field": field,
                        "reason": "Field is not restorable on Movie",
                    })
                    continue
                current_value = getattr(movie, field, None)
                expected_current = diff.get("current")
                restored_value = diff.get("target")
                if current_value != expected_current:
                    conflicts.append({
                        "action": "restore_field",
                        "field": field,
                        "current": current_value,
                        "expected_current": expected_current,
                        "restored": restored_value,
                    })
                    continue
                fields.append({
                    "field": field,
                    "before": current_value,
                    "restored": restored_value,
                })
        return {"fields": fields, "conflicts": conflicts, "skipped": skipped}

    def _file_plan(self, preview: dict, requested_files: list[str]) -> dict:
        if not requested_files:
            return {"files": [], "skipped": []}
        restorable = preview.get("restorable_files") or []
        files = []
        skipped = []
        for file_type in requested_files:
            item = self._first_file(restorable, file_type)
            if not item:
                skipped.append({
                    "action": f"restore_{file_type}",
                    "file_type": file_type,
                    "reason": "No restorable backup is available in preview",
                })
                continue
            try:
                files.append(self._checked_file_item(item, preview["movie_id"]))
            except ValueError as exc:
                skipped.append({
                    "action": f"restore_{file_type}",
                    "file_type": file_type,
                    "event_id": item.get("event_id"),
                    "reason": str(exc),
                })
        return {"files": files, "skipped": skipped}

    def _first_file(self, items: list[dict], file_type: str) -> Optional[dict]:
        for item in items:
            if item.get("file_type") == file_type:
                return item
        return None

    def _checked_file_item(self, item: dict, movie_id: str) -> dict:
        file_type = item.get("file_type")
        backup = self._safe_path(item.get("backup_path"), "backup_path")
        destination = self._safe_path(item.get("path"), "path")
        if not backup.exists():
            raise ValueError("Backup file is missing")
        if not destination.parent.exists():
            raise ValueError("Destination parent directory is missing")
        event_id = item.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("Restorable file is missing event_id")
        event_type = item.get("type")
        if file_type in {"poster", "backdrop"} and event_type != "ArtworkDownloaded":
            raise ValueError("Artwork restore requires an ArtworkDownloaded event")
        if file_type == "nfo" and event_type != "NfoWritten":
            raise ValueError("NFO restore requires an NfoWritten event")
        return {**item, "movie_id": movie_id, "backup": backup, "destination": destination}

    def _restore_fields(
        self,
        *,
        movie_id: str,
        preview: dict,
        restore_command_id: str,
        restore_correlation_id: str,
        fields: list[dict],
        conflicts: list[dict],
        skipped_fields: list[dict],
    ) -> dict:
        with Session(engine) as session:
            movie = session.get(Movie, movie_id)
            if not movie:
                raise LookupError("Movie not found")
            before = movie.model_dump()
            event = EventRecord(
                aggregate_type="movie",
                aggregate_id=movie_id,
                type="MovieStateRestored",
                command_id=restore_command_id,
                correlation_id=restore_correlation_id,
                causation_id=(preview.get("target") or {}).get("before_event_id"),
                payload={
                    "action": "restore_timeline_fields",
                    "movie_id": movie_id,
                    "target": preview.get("target"),
                    "restored_fields": fields,
                    "conflicts": conflicts,
                    "skipped_fields": skipped_fields,
                    "before": before,
                    "preview_status": preview.get("status"),
                },
                context={"operation": "restore_timeline"},
            )
            session.add(event)
            session.flush()
            projected = movie_projector.apply(event, session)
            event.payload = {
                **(event.payload or {}),
                "after": projected or movie.model_dump(),
            }
            session.add(event)
            session.commit()
            session.refresh(event)
        return {
            "action": "restore_fields",
            "event_id": event.id,
            "movie_id": movie_id,
            "restored_fields": len(fields),
            "conflicts": len(conflicts),
            "skipped_fields": len(skipped_fields),
        }

    def _restore_file(
        self,
        item: dict,
        *,
        restore_command_id: str,
        restore_correlation_id: str,
    ) -> dict:
        backup: Path = item["backup"]
        destination: Path = item["destination"]
        before = self._file_snapshot(destination)
        shutil.copy2(backup, destination)
        after = self._file_snapshot(destination)
        file_type = item.get("file_type")
        event_type = "NfoRestored" if file_type == "nfo" else "ArtworkRestored"
        payload = {
            "action": f"restore_{file_type}",
            "movie_id": item.get("movie_id"),
            "restored_event_id": item["event_id"],
            "backup_path": str(backup),
            "before": before,
            "after": after,
        }
        if file_type == "nfo":
            payload["path"] = str(destination)
        else:
            payload["asset_type"] = file_type
            payload["destination"] = str(destination)
        restore_event = event_store.append(
            event_type,
            "movie",
            item.get("movie_id"),
            payload,
            command_id=restore_command_id,
            correlation_id=restore_correlation_id,
            causation_id=item["event_id"],
            context={"operation": "restore_timeline"},
        )
        return {
            "action": f"restore_{file_type}",
            "event_id": restore_event["id"],
            "restored_event_id": item["event_id"],
            "path": str(destination),
            "backup_path": str(backup),
        }

    def _report(
        self,
        *,
        movie_id: str,
        restore_command_id: Optional[str],
        restore_correlation_id: Optional[str],
        actions_requested: dict,
        restored: list[dict],
        skipped: list[dict],
        conflicts: list[dict],
        dry_run: dict,
    ) -> dict:
        if restored and (skipped or conflicts):
            status = "partial"
        elif restored:
            status = "restored"
        else:
            status = "skipped"
        return {
            "status": status,
            "movie_id": movie_id,
            "restore_command_id": restore_command_id,
            "restore_correlation_id": restore_correlation_id,
            "target": dry_run.get("target"),
            "actions_requested": actions_requested,
            "restored": restored,
            "skipped": skipped,
            "conflicts": conflicts,
            "dry_run": dry_run,
        }

    def _safe_path(self, value: object, field: str) -> Path:
        if not isinstance(value, str) or not value:
            raise ValueError(f"Missing path field: {field}")
        candidate = Path(value)
        if not candidate.is_absolute():
            raise ValueError(f"Path field must be absolute: {field}")
        media_roots = self._media_roots()
        if not media_roots:
            raise ValueError("MEDIA_DIR is not configured")
        resolved = candidate.resolve(strict=False)
        for media_root in media_roots:
            try:
                resolved.relative_to(media_root)
                return resolved
            except ValueError:
                continue
        raise ValueError(f"Path is outside MEDIA_DIR: {field}")

    def _media_roots(self) -> list[Path]:
        roots = []
        for value in (get_media_dir(), os.getenv("MEDIA_DIR")):
            if not value:
                continue
            root = Path(value).resolve(strict=False)
            if root not in roots:
                roots.append(root)
        return roots

    def _file_snapshot(self, path: Path) -> dict:
        try:
            stat = path.stat()
        except OSError:
            return {"path": str(path), "exists": False}
        return {
            "path": str(path),
            "filename": path.name,
            "exists": True,
            "size": stat.st_size,
            "mtime": stat.st_mtime,
        }


movie_timeline_restore = MovieTimelineRestore()
