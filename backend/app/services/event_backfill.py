from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, select

from app.database import engine
from app.models import EventRecord, Movie
from app.services.library import SCAN_EVENT_FIELDS


class MovieDiscoveredBackfill:
    """Create missing MovieDiscovered initialization events for existing movies."""

    def run(self, *, dry_run: bool = True, movie_id: Optional[str] = None, sample_limit: int = 20) -> dict:
        sample_limit = max(0, min(sample_limit, 50))
        with Session(engine) as session:
            movies = self._movies(session, movie_id)
            existing_discovered_ids = self._existing_discovered_ids(session, movie_id)
            earliest_event_times = self._earliest_event_times(session, movie_id)

            event_specs = [
                self._event_spec(movie, earliest_event_times.get(movie.id))
                for movie in movies
                if movie.id not in existing_discovered_ids
            ]

            created_event_ids: list[str] = []
            if not dry_run and event_specs:
                events = [self._event_record(spec) for spec in event_specs]
                session.add_all(events)
                session.commit()
                created_event_ids = [event.id for event in events]

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

    def _existing_discovered_ids(self, session: Session, movie_id: Optional[str]) -> set[str]:
        statement = select(EventRecord.aggregate_id).where(
            EventRecord.aggregate_type == "movie",
            EventRecord.type == "MovieDiscovered",
        )
        if movie_id:
            statement = statement.where(EventRecord.aggregate_id == movie_id)
        return {aggregate_id for aggregate_id in session.exec(statement).all() if aggregate_id}

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
                "source": "movie_discovered_backfill",
                "reason": "initialize_event_replay",
            },
            "occurred_at": self._backfill_time(movie_data, earliest_event_at),
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
