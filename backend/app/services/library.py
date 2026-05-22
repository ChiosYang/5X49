import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Optional
from pathlib import Path
from sqlalchemy import or_
from sqlmodel import Session, select, delete
from app.database import engine, create_db_and_tables, get_session
from app.models import Movie
from app.services.event_store import event_store

# Configuration via environment variables
SEED_DATA_FILE = Path(__file__).parent.parent / "data" / "seed_movies.json"

SCAN_EVENT_FIELDS = (
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
)

FILE_OBSERVED_FIELDS = (
    "media_path",
    "folder_path",
    "video_file",
    "file_size",
    "file_mtime",
    "video_width",
    "video_height",
    "video_codec",
    "video_duration",
)

NFO_SIGNATURE_FIELDS = (
    "nfo_file",
    "nfo_path",
    "nfo_size",
    "nfo_mtime",
    "nfo_fingerprint",
)

NFO_METADATA_FIELDS = (
    "id",
    "title",
    "title_cn",
    "year",
    "tmdb_id",
    "imdb_id",
    "plot",
    "runtime",
    "countries",
    "audio_tracks",
    "genres",
    "director",
    "imdb_rating",
    "actors",
    "poster_local",
    "backdrop_local",
    "poster_thumb_local",
    "backdrop_thumb_local",
    "poster_path",
    "backdrop_path",
    "nfo_source",
    "metadata_source",
    "scrape_status",
)


class LibraryManager:
    def __init__(self):
        # We handle DB creation in main.py, but good to ensure tables exist
        pass

    def add_movies(self, movies_data: list[dict]) -> int:
        """Add multiple movies to the library (upsert)."""
        added = 0
        scan_events: list[dict] = []
        with Session(engine) as session:
            for movie_dict in movies_data:
                # Convert dict to Movie model
                # Check if movie exists
                movie_id = movie_dict.get("id")
                if not movie_id:
                    continue
                
                existing_movie = session.get(Movie, movie_id)
                if not existing_movie and movie_dict.get("media_path"):
                    existing_movie = self._get_by_media_path(session, movie_dict["media_path"])
                if existing_movie:
                    previous_movie = existing_movie.model_dump()
                    if existing_movie.library_status == "ignored" and movie_dict.get("library_status") == "available":
                        movie_dict = {**movie_dict, "library_status": "ignored", "missing_since": None}
                    if not existing_movie.added_at:
                        existing_movie.added_at = self._fallback_added_at(movie_dict)
                    # Update fields
                    for key, value in movie_dict.items():
                        if key == "added_at" and existing_movie.added_at:
                            continue
                        setattr(existing_movie, key, value)
                    session.add(existing_movie)
                    scan_events.extend(self._scan_events_for_existing(previous_movie, movie_dict, existing_movie.id))
                else:
                    # Create new
                    new_movie = Movie(**self._with_added_at(movie_dict))
                    session.add(new_movie)
                    added += 1
                    scan_events.append({
                        "type": "MovieDiscovered",
                        "aggregate_id": movie_id,
                        "payload": self._movie_event_payload(movie_dict),
                        "project": False,
                    })
            session.commit()
        self._append_scan_events(scan_events)
        return added

    def upsert_movie(
        self,
        movie_data: dict,
        preserve_id: Optional[str] = None,
        *,
        command_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Insert or update one movie and return the stored record."""
        result = self.upsert_movie_with_events(
            movie_data,
            preserve_id=preserve_id,
            command_id=command_id,
            correlation_id=correlation_id,
        )
        return result["movie"] if result else None

    def upsert_movie_with_events(
        self,
        movie_data: dict,
        preserve_id: Optional[str] = None,
        *,
        command_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Insert or update one movie and return the stored record plus emitted scan event types."""
        movie_id = preserve_id or movie_data.get("id")
        if not movie_id:
            return None

        movie_data = {**movie_data, "id": movie_id}
        scan_events: list[dict] = []
        with Session(engine) as session:
            existing_movie = session.get(Movie, movie_id)
            if not existing_movie and movie_data.get("media_path"):
                existing_movie = self._get_by_media_path(session, movie_data["media_path"])

            if existing_movie:
                previous_movie = existing_movie.model_dump()
                if existing_movie.library_status == "ignored" and movie_data.get("library_status") == "available":
                    movie_data = {**movie_data, "library_status": "ignored", "missing_since": None}
                if not existing_movie.added_at:
                    existing_movie.added_at = self._fallback_added_at(movie_data)
                for key, value in movie_data.items():
                    if key == "added_at" and existing_movie.added_at:
                        continue
                    setattr(existing_movie, key, value)
                session.add(existing_movie)
                session.commit()
                session.refresh(existing_movie)
                stored = existing_movie.model_dump()
                scan_events.extend(self._scan_events_for_existing(previous_movie, movie_data, existing_movie.id))
                self._append_scan_events(scan_events, command_id=command_id, correlation_id=correlation_id)
                return {
                    "movie": stored,
                    "event_types": self._event_types(scan_events),
                }

            new_movie = Movie(**self._with_added_at(movie_data))
            session.add(new_movie)
            session.commit()
            session.refresh(new_movie)
            scan_events.append({
                "type": "MovieDiscovered",
                "aggregate_id": movie_id,
                "payload": self._movie_event_payload(movie_data),
                "project": False,
            })
            self._append_scan_events(scan_events, command_id=command_id, correlation_id=correlation_id)
            return {
                "movie": new_movie.model_dump(),
                "event_types": self._event_types(scan_events),
            }

    def get_movies(self) -> List[dict]:
        with Session(engine) as session:
            statement = select(Movie).order_by(Movie.title, Movie.year, Movie.id)
            results = session.exec(statement).all()
            # Convert to dicts for frontend compatibility
            return [movie.model_dump() for movie in results]

    def get_movie(self, movie_id: str) -> Optional[dict]:
        with Session(engine) as session:
            movie = session.get(Movie, movie_id)
            return movie.model_dump() if movie else None

    def mark_missing_not_seen_since(self, seen_at: str) -> int:
        """Mark available movies missing when they were not observed in a reconcile pass."""
        from datetime import datetime, timezone

        missing_at = datetime.now(timezone.utc).isoformat()
        updated = 0
        with Session(engine) as session:
            statement = select(Movie).where(Movie.library_status.not_in(["missing", "ignored", "reverted"]))
            movies = [
                movie.model_dump()
                for movie in session.exec(statement).all()
                if not movie.last_seen_at or movie.last_seen_at < seen_at
            ]
        for movie in movies:
            _, projected = event_store.append_and_project(
                "MovieMarkedMissing",
                "movie",
                movie["id"],
                {"movie_id": movie["id"], "missing_since": missing_at, "seen_at": seen_at},
            )
            if projected:
                updated += 1
        return updated

    def mark_path_missing(self, path: str) -> int:
        from datetime import datetime, timezone

        missing_at = datetime.now(timezone.utc).isoformat()
        updated = 0
        with Session(engine) as session:
            statement = select(Movie).where(or_(Movie.media_path == path, Movie.folder_path == path))
            movies = [
                movie.model_dump()
                for movie in session.exec(statement).all()
                if movie.library_status not in {"ignored", "reverted"}
            ]
        for movie in movies:
            _, projected = event_store.append_and_project(
                "MovieMarkedMissing",
                "movie",
                movie["id"],
                {"movie_id": movie["id"], "missing_since": missing_at, "path": path},
            )
            if projected:
                updated += 1
        return updated

    def ignore_movie(self, movie_id: str) -> Optional[dict]:
        """Mark one movie as ignored so it is hidden from the normal library."""
        with Session(engine) as session:
            movie = session.get(Movie, movie_id)
            if not movie:
                return None
            payload = {"movie_id": movie_id, "title": movie.title, "year": movie.year}

        _, projected = event_store.append_and_project("MovieIgnored", "movie", movie_id, payload)
        return projected

    def cleanup_missing(self) -> int:
        """Delete records already marked as missing."""
        deleted_ids: list[str] = []
        with Session(engine) as session:
            deleted_ids = [movie.id for movie in session.exec(select(Movie).where(Movie.library_status == "missing")).all()]
            statement = delete(Movie).where(Movie.library_status == "missing")
            result = session.exec(statement)
            session.commit()
            deleted = result.rowcount or 0
        if deleted:
            event_store.safe_append(
                "MissingMoviesCleaned",
                "library",
                None,
                {"deleted": deleted, "movie_ids": deleted_ids[:200], "truncated": len(deleted_ids) > 200},
            )
        return deleted

    def clear_library(self):
        """Clear all movies from the library."""
        count = 0
        with Session(engine) as session:
            count = len(session.exec(select(Movie)).all())
            statement = delete(Movie)
            session.exec(statement)
            session.commit()
        event_store.safe_append("LibraryCleared", "library", None, {"deleted": count})

    def seed_test_data(self):
        """Populates the library with mock data from external JSON file."""
        try:
            with open(SEED_DATA_FILE, 'r') as f:
                movies_list = json.load(f)
        except FileNotFoundError:
            print(f"Warning: Seed file not found at {SEED_DATA_FILE}")
            movies_list = []
        
        # Add to DB
        self.add_movies(movies_list)
        event_store.safe_append("LibrarySeeded", "library", None, {"count": len(movies_list)})
        return movies_list

    def _get_by_media_path(self, session: Session, media_path: str) -> Optional[Movie]:
        statement = select(Movie).where(Movie.media_path == media_path)
        return session.exec(statement).first()

    def _with_added_at(self, movie_data: dict) -> dict:
        if movie_data.get("added_at"):
            return movie_data
        return {**movie_data, "added_at": self._fallback_added_at(movie_data)}

    def _fallback_added_at(self, movie_data: dict) -> str:
        return (
            movie_data.get("metadata_updated_at")
            or movie_data.get("last_seen_at")
            or datetime.now(timezone.utc).isoformat()
        )

    def _movie_event_payload(self, movie_data: dict) -> dict:
        payload = {
            field: movie_data.get(field)
            for field in SCAN_EVENT_FIELDS
            if movie_data.get(field) is not None
        }
        if payload.get("id") and not payload.get("movie_id"):
            payload["movie_id"] = payload["id"]
        return payload

    def _scan_events_for_existing(self, previous_movie: dict, movie_data: dict, movie_id: str) -> list[dict]:
        events = []
        current_payload = self._movie_event_payload({**previous_movie, **movie_data, "id": movie_id})
        if previous_movie.get("library_status") == "missing" and movie_data.get("library_status") == "available":
            events.append({
                "type": "MovieRestored",
                "aggregate_id": movie_id,
                "payload": current_payload,
                "project": True,
            })

        file_changes = self._file_observation_changes(previous_movie, movie_data)
        if file_changes:
            events.append({
                "type": "MovieFileObserved",
                "aggregate_id": movie_id,
                "payload": {
                    **current_payload,
                    **file_changes,
                },
                "project": False,
            })

        nfo_changes = self._nfo_metadata_changes(previous_movie, movie_data)
        if nfo_changes:
            events.append({
                "type": "MovieMetadataParsedFromNfo",
                "aggregate_id": movie_id,
                "payload": {
                    **self._nfo_metadata_payload({**previous_movie, **movie_data, "id": movie_id}),
                    **nfo_changes,
                },
                "project": False,
            })
        return events

    def _file_observation_changes(self, previous_movie: dict, movie_data: dict) -> Optional[dict]:
        previous = {}
        current = {}
        changed_fields = []
        for field in FILE_OBSERVED_FIELDS:
            if field not in movie_data:
                continue
            previous_value = previous_movie.get(field)
            current_value = movie_data.get(field)
            if previous_value != current_value:
                changed_fields.append(field)
                previous[field] = previous_value
                current[field] = current_value

        if not changed_fields:
            return None
        return {
            "changed_fields": changed_fields,
            "previous": previous,
            "current": current,
        }

    def _nfo_metadata_changes(self, previous_movie: dict, movie_data: dict) -> Optional[dict]:
        if not movie_data.get("nfo_fingerprint"):
            return None

        previous = {}
        current = {}
        changed_fields = []
        for field in NFO_SIGNATURE_FIELDS:
            if field not in movie_data:
                continue
            previous_value = previous_movie.get(field)
            current_value = movie_data.get(field)
            if previous_value != current_value:
                changed_fields.append(field)
                previous[field] = previous_value
                current[field] = current_value

        if not changed_fields:
            return None
        return {
            "changed_fields": changed_fields,
            "previous": previous,
            "current": current,
        }

    def _nfo_metadata_payload(self, movie_data: dict) -> dict:
        payload = {
            field: movie_data.get(field)
            for field in (*NFO_METADATA_FIELDS, *NFO_SIGNATURE_FIELDS)
            if movie_data.get(field) is not None
        }
        if payload.get("id") and not payload.get("movie_id"):
            payload["movie_id"] = payload["id"]
        return payload

    def _append_scan_events(
        self,
        events: list[dict],
        *,
        command_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ):
        for event in events:
            if event.get("project"):
                event_store.append_and_project(
                    event["type"],
                    "movie",
                    event["aggregate_id"],
                    event["payload"],
                    command_id=command_id,
                    correlation_id=correlation_id,
                )
            else:
                event_store.safe_append(
                    event["type"],
                    "movie",
                    event["aggregate_id"],
                    event["payload"],
                    command_id=command_id,
                    correlation_id=correlation_id,
                )

    def _event_types(self, events: list[dict]) -> list[str]:
        return [event["type"] for event in events if event.get("type")]

library_manager = LibraryManager()
