from sqlmodel import Session, select
import json
import logging
from pathlib import Path
from app.database import engine, create_db_and_tables
from app.models import Movie

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")

LIBRARY_FILE = Path("library.json")

def migrate():
    if not LIBRARY_FILE.exists():
        logger.error(f"Library file not found: {LIBRARY_FILE}")
        return

    logger.info("Starting migration...")
    
    # Create tables if they don't exist
    create_db_and_tables()

    with open(LIBRARY_FILE, "r") as f:
        data = json.load(f)
        movies_data = data.get("movies", {})
    
    count = 0
    with Session(engine) as session:
        for movie_id, movie_dict in movies_data.items():
            # Check if exists
            existing = session.get(Movie, movie_id)
            if existing:
                logger.info(f"Skipping existing movie: {movie_id}")
                continue
            
            try:
                # Create Movie instance
                # The dictionary keys match the model fields mostly
                # Handling genres and actors: if they are lists/dicts in JSON, 
                # SQLModel + valid types should handle it if the db supports JSON,
                # but SQLite JSON support via SQLAlchemy is tricky without specific setup.
                # However, let's try direct assignment.
                # If there are extra fields in JSON not in model, they will be ignored by ** unpacking if we use exclude_unset or similar,
                # but direct **movie_dict might fail if there are extra keys.
                # Let's filter keys based on model fields.
                
                model_fields = Movie.model_fields.keys()
                filtered_data = {k: v for k, v in movie_dict.items() if k in model_fields}
                
                movie = Movie(**filtered_data)
                session.add(movie)
                count += 1
            except Exception as e:
                logger.error(f"Error migrating movie {movie_id}: {e}")

        session.commit()
    
    logger.info(f"Migration complete. Imported {count} movies.")

if __name__ == "__main__":
    migrate()
