from collections import Counter
from typing import Optional

from sqlmodel import Session, select

from app.database import engine
from app.models import EventRecord, Movie


PROJECTABLE_EVENTS = {
    "MovieIgnored",
    "MovieMarkedMissing",
    "MovieRestored",
    "AnalysisStarted",
    "AnalysisCompleted",
    "AnalysisFailed",
}

COMPARE_FIELDS = (
    "library_status",
    "missing_since",
    "analysis_status",
    "analysis_data",
    "micro_genre",
    "micro_genre_definition",
)


class MovieProjectionDryRun:
    """Read-only projection consistency checker.

    This is not a canonical replay from an empty state. It starts with the
    current Movie snapshot and reapplies supported events in memory so we can
    detect whether current state still agrees with the event-driven rules.
    """

    def run(
        self,
        *,
        movie_id: Optional[str] = None,
        limit: int = 1000,
        since: Optional[str] = None,
    ) -> dict:
        limit = max(1, min(limit, 5000))
        with Session(engine) as session:
            current_movies = self._current_movies(session, movie_id)
            events = self._events(session, movie_id=movie_id, limit=limit, since=since)

        projected_movies = {movie_id: dict(movie) for movie_id, movie in current_movies.items()}
        touched_movie_ids: set[str] = set()
        unsupported_event_types: Counter[str] = Counter()
        projectable_events = 0

        for event in events:
            if event.type not in PROJECTABLE_EVENTS:
                unsupported_event_types[event.type] += 1
                continue
            projectable_events += 1
            if not event.aggregate_id:
                continue
            state = projected_movies.get(event.aggregate_id)
            if state is None:
                continue
            touched_movie_ids.add(event.aggregate_id)
            self._apply_event(state, event)

        differences = self._differences(current_movies, projected_movies, touched_movie_ids)
        return {
            "dry_run": True,
            "mode": "current_snapshot_plus_events",
            "note": "Consistency dry-run only; this is not a canonical replay from an empty state.",
            "base": "current_movie_snapshot",
            "movie_id": movie_id,
            "since": since,
            "limit": limit,
            "events_processed": len(events),
            "projectable_events": projectable_events,
            "unsupported_events": sum(unsupported_event_types.values()),
            "unsupported_event_types": dict(sorted(unsupported_event_types.items())),
            "movies_compared": len(touched_movie_ids),
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

    def _apply_event(self, state: dict, event: EventRecord):
        payload = event.payload or {}
        if event.type == "MovieIgnored":
            state["library_status"] = "ignored"
            state["missing_since"] = None
        elif event.type == "MovieMarkedMissing":
            if state.get("library_status") != "ignored":
                state["library_status"] = "missing"
                state["missing_since"] = payload.get("missing_since")
        elif event.type == "MovieRestored":
            if state.get("library_status") != "ignored":
                state["library_status"] = "available"
                state["missing_since"] = None
        elif event.type == "AnalysisStarted":
            state["analysis_status"] = "processing"
        elif event.type == "AnalysisCompleted":
            state["analysis_status"] = "completed"
            state["analysis_data"] = payload.get("analysis_data")
            state["micro_genre"] = payload.get("micro_genre")
            state["micro_genre_definition"] = payload.get("micro_genre_definition")
        elif event.type == "AnalysisFailed":
            state["analysis_status"] = "failed"

    def _differences(
        self,
        current_movies: dict[str, dict],
        projected_movies: dict[str, dict],
        movie_ids: set[str],
    ) -> list[dict]:
        differences = []
        for movie_id in sorted(movie_ids):
            current = current_movies.get(movie_id)
            projected = projected_movies.get(movie_id)
            if not current or not projected:
                continue
            for field in COMPARE_FIELDS:
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
