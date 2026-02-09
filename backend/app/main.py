from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.services.historian import FilmHistorian
from app.services.library import library_manager
from app.services.scanner import NFOScanner
from app.services.analysis import analysis_service
from app.database import create_db_and_tables
from app.utils.security import validate_movie_id
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

# Enable CORS for frontend
# In production, replace localhost with your actual domain
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # Add production domain here when deployed
    # "https://yourdomain.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Configuration for media directory (can be overridden via env var)
# Security: Validate that MEDIA_DIR is within allowed paths
from pathlib import Path

ALLOWED_BASE_DIR = "/Users/alicolia/Projects"
DEFAULT_MEDIA_DIR = f"{ALLOWED_BASE_DIR}/movies-nfo-test"
MEDIA_DIR = os.getenv("MEDIA_DIR", DEFAULT_MEDIA_DIR)

# Validate media directory path
try:
    media_path = Path(MEDIA_DIR).resolve()
    if not str(media_path).startswith(ALLOWED_BASE_DIR):
        raise ValueError(f"MEDIA_DIR must be within {ALLOWED_BASE_DIR}")
    MEDIA_DIR = str(media_path)
except Exception as e:
    print(f"⚠️ Warning: Invalid MEDIA_DIR ({e}), using default")
    MEDIA_DIR = DEFAULT_MEDIA_DIR

# Mount media directory for static file serving (local images)
if os.path.exists(MEDIA_DIR):
    app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
else:
    print(f"⚠️ Warning: MEDIA_DIR does not exist: {MEDIA_DIR}")

historian = FilmHistorian()

@app.get("/")
def read_root():
    return {"message": "Film Genealogy API is running", "media_dir": MEDIA_DIR}

@app.get("/analyze/{movie_name}")
def analyze_movie(movie_name: str):
    result = historian.analyze_genealogy(movie_name)
    if not result:
        raise HTTPException(status_code=404, detail="Film not found or analysis failed")
    return result

@app.get("/library")
def get_library():
    """Get all movies in the local library."""
    return library_manager.get_movies()

@app.get("/library/{movie_id}")
def get_library_movie(movie_id: str):
    """Get details for a specific movie."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")
    
    movie = library_manager.get_movie(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie

@app.post("/library/seed")
def seed_library():
    """Seed the library with test data."""
    return library_manager.seed_test_data()

@app.post("/library/scan")
def scan_library(background_tasks: BackgroundTasks, media_dir: str = Query(default=None)):
    """
    Scan a directory for TMM-scraped movies and add them to library.
    If no media_dir is provided, uses the default MEDIA_DIR.
    """
    target_dir = media_dir or MEDIA_DIR
    
    if not os.path.exists(target_dir):
        raise HTTPException(status_code=400, detail=f"Directory not found: {target_dir}")
    
    print(f"\n🔍 Scanning media directory: {target_dir}")
    scanner = NFOScanner(target_dir)
    movies = scanner.scan()
    
    added = library_manager.add_movies(movies)
    
    # Queue analysis for all scanned movies
    # Analysis service will skip already completed ones
    for movie in movies:
        background_tasks.add_task(analysis_service.analyze_movie, movie["id"])
    
    return {
        "scanned": len(movies),
        "added": added,
        "queued_for_analysis": len(movies),
        "media_dir": target_dir
    }

@app.post("/library/analyze/{movie_id}")
def trigger_analysis(movie_id: str, background_tasks: BackgroundTasks):
    """Manually trigger analysis for a specific movie."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")
    
    background_tasks.add_task(analysis_service.analyze_movie, movie_id)
    return {"message": f"Analysis queued for {movie_id}"}

@app.delete("/library")
def clear_library():
    """Clear all movies from the library."""
    library_manager.clear_library()
    return {"message": "Library cleared"}
