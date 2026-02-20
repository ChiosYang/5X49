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
from pathlib import Path

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

# Health check for Docker
@app.get("/health")
def health_check():
    return {"status": "healthy"}

# CORS - configurable via environment variable
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000"
).split(",")


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

from app.services.settings import get_default_settings, save_settings, get_available_models, get_current_model, set_current_model, get_base_url, set_base_url, refresh_models_cache, get_media_dir, set_media_dir, get_language, set_language

# Configuration for media directory
# Prioritize settings.json, then env var, then default
DEFAULT_MEDIA_DIR = os.getenv("MEDIA_DIR", "/media")
MEDIA_DIR = get_media_dir() or DEFAULT_MEDIA_DIR

# Mount media directory for static file serving (local images)
# Dynamic mounting is tricky in FastAPI, so we mount the current MEDIA_DIR
# If user changes it, they might need to restart or we need a way to remount
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
    If no media_dir is provided, uses the configured MEDIA_DIR from settings.
    """
    # Fetch latest setting dynamically
    target_dir = media_dir or get_media_dir() or DEFAULT_MEDIA_DIR
    
    if not os.path.exists(target_dir):
        raise HTTPException(status_code=400, detail=f"Directory not found: {target_dir}")
    
    print(f"\n🔍 Scanning media directory: {target_dir}")
    scanner = NFOScanner(target_dir)
    movies = scanner.scan()
    
    added = library_manager.add_movies(movies)
    
    # Analysis is now triggered manually or via separate process
    # for movie in movies:
    #     background_tasks.add_task(analysis_service.analyze_movie, movie["id"])
    
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

# Settings endpoints
from app.services.settings import load_settings, save_settings, get_current_model, set_current_model, get_base_url, set_base_url, refresh_models_cache

@app.get("/settings")
def get_settings():
    """Get current system settings"""
    settings = load_settings()
    return settings

@app.get("/settings/model")
def get_model_setting():
    """Get current model configuration"""
    settings = load_settings()
    return {
        "current_model": settings.get("model_name"),
        "available_models": settings.get("available_models", [])
    }

@app.put("/settings/model")
def update_model_setting(model_name: str):
    """Update the current model"""
    success = set_current_model(model_name)
    if success:
        return {"message": "Model updated", "model_name": model_name}
    else:
        raise HTTPException(status_code=500, detail="Failed to save settings")

@app.get("/settings/media-dir")
def get_media_directory():
    return {"media_dir": get_media_dir()}

@app.put("/settings/media-dir")
def update_media_directory(media_dir: str):
    if not media_dir:
        raise HTTPException(status_code=400, detail="Media directory cannot be empty")
    
    # Optional: Check if directory exists, but don't strictly block it (could be mounted later)
    if not os.path.exists(media_dir):
        print(f"Warning: Setting non-existent media_dir: {media_dir}")

    success = set_media_dir(media_dir)
    if success:
        return {"status": "success", "media_dir": media_dir, "message": "Media directory updated. Please restart server to apply changes for static file serving."}
    else:
        raise HTTPException(status_code=500, detail="Failed to save settings")

@app.get("/settings/language")
def get_language_setting():
    return {"language": get_language()}

@app.put("/settings/language")
def update_language_setting(language: str):
    if language not in ["zh", "en"]:
        raise HTTPException(status_code=400, detail="Language must be 'zh' or 'en'")
    success = set_language(language)
    if success:
        return {"status": "success", "language": language}
    else:
        raise HTTPException(status_code=500, detail="Failed to save settings")

@app.get("/settings/base-url")
def get_base_url_setting():
    """Get current API base URL"""
    return {
        "base_url": get_base_url()
    }

@app.put("/settings/base-url")
def update_base_url_setting(base_url: str):
    """Update the API base URL"""
    success = set_base_url(base_url)
    if success:
        return {"message": "Base URL updated", "base_url": base_url}
    else:
        raise HTTPException(status_code=500, detail="Failed to save settings")
@app.post("/settings/models/refresh")
def refresh_models():
    """Force refresh the available models from OpenRouter API"""
    models = refresh_models_cache()
    if models:
        return {
            "message": "Models refreshed successfully",
            "count": len(models),
            "models": models
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to refresh models")

@app.get("/settings/test-api-key")
def test_api_key():
    """Test if OpenRouter API key is working"""
    import requests
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return {
            "status": "error",
            "message": "OPENROUTER_API_KEY not configured"
        }
    
    try:
        # Test API by fetching models list
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            model_count = len(data.get("data", []))
            return {
                "status": "success",
                "message": f"API key is valid. {model_count} models available.",
                "model_count": model_count
            }
        elif response.status_code == 401:
            return {
                "status": "error",
                "message": "Invalid API key. Please check your OPENROUTER_API_KEY."
            }
        else:
            return {
                "status": "error",
                "message": f"API returned status code {response.status_code}"
            }
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "message": "Request timeout. Please check your network connection."
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error testing API: {str(e)}"
        }

@app.get("/sys/list-dirs")
def list_directories(path: str = Query(default="/")):
    """
    List subdirectories in the given path.
    Used for the frontend file browser.
    """
    # Security: In a real app, you might restrict this to certain roots.
    # For a personal media server, full access is usually expected.
    
    target_path = Path(path).resolve()
    
    if not target_path.exists():
        # Fallback to root if path doesn't exist
        target_path = Path("/")
    
    if not target_path.is_dir():
        target_path = target_path.parent

    dirs = []
    try:
        # List items
        for item in target_path.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                dirs.append({
                    "name": item.name,
                    "path": str(item.resolve())
                })
        
        # Sort by name
        dirs.sort(key=lambda x: x["name"].lower())
        
        return {
            "current_path": str(target_path),
            "parent_path": str(target_path.parent) if target_path != target_path.parent else None,
            "directories": dirs
        }
    except Exception as e:
        print(f"Error listing directories at {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/sys/scan-library")
def trigger_manual_scan(background_tasks: BackgroundTasks):
    """
    Manually trigger a library scan.
    """
    try:
        # Use background task to avoid blocking the request
        # Pass the background_tasks object to scan_library so it can queue analysis tasks
        background_tasks.add_task(scan_library, background_tasks=background_tasks, media_dir=None)
        return {"status": "success", "message": "Library scan started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start scan: {str(e)}")
