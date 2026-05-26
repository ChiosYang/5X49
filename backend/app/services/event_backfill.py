import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.database import engine
from app.models import EventRecord, Movie
from app.services.library import SCAN_EVENT_FIELDS
from app.services.projections.movie_fields import CORE_COMPARE_FIELDS
from app.services.settings import get_media_dir


FIELD_BACKFILL_SOURCE_TYPES = {"MetadataMatched", "ArtworkSelected"}
FILE_SNAPSHOT_FIELDS = (
    ("poster", "poster_local"),
    ("backdrop", "backdrop_local"),
    ("nfo", "nfo_path"),
    ("nfo", "nfo_file"),
)


class MovieDiscoveredBackfill:
    """Create missing MovieDiscovered initialization events for existing movies."""

    def run(self, *, dry_run: bool = True, movie_id: Optional[str] = None, sample_limit: int = 20) -> dict:
        return movie_replay_backfill.run_movie_discovered(
            dry_run=dry_run,
            movie_id=movie_id,
            sample_limit=sample_limit,
        )


class MovieReplayBackfill:
    """Plan and append replay backfill events without changing current Movie rows."""

    def run(self, *, dry_run: bool = True, movie_id: Optional[str] = None, sample_limit: int = 20) -> dict:
        sample_limit = max(0, min(sample_limit, 50))
        with Session(engine) as session:
            movies = self._movies(session, movie_id)
            movie_ids = {movie.id for movie in movies}
            events = self._events(session, movie_id)
            events_checked = len([event for event in events if not movie_ids or event.aggregate_id in movie_ids])
            existing_backfills = self._existing_backfills(events)
            earliest_event_times = self._earliest_event_times(session, movie_id)

            discovered_specs = [
                self._event_spec(movie, earliest_event_times.get(movie.id))
                for movie in movies
                if movie.id not in existing_backfills["movie_discovered"]
            ]
            state_specs, unsupported = self._state_backfill_specs(movies, events, existing_backfills)
            file_specs, unavailable_file_snapshots = self._file_snapshot_specs(movies, existing_backfills)
            event_specs = [*discovered_specs, *state_specs, *file_specs]

            created_event_ids: list[str] = []
            if not dry_run and event_specs:
                events = [self._event_record(spec) for spec in event_specs]
                session.add_all(events)
                session.commit()
                created_event_ids = [event.id for event in events]

        coverage_before = self._coverage_before(movie_id)
        return {
            "dry_run": dry_run,
            "movie_id": movie_id,
            "movies_checked": len(movies),
            "events_checked": events_checked,
            "events_to_create": len(event_specs),
            "created_events": 0 if dry_run else len(created_event_ids),
            "created_event_ids": created_event_ids[:50],
            "sample_events": event_specs[:sample_limit],
            "unsupported": unsupported,
            "unavailable_file_snapshots": unavailable_file_snapshots,
            "coverage_before": coverage_before,
            "notes": [
                "Backfill events are migration snapshots with source=backfill; they do not rewrite original events.",
                "MovieDiscovered backfills sort before each movie's earliest existing movie event.",
                "MovieStateBackfilled and MovieFileSnapshotBackfilled use the migration execution time.",
                "No media files are copied, moved, or modified.",
            ],
        }

    def run_movie_discovered(
        self,
        *,
        dry_run: bool = True,
        movie_id: Optional[str] = None,
        sample_limit: int = 20,
    ) -> dict:
        sample_limit = max(0, min(sample_limit, 50))
        with Session(engine) as session:
            movies = self._movies(session, movie_id)
            events = self._events(session, movie_id)
            existing_backfills = self._existing_backfills(events)
            earliest_event_times = self._earliest_event_times(session, movie_id)
            event_specs = [
                self._event_spec(movie, earliest_event_times.get(movie.id))
                for movie in movies
                if movie.id not in existing_backfills["movie_discovered"]
            ]
            created_event_ids: list[str] = []
            if not dry_run and event_specs:
                events_to_create = [self._event_record(spec) for spec in event_specs]
                session.add_all(events_to_create)
                session.commit()
                created_event_ids = [event.id for event in events_to_create]

        return {
            "dry_run": dry_run,
            "event_type": "MovieDiscovered",
            "movie_id": movie_id,
            "movies_checked": len(movies),
            "already_initialized": len(movies) - len(event_specs),
            "events_to_create": len(event_specs),
            "created_events": 0 if dry_run else len(created_event_ids),
            "created_event_ids": created_event_ids[:50],
            "sample_events": event_specs[:sample_limit],
            "timestamp_strategy": (
                "Backfilled initialization events are placed just before each movie's earliest existing movie event "
                "when one exists; otherwise they use added_at, last_seen_at, or current time."
            ),
        }

    def _movies(self, session: Session, movie_id: Optional[str]) -> list[Movie]:
        statement = select(Movie).order_by(Movie.title, Movie.year, Movie.id)
        if movie_id:
            statement = statement.where(Movie.id == movie_id)
        return list(session.exec(statement).all())

    def _events(self, session: Session, movie_id: Optional[str]) -> list[EventRecord]:
        statement = select(EventRecord).where(EventRecord.aggregate_type == "movie")
        if movie_id:
            statement = statement.where(EventRecord.aggregate_id == movie_id)
        statement = statement.order_by(EventRecord.occurred_at, EventRecord.id)
        return list(session.exec(statement).all())

    def _earliest_event_times(self, session: Session, movie_id: Optional[str]) -> dict[str, str]:
        statement = select(EventRecord).where(EventRecord.aggregate_type == "movie")
        if movie_id:
            statement = statement.where(EventRecord.aggregate_id == movie_id)
        statement = statement.order_by(EventRecord.aggregate_id, EventRecord.occurred_at, EventRecord.id)

        earliest: dict[str, str] = {}
        for event in session.exec(statement).all():
            if event.aggregate_id and event.aggregate_id not in earliest:
                earliest[event.aggregate_id] = event.occurred_at
        return earliest

    def _event_spec(self, movie: Movie, earliest_event_at: Optional[str]) -> dict:
        movie_data = movie.model_dump()
        payload = {
            field: movie_data.get(field)
            for field in SCAN_EVENT_FIELDS
            if movie_data.get(field) is not None
        }
        payload["id"] = movie.id
        payload["movie_id"] = movie.id

        return {
            "type": "MovieDiscovered",
            "aggregate_type": "movie",
            "aggregate_id": movie.id,
            "actor_type": "migration",
            "payload": payload,
            "context": {
                "source": "backfill",
                "backfill_kind": "movie_discovered",
                "reason": "initialize_event_replay",
            },
            "occurred_at": self._backfill_time(movie_data, earliest_event_at),
        }

    def _state_backfill_specs(
        self,
        movies: list[Movie],
        events: list[EventRecord],
        existing_backfills: dict[str, set],
    ) -> tuple[list[dict], list[dict]]:
        movies_by_id = {movie.id: movie for movie in movies}
        source_events_by_movie: dict[str, list[EventRecord]] = {}
        unsupported = []
        for event in events:
            if event.type not in FIELD_BACKFILL_SOURCE_TYPES:
                continue
            payload = event.payload or {}
            current = payload.get("current")
            if isinstance(current, dict) and current:
                continue
            movie_id = payload.get("movie_id") or payload.get("id") or event.aggregate_id
            if not movie_id or movie_id not in movies_by_id:
                unsupported.append({
                    "event_id": event.id,
                    "type": event.type,
                    "aggregate_id": event.aggregate_id,
                    "reason": "Cannot identify target movie for old payload",
                })
                continue
            source_events_by_movie.setdefault(movie_id, []).append(event)

        specs = []
        now = datetime.now(timezone.utc).isoformat()
        for movie_id, source_events in sorted(source_events_by_movie.items()):
            if movie_id in existing_backfills["movie_state"]:
                continue
            movie_data = movies_by_id[movie_id].model_dump()
            current = {
                field: movie_data.get(field)
                for field in CORE_COMPARE_FIELDS
                if field in Movie.model_fields and movie_data.get(field) is not None
            }
            if not current:
                unsupported.append({
                    "movie_id": movie_id,
                    "reason": "Current Movie row has no projectable fields to snapshot",
                })
                continue
            specs.append({
                "type": "MovieStateBackfilled",
                "aggregate_type": "movie",
                "aggregate_id": movie_id,
                "actor_type": "migration",
                "payload": {
                    "movie_id": movie_id,
                    "current": current,
                    "source_event_ids": [event.id for event in source_events],
                    "source_event_types": sorted({event.type for event in source_events}),
                    "reason": "old_projectable_event_payload_missing_current",
                    "source": "backfill",
                },
                "context": {
                    "source": "backfill",
                    "backfill_kind": "movie_state",
                    "reason": "old_projectable_event_payload_missing_current",
                },
                "occurred_at": now,
            })
        return specs, unsupported

    def _file_snapshot_specs(
        self,
        movies: list[Movie],
        existing_backfills: dict[str, set],
    ) -> tuple[list[dict], list[dict]]:
        specs = []
        unavailable = []
        now = datetime.now(timezone.utc).isoformat()
        for movie in movies:
            movie_data = movie.model_dump()
            seen_types = set()
            for file_type, field in FILE_SNAPSHOT_FIELDS:
                if file_type in seen_types or (movie.id, file_type) in existing_backfills["file_snapshot"]:
                    continue
                raw_path = movie_data.get(field)
                if not raw_path and file_type == "nfo" and movie_data.get("folder_path") and movie_data.get("nfo_file"):
                    raw_path = str(Path(movie_data["folder_path"]) / movie_data["nfo_file"])
                if not raw_path:
                    continue
                try:
                    path = self._resolve_media_path(raw_path, movie_data)
                except ValueError as exc:
                    unavailable.append({
                        "movie_id": movie.id,
                        "file_type": file_type,
                        "field": field,
                        "path": raw_path,
                        "reason": str(exc),
                    })
                    seen_types.add(file_type)
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    unavailable.append({
                        "movie_id": movie.id,
                        "file_type": file_type,
                        "field": field,
                        "path": str(path),
                        "reason": "File does not exist",
                    })
                    seen_types.add(file_type)
                    continue
                specs.append({
                    "type": "MovieFileSnapshotBackfilled",
                    "aggregate_type": "movie",
                    "aggregate_id": movie.id,
                    "actor_type": "migration",
                    "payload": {
                        "movie_id": movie.id,
                        "file_type": file_type,
                        "path": str(path),
                        "exists": True,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                        "restore_available": False,
                        "source": "backfill",
                    },
                    "context": {
                        "source": "backfill",
                        "backfill_kind": "file_snapshot",
                        "file_type": file_type,
                        "reason": "current_file_snapshot",
                    },
                    "occurred_at": now,
                })
                seen_types.add(file_type)
        return specs, unavailable

    def _existing_backfills(self, events: list[EventRecord]) -> dict[str, set]:
        discovered = set()
        state = set()
        file_snapshot = set()
        for event in events:
            payload = event.payload or {}
            context = event.context or {}
            movie_id = payload.get("movie_id") or payload.get("id") or event.aggregate_id
            if event.type == "MovieDiscovered" and movie_id:
                discovered.add(movie_id)
            if context.get("source") != "backfill" and payload.get("source") != "backfill":
                continue
            if event.type == "MovieStateBackfilled" and movie_id:
                state.add(movie_id)
            if event.type == "MovieFileSnapshotBackfilled" and movie_id:
                file_type = payload.get("file_type") or context.get("file_type")
                if file_type:
                    file_snapshot.add((movie_id, file_type))
        return {
            "movie_discovered": discovered,
            "movie_state": state,
            "file_snapshot": file_snapshot,
        }

    def _event_record(self, spec: dict) -> EventRecord:
        return EventRecord(
            aggregate_type=spec["aggregate_type"],
            aggregate_id=spec["aggregate_id"],
            type=spec["type"],
            actor_type=spec["actor_type"],
            payload=spec["payload"],
            context=spec["context"],
            occurred_at=spec["occurred_at"],
        )

    def _coverage_before(self, movie_id: Optional[str]) -> dict:
        try:
            from app.services.projections.movie_rebuild import movie_projection_dry_run

            report = movie_projection_dry_run.run(movie_id=movie_id, limit=5000, base="empty")
        except Exception as exc:
            return {"available": False, "error": str(exc)}
        return {
            "available": True,
            "events_processed": report.get("events_processed"),
            "projectable_events": report.get("projectable_events"),
            "skipped_projectable_events": report.get("skipped_projectable_events"),
            "unsupported_events": report.get("unsupported_events"),
            "unsupported_event_types": report.get("unsupported_event_types"),
            "movies_compared": report.get("movies_compared"),
            "movies_with_differences": report.get("movies_with_differences"),
        }

    def _resolve_media_path(self, value: str, movie_data: dict) -> Path:
        media_roots = self._media_roots()
        if not media_roots:
            raise ValueError("MEDIA_DIR is not configured")
        if value.startswith("/media/"):
            candidate = media_roots[0] / value.removeprefix("/media/")
        else:
            candidate = Path(value)
            if not candidate.is_absolute():
                folder_path = movie_data.get("folder_path")
                if not isinstance(folder_path, str) or not folder_path:
                    raise ValueError("Relative path cannot be resolved without folder_path")
                folder = Path(folder_path)
                if str(folder_path).startswith("/media/"):
                    folder = media_roots[0] / str(folder_path).removeprefix("/media/")
                candidate = folder / candidate
        resolved = candidate.resolve(strict=False)
        for media_root in media_roots:
            try:
                resolved.relative_to(media_root)
                return resolved
            except ValueError:
                continue
        raise ValueError("Path is outside MEDIA_DIR")

    def _media_roots(self) -> list[Path]:
        roots = []
        for value in (get_media_dir(), os.getenv("MEDIA_DIR")):
            if not value:
                continue
            root = Path(value).resolve(strict=False)
            if root not in roots:
                roots.append(root)
        return roots

    def _backfill_time(self, movie_data: dict, earliest_event_at: Optional[str]) -> str:
        if earliest_event_at:
            parsed = self._parse_iso(earliest_event_at)
            if parsed:
                return (parsed - timedelta(microseconds=1)).isoformat()
            return "1970-01-01T00:00:00+00:00"

        return (
            movie_data.get("added_at")
            or movie_data.get("last_seen_at")
            or datetime.now(timezone.utc).isoformat()
        )

    def _parse_iso(self, value: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


movie_discovered_backfill = MovieDiscoveredBackfill()
movie_replay_backfill = MovieReplayBackfill()
