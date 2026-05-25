from typing import Optional

from sqlmodel import Session, select

from app.database import engine
from app.models import EventRecord, Movie
from app.services.projections.movie_fields import (
    CORE_COMPARE_FIELDS,
    PROJECTABLE_EVENT_TYPES,
)
from app.services.projections.movie_replay import movie_event_replayer


CURRENT_BASE_PROJECTABLE_EVENTS = PROJECTABLE_EVENT_TYPES

EMPTY_BASE_PROJECTABLE_EVENTS = PROJECTABLE_EVENT_TYPES

BASES = {"current", "empty"}

CURRENT_BASE_COMPARE_FIELDS = CORE_COMPARE_FIELDS

EMPTY_BASE_COMPARE_FIELDS = CORE_COMPARE_FIELDS


class MovieProjectionDryRun:
    """Read-only projection consistency checker.

    In current mode it starts with the current Movie snapshot and reapplies
    supported projectable events. In empty mode it starts from no movies and
    replays the currently supported subset of movie events in memory.
    """

    def run(
        self,
        *,
        movie_id: Optional[str] = None,
        limit: int = 1000,
        since: Optional[str] = None,
        base: str = "current",
    ) -> dict:
        if base not in BASES:
            raise ValueError("base must be 'current' or 'empty'")

        limit = max(1, min(limit, 5000))
        with Session(engine) as session:
            current_movies = self._current_movies(session, movie_id)
            events = self._events(session, movie_id=movie_id, limit=limit, since=since)

        projected_movies = (
            {movie_id: dict(movie) for movie_id, movie in current_movies.items()}
            if base == "current"
            else {}
        )
        projectable_event_types = (
            CURRENT_BASE_PROJECTABLE_EVENTS
            if base == "current"
            else EMPTY_BASE_PROJECTABLE_EVENTS
        )
        replay = movie_event_replayer.replay(
            events=events,
            projected_movies=projected_movies,
            projectable_event_types=projectable_event_types,
        )

        compare_fields = CURRENT_BASE_COMPARE_FIELDS if base == "current" else EMPTY_BASE_COMPARE_FIELDS
        differences = self._differences(current_movies, projected_movies, replay["touched_movie_ids"], compare_fields)
        return {
            "dry_run": True,
            "mode": "current_snapshot_plus_events" if base == "current" else "empty_replay",
            "note": (
                "Consistency dry-run only; this is not a canonical replay from an empty state."
                if base == "current"
                else "Empty-base dry-run replays only currently supported movie events; unsupported events are reported but not applied."
            ),
            "base": base,
            "movie_id": movie_id,
            "since": since,
            "limit": limit,
            "events_processed": len(events),
            "projectable_events": replay["projectable_events"],
            "skipped_projectable_events": replay["skipped_projectable_events"],
            "skipped_events": replay["skipped_events"],
            "unsupported_events": replay["unsupported_events"],
            "unsupported_event_types": replay["unsupported_event_types"],
            "movies_compared": len(replay["touched_movie_ids"]),
            "movies_with_differences": len({diff["movie_id"] for diff in differences}),
            "differences": differences,
        }

    def _current_movies(self, session: Session, movie_id: Optional[str]) -> dict[str, dict]:
        statement = select(Movie)
        if movie_id:
            statement = statement.where(Movie.id == movie_id)
        return {
            movie.id: movie.model_dump()
            for movie in session.exec(statement).all()
        }

    def _events(
        self,
        session: Session,
        *,
        movie_id: Optional[str],
        limit: int,
        since: Optional[str],
    ) -> list[EventRecord]:
        statement = select(EventRecord).where(EventRecord.aggregate_type == "movie")
        if movie_id:
            statement = statement.where(EventRecord.aggregate_id == movie_id)
        if since:
            statement = statement.where(EventRecord.occurred_at >= since)
        statement = statement.order_by(EventRecord.occurred_at, EventRecord.id).limit(limit)
        return list(session.exec(statement).all())

    def _differences(
        self,
        current_movies: dict[str, dict],
        projected_movies: dict[str, dict],
        movie_ids: set[str],
        compare_fields: tuple[str, ...],
    ) -> list[dict]:
        differences = []
        for movie_id in sorted(movie_ids):
            current = current_movies.get(movie_id)
            projected = projected_movies.get(movie_id)
            if current and not projected:
                differences.append({
                    "movie_id": movie_id,
                    "field": "__movie__",
                    "current": "present",
                    "projected": None,
                    "reason": "Movie exists in current table but was not projected",
                })
                continue
            if projected and not current:
                differences.append({
                    "movie_id": movie_id,
                    "field": "__movie__",
                    "current": None,
                    "projected": "present",
                    "reason": "Movie was projected but does not exist in current table",
                })
                continue
            if not current or not projected:
                continue
            for field in compare_fields:
                if current.get(field) != projected.get(field):
                    differences.append({
                        "movie_id": movie_id,
                        "field": field,
                        "current": current.get(field),
                        "projected": projected.get(field),
                        "reason": "Projected state differs from current Movie table",
                    })
        return differences


movie_projection_dry_run = MovieProjectionDryRun()
