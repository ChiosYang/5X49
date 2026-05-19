import os
from pathlib import Path
from typing import Callable

from app.services.analysis import analysis_service
from app.services.external_scores import external_score_service
from app.services.library_sync import library_sync_service
from app.services.metadata.models import BatchScrapeOptions, RootOrganizeOptions
from app.services.metadata.organizer import root_video_organizer
from app.services.metadata.scraper import metadata_scraper
from app.services.settings import get_media_dir


DEFAULT_MEDIA_DIR = os.getenv("MEDIA_DIR", "/media")


def _media_dir(payload: dict) -> str:
    return payload.get("media_dir") or get_media_dir() or DEFAULT_MEDIA_DIR


def reconcile_library(payload: dict) -> dict:
    return library_sync_service.reconcile(_media_dir(payload))


def scan_folder(payload: dict) -> dict:
    folder_path = payload["folder_path"]
    movie = library_sync_service.scan_folder(folder_path)
    if not movie:
        raise FileNotFoundError("Movie folder or video file not found")
    return {"status": "success", "movie": movie}


def mark_path_missing(payload: dict) -> dict:
    updated = library_sync_service.mark_path_missing(payload["path"])
    return {"status": "success", "updated": updated, "path": payload["path"]}


def refresh_movie(payload: dict) -> dict:
    return library_sync_service.refresh_movie(payload["movie_id"])


def scrape_library(payload: dict) -> dict:
    return metadata_scraper.scrape_library(BatchScrapeOptions(**payload.get("options", {})))


def organize_root(payload: dict) -> dict:
    options_payload = payload.get("options") or {}
    options = RootOrganizeOptions(**options_payload) if options_payload else None
    return root_video_organizer.organize_root(_media_dir(payload), options)


def confirm_root_video(payload: dict) -> dict:
    result = root_video_organizer.organize_file_confirmed(
        Path(payload["path"]),
        Path(_media_dir(payload)).resolve(),
        payload["tmdb_id"],
        RootOrganizeOptions(**(payload.get("options") or {})),
    )
    if result.get("status") == "failed":
        raise RuntimeError(result.get("message") or "Root video organization failed")
    if result.get("status") == "skipped":
        raise ValueError(result.get("message") or "Root video organization skipped")
    return result


def analyze_movie(payload: dict) -> dict:
    analysis_service.analyze_movie(payload["movie_id"])
    return {"status": "success", "movie_id": payload["movie_id"]}


def refresh_movie_external_scores(payload: dict) -> dict:
    return external_score_service.refresh_movie(
        payload["movie_id"],
        force=payload.get("force", False),
    )


def refresh_library_external_scores(payload: dict) -> dict:
    return external_score_service.refresh_library(payload.get("force", False))


JOB_HANDLERS: dict[str, Callable[[dict], dict]] = {
    "library.reconcile": reconcile_library,
    "library.scan_folder": scan_folder,
    "library.mark_path_missing": mark_path_missing,
    "library.refresh_movie": refresh_movie,
    "metadata.scrape_library": scrape_library,
    "organizer.organize_root": organize_root,
    "organizer.confirm_root_video": confirm_root_video,
    "analysis.analyze_movie": analyze_movie,
    "external_scores.refresh_movie": refresh_movie_external_scores,
    "external_scores.refresh_library": refresh_library_external_scores,
}
