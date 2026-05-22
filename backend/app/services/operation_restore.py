import os
import shutil
from pathlib import Path
from typing import Optional
from uuid import uuid4

from sqlmodel import Session, select

from app.database import engine
from app.models import EventRecord, Movie
from app.services.event_store import event_store
from app.services.operation_dry_run import operation_dry_run
from app.services.settings import get_media_dir


RESTORE_ACTIONS = {
    "restore_artwork_selection",
    "restore_metadata",
    "restore_nfo",
    "restore_poster",
    "reverse_root_move",
}


class OperationRestore:
    """Execute narrowly scoped compensation actions for one operation."""

    def run(
        self,
        *,
        correlation_id: Optional[str] = None,
        command_id: Optional[str] = None,
        actions: Optional[list[str]] = None,
        limit: int = 500,
    ) -> dict:
        if not correlation_id and not command_id:
            raise ValueError("correlation_id or command_id is required")

        requested_actions = actions or sorted(RESTORE_ACTIONS)
        unknown_actions = [action for action in requested_actions if action not in RESTORE_ACTIONS]
        if unknown_actions:
            raise ValueError(f"Unsupported restore actions: {', '.join(unknown_actions)}")

        dry_run = operation_dry_run.run(correlation_id=correlation_id, command_id=command_id, limit=limit)
        events = self._events(correlation_id=correlation_id, command_id=command_id, limit=limit)
        restore_command_id = f"cmd_restore_{uuid4().hex}"
        restore_correlation_id = f"corr_restore_{uuid4().hex}"
        restored = []
        skipped = []

        for action in requested_actions:
            try:
                result = self._run_action(
                    action,
                    events,
                    dry_run,
                    restore_command_id=restore_command_id,
                    restore_correlation_id=restore_correlation_id,
                )
            except ValueError as exc:
                skipped.append({"action": action, "reason": str(exc)})
                continue
            if result:
                restored.append(result)
            else:
                skipped.append({"action": action, "reason": "No applicable event was found"})

        return {
            "status": "restored" if restored else "skipped",
            "operation_id": correlation_id or command_id,
            "correlation_id": correlation_id,
            "command_id": command_id,
            "restore_command_id": restore_command_id if restored else None,
            "restore_correlation_id": restore_correlation_id if restored else None,
            "actions_requested": requested_actions,
            "restored": restored,
            "skipped": skipped,
            "dry_run": dry_run,
        }

    def _run_action(
        self,
        action: str,
        events: list[EventRecord],
        dry_run: dict,
        *,
        restore_command_id: str,
        restore_correlation_id: str,
    ) -> Optional[dict]:
        if action == "restore_poster":
            if not dry_run.get("can_restore_poster"):
                raise ValueError("Poster restore is not safe according to dry-run")
            return self._restore_artwork(
                events,
                asset_type="poster",
                restore_command_id=restore_command_id,
                restore_correlation_id=restore_correlation_id,
            )
        if action == "restore_nfo":
            return self._restore_nfo(
                events,
                restore_command_id=restore_command_id,
                restore_correlation_id=restore_correlation_id,
            )
        if action == "restore_metadata":
            return self._restore_movie_fields(
                events,
                source_event_type="MetadataMatched",
                restore_event_type="MetadataRestored",
                action="restore_metadata",
                restore_command_id=restore_command_id,
                restore_correlation_id=restore_correlation_id,
            )
        if action == "restore_artwork_selection":
            return self._restore_movie_fields(
                events,
                source_event_type="ArtworkSelected",
                restore_event_type="ArtworkSelectionRestored",
                action="restore_artwork_selection",
                restore_command_id=restore_command_id,
                restore_correlation_id=restore_correlation_id,
            )
        if action == "reverse_root_move":
            if not dry_run.get("can_reverse_root_move"):
                raise ValueError("Root move reverse is not safe according to dry-run")
            return self._reverse_root_move(
                events,
                restore_command_id=restore_command_id,
                restore_correlation_id=restore_correlation_id,
            )
        raise ValueError(f"Unsupported restore action: {action}")

    def _restore_artwork(
        self,
        events: list[EventRecord],
        *,
        asset_type: str,
        restore_command_id: str,
        restore_correlation_id: str,
    ) -> Optional[dict]:
        event = self._latest_event(
            events,
            "ArtworkDownloaded",
            lambda item: (item.payload or {}).get("asset_type") == asset_type,
        )
        if not event:
            return None
        if self._already_restored("ArtworkRestored", event.id):
            raise ValueError("Artwork was already restored for this event")
        payload = event.payload or {}
        backup = self._safe_path(payload.get("backup_path"), "backup_path")
        destination = self._safe_path(payload.get("destination"), "destination")
        if not backup.exists():
            raise ValueError("Artwork backup file is missing")
        if not destination.parent.exists():
            raise ValueError("Artwork destination parent directory is missing")

        before = self._file_snapshot(destination)
        shutil.copy2(backup, destination)
        after = self._file_snapshot(destination)
        restore_event = event_store.append(
            "ArtworkRestored",
            event.aggregate_type,
            event.aggregate_id,
            {
                "action": "restore_poster",
                "asset_type": asset_type,
                "restored_event_id": event.id,
                "backup_path": str(backup),
                "destination": str(destination),
                "before": before,
                "after": after,
            },
            command_id=restore_command_id,
            correlation_id=restore_correlation_id,
            causation_id=event.id,
            context={"operation": "restore_operation"},
        )
        return {
            "action": "restore_poster",
            "event_id": restore_event["id"],
            "restored_event_id": event.id,
            "path": str(destination),
            "backup_path": str(backup),
        }

    def _restore_nfo(
        self,
        events: list[EventRecord],
        *,
        restore_command_id: str,
        restore_correlation_id: str,
    ) -> Optional[dict]:
        event = self._latest_event(events, "NfoWritten", lambda item: bool((item.payload or {}).get("backup_path")))
        if not event:
            return None
        if self._already_restored("NfoRestored", event.id):
            raise ValueError("NFO was already restored for this event")
        payload = event.payload or {}
        backup = self._safe_path(payload.get("backup_path"), "backup_path")
        destination = self._safe_path(payload.get("path"), "path")
        if not backup.exists():
            raise ValueError("NFO backup file is missing")
        if not destination.parent.exists():
            raise ValueError("NFO destination parent directory is missing")

        before = self._file_snapshot(destination)
        shutil.copy2(backup, destination)
        after = self._file_snapshot(destination)
        restore_event = event_store.append(
            "NfoRestored",
            event.aggregate_type,
            event.aggregate_id,
            {
                "action": "restore_nfo",
                "restored_event_id": event.id,
                "backup_path": str(backup),
                "path": str(destination),
                "before": before,
                "after": after,
            },
            command_id=restore_command_id,
            correlation_id=restore_correlation_id,
            causation_id=event.id,
            context={"operation": "restore_operation"},
        )
        return {
            "action": "restore_nfo",
            "event_id": restore_event["id"],
            "restored_event_id": event.id,
            "path": str(destination),
            "backup_path": str(backup),
        }

    def _restore_movie_fields(
        self,
        events: list[EventRecord],
        *,
        source_event_type: str,
        restore_event_type: str,
        action: str,
        restore_command_id: str,
        restore_correlation_id: str,
    ) -> Optional[dict]:
        event = self._latest_event(events, source_event_type)
        if not event:
            return None
        if not event.aggregate_id:
            raise ValueError(f"{source_event_type} is missing movie aggregate ID")
        if self._already_restored(restore_event_type, event.id):
            raise ValueError(f"{source_event_type} was already restored")

        payload = event.payload or {}
        previous = payload.get("previous")
        current = payload.get("current")
        changed_fields = payload.get("changed_fields")
        if not isinstance(previous, dict) or not isinstance(current, dict) or not isinstance(changed_fields, list):
            raise ValueError(f"{source_event_type} is missing field recovery payload")

        with Session(engine) as session:
            movie = session.get(Movie, event.aggregate_id)
            if not movie:
                raise ValueError("Movie not found for field restore")
            movie_before = movie.model_dump()
            restored_fields = []
            conflicts = []
            missing_payload = []

            for field in changed_fields:
                if not isinstance(field, str):
                    continue
                if field not in Movie.model_fields:
                    missing_payload.append({"field": field, "reason": "field is not restorable on Movie"})
                    continue
                if field not in previous:
                    missing_payload.append({"field": field, "reason": "previous value is missing"})
                    continue
                if field not in current:
                    missing_payload.append({"field": field, "reason": "current value is missing"})
                    continue
                current_value = getattr(movie, field, None)
                expected_current = current[field]
                restored_value = previous[field]
                if current_value != expected_current:
                    conflicts.append({
                        "field": field,
                        "current": current_value,
                        "expected_current": expected_current,
                        "restored": restored_value,
                    })
                    continue
                setattr(movie, field, restored_value)
                restored_fields.append({
                    "field": field,
                    "before": current_value,
                    "restored": restored_value,
                })

            if not restored_fields:
                raise ValueError(f"No {source_event_type} fields can be safely restored")

            session.add(movie)
            restore_event = EventRecord(
                aggregate_type="movie",
                aggregate_id=event.aggregate_id,
                type=restore_event_type,
                command_id=restore_command_id,
                correlation_id=restore_correlation_id,
                causation_id=event.id,
                payload={
                    "action": action,
                    "movie_id": event.aggregate_id,
                    "restored_event_id": event.id,
                    "restored_fields": restored_fields,
                    "conflicts": conflicts,
                    "missing_payload": missing_payload,
                    "before": movie_before,
                    "after": movie.model_dump(),
                },
                context={"operation": "restore_operation"},
            )
            session.add(restore_event)
            session.commit()
            session.refresh(restore_event)

        return {
            "action": action,
            "event_id": restore_event.id,
            "restored_event_id": event.id,
            "movie_id": event.aggregate_id,
            "restored_fields": len(restored_fields),
            "conflicts": len(conflicts),
            "missing_payload": len(missing_payload),
        }

    def _reverse_root_move(
        self,
        events: list[EventRecord],
        *,
        restore_command_id: str,
        restore_correlation_id: str,
    ) -> Optional[dict]:
        event = self._latest_event(events, "RootVideoMoved")
        if not event:
            return None
        if self._already_restored("RootVideoMoveReversed", event.id):
            raise ValueError("Root video move was already reversed for this event")
        payload = event.payload or {}
        source = self._safe_path(payload.get("source_path"), "source_path")
        target = self._safe_path(payload.get("target_path"), "target_path")
        sidecars = self._root_sidecars(payload.get("sidecars"))
        self._validate_reverse_move(source, target, sidecars)

        before = {
            "source": self._file_snapshot(source),
            "target": self._file_snapshot(target),
            "sidecars": [
                {
                    "source": self._file_snapshot(item["source"]),
                    "target": self._file_snapshot(item["target"]),
                }
                for item in sidecars
            ],
        }
        shutil.move(str(target), str(source))
        for item in sidecars:
            shutil.move(str(item["target"]), str(item["source"]))
        after = {
            "source": self._file_snapshot(source),
            "target": self._file_snapshot(target),
            "sidecars": [
                {
                    "source": self._file_snapshot(item["source"]),
                    "target": self._file_snapshot(item["target"]),
                }
                for item in sidecars
            ],
        }
        restore_event = event_store.append(
            "RootVideoMoveReversed",
            "file",
            str(source),
            {
                "action": "reverse_root_move",
                "restored_event_id": event.id,
                "source_path": str(source),
                "target_path": str(target),
                "sidecars": [
                    {"source_path": str(item["source"]), "target_path": str(item["target"])}
                    for item in sidecars
                ],
                "before": before,
                "after": after,
            },
            command_id=restore_command_id,
            correlation_id=restore_correlation_id,
            causation_id=event.id,
            context={"operation": "restore_operation"},
        )
        result = {
            "action": "reverse_root_move",
            "event_id": restore_event["id"],
            "restored_event_id": event.id,
            "source_path": str(source),
            "target_path": str(target),
            "sidecars_reversed": len(sidecars),
        }
        reverted = self._append_root_organization_reverted(
            events,
            restored_event_id=event.id,
            source=source,
            target=target,
            restore_command_id=restore_command_id,
            restore_correlation_id=restore_correlation_id,
        )
        if reverted:
            result["organization_reverted_event_id"] = reverted["id"]
            result["movie_id"] = reverted.get("aggregate_id")
        return result

    def _append_root_organization_reverted(
        self,
        events: list[EventRecord],
        *,
        restored_event_id: str,
        source: Path,
        target: Path,
        restore_command_id: str,
        restore_correlation_id: str,
    ) -> Optional[dict]:
        organized = self._latest_event(events, "RootVideoOrganized")
        if not organized or not organized.aggregate_id:
            return None
        discovered = self._latest_event(
            events,
            "MovieDiscovered",
            lambda item: item.aggregate_id == organized.aggregate_id,
        )
        if not discovered:
            return None
        if self._event_with_payload_value_exists("RootVideoOrganizationReverted", "organized_event_id", organized.id):
            return None
        event, projected = event_store.append_and_project(
            "RootVideoOrganizationReverted",
            "movie",
            organized.aggregate_id,
            {
                "movie_id": organized.aggregate_id,
                "restored_event_id": restored_event_id,
                "organized_event_id": organized.id,
                "discovered_event_id": discovered.id,
                "source_path": str(source),
                "target_path": str(target),
                "library_status": "reverted",
            },
            command_id=restore_command_id,
            correlation_id=restore_correlation_id,
            causation_id=restored_event_id,
            context={"operation": "restore_operation"},
        )
        return {**event, "projected": projected}

    def _events(
        self,
        *,
        correlation_id: Optional[str],
        command_id: Optional[str],
        limit: int,
    ) -> list[EventRecord]:
        statement = select(EventRecord)
        if correlation_id:
            statement = statement.where(EventRecord.correlation_id == correlation_id)
        else:
            statement = statement.where(EventRecord.command_id == command_id)
        statement = statement.order_by(EventRecord.occurred_at, EventRecord.id).limit(max(1, min(limit, 500)))
        with Session(engine) as session:
            return list(session.exec(statement).all())

    def _already_restored(self, restore_type: str, restored_event_id: str) -> bool:
        return self._event_with_payload_value_exists(restore_type, "restored_event_id", restored_event_id)

    def _event_with_payload_value_exists(self, event_type: str, payload_key: str, payload_value: str) -> bool:
        statement = select(EventRecord).where(EventRecord.type == event_type)
        with Session(engine) as session:
            events = session.exec(statement).all()
        return any((event.payload or {}).get(payload_key) == payload_value for event in events)

    def _latest_event(self, events: list[EventRecord], event_type: str, predicate=None) -> Optional[EventRecord]:
        for event in reversed(events):
            if event.type != event_type:
                continue
            if predicate and not predicate(event):
                continue
            return event
        return None

    def _root_sidecars(self, sidecars: object) -> list[dict]:
        if not isinstance(sidecars, list):
            return []
        checked = []
        for item in sidecars:
            if not isinstance(item, dict):
                continue
            checked.append({
                "source": self._safe_path(item.get("source_path"), "sidecar.source_path"),
                "target": self._safe_path(item.get("target_path"), "sidecar.target_path"),
            })
        return checked

    def _validate_reverse_move(self, source: Path, target: Path, sidecars: list[dict]):
        if not target.exists():
            raise ValueError("Root move target file is missing")
        if source.exists():
            raise ValueError("Root move source path is occupied")
        for item in sidecars:
            if not item["target"].exists():
                raise ValueError(f"Root move sidecar target is missing: {item['target']}")
            if item["source"].exists():
                raise ValueError(f"Root move sidecar source path is occupied: {item['source']}")

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


operation_restore = OperationRestore()
