from collections import Counter
from typing import Optional

from sqlmodel import Session, select

from app.database import engine
from app.models import EventRecord, Movie


CURRENT_BASE_PROJECTABLE_EVENTS = {
    "MovieIgnored",
    "MovieMarkedMissing",
    "MovieRestored",
    "RootVideoOrganizationReverted",
    "AnalysisStarted",
    "AnalysisCompleted",
    "AnalysisFailed",
}

EMPTY_BASE_PROJECTABLE_EVENTS = {
    *CURRENT_BASE_PROJECTABLE_EVENTS,
    "MovieDiscovered",
    "MovieFileObserved",
}

BASES = {"current", "empty"}

CURRENT_BASE_COMPARE_FIELDS = (
    "library_status",
    "missing_since",
    "analysis_status",
    "analysis_data",
    "micro_genre",
    "micro_genre_definition",
)

EMPTY_BASE_COMPARE_FIELDS = (
    "id",
    "title",
    "title_cn",
    "year",
    "media_path",
    "folder_path",
    "folder_name",
    "video_file",
    "file_size",
    "file_mtime",
    "last_seen_at",
    "library_status",
    "metadata_source",
    "scrape_status",
    "tmdb_id",
    "imdb_id",
    "video_width",
    "video_height",
    "video_codec",
    "video_bitrate",
    "video_duration",
    "video_fps",
    "video_dynamic_range",
    "video_bit_depth",
    "nfo_source",
    "nfo_file",
    "nfo_path",
    "nfo_size",
    "nfo_mtime",
    "nfo_fingerprint",
    *CURRENT_BASE_COMPARE_FIELDS,
)

FILE_OBSERVED_FIELDS = (
    "media_path",
    "folder_path",
    "folder_name",
    "video_file",
    "file_size",
    "file_mtime",
    "last_seen_at",
    "video_width",
    "video_height",
    "video_codec",
    "video_bitrate",
    "video_duration",
    "video_fps",
    "video_dynamic_range",
    "video_bit_depth",
    "nfo_source",
    "nfo_file",
    "nfo_path",
    "nfo_size",
    "nfo_mtime",
    "nfo_fingerprint",
)


class MovieProjectionDryRun:
    """Read-only projection consistency checker.

    In current mode it starts with the current Movie snapshot and reapplies
    supported low-risk events. In empty mode it starts from no movies and
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
        touched_movie_ids: set[str] = set()
        unsupported_event_types: Counter[str] = Counter()
        projectable_events = 0
        skipped_projectable_events = 0
        skipped_events: list[dict] = []
        projectable_event_types = (
            CURRENT_BASE_PROJECTABLE_EVENTS
            if base == "current"
            else EMPTY_BASE_PROJECTABLE_EVENTS
        )

        for event in events:
            if event.type not in projectable_event_types:
                unsupported_event_types[event.type] += 1
                continue
            projectable_events += 1
            touched_id = event.aggregate_id or (event.payload or {}).get("movie_id")
            if not touched_id:
                skipped_projectable_events += 1
                self._record_skipped_event(skipped_events, event, "Missing movie aggregate ID")
                continue
            state = projected_movies.get(touched_id)
            if state is None:
                if base == "empty" and event.type == "MovieDiscovered":
                    state = self._state_from_discovered(event)
                    if state is None:
                        skipped_projectable_events += 1
                        self._record_skipped_event(
                            skipped_events,
                            event,
                            "MovieDiscovered payload is missing id, title, or year",
                        )
                        continue
                    projected_movies[touched_id] = state
                else:
                    skipped_projectable_events += 1
                    self._record_skipped_event(
                        skipped_events,
                        event,
                        "No projected movie state exists for this event",
                    )
                    continue
            touched_movie_ids.add(touched_id)
            self._apply_event(state, event)

        compare_fields = CURRENT_BASE_COMPARE_FIELDS if base == "current" else EMPTY_BASE_COMPARE_FIELDS
        differences = self._differences(current_movies, projected_movies, touched_movie_ids, compare_fields)
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
            "projectable_events": projectable_events,
            "skipped_projectable_events": skipped_projectable_events,
            "skipped_events": skipped_events,
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
        if event.type == "MovieDiscovered":
            state.update(self._discovered_payload(payload, event))
        elif event.type == "MovieFileObserved":
            for field in FILE_OBSERVED_FIELDS:
                if field in payload:
                    state[field] = payload[field]
            current = payload.get("current")
            if isinstance(current, dict):
                for field in FILE_OBSERVED_FIELDS:
                    if field in current:
                        state[field] = current[field]
        elif event.type == "MovieIgnored":
            state["library_status"] = "ignored"
            state["missing_since"] = None
        elif event.type == "MovieMarkedMissing":
            if state.get("library_status") not in {"ignored", "reverted"}:
                state["library_status"] = "missing"
                state["missing_since"] = payload.get("missing_since")
        elif event.type == "MovieRestored":
            if state.get("library_status") != "ignored":
                state["library_status"] = "available"
                state["missing_since"] = None
        elif event.type == "RootVideoOrganizationReverted":
            state["library_status"] = "reverted"
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

    def _state_from_discovered(self, event: EventRecord) -> Optional[dict]:
        payload = event.payload or {}
        movie_id = payload.get("movie_id") or payload.get("id") or event.aggregate_id
        if not movie_id or not payload.get("title") or payload.get("year") is None:
            return None
        state = {
            "id": movie_id,
            "title": payload["title"],
            "year": payload["year"],
            "library_status": "available",
            "analysis_status": "pending",
            "scrape_status": "pending",
        }
        state.update(self._discovered_payload(payload, event))
        return state

    def _discovered_payload(self, payload: dict, event: EventRecord) -> dict:
        movie_id = payload.get("movie_id") or payload.get("id") or event.aggregate_id
        return {
            key: value
            for key, value in {
                **payload,
                "id": movie_id,
            }.items()
            if key in EMPTY_BASE_COMPARE_FIELDS and value is not None
        }

    def _record_skipped_event(self, skipped_events: list[dict], event: EventRecord, reason: str):
        if len(skipped_events) >= 20:
            return
        skipped_events.append({
            "event_id": event.id,
            "type": event.type,
            "aggregate_id": event.aggregate_id,
            "reason": reason,
        })

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
