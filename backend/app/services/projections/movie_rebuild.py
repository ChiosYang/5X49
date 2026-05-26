import hashlib
import json
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


class ProjectionRebuildBlocked(ValueError):
    def __init__(self, message: str, report: Optional[dict] = None):
        super().__init__(message)
        self.report = report or {"status": "blocked", "reason": message}


class MovieProjectionDryRun:
    """Read-only projection consistency checker.

    In current mode it starts with the current Movie snapshot and reapplies
    supported projectable events. In empty mode it starts from no movies and
    replays the currently supported subset of movie events in memory.
    """

    def run(
        self,
        *,
        dry_run: bool = True,
        movie_id: Optional[str] = None,
        limit: int = 1000,
        since: Optional[str] = None,
        base: str = "current",
        confirmation_token: Optional[str] = None,
    ) -> dict:
        if base not in BASES:
            raise ValueError("base must be 'current' or 'empty'")

        if not dry_run:
            return self._execute(
                movie_id=movie_id,
                limit=limit,
                since=since,
                base=base,
                confirmation_token=confirmation_token,
            )

        return self._build_report(movie_id=movie_id, limit=limit, since=since, base=base)

    def _build_report(
        self,
        *,
        movie_id: Optional[str],
        limit: int,
        since: Optional[str],
        base: str,
    ) -> dict:
        limit = max(1, min(limit, 5000))
        with Session(engine) as session:
            current_movies = self._current_movies(session, movie_id)
            events, event_stream_truncated = self._events(session, movie_id=movie_id, limit=limit, since=since)

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
        last_event = self._event_summary(events[-1]) if events else None
        report = {
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
            "event_stream_truncated": event_stream_truncated,
            "last_event": last_event,
            "projectable_events": replay["projectable_events"],
            "skipped_projectable_events": replay["skipped_projectable_events"],
            "skipped_events": replay["skipped_events"],
            "unsupported_events": replay["unsupported_events"],
            "unsupported_event_types": replay["unsupported_event_types"],
            "movies_compared": len(replay["touched_movie_ids"]),
            "movies_with_differences": len({diff["movie_id"] for diff in differences}),
            "differences": differences,
        }
        if movie_id:
            report["projected_state"] = projected_movies.get(movie_id)
        report["confirmation_token"] = self._confirmation_token(report)
        return report

    def _execute(
        self,
        *,
        movie_id: Optional[str],
        limit: int,
        since: Optional[str],
        base: str,
        confirmation_token: Optional[str],
    ) -> dict:
        if not movie_id:
            raise ValueError("movie_id is required when dry_run=false")
        if base != "empty":
            raise ValueError("base=empty is required when dry_run=false")
        if since:
            raise ValueError("since is not supported when dry_run=false")
        report = self._build_report(movie_id=movie_id, limit=limit, since=since, base=base)
        if not confirmation_token:
            raise ProjectionRebuildBlocked("confirmation_token is required when dry_run=false", report)
        if confirmation_token != report["confirmation_token"]:
            raise ProjectionRebuildBlocked("confirmation_token does not match the current dry-run report", report)
        if report["event_stream_truncated"]:
            raise ProjectionRebuildBlocked("Event stream is truncated by limit", report)
        if report["skipped_projectable_events"]:
            raise ProjectionRebuildBlocked("Projection rebuild has skipped projectable events", report)
        projected_state = report.get("projected_state")
        if not isinstance(projected_state, dict):
            raise ProjectionRebuildBlocked("Movie could not be projected from events", report)

        with Session(engine) as session:
            movie = session.get(Movie, movie_id)
            if not movie:
                raise LookupError("Movie not found")
            before = movie.model_dump()
            fields_replaced = []
            for field in CORE_COMPARE_FIELDS:
                if field == "id" or field not in Movie.model_fields:
                    continue
                projected_value = projected_state.get(field)
                if before.get(field) != projected_value:
                    fields_replaced.append(field)
                setattr(movie, field, projected_value)
            after = movie.model_dump()
            event = EventRecord(
                aggregate_type="projection",
                aggregate_id=movie_id,
                type="MovieProjectionRebuilt",
                actor_type="system",
                payload={
                    "movie_id": movie_id,
                    "confirmation_token": confirmation_token,
                    "fields_replaced": fields_replaced,
                    "before": before,
                    "after": after,
                    "dry_run_summary": self._dry_run_summary(report),
                },
                context={
                    "source": "projection_rebuild",
                    "base": base,
                    "dry_run": False,
                },
            )
            session.add(movie)
            session.add(event)
            session.commit()
            session.refresh(event)

        return {
            "status": "rebuilt" if fields_replaced else "skipped",
            "movie_id": movie_id,
            "confirmation_token": confirmation_token,
            "fields_replaced": fields_replaced,
            "before": before,
            "after": after,
            "dry_run": report,
            "audit_event_id": event.id,
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
    ) -> tuple[list[EventRecord], bool]:
        statement = select(EventRecord).where(EventRecord.aggregate_type == "movie")
        if movie_id:
            statement = statement.where(EventRecord.aggregate_id == movie_id)
        if since:
            statement = statement.where(EventRecord.occurred_at >= since)
        statement = statement.order_by(EventRecord.occurred_at, EventRecord.id).limit(limit + 1)
        events = list(session.exec(statement).all())
        return events[:limit], len(events) > limit

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

    def _event_summary(self, event: EventRecord) -> dict:
        return {
            "id": event.id,
            "type": event.type,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": event.aggregate_id,
            "occurred_at": event.occurred_at,
        }

    def _dry_run_summary(self, report: dict) -> dict:
        return {
            "base": report.get("base"),
            "movie_id": report.get("movie_id"),
            "limit": report.get("limit"),
            "events_processed": report.get("events_processed"),
            "event_stream_truncated": report.get("event_stream_truncated"),
            "last_event": report.get("last_event"),
            "projectable_events": report.get("projectable_events"),
            "skipped_projectable_events": report.get("skipped_projectable_events"),
            "unsupported_events": report.get("unsupported_events"),
            "unsupported_event_types": report.get("unsupported_event_types"),
            "movies_compared": report.get("movies_compared"),
            "movies_with_differences": report.get("movies_with_differences"),
            "differences_count": len(report.get("differences") or []),
        }

    def _confirmation_token(self, report: dict) -> str:
        payload = {
            "movie_id": report.get("movie_id"),
            "base": report.get("base"),
            "since": report.get("since"),
            "limit": report.get("limit"),
            "events_processed": report.get("events_processed"),
            "event_stream_truncated": report.get("event_stream_truncated"),
            "last_event": report.get("last_event"),
            "projected_state": report.get("projected_state"),
            "differences": report.get("differences"),
            "skipped_projectable_events": report.get("skipped_projectable_events"),
            "skipped_events": report.get("skipped_events"),
            "unsupported_events": report.get("unsupported_events"),
            "unsupported_event_types": report.get("unsupported_event_types"),
            "movies_compared": report.get("movies_compared"),
            "movies_with_differences": report.get("movies_with_differences"),
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


movie_projection_dry_run = MovieProjectionDryRun()
