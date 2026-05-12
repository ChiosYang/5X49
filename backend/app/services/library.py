import json
import os
from typing import List, Dict, Optional
from pathlib import Path
from sqlalchemy import or_
from sqlmodel import Session, select, delete
from app.database import engine, create_db_and_tables, get_session
from app.models import Movie

# Configuration via environment variables
SEED_DATA_FILE = Path(__file__).parent.parent / "data" / "seed_movies.json"

class LibraryManager:
    def __init__(self):
        # We handle DB creation in main.py, but good to ensure tables exist
        pass

    def add_movies(self, movies_data: list[dict]) -> int:
        """Add multiple movies to the library (upsert)."""
        added = 0
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
                    if existing_movie.library_status == "ignored" and movie_dict.get("library_status") == "available":
                        movie_dict = {**movie_dict, "library_status": "ignored", "missing_since": None}
                    # Update fields
                    for key, value in movie_dict.items():
                        setattr(existing_movie, key, value)
                    session.add(existing_movie)
                else:
                    # Create new
                    new_movie = Movie(**movie_dict)
                    session.add(new_movie)
                    added += 1
            session.commit()
        return added

    def upsert_movie(self, movie_data: dict, preserve_id: Optional[str] = None) -> Optional[dict]:
        """Insert or update one movie and return the stored record."""
        movie_id = preserve_id or movie_data.get("id")
        if not movie_id:
            return None

        movie_data = {**movie_data, "id": movie_id}
        with Session(engine) as session:
            existing_movie = session.get(Movie, movie_id)
            if not existing_movie and movie_data.get("media_path"):
                existing_movie = self._get_by_media_path(session, movie_data["media_path"])

            if existing_movie:
                if existing_movie.library_status == "ignored" and movie_data.get("library_status") == "available":
                    movie_data = {**movie_data, "library_status": "ignored", "missing_since": None}
                for key, value in movie_data.items():
                    setattr(existing_movie, key, value)
                session.add(existing_movie)
                session.commit()
                session.refresh(existing_movie)
                return existing_movie.model_dump()

            new_movie = Movie(**movie_data)
            session.add(new_movie)
            session.commit()
            session.refresh(new_movie)
            return new_movie.model_dump()

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
            statement = select(Movie).where(Movie.library_status.not_in(["missing", "ignored"]))
            movies = session.exec(statement).all()
            for movie in movies:
                if not movie.last_seen_at or movie.last_seen_at < seen_at:
                    movie.library_status = "missing"
                    movie.missing_since = missing_at
                    session.add(movie)
                    updated += 1
            session.commit()
        return updated

    def mark_path_missing(self, path: str) -> int:
        from datetime import datetime, timezone

        missing_at = datetime.now(timezone.utc).isoformat()
        updated = 0
        with Session(engine) as session:
            statement = select(Movie).where(or_(Movie.media_path == path, Movie.folder_path == path))
            movies = session.exec(statement).all()
            for movie in movies:
                if movie.library_status == "ignored":
                    continue
                movie.library_status = "missing"
                movie.missing_since = missing_at
                session.add(movie)
                updated += 1
            session.commit()
        return updated

    def ignore_movie(self, movie_id: str) -> Optional[dict]:
        """Mark one movie as ignored so it is hidden from the normal library."""
        with Session(engine) as session:
            movie = session.get(Movie, movie_id)
            if not movie:
                return None
            movie.library_status = "ignored"
            movie.missing_since = None
            session.add(movie)
            session.commit()
            session.refresh(movie)
            return movie.model_dump()

    def cleanup_missing(self) -> int:
        """Delete records already marked as missing."""
        with Session(engine) as session:
            statement = delete(Movie).where(Movie.library_status == "missing")
            result = session.exec(statement)
            session.commit()
            return result.rowcount or 0

    def clear_library(self):
        """Clear all movies from the library."""
        with Session(engine) as session:
            statement = delete(Movie)
            session.exec(statement)
            session.commit()

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
        return movies_list

    def _get_by_media_path(self, session: Session, media_path: str) -> Optional[Movie]:
        statement = select(Movie).where(Movie.media_path == media_path)
        return session.exec(statement).first()

library_manager = LibraryManager()
