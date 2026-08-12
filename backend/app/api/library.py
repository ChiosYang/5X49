import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field as PydanticField

from app.api.common import DEFAULT_MEDIA_DIR, job_response
from app.jobs import job_runtime
from app.services.event_bus import library_event_bus
from app.services.library import library_manager
from app.services.library_sync import library_sync_service
from app.services.metadata.organizer import root_video_organizer
from app.services.settings import get_media_dir
from app.services.user_state import movie_user_state_manager
from app.services.watcher import library_watcher
from app.utils.security import validate_movie_id


router = APIRouter()


class MovieUserStateUpdate(BaseModel):
    watched: bool | None = None
    watched_at: str | None = None
    rating: int | None = PydanticField(default=None, ge=1, le=5)
    favorite: bool | None = None
    notes: str | None = None


@router.get("/library")
def get_library():
    """Get all movies in the local library."""
    return library_manager.get_movies()


@router.get("/watch-history")
def get_watch_history():
    """List watched movies with personal user state, newest first."""
    return movie_user_state_manager.watch_history()


@router.get("/library/root-videos")
def get_library_root_videos():
    """List direct video files in the media root that are waiting for organization."""
    try:
        return root_video_organizer.list_root_videos(get_media_dir() or DEFAULT_MEDIA_DIR)
    except (FileNotFoundError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/library/user-states")
def get_library_user_states():
    """List stored personal user states for library movies."""
    return movie_user_state_manager.list_all()


@router.get("/library/{movie_id}/user-state")
def get_library_movie_user_state(movie_id: str):
    """Get personal user state for one movie."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")
    if not library_manager.get_movie(movie_id):
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie_user_state_manager.get(movie_id)


@router.put("/library/{movie_id}/user-state")
def update_library_movie_user_state(movie_id: str, request: MovieUserStateUpdate):
    """Update personal user state for one movie."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")
    if not library_manager.get_movie(movie_id):
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie_user_state_manager.upsert(
        movie_id,
        watched=request.watched,
        watched_at=request.watched_at,
        rating=request.rating,
        favorite=request.favorite,
        notes=request.notes,
        fields_set=request.model_fields_set,
    )


@router.get("/library/{movie_id}")
def get_library_movie(movie_id: str):
    """Get details for a specific movie."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")

    movie = library_manager.get_movie(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie


@router.post("/library/seed")
def seed_library():
    """Seed the library with test data."""
    movies = library_manager.seed_test_data()
    library_event_bus.publish_library_changed("seed", count=len(movies))
    return movies


@router.post("/library/scan")
def scan_library(media_dir: str = Query(default=None)):
    """
    Scan a directory for TMM-scraped movies and add them to library.
    If no media_dir is provided, uses the configured MEDIA_DIR from settings.
    """
    target_dir = media_dir or get_media_dir() or DEFAULT_MEDIA_DIR

    if not os.path.exists(target_dir):
        raise HTTPException(status_code=400, detail=f"Directory not found: {target_dir}")

    job = job_runtime.enqueue(
        "library.reconcile",
        {"media_dir": target_dir},
        dedupe_key=f"library.reconcile:{target_dir}",
    )
    return job_response(job, "Library scan queued")


@router.post("/library/reconcile")
def reconcile_library(media_dir: str = Query(default=None)):
    """Scan all configured media folders and mark disappeared movies as missing."""
    target_dir = media_dir or get_media_dir() or DEFAULT_MEDIA_DIR
    if not os.path.exists(target_dir):
        raise HTTPException(status_code=400, detail=f"Directory not found: {target_dir}")

    job = job_runtime.enqueue(
        "library.reconcile",
        {"media_dir": target_dir},
        dedupe_key=f"library.reconcile:{target_dir}",
    )
    return job_response(job, "Library reconcile queued")


@router.post("/library/scan-folder")
def scan_library_folder(folder_path: str):
    """Scan one movie folder and upsert its movie record."""
    if not Path(folder_path).exists():
        raise HTTPException(status_code=404, detail="Movie folder or video file not found")
    job = job_runtime.enqueue(
        "library.scan_folder",
        {"folder_path": folder_path},
        dedupe_key=f"library.scan_folder:{folder_path}",
    )
    return job_response(job, "Folder scan queued")


@router.post("/library/{movie_id}/refresh")
def refresh_library_movie(movie_id: str):
    """Refresh one movie from its known local folder."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")

    if not library_manager.get_movie(movie_id):
        raise HTTPException(status_code=404, detail="Movie not found")
    job = job_runtime.enqueue(
        "library.refresh_movie",
        {"movie_id": movie_id},
        dedupe_key=f"library.refresh_movie:{movie_id}",
    )
    return job_response(job, "Movie refresh queued")


@router.post("/library/{movie_id}/ignore")
def ignore_library_movie(movie_id: str):
    """Mark one movie as ignored so it is hidden from normal library views."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")

    movie = library_manager.ignore_movie(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    library_event_bus.publish_library_changed("ignored", movie_id=movie_id)
    return {"status": "success", "movie": movie}


@router.get("/library/sync/status")
def get_library_sync_status():
    """Get latest library sync and watcher status."""
    return {
        "sync": library_sync_service.get_status(),
        "watcher": library_watcher.status(),
    }


@router.post("/library/analyze/{movie_id}")
def trigger_analysis(movie_id: str):
    """Manually trigger analysis for a specific movie."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")
    if not library_manager.get_movie(movie_id):
        raise HTTPException(status_code=404, detail="Movie not found")

    job = job_runtime.enqueue(
        "analysis.analyze_movie",
        {"movie_id": movie_id},
        dedupe_key=f"analysis.analyze_movie:{movie_id}",
    )
    return job_response(job, f"Analysis queued for {movie_id}")


@router.delete("/library")
def clear_library():
    """Clear all movies from the library."""
    library_manager.clear_library()
    library_event_bus.publish_library_changed("clear")
    return {"message": "Library cleared"}


@router.delete("/library/data")
def clear_library_data():
    """Clear all database-backed library data while preserving settings and media files."""
    deleted = library_manager.clear_all_data()
    library_event_bus.publish_library_changed("data_clear", deleted=deleted)
    return {
        "status": "success",
        "message": "Library data cleared",
        "deleted": deleted,
    }


@router.delete("/library/missing")
def cleanup_missing_library_movies():
    """Delete records already marked as missing."""
    deleted = library_manager.cleanup_missing()
    if deleted:
        library_event_bus.publish_library_changed("missing_cleanup", deleted=deleted)
    return {"status": "success", "deleted": deleted}
