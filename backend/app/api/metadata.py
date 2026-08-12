from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException, Query

from app.api.common import DEFAULT_MEDIA_DIR, job_response
from app.jobs import job_runtime
from app.services.external_scores import external_score_service
from app.services.library import library_manager
from app.services.metadata.models import (
    ArtworkSelection,
    BatchScrapeOptions,
    RootOrganizeConfirmRequest,
    RootOrganizeOptions,
    ScrapeOptions,
)
from app.services.metadata.organizer import root_video_organizer
from app.services.metadata.scraper import metadata_scraper
from app.services.settings import get_media_dir
from app.utils.security import validate_movie_id


router = APIRouter()


@router.post("/library/external-scores/refresh")
def refresh_library_external_scores(force: bool = Query(default=False)):
    """Start a background refresh of external score sources for available movies."""
    job = job_runtime.enqueue(
        "external_scores.refresh_library",
        {"force": force},
        dedupe_key=f"external_scores.refresh_library:{force}",
    )
    return job_response(job, "External score refresh queued")


@router.get("/library/external-scores/status")
def get_library_external_scores_status():
    """Get latest external score refresh status."""
    return external_score_service.get_status()


@router.get("/metadata/search")
def search_metadata(query: str, year: int | None = Query(default=None), language: str | None = Query(default=None)):
    """Search TMDB movie metadata using the configured TMDB_API_KEY."""
    try:
        return [candidate.model_dump() for candidate in metadata_scraper.search(query, year, language)]
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Metadata search failed: {str(exc)}")


@router.get("/metadata/movie/{tmdb_id}")
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


@router.post("/library/{movie_id}/external-scores/refresh")
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


@router.get("/library/{movie_id}/artwork")
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


@router.put("/library/{movie_id}/artwork")
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


@router.post("/library/{movie_id}/scrape")
def scrape_library_movie(movie_id: str, options: ScrapeOptions | None = None):
    """Scrape TMDB metadata for one movie, optionally writing local artwork and NFO files."""
    if not validate_movie_id(movie_id):
        raise HTTPException(status_code=400, detail="Invalid movie ID format")

    result = metadata_scraper.scrape_movie(movie_id, options or ScrapeOptions())
    if result.status == "failed":
        raise HTTPException(status_code=409, detail=result.model_dump())
    return result.model_dump()


@router.post("/library/{movie_id}/scrape/confirm")
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


@router.post("/library/scrape")
def scrape_library(options: BatchScrapeOptions | None = None):
    """Start a background metadata scrape for movies matching the requested scope."""
    job = job_runtime.enqueue(
        "metadata.scrape_library",
        {"options": (options or BatchScrapeOptions()).model_dump()},
        dedupe_key=f"metadata.scrape_library:{(options or BatchScrapeOptions()).model_dump_json()}",
    )
    return job_response(job, "Metadata scrape queued")


@router.get("/library/scrape/status")
def get_library_scrape_status():
    """Get latest metadata scrape status."""
    return metadata_scraper.get_status()


@router.post("/library/organize-root")
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


@router.post("/library/organize-root/confirm")
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


@router.get("/library/organize/status")
def get_library_organize_status():
    """Get latest root video organization status."""
    return root_video_organizer.get_status()
