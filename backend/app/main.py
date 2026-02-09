from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.services.historian import FilmHistorian
from app.services.library import library_manager
from app.services.scanner import NFOScanner
from app.services.analysis import analysis_service
from app.database import create_db_and_tables
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration for media directory (can be overridden via env var)
MEDIA_DIR = os.getenv("MEDIA_DIR", "/Users/alicolia/Projects/movies-nfo-test")

# Mount media directory for static file serving (local images)
if os.path.exists(MEDIA_DIR):
    app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

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
    background_tasks.add_task(analysis_service.analyze_movie, movie_id)
    return {"message": f"Analysis queued for {movie_id}"}

@app.delete("/library")
def clear_library():
    """Clear all movies from the library."""
    library_manager.clear_library()
    return {"message": "Library cleared"}
