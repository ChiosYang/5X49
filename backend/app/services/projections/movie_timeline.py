from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.database import engine
from app.models import EventRecord, Movie
from app.services.projections.movie_fields import CORE_COMPARE_FIELDS
from app.services.projections.movie_replay import movie_event_replayer


FILE_SIDE_EFFECT_EVENT_TYPES = {
    "ArtworkDownloaded",
    "NfoWritten",
    "RootVideoMoved",
    "RootVideoOrganized",
}


class MovieTimelineDryRun:
    """Read-only historical state and restore preview for one movie."""

    def state(
        self,
        *,
        movie_id: str,
        before_event_id: Optional[str] = None,
        at: Optional[str] = None,
    ) -> dict:
        current_movie, events = self._load(movie_id)
        events_to_replay, events_after_cutoff, target = self._select_events(
            events,
            before_event_id=before_event_id,
            at=at,
        )
        return self._state_report(
            movie_id=movie_id,
            current_movie=current_movie,
            events_to_replay=events_to_replay,
            events_after_cutoff=events_after_cutoff,
            target=target,
        )

    def restore_preview(
        self,
        *,
        movie_id: str,
        before_event_id: Optional[str] = None,
        at: Optional[str] = None,
    ) -> dict:
        current_movie, events = self._load(movie_id)
        events_to_replay, events_after_cutoff, target = self._select_events(
            events,
            before_event_id=before_event_id,
            at=at,
        )
        report = self._state_report(
            movie_id=movie_id,
            current_movie=current_movie,
            events_to_replay=events_to_replay,
            events_after_cutoff=events_after_cutoff,
            target=target,
        )
        file_restore = self._file_restore_preview(events_after_cutoff)
        field_restore = [diff for diff in report["field_diff"] if diff["restorable"]]
        status = self._preview_status(field_restore, file_restore, report)
        return {
            **report,
            "status": status,
            "field_restore": field_restore,
            "file_restore": file_restore,
            "restorable_files": file_restore["restorable_files"],
            "missing_file_backups": file_restore["missing_file_backups"],
        }

    def _load(self, movie_id: str) -> tuple[dict, list[EventRecord]]:
        with Session(engine) as session:
            movie = session.get(Movie, movie_id)
            if not movie:
                raise LookupError("Movie not found")
            statement = (
                select(EventRecord)
                .where(EventRecord.aggregate_type == "movie")
                .where(EventRecord.aggregate_id == movie_id)
                .order_by(EventRecord.occurred_at, EventRecord.id)
            )
            events = list(session.exec(statement).all())
            return movie.model_dump(), events

    def _select_events(
        self,
        events: list[EventRecord],
        *,
        before_event_id: Optional[str],
        at: Optional[str],
    ) -> tuple[list[EventRecord], list[EventRecord], dict]:
        if bool(before_event_id) == bool(at):
            raise ValueError("Exactly one of before_event_id or at is required")

        if before_event_id:
            for index, event in enumerate(events):
                if event.id == before_event_id:
                    return (
                        events[:index],
                        events[index:],
                        {
                            "selector_type": "before_event_id",
                            "before_event_id": before_event_id,
                            "at": None,
                            "cutoff_event": self._event_summary(event),
                        },
                    )
            raise LookupError("before_event_id does not belong to this movie")

        target_at = self._parse_iso_timestamp(at or "")
        replay: list[EventRecord] = []
        after: list[EventRecord] = []
        for event in events:
            event_at = self._parse_iso_timestamp(event.occurred_at)
            if event_at <= target_at:
                replay.append(event)
            else:
                after.append(event)
        return (
            replay,
            after,
            {
                "selector_type": "at",
                "before_event_id": None,
                "at": at,
                "cutoff_event": self._event_summary(replay[-1]) if replay else None,
            },
        )

    def _state_report(
        self,
        *,
        movie_id: str,
        current_movie: dict,
        events_to_replay: list[EventRecord],
        events_after_cutoff: list[EventRecord],
        target: dict,
    ) -> dict:
        projected_movies: dict[str, dict] = {}
        replay = movie_event_replayer.replay(events=events_to_replay, projected_movies=projected_movies)
        target_state = projected_movies.get(movie_id)
        return {
            "dry_run": True,
            "movie_id": movie_id,
            "target": target,
            "current_state": current_movie,
            "target_state": target_state,
            "field_diff": self._field_diff(current_movie, target_state),
            "events_processed": len(events_to_replay),
            "events_after_cutoff": len(events_after_cutoff),
            "projectable_events": replay["projectable_events"],
            "skipped_projectable_events": replay["skipped_projectable_events"],
            "unsupported_events": replay["unsupported_events"],
            "unsupported_event_types": replay["unsupported_event_types"],
            "skipped_events": replay["skipped_events"],
            "missing_payload": replay["missing_payload"],
        }

    def _field_diff(self, current_state: dict, target_state: Optional[dict]) -> list[dict]:
        if target_state is None:
            return []
        differences = []
        for field in CORE_COMPARE_FIELDS:
            current = current_state.get(field)
            target = target_state.get(field)
            if current is None and target is None:
                continue
            if current != target:
                differences.append({
                    "field": field,
                    "current": current,
                    "target": target,
                    "restorable": field in target_state,
                })
        return differences

    def _file_restore_preview(self, events_after_cutoff: list[EventRecord]) -> dict:
        restorable_files = []
        missing_file_backups = []
        unsafe_files = []

        for event in events_after_cutoff:
            if event.type not in FILE_SIDE_EFFECT_EVENT_TYPES:
                continue
            payload = event.payload or {}
            if event.type == "ArtworkDownloaded":
                self._append_backup_file_preview(
                    event,
                    payload,
                    restorable_files,
                    missing_file_backups,
                    file_type=payload.get("asset_type") or "artwork",
                    path=payload.get("destination"),
                )
            elif event.type == "NfoWritten":
                self._append_backup_file_preview(
                    event,
                    payload,
                    restorable_files,
                    missing_file_backups,
                    file_type="nfo",
                    path=payload.get("path"),
                )
            elif event.type in {"RootVideoMoved", "RootVideoOrganized"}:
                preview = self._root_video_preview(event, payload)
                if preview["can_reverse"]:
                    restorable_files.append(preview)
                else:
                    unsafe_files.append(preview)

        return {
            "restorable_files": restorable_files,
            "missing_file_backups": missing_file_backups,
            "unsafe_files": unsafe_files,
        }

    def _append_backup_file_preview(
        self,
        event: EventRecord,
        payload: dict,
        restorable_files: list[dict],
        missing_file_backups: list[dict],
        *,
        file_type: str,
        path: Optional[str],
    ):
        backup_path = payload.get("backup_path")
        item = {
            "event_id": event.id,
            "type": event.type,
            "file_type": file_type,
            "path": path,
            "backup_path": backup_path,
            "backup_file_exists": bool(isinstance(backup_path, str) and Path(backup_path).exists()),
        }
        if item["backup_file_exists"]:
            restorable_files.append(item)
        else:
            missing_file_backups.append({
                **item,
                "reason": "Side-effect event has no available backup file",
            })

    def _root_video_preview(self, event: EventRecord, payload: dict) -> dict:
        source_path = payload.get("source_path")
        target_path = payload.get("target_path")
        target_exists = bool(isinstance(target_path, str) and Path(target_path).exists())
        source_available = bool(isinstance(source_path, str) and not Path(source_path).exists())
        return {
            "event_id": event.id,
            "type": event.type,
            "file_type": "root_video",
            "source_path": source_path,
            "target_path": target_path,
            "target_exists": target_exists,
            "source_available": source_available,
            "can_reverse": target_exists and source_available,
            "reason": "Root video preview does not execute filesystem changes",
        }

    def _preview_status(self, field_restore: list[dict], file_restore: dict, report: dict) -> str:
        if file_restore["unsafe_files"]:
            return "unsafe"
        if report["missing_payload"] or report["skipped_events"] or file_restore["missing_file_backups"]:
            return "partial"
        if field_restore or file_restore["restorable_files"]:
            return "safe"
        return "unknown"

    def _parse_iso_timestamp(self, value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("at must be a valid ISO timestamp") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _event_summary(self, event: EventRecord) -> dict:
        return {
            "id": event.id,
            "type": event.type,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": event.aggregate_id,
            "occurred_at": event.occurred_at,
            "command_id": event.command_id,
            "correlation_id": event.correlation_id,
        }


movie_timeline_dry_run = MovieTimelineDryRun()
