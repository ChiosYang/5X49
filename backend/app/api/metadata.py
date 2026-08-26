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
from app.services.operation_manifests import OperationManifestError, operation_manifest_store
from app.services.metadata.scraper import metadata_scraper
from app.services.settings import get_media_dir
from app.utils.security import validate_resource_id


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


@router.post("/films/{film_id}/external-scores/refresh")
def refresh_film_external_scores(film_id: str, force: bool = Query(default=False)):
    if not validate_resource_id(film_id, "film"):
        raise HTTPException(status_code=400, detail="Invalid Film ID format")

    if not library_manager.get_film(film_id):
        raise HTTPException(status_code=404, detail="Film not found")
    job = job_runtime.enqueue(
        "external_scores.refresh_film",
        {"film_id": film_id, "force": force},
        dedupe_key=f"external_scores.refresh_film:{film_id}:{force}",
    )
    return job_response(job, "Film external score refresh queued")


@router.get("/films/{film_id}/artwork")
def get_film_artwork(film_id: str):
    if not validate_resource_id(film_id, "film"):
        raise HTTPException(status_code=400, detail="Invalid Film ID format")

    try:
        return metadata_scraper.artwork_options(film_id).model_dump()
    except LookupError:
        raise HTTPException(status_code=404, detail="Film not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 502
        raise HTTPException(status_code=status_code, detail=f"TMDB artwork lookup failed: {str(exc)}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TMDB artwork lookup failed: {str(exc)}")


@router.put("/films/{film_id}/artwork")
def update_film_artwork(film_id: str, selection: ArtworkSelection):
    if not validate_resource_id(film_id, "film"):
        raise HTTPException(status_code=400, detail="Invalid Film ID format")

    try:
        return metadata_scraper.apply_artwork(film_id, selection)
    except LookupError:
        raise HTTPException(status_code=404, detail="Film not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 502
        raise HTTPException(status_code=status_code, detail=f"TMDB artwork update failed: {str(exc)}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TMDB artwork update failed: {str(exc)}")


@router.post("/films/{film_id}/scrape")
def scrape_film(film_id: str, options: ScrapeOptions | None = None):
    if not validate_resource_id(film_id, "film"):
        raise HTTPException(status_code=400, detail="Invalid Film ID format")

    result = metadata_scraper.scrape_film(film_id, options or ScrapeOptions())
    if result.status == "failed":
        raise HTTPException(status_code=409, detail=result.model_dump())
    return result.model_dump()


@router.post("/films/{film_id}/scrape/confirm")
def confirm_film_scrape(film_id: str, tmdb_id: int, options: ScrapeOptions | None = None):
    if not validate_resource_id(film_id, "film"):
        raise HTTPException(status_code=400, detail="Invalid Film ID format")

    scrape_options = options or ScrapeOptions()
    scrape_options.tmdb_id = tmdb_id
    scrape_options.mode = "manual"
    result = metadata_scraper.scrape_film(film_id, scrape_options)
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
            "options": options.model_dump() if options else None,
        },
        dedupe_key="organizer.organize_root",
    )
    return job_response(job, "Root video organization queued")


@router.post("/library/organize-root/confirm")
def confirm_root_library_video(payload: RootOrganizeConfirmRequest):
    """Organize one root video using a user-confirmed TMDB ID."""
    if not Path(payload.path).exists():
        raise HTTPException(status_code=404, detail="Root video file not found")
    try:
        manifest_ref = operation_manifest_store.create(
            Path(get_media_dir() or DEFAULT_MEDIA_DIR),
            Path(payload.path),
        )
    except OperationManifestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = job_runtime.enqueue(
        "organizer.confirm_root_video",
        {
            "manifest_ref": manifest_ref,
            "tmdb_id": payload.tmdb_id,
            "options": (payload.options or RootOrganizeOptions()).model_dump(),
        },
        dedupe_key=f"organizer.confirm_root_video:{manifest_ref}",
    )
    return job_response(job, "Root video confirmation queued")


@router.get("/library/organize/status")
def get_library_organize_status():
    """Get latest root video organization status."""
    return root_video_organizer.get_status()
