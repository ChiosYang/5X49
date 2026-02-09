import json
import os
from typing import List, Dict, Optional
from pathlib import Path
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
                if existing_movie:
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

    def get_movies(self) -> List[dict]:
        with Session(engine) as session:
            statement = select(Movie)
            results = session.exec(statement).all()
            # Convert to dicts for frontend compatibility
            return [movie.model_dump() for movie in results]

    def get_movie(self, movie_id: str) -> Optional[dict]:
        with Session(engine) as session:
            movie = session.get(Movie, movie_id)
            return movie.model_dump() if movie else None

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

library_manager = LibraryManager()
