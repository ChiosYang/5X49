from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field as PydanticField
from app.services.historian import FilmHistorian
from app.services.event_bus import library_event_bus
from app.services.event_backfill import movie_discovered_backfill, movie_replay_backfill
from app.services.event_store import event_store
from app.services.external_scores import external_score_service
from app.jobs import job_runtime
from app.services.library import library_manager
from app.services.artwork_cache import ARTWORK_CACHE_DIR
from app.services.library_sync import library_sync_service
from app.services.watcher import library_watcher
from app.services.metadata.models import ArtworkSelection, BatchScrapeOptions, RootOrganizeConfirmRequest, RootOrganizeOptions, ScrapeOptions
from app.services.metadata.organizer import root_video_organizer
from app.services.metadata.scraper import metadata_scraper
from app.services.nfo_signature_dry_run import nfo_signature_dry_run
from app.services.operation_dry_run import operation_dry_run
from app.services.operation_restore import operation_restore
from app.services.projections.movie_rebuild import ProjectionRebuildBlocked, movie_projection_dry_run
from app.services.projections.movie_timeline import movie_timeline_dry_run
from app.services.timeline_restore import TimelineRestoreBlocked, movie_timeline_restore
from app.services.user_state import movie_user_state_manager
from app.database import create_db_and_tables
from app.utils.security import validate_movie_id
import os
from pathlib import Path
import requests


class TmdbApiKeyUpdate(BaseModel):
    api_key: str = ""


class OperationRestoreRequest(BaseModel):
    correlation_id: str | None = None
    command_id: str | None = None
    actions: list[str] | None = None
    limit: int = 500


class TimelineRestoreRequest(BaseModel):
    before_event_id: str | None = None
    at: str | None = None
    restore_fields: list[str] | None = None
    restore_files: list[str] | None = None
    allow_partial: bool = False


class MovieUserStateUpdate(BaseModel):
    watched: bool | None = None
    watched_at: str | None = None
    rating: int | None = PydanticField(default=None, ge=1, le=5)
    favorite: bool | None = None
    notes: str | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    job_runtime.start()
    if get_watch_library():
        library_watcher.start()
    yield
    job_runtime.stop()
    library_watcher.stop()

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

from app.services.settings import get_default_settings, save_settings, get_available_models, get_current_model, set_current_model, get_base_url, set_base_url, refresh_models_cache, get_media_dir, set_media_dir, get_language, set_language, get_watch_library, set_watch_library, get_tmdb_key_status, set_tmdb_api_key, get_artwork_language, set_artwork_language

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

ARTWORK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/artwork-cache", StaticFiles(directory=ARTWORK_CACHE_DIR), name="artwork-cache")

historian = FilmHistorian()


def job_response(job: dict, message: str) -> dict:
    return {
        "status": "queued",
        "message": message,
        "job_id": job["id"],
        "job": job,
    }

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

@app.get("/watch-history")
def get_watch_history():
    """List watched movies with personal user state, newest first."""
    return movie_user_state_manager.watch_history()

@app.get("/jobs")
def list_jobs(
    status: str | None = Query(default=None),
    type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List recent background jobs."""
    return job_runtime.list(status=status, job_type=type, limit=limit)

@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    """Get one background job by ID."""
    job = job_runtime.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    """Request cancellation for one background job."""
    job = job_runtime.cancel(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.post("/jobs/{job_id}/retry")
def retry_job(job_id: str):
    """Retry a failed or cancelled background job."""
    existing_job = job_runtime.get(job_id)
    if not existing_job:
        raise HTTPException(status_code=404, detail="Job not found")
    if existing_job.get("status") not in {"failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Only failed or cancelled jobs can be retried")
    job = job_runtime.retry(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_response(job, "Job retry queued")

@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    """Delete a completed, failed, or cancelled background job."""
    deleted = job_runtime.delete(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found or still active")
    return {"status": "success", "deleted": True}

@app.post("/library/external-scores/refresh")
def refresh_library_external_scores(force: bool = Query(default=False)):
    """Start a background refresh of external score sources for available movies."""
    job = job_runtime.enqueue(
        "external_scores.refresh_library",
        {"force": force},
        dedupe_key=f"external_scores.refresh_library:{force}",
    )
    return job_response(job, "External score refresh queued")

@app.get("/library/external-scores/status")
def get_library_external_scores_status():
    """Get latest external score refresh status."""
    return external_score_service.get_status()

@app.get("/metadata/search")
def search_metadata(query: str, year: int | None = Query(default=None), language: str | None = Query(default=None)):
    """Search TMDB movie metadata using the configured TMDB_API_KEY."""
    try:
        return [candidate.model_dump() for candidate in metadata_scraper.search(query, year, language)]
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Metadata search failed: {str(exc)}")

@app.get("/metadata/movie/{tmdb_id}")
def get_metadata_movie(tmdb_id: int, language: str | None = Query(default=None)):
    """Get one TMDB movie as a scored candidate for manual confirmation."""
    try:
        return metadata_scraper.get_candidate(tmdb_id, language).model_dump()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 502
        raise HTTPException(status_code=status_code, detail=f"TMDB movie lookup failed: {str(exc)}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TMDB movie lookup failed: {str(exc)}")

@app.get("/library/events")
async def get_library_events(request: Request):
    """Subscribe to library change events via Server-Sent Events."""
    return StreamingResponse(
        library_event_bus.subscribe(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@app.get("/library/root-videos")
def get_library_root_videos():
    """List direct video files in the media root that are waiting for organization."""
    try:
        return root_video_organizer.list_root_videos(get_media_dir() or DEFAULT_MEDIA_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/library/audit-events")
def get_library_audit_events(
    aggregate_type: str | None = Query(default=None),
    aggregate_id: str | None = Query(default=None),
    type: str | None = Query(default=None),
    command_id: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    """List persisted library audit events."""
    return event_store.list(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=type,
        command_id=command_id,
        correlation_id=correlation_id,
        limit=limit,
    )

@app.get("/library/{movie_id}/audit-events")
def get_library_movie_audit_events(
    movie_id: str,
    type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    """List persisted audit events for a specific movie."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")
    if not library_manager.get_movie(movie_id):
        raise HTTPException(status_code=404, detail="Movie not found")
    return event_store.list(
        aggregate_type="movie",
        aggregate_id=movie_id,
        event_type=type,
        limit=limit,
    )

@app.get("/library/user-states")
def get_library_user_states():
    """List stored personal user states for library movies."""
    return movie_user_state_manager.list_all()

@app.get("/library/{movie_id}/user-state")
def get_library_movie_user_state(movie_id: str):
    """Get personal user state for one movie."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")
    if not library_manager.get_movie(movie_id):
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie_user_state_manager.get(movie_id)

@app.put("/library/{movie_id}/user-state")
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

@app.get("/library/{movie_id}/timeline/state")
def get_library_movie_timeline_state(
    movie_id: str,
    before_event_id: str | None = Query(default=None),
    at: str | None = Query(default=None),
):
    """Dry-run a movie's historical state at one timeline cutoff."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")
    if not library_manager.get_movie(movie_id):
        raise HTTPException(status_code=404, detail="Movie not found")
    try:
        return movie_timeline_dry_run.state(movie_id=movie_id, before_event_id=before_event_id, at=at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.get("/library/{movie_id}/timeline/restore-preview")
def get_library_movie_timeline_restore_preview(
    movie_id: str,
    before_event_id: str | None = Query(default=None),
    at: str | None = Query(default=None),
):
    """Preview field and file recoverability for one movie timeline cutoff."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")
    if not library_manager.get_movie(movie_id):
        raise HTTPException(status_code=404, detail="Movie not found")
    try:
        return movie_timeline_dry_run.restore_preview(movie_id=movie_id, before_event_id=before_event_id, at=at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/library/{movie_id}/timeline/restore")
def restore_library_movie_timeline(movie_id: str, request: TimelineRestoreRequest):
    """Execute supported timeline compensation actions for one movie."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")
    if not library_manager.get_movie(movie_id):
        raise HTTPException(status_code=404, detail="Movie not found")
    try:
        result = movie_timeline_restore.run(
            movie_id=movie_id,
            before_event_id=request.before_event_id,
            at=request.at,
            restore_fields=request.restore_fields,
            restore_files=request.restore_files,
            allow_partial=request.allow_partial,
        )
    except TimelineRestoreBlocked as exc:
        raise HTTPException(status_code=409, detail=exc.report)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if result["restored"]:
        library_event_bus.publish_library_changed("timeline_restored", movie_id=movie_id)
    return result

@app.get("/library/operations/dry-run")
def dry_run_library_operation(
    correlation_id: str | None = Query(default=None),
    command_id: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=500),
):
    """Run a read-only consistency check for one correlated library operation."""
    try:
        return operation_dry_run.run(correlation_id=correlation_id, command_id=command_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/library/operations/restore")
def restore_library_operation(request: OperationRestoreRequest):
    """Execute supported compensation actions for one correlated library operation."""
    if not request.correlation_id and not request.command_id:
        raise HTTPException(status_code=400, detail="correlation_id or command_id is required")
    try:
        result = operation_restore.run(
            correlation_id=request.correlation_id,
            command_id=request.command_id,
            actions=request.actions,
            limit=request.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if result["restored"]:
        library_event_bus.publish_library_changed("operation_restored")
    return result

@app.post("/library/projections/movie/rebuild")
def rebuild_movie_projection_dry_run(
    dry_run: bool = Query(default=True),
    movie_id: str | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
    since: str | None = Query(default=None),
    base: str = Query(default="current"),
    confirmation_token: str | None = Query(default=None),
):
    """Run or execute a controlled Movie projection rebuild."""
    if movie_id:
        if not validate_movie_id(movie_id):
            raise HTTPException(status_code=400, detail="Invalid movie ID format")
        if not library_manager.get_movie(movie_id):
            raise HTTPException(status_code=404, detail="Movie not found")
    try:
        result = movie_projection_dry_run.run(
            dry_run=dry_run,
            movie_id=movie_id,
            limit=limit,
            since=since,
            base=base,
            confirmation_token=confirmation_token,
        )
    except ProjectionRebuildBlocked as exc:
        raise HTTPException(status_code=409, detail=exc.report)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not dry_run and result.get("status") == "rebuilt":
        library_event_bus.publish_library_changed("projection_rebuilt", movie_id=movie_id)
    return result

@app.post("/library/events/backfill/movie-discovered")
def backfill_movie_discovered_events(
    dry_run: bool = Query(default=True),
    movie_id: str | None = Query(default=None),
    sample_limit: int = Query(default=20, ge=0, le=50),
):
    """Backfill missing MovieDiscovered initialization events for existing movies."""
    if movie_id:
        if not validate_movie_id(movie_id):
            raise HTTPException(status_code=400, detail="Invalid movie ID format")
        if not library_manager.get_movie(movie_id):
            raise HTTPException(status_code=404, detail="Movie not found")
    return movie_discovered_backfill.run(dry_run=dry_run, movie_id=movie_id, sample_limit=sample_limit)

@app.post("/library/events/backfill/movie-replay")
def backfill_movie_replay_events(
    dry_run: bool = Query(default=True),
    movie_id: str | None = Query(default=None),
    sample_limit: int = Query(default=20, ge=0, le=50),
):
    """Backfill replay migration events for existing movie rows and files."""
    if movie_id:
        if not validate_movie_id(movie_id):
            raise HTTPException(status_code=400, detail="Invalid movie ID format")
        if not library_manager.get_movie(movie_id):
            raise HTTPException(status_code=404, detail="Movie not found")
    return movie_replay_backfill.run(dry_run=dry_run, movie_id=movie_id, sample_limit=sample_limit)

@app.post("/library/events/dry-run/nfo-signatures")
def dry_run_nfo_signatures(
    media_dir: str | None = Query(default=None),
    folder_path: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    include_unchanged: bool = Query(default=False),
):
    """Read-only check for NFO signature changes discovered by a scan."""
    try:
        return nfo_signature_dry_run.run(
            media_dir=media_dir,
            folder_path=folder_path,
            limit=limit,
            include_unchanged=include_unchanged,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.get("/library/{movie_id}")
def get_library_movie(movie_id: str):
    """Get details for a specific movie."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")
    
    movie = library_manager.get_movie(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie

@app.post("/library/{movie_id}/external-scores/refresh")
def refresh_library_movie_external_scores(movie_id: str, force: bool = Query(default=False)):
    """Refresh external score sources for a specific movie."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")

    if not library_manager.get_movie(movie_id):
        raise HTTPException(status_code=404, detail="Movie not found")
    job = job_runtime.enqueue(
        "external_scores.refresh_movie",
        {"movie_id": movie_id, "force": force},
        dedupe_key=f"external_scores.refresh_movie:{movie_id}:{force}",
    )
    return job_response(job, "Movie external score refresh queued")

@app.post("/library/seed")
def seed_library():
    """Seed the library with test data."""
    movies = library_manager.seed_test_data()
    library_event_bus.publish_library_changed("seed", count=len(movies))
    return movies

@app.post("/library/scan")
def scan_library(media_dir: str = Query(default=None)):
    """
    Scan a directory for TMM-scraped movies and add them to library.
    If no media_dir is provided, uses the configured MEDIA_DIR from settings.
    """
    # Fetch latest setting dynamically
    target_dir = media_dir or get_media_dir() or DEFAULT_MEDIA_DIR
    
    if not os.path.exists(target_dir):
        raise HTTPException(status_code=400, detail=f"Directory not found: {target_dir}")
    
    job = job_runtime.enqueue(
        "library.reconcile",
        {"media_dir": target_dir},
        dedupe_key=f"library.reconcile:{target_dir}",
    )
    return job_response(job, "Library scan queued")

@app.post("/library/reconcile")
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

@app.post("/library/scan-folder")
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

@app.post("/library/{movie_id}/refresh")
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

@app.get("/library/{movie_id}/artwork")
def get_library_movie_artwork(movie_id: str):
    """List selectable TMDB posters and backdrops for one movie."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")

    try:
        return metadata_scraper.artwork_options(movie_id).model_dump()
    except LookupError:
        raise HTTPException(status_code=404, detail="Movie not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 502
        raise HTTPException(status_code=status_code, detail=f"TMDB artwork lookup failed: {str(exc)}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TMDB artwork lookup failed: {str(exc)}")

@app.put("/library/{movie_id}/artwork")
def update_library_movie_artwork(movie_id: str, selection: ArtworkSelection):
    """Apply a selected TMDB poster and/or backdrop to one movie."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")

    try:
        return metadata_scraper.apply_artwork(movie_id, selection)
    except LookupError:
        raise HTTPException(status_code=404, detail="Movie not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 502
        raise HTTPException(status_code=status_code, detail=f"TMDB artwork update failed: {str(exc)}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TMDB artwork update failed: {str(exc)}")

@app.post("/library/{movie_id}/scrape")
def scrape_library_movie(movie_id: str, options: ScrapeOptions | None = None):
    """Scrape TMDB metadata for one movie, optionally writing local artwork and NFO files."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")

    result = metadata_scraper.scrape_movie(movie_id, options or ScrapeOptions())
    if result.status == "failed":
        raise HTTPException(status_code=409, detail=result.model_dump())
    return result.model_dump()

@app.post("/library/{movie_id}/ignore")
def ignore_library_movie(movie_id: str):
    """Mark one movie as ignored so it is hidden from normal library views."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")

    movie = library_manager.ignore_movie(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    library_event_bus.publish_library_changed("ignored", movie_id=movie_id)
    return {"status": "success", "movie": movie}

@app.post("/library/{movie_id}/scrape/confirm")
def confirm_library_movie_scrape(movie_id: str, tmdb_id: int, options: ScrapeOptions | None = None):
    """Scrape one movie using a user-confirmed TMDB ID."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")

    scrape_options = options or ScrapeOptions()
    scrape_options.tmdb_id = tmdb_id
    scrape_options.mode = "manual"
    result = metadata_scraper.scrape_movie(movie_id, scrape_options)
    if result.status == "failed":
        raise HTTPException(status_code=409, detail=result.model_dump())
    return result.model_dump()

@app.post("/library/scrape")
def scrape_library(options: BatchScrapeOptions | None = None):
    """Start a background metadata scrape for movies matching the requested scope."""
    job = job_runtime.enqueue(
        "metadata.scrape_library",
        {"options": (options or BatchScrapeOptions()).model_dump()},
        dedupe_key=f"metadata.scrape_library:{(options or BatchScrapeOptions()).model_dump_json()}",
    )
    return job_response(job, "Metadata scrape queued")

@app.get("/library/scrape/status")
def get_library_scrape_status():
    """Get latest metadata scrape status."""
    return metadata_scraper.get_status()

@app.post("/library/organize-root")
def organize_root_library_videos(options: RootOrganizeOptions | None = None):
    """Start background organization of direct video files in the media root."""
    job = job_runtime.enqueue(
        "organizer.organize_root",
        {
            "media_dir": get_media_dir() or DEFAULT_MEDIA_DIR,
            "options": options.model_dump() if options else None,
        },
        dedupe_key=f"organizer.organize_root:{get_media_dir() or DEFAULT_MEDIA_DIR}",
    )
    return job_response(job, "Root video organization queued")

@app.post("/library/organize-root/confirm")
def confirm_root_library_video(payload: RootOrganizeConfirmRequest):
    """Organize one root video using a user-confirmed TMDB ID."""
    if not Path(payload.path).exists():
        raise HTTPException(status_code=404, detail="Root video file not found")
    job = job_runtime.enqueue(
        "organizer.confirm_root_video",
        {
            "path": payload.path,
            "tmdb_id": payload.tmdb_id,
            "media_dir": get_media_dir() or DEFAULT_MEDIA_DIR,
            "options": (payload.options or RootOrganizeOptions()).model_dump(),
        },
        dedupe_key=f"organizer.confirm_root_video:{payload.path}",
    )
    return job_response(job, "Root video confirmation queued")

@app.get("/library/organize/status")
def get_library_organize_status():
    """Get latest root video organization status."""
    return root_video_organizer.get_status()

@app.get("/library/sync/status")
def get_library_sync_status():
    """Get latest library sync and watcher status."""
    return {
        "sync": library_sync_service.get_status(),
        "watcher": library_watcher.status(),
    }

@app.post("/library/analyze/{movie_id}")
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

@app.delete("/library")
def clear_library():
    """Clear all movies from the library."""
    library_manager.clear_library()
    library_event_bus.publish_library_changed("clear")
    return {"message": "Library cleared"}

@app.delete("/library/missing")
def cleanup_missing_library_movies():
    """Delete records already marked as missing."""
    deleted = library_manager.cleanup_missing()
    if deleted:
        library_event_bus.publish_library_changed("missing_cleanup", deleted=deleted)
    return {"status": "success", "deleted": deleted}

# Settings endpoints
from app.services.settings import load_settings, save_settings, get_current_model, set_current_model, get_base_url, set_base_url, refresh_models_cache, get_auto_organize_root_videos, set_auto_organize_root_videos, get_scrape_require_confirmation, set_scrape_require_confirmation

@app.get("/settings")
def get_settings():
    """Get current system settings"""
    settings = load_settings()
    settings.pop("tmdb_api_key", None)
    settings["tmdb"] = get_tmdb_key_status()
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

@app.get("/settings/artwork-language")
def get_artwork_language_setting():
    return {"artwork_language": get_artwork_language()}

@app.put("/settings/artwork-language")
def update_artwork_language_setting(language: str):
    if language not in {"metadata", "zh", "en", "none"}:
        raise HTTPException(status_code=400, detail="Artwork language must be 'metadata', 'zh', 'en', or 'none'")
    success = set_artwork_language(language)
    if success:
        return {"status": "success", "artwork_language": language}
    else:
        raise HTTPException(status_code=500, detail="Failed to save settings")

@app.get("/settings/library-watch")
def get_library_watch_setting():
    return {"watch_library": get_watch_library(), "watcher": library_watcher.status()}

@app.put("/settings/library-watch")
def update_library_watch_setting(enabled: bool):
    success = set_watch_library(enabled)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save settings")

    if enabled:
        watcher_status = library_watcher.start()
    else:
        watcher_status = library_watcher.stop()

    return {"status": "success", "watch_library": enabled, "watcher": watcher_status}

@app.get("/settings/auto-organize-root")
def get_auto_organize_root_setting():
    return {"auto_organize_root_videos": get_auto_organize_root_videos()}

@app.put("/settings/auto-organize-root")
def update_auto_organize_root_setting(enabled: bool):
    success = set_auto_organize_root_videos(enabled)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save settings")
    return {"status": "success", "auto_organize_root_videos": enabled}

@app.get("/settings/scrape-confirmation")
def get_scrape_confirmation_setting():
    return {"scrape_require_confirmation": get_scrape_require_confirmation()}

@app.put("/settings/scrape-confirmation")
def update_scrape_confirmation_setting(enabled: bool):
    success = set_scrape_require_confirmation(enabled)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save settings")
    return {"status": "success", "scrape_require_confirmation": enabled}

@app.get("/settings/tmdb")
def get_tmdb_setting():
    """Get TMDB API key configuration status without exposing the key."""
    return get_tmdb_key_status()

@app.put("/settings/tmdb")
def update_tmdb_setting(payload: TmdbApiKeyUpdate):
    """Persist a TMDB API key unless TMDB_API_KEY is managed by the environment."""
    if get_tmdb_key_status()["source"] == "environment":
        raise HTTPException(status_code=409, detail="TMDB_API_KEY is configured by environment")

    success = set_tmdb_api_key(payload.api_key)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save settings")
    return {"status": "success", **get_tmdb_key_status()}

@app.post("/settings/tmdb/test")
def test_tmdb_api_key():
    """Test the currently configured TMDB API key."""
    try:
        metadata_scraper.tmdb.configuration()
        return {"status": "success", "message": "TMDB API key is valid"}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 502
        if status_code == 401:
            return {"status": "error", "message": "Invalid TMDB API key"}
        raise HTTPException(status_code=502, detail=f"TMDB API test failed: {str(exc)}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TMDB API test failed: {str(exc)}")

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
def trigger_manual_scan():
    """
    Manually trigger a library scan.
    """
    try:
        target_dir = get_media_dir() or DEFAULT_MEDIA_DIR
        job = job_runtime.enqueue(
            "library.reconcile",
            {"media_dir": target_dir},
            dedupe_key=f"library.reconcile:{target_dir}",
        )
        return job_response(job, "Library scan queued")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start scan: {str(e)}")

from fastapi.responses import StreamingResponse
import json
from app.agents.librarian import get_librarian_agent

@app.get("/api/agents/clean-inbox")
async def clean_inbox_stream():
    """Stream the thoughtful execution of the librarian agent as it cleans the inbox."""
    async def event_generator():
        yield "data: " + json.dumps({"type": "info", "message": "Summoning Librarian Agent..."}) + "\n\n"
        
        try:
            agent_executor = get_librarian_agent()
            inputs = {"messages": [("user", "Please organize my inbox directory.")]}
            
            # Use 'updates' mode to stream Node updates from LangGraph
            async for chunk in agent_executor.astream(inputs, stream_mode="updates"):
                for node, values in chunk.items():
                    if node == "tools":
                        # The agent executed a tool!
                        tool_msgs = values.get("messages", [])
                        for tool_msg in tool_msgs:
                            msg = {
                                "type": "tool_execution",
                                "tool_name": tool_msg.name,
                                "content": tool_msg.content
                            }
                            yield f"data: {json.dumps(msg)}\n\n"
                            
                    elif node == "agent":
                        # Agent is thinking or responding
                        agent_msgs = values.get("messages", [])
                        for agent_msg in agent_msgs:
                            if hasattr(agent_msg, 'tool_calls') and agent_msg.tool_calls:
                                # Agent decided to call a tool
                                for tc in agent_msg.tool_calls:
                                    msg = {
                                        "type": "thought",
                                        "message": f"I need to use '{tc['name']}' with arguments: {tc['args']}"
                                    }
                                    yield f"data: {json.dumps(msg)}\n\n"
                            else:
                                # Agent is outputting text (like a final summary)
                                msg = {
                                    "type": "thought",
                                    "message": agent_msg.content
                                }
                                yield f"data: {json.dumps(msg)}\n\n"

            yield "data: " + json.dumps({"type": "done", "message": "Agent finished task."}) + "\n\n"
        except Exception as e:
            yield "data: " + json.dumps({"type": "error", "message": str(e)}) + "\n\n"
            yield "data: " + json.dumps({"type": "done", "message": "Terminated with error."}) + "\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
