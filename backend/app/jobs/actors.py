import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.services.event_bus import library_event_bus
from app.services.analysis import analysis_service
from app.services.external_scores import external_score_service
from app.services.library import library_manager
from app.services.library_sync import library_sync_service
from app.services.metadata.models import BatchScrapeOptions, RootOrganizeOptions, ScrapeOptions
from app.services.metadata.organizer import root_video_organizer
from app.services.metadata.scraper import metadata_scraper
from app.services.settings import get_media_dir


DEFAULT_MEDIA_DIR = os.getenv("MEDIA_DIR", "/media")


def _media_dir(payload: dict) -> str:
    return payload.get("media_dir") or get_media_dir() or DEFAULT_MEDIA_DIR


def reconcile_library(payload: dict, ctx) -> dict:
    ctx.progress(stage="scanning", message="Scanning library")
    ctx.raise_if_cancelled()
    return library_sync_service.reconcile(_media_dir(payload))


def scan_folder(payload: dict, ctx) -> dict:
    ctx.progress(stage="scanning", message="Scanning folder")
    folder_path = payload["folder_path"]
    movie = library_sync_service.scan_folder(folder_path)
    if not movie:
        raise FileNotFoundError("Movie folder or video file not found")
    return {"status": "success", "movie": movie}


def mark_path_missing(payload: dict, ctx) -> dict:
    ctx.progress(stage="marking_missing", message="Marking path missing")
    updated = library_sync_service.mark_path_missing(payload["path"])
    return {"status": "success", "updated": updated, "path": payload["path"]}


def refresh_movie(payload: dict, ctx) -> dict:
    ctx.progress(stage="refreshing", message="Refreshing movie")
    return library_sync_service.refresh_movie(payload["movie_id"])


def scrape_library(payload: dict, ctx) -> dict:
    options = BatchScrapeOptions(**payload.get("options", {}))
    movies = [movie for movie in library_manager.get_movies() if metadata_scraper._in_scope(movie, options)]
    total = len(movies)
    result = {"processed": 0, "succeeded": 0, "needs_review": 0, "failed": 0, "skipped": 0}
    metadata_scraper._set_status(
        state="running",
        last_started_at=datetime.now(timezone.utc).isoformat(),
        last_error=None,
    )
    ctx.progress(stage="scraping", current=0, total=total, message="Scraping metadata")

    try:
        for movie in movies:
            ctx.raise_if_cancelled()
            scrape_result = metadata_scraper.scrape_movie(
                movie["id"],
                ScrapeOptions(
                    mode="auto",
                    language=options.language,
                    artwork_language=options.artwork_language,
                    overwrite=options.overwrite,
                    write_nfo=options.write_nfo,
                    download_artwork=options.download_artwork,
                ),
            )
            result["processed"] += 1
            if scrape_result.status == "success":
                result["succeeded"] += 1
            elif scrape_result.status == "needs_review":
                result["needs_review"] += 1
            elif scrape_result.status == "skipped":
                result["skipped"] += 1
            else:
                result["failed"] += 1
            ctx.progress(
                stage="scraping",
                current=result["processed"],
                total=total,
                message=f"Scraped {result['processed']} of {total}",
                counts=result,
            )

        metadata_scraper._set_status(
            state="idle",
            last_finished_at=datetime.now(timezone.utc).isoformat(),
            last_result=result,
        )
        library_event_bus.publish_library_changed("metadata_batch_scraped", result=result)
        return result
    except Exception as exc:
        if exc.__class__.__name__ == "JobCancelled":
            metadata_scraper._set_status(
                state="idle",
                last_finished_at=datetime.now(timezone.utc).isoformat(),
                last_result=result,
            )
            raise
        metadata_scraper._set_status(
            state="error",
            last_finished_at=datetime.now(timezone.utc).isoformat(),
            last_error=str(exc),
        )
        raise


def organize_root(payload: dict, ctx) -> dict:
    options_payload = payload.get("options") or {}
    options = RootOrganizeOptions(**options_payload) if options_payload else RootOrganizeOptions()
    root = Path(_media_dir(payload)).resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root}")
    videos = root_video_organizer._root_videos(root)
    total = len(videos)
    result = {
        "processed": 0,
        "organized": 0,
        "scraped": 0,
        "needs_review": 0,
        "failed": 0,
        "skipped": 0,
        "items": [],
    }
    root_video_organizer._set_status(
        state="running",
        last_started_at=datetime.now(timezone.utc).isoformat(),
        last_error=None,
    )
    ctx.progress(stage="organizing", current=0, total=total, message="Organizing root videos")

    try:
        for video_path in videos:
            ctx.raise_if_cancelled()
            item = root_video_organizer.organize_file(video_path, root, options)
            result["processed"] += 1
            result["items"].append(item)
            status = item.get("status")
            if status == "success":
                result["organized"] += 1
                result["scraped"] += 1 if item.get("scrape_status") == "success" else 0
            elif status == "needs_review":
                result["needs_review"] += 1
            elif status == "skipped":
                result["skipped"] += 1
            else:
                result["failed"] += 1
            ctx.progress(
                stage="organizing",
                current=result["processed"],
                total=total,
                message=f"Processed {result['processed']} of {total}",
                counts={key: value for key, value in result.items() if key != "items"},
            )

        root_video_organizer._set_status(
            state="idle",
            last_finished_at=datetime.now(timezone.utc).isoformat(),
            last_result=result,
        )
        if result["processed"]:
            library_event_bus.publish_library_changed("root_videos_organized", result=result)
        return result
    except Exception as exc:
        if exc.__class__.__name__ == "JobCancelled":
            root_video_organizer._set_status(
                state="idle",
                last_finished_at=datetime.now(timezone.utc).isoformat(),
                last_result=result,
            )
            raise
        root_video_organizer._set_status(
            state="error",
            last_finished_at=datetime.now(timezone.utc).isoformat(),
            last_error=str(exc),
        )
        raise


def confirm_root_video(payload: dict, ctx) -> dict:
    ctx.progress(stage="organizing", message="Organizing confirmed root video")
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


def analyze_movie(payload: dict, ctx) -> dict:
    ctx.progress(stage="analyzing", message="Running film analysis")
    analysis_service.analyze_movie(payload["movie_id"])
    return {"status": "success", "movie_id": payload["movie_id"]}


def refresh_movie_external_scores(payload: dict, ctx) -> dict:
    ctx.progress(stage="refreshing", message="Refreshing external scores")
    return external_score_service.refresh_movie(
        payload["movie_id"],
        force=payload.get("force", False),
    )


def refresh_library_external_scores(payload: dict, ctx) -> dict:
    movies = [
        movie
        for movie in library_manager.get_movies()
        if movie.get("library_status") not in {"missing", "ignored"}
    ]
    total = len(movies)
    result = {"processed": 0, "updated": 0, "skipped": 0, "failed": 0}
    external_score_service._set_status(
        state="running",
        last_started_at=datetime.now(timezone.utc).isoformat(),
        last_error=None,
    )
    ctx.progress(stage="refreshing", current=0, total=total, message="Refreshing external scores")

    try:
        for movie in movies:
            ctx.raise_if_cancelled()
            result["processed"] += 1
            try:
                refresh_result = external_score_service.refresh_movie(
                    movie["id"],
                    force=payload.get("force", False),
                )
                if refresh_result["updated_sources"]:
                    result["updated"] += 1
                else:
                    result["skipped"] += 1
            except Exception:
                result["failed"] += 1
            ctx.progress(
                stage="refreshing",
                current=result["processed"],
                total=total,
                message=f"Refreshed {result['processed']} of {total}",
                counts=result,
            )

        external_score_service._set_status(
            state="idle",
            last_finished_at=datetime.now(timezone.utc).isoformat(),
            last_result=result,
        )
        library_event_bus.publish_library_changed("external_scores_batch_updated", result=result)
        return result
    except Exception as exc:
        if exc.__class__.__name__ == "JobCancelled":
            external_score_service._set_status(
                state="idle",
                last_finished_at=datetime.now(timezone.utc).isoformat(),
                last_result=result,
            )
            raise
        external_score_service._set_status(
            state="error",
            last_finished_at=datetime.now(timezone.utc).isoformat(),
            last_error=str(exc),
        )
        raise


JOB_HANDLERS: dict[str, Callable[[dict, object], dict]] = {
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
