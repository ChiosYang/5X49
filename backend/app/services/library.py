import json
import os
from typing import List, Dict, Optional
from pathlib import Path

# Configuration via environment variables
LIBRARY_FILE = os.getenv("LIBRARY_FILE", "library.json")
SEED_DATA_FILE = Path(__file__).parent.parent / "data" / "seed_movies.json"

class LibraryManager:
    def __init__(self):
        self.library_file = LIBRARY_FILE
        self._ensure_library_file()

    def _ensure_library_file(self):
        if not os.path.exists(self.library_file):
            self.save_library({"scanned_paths": [], "movies": {}})

    def load_library(self) -> Dict:
        try:
            with open(self.library_file, 'r') as f:
                return json.load(f)
        except:
            return {"scanned_paths": [], "movies": {}}

    def save_library(self, data: Dict):
        with open(self.library_file, 'w') as f:
            json.dump(data, f, indent=2)

    def get_movies(self) -> List[Dict]:
        data = self.load_library()
        # Convert dictionary to list for frontend
        return list(data.get("movies", {}).values())

    def get_movie(self, movie_id: str) -> Optional[Dict]:
        data = self.load_library()
        return data.get("movies", {}).get(movie_id)

    def seed_test_data(self):
        """Populates the library with mock data from external JSON file."""
        try:
            with open(SEED_DATA_FILE, 'r') as f:
                movies_list = json.load(f)
        except FileNotFoundError:
            print(f"Warning: Seed file not found at {SEED_DATA_FILE}")
            movies_list = []
        
        # Convert list to dict keyed by ID
        mock_movies = {movie["id"]: movie for movie in movies_list}
        
        data = self.load_library()
        data["movies"] = mock_movies
        self.save_library(data)
        return list(mock_movies.values())

    def add_movies(self, movies: list[dict]) -> int:
        """Add multiple movies to the library (from scanner)."""
        data = self.load_library()
        added = 0
        for movie in movies:
            movie_id = movie.get("id")
            if movie_id and movie_id not in data["movies"]:
                data["movies"][movie_id] = movie
                added += 1
        self.save_library(data)
        return added

    def clear_library(self):
        """Clear all movies from the library."""
        self.save_library({"scanned_paths": [], "movies": {}})

library_manager = LibraryManager()
