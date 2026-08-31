from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
from typing import Callable

from app.services.event_bus import library_event_bus
from app.services.analysis import analysis_service
from app.services.external_scores import external_score_service
from app.services.library import library_manager
from app.services.library_sync import library_sync_service
from app.services.metadata.models import BatchScrapeOptions, MetadataSearchResult, RootOrganizeOptions, ScrapeOptions
from app.services.metadata.organizer import root_video_organizer
from app.services.metadata.scraper import metadata_scraper
from app.services.operation_manifests import operation_manifest_store
from app.services.settings import get_media_dir, get_organize_rename_style, get_tmdb_scrape_concurrency
from app.workflows.analysis import execute_analysis_workflow


DEFAULT_MEDIA_DIR = os.getenv("MEDIA_DIR", "/media")
logger = logging.getLogger(__name__)


def _media_dir(payload: dict) -> str:
    if payload.get("media_root_ref"):
        media_root, _path = operation_manifest_store.resolve_path(payload["media_root_ref"])
        return str(media_root)
    return get_media_dir() or DEFAULT_MEDIA_DIR


def reconcile_library(payload: dict, ctx) -> dict:
    return library_sync_service.reconcile(_media_dir(payload), ctx=ctx)


def scan_folder(payload: dict, ctx) -> dict:
    _media_root, folder_path = operation_manifest_store.resolve_path(payload["path_ref"])
    film = library_sync_service.scan_folder(folder_path, ctx=ctx)
    if not film:
        raise FileNotFoundError("Film folder or video file not found")
    if film.get("status") == "pending_relink":
        return film
    return {
        "status": "success",
        "film_id": film["id"],
        "library_item_id": film["primary_item"]["id"],
    }


def mark_path_missing(payload: dict, ctx) -> dict:
    ctx.progress(stage="resolve_subject", message="Resolving missing path reference")
    _media_root, path = operation_manifest_store.resolve_path(payload["path_ref"])
    ctx.progress(stage="persist", message="Persisting missing edition state")
    updated = library_sync_service.mark_path_missing(str(path))
    ctx.progress(stage="finalize", message="Finalizing missing edition update")
    return {"status": "success", "updated": updated}


def refresh_item(payload: dict, ctx) -> dict:
    result = library_sync_service.refresh_item(payload["library_item_id"], ctx=ctx)
    return {
        "status": result.get("status", "success"),
        "library_item_id": payload["library_item_id"],
        "updated": bool(result.get("updated")),
    }


def resolve_relink(payload: dict, ctx) -> dict:
    ctx.progress(stage="inspect", message="Inspecting ambiguous file identity")
    ctx.raise_if_cancelled()
    try:
        ctx.progress(stage="resolve", message="Resolving file identity")
        ctx.progress(stage="persist", message="Persisting relink decision")
        result = library_manager.resolve_relink(
            payload,
            job_id=getattr(ctx, "job_id", None),
        )
        ctx.progress(stage="finalize", message="Finalizing relink")
        return result
    except Exception:
        raise RuntimeError("Relink resolution failed") from None


def scrape_library(payload: dict, ctx) -> dict:
    options = BatchScrapeOptions(**payload.get("options", {}))
    ctx.progress(stage="resolve_subject", message="Resolving metadata refresh scope")
    films = [
        film
        for film in library_manager.list_operation_contexts()
        if metadata_scraper._in_scope(film, options)
    ]
    total = len(films)
    result = {"processed": 0, "succeeded": 0, "needs_review": 0, "failed": 0, "skipped": 0}
    metadata_scraper._set_status(
        state="running",
        last_started_at=datetime.now(timezone.utc).isoformat(),
        last_error=None,
    )
    ctx.progress(stage="search_match", current=0, total=total, message="Searching metadata matches")

    try:
        ctx.raise_if_cancelled()
        ctx.progress(stage="fetch", current=0, total=total, message="Fetching metadata observations")
        concurrency = min(get_tmdb_scrape_concurrency(), total) if total else 1
        film_iterator = iter(films)
        futures: dict[Future, dict] = {}
        cancellation_seen = False

        def submit_next(executor: ThreadPoolExecutor) -> bool:
            try:
                film = next(film_iterator)
            except StopIteration:
                return False
            future = executor.submit(
                metadata_scraper.scrape_film,
                film["id"],
                ScrapeOptions(
                    mode="auto",
                    language=options.language,
                    artwork_language=options.artwork_language,
                    overwrite=options.overwrite,
                    write_nfo=options.write_nfo,
                    download_artwork=options.download_artwork,
                ),
            )
            futures[future] = film
            return True

        with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="tmdb-scrape") as executor:
            for _ in range(concurrency):
                if not submit_next(executor):
                    break

            while futures:
                if ctx.is_cancel_requested():
                    cancellation_seen = True
                    for future in futures:
                        future.cancel()

                completed, _ = wait(
                    futures,
                    timeout=0.1,
                    return_when=FIRST_COMPLETED,
                )
                if not completed:
                    continue

                completed_count = 0
                for future in completed:
                    film = futures.pop(future)
                    if future.cancelled():
                        continue
                    completed_count += 1
                    try:
                        scrape_status = future.result().status
                    except Exception as exc:
                        logger.error(
                            "Metadata scrape worker failed film_id=%s error_type=%s",
                            film.get("id"),
                            exc.__class__.__name__,
                        )
                        scrape_status = "failed"

                    result["processed"] += 1
                    if scrape_status == "success":
                        result["succeeded"] += 1
                    elif scrape_status == "needs_review":
                        result["needs_review"] += 1
                    elif scrape_status == "skipped":
                        result["skipped"] += 1
                    else:
                        result["failed"] += 1
                    ctx.progress(
                        stage="fetch",
                        current=result["processed"],
                        total=total,
                        message=f"Scraped {result['processed']} of {total}",
                        counts=result,
                    )
                    if ctx.is_cancel_requested():
                        cancellation_seen = True

                if not cancellation_seen:
                    for _ in range(completed_count):
                        if not submit_next(executor):
                            break

        ctx.raise_if_cancelled()

        ctx.progress(stage="persist", message="Persisting metadata results")
        ctx.progress(stage="artwork_scores", message="Finalizing artwork and score state")

        metadata_scraper._set_status(
            state="idle",
            last_finished_at=datetime.now(timezone.utc).isoformat(),
            last_result=result,
        )
        library_event_bus.publish_library_changed("metadata_batch_scraped", result=result)
        ctx.progress(stage="finalize", message="Metadata refresh complete")
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
            last_error=exc.__class__.__name__,
        )
        raise


def organize_root(payload: dict, ctx) -> dict:
    options_payload = payload.get("options") or {}
    options = (
        RootOrganizeOptions(**options_payload)
        if options_payload
        else RootOrganizeOptions(rename_style=get_organize_rename_style())
    )
    ctx.progress(stage="resolve_subject", message="Resolving media root")
    root = Path(_media_dir(payload)).resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root}")
    ctx.progress(stage="inspect", message="Inspecting root videos")
    videos = root_video_organizer._root_videos(root)
    total = len(videos)
    result = {
        "processed": 0,
        "organized": 0,
        "scraped": 0,
        "needs_review": 0,
        "failed": 0,
        "skipped": 0,
    }
    root_video_organizer._set_status(
        state="running",
        last_started_at=datetime.now(timezone.utc).isoformat(),
        last_error=None,
    )
    ctx.progress(stage="persist", current=0, total=total, message="Organizing root videos")

    try:
        for video_path in videos:
            ctx.raise_if_cancelled()
            item = root_video_organizer.organize_file(video_path, root, options)
            result["processed"] += 1
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
                stage="persist",
                current=result["processed"],
                total=total,
                message=f"Processed {result['processed']} of {total}",
                counts=result,
            )

        root_video_organizer._set_status(
            state="idle",
            last_finished_at=datetime.now(timezone.utc).isoformat(),
            last_result=result,
        )
        if result["processed"]:
            library_event_bus.publish_library_changed("root_videos_organized", result=result)
        ctx.progress(stage="finalize", current=result["processed"], total=total, message="Root organization complete")
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
            last_error=exc.__class__.__name__,
        )
        raise


def confirm_root_video(payload: dict, ctx) -> dict:
    ctx.progress(stage="resolve_subject", message="Resolving confirmed root video")
    manifest_ref = payload["manifest_ref"]
    manifest = operation_manifest_store.load(manifest_ref)
    ctx.progress(stage="inspect", message="Inspecting confirmed root video")
    preview = root_video_organizer.validate_organization_confirmation(
        manifest["media_root"],
        payload["source_path"],
        payload["tmdb_id"],
        payload["rename_style"],
        payload["confirmation_token"],
    )
    ctx.progress(stage="persist", message="Organizing confirmed root video")
    result = root_video_organizer.organize_file_confirmed(
        Path(manifest["source"]),
        Path(manifest["media_root"]),
        payload["tmdb_id"],
        RootOrganizeOptions(
            rename_style=payload["rename_style"],
            overwrite=False,
            write_nfo=True,
            download_artwork=True,
        ),
        candidate=MetadataSearchResult.model_validate(preview["match"]),
        manifest_ref=manifest_ref,
    )
    if result.get("status") == "failed":
        raise RuntimeError(result.get("message") or "Root video organization failed")
    if result.get("status") == "skipped":
        raise ValueError(result.get("message") or "Root video organization skipped")
    ctx.progress(stage="finalize", message="Confirmed root video organized")
    return {
        key: value
        for key, value in result.items()
        if key in {"status", "film_id", "library_item_id", "tmdb_id", "sidecar_count", "snapshot_id"}
    }


def analyze_film(payload: dict, ctx) -> dict:
    result = execute_analysis_workflow(analysis_service, payload["film_id"], ctx=ctx)
    return {
        "status": result["status"],
        "film_id": result["film_id"],
        "cached": result["cached"],
        "assertions": result["assertions"],
        "evidence": result["evidence"],
        "reviews": result["reviews"],
        "analysis_run_id": (result.get("analysis") or {}).get("run", {}).get("id"),
    }


def refresh_film_external_scores(payload: dict, ctx) -> dict:
    ctx.progress(stage="resolve_subject", message="Resolving Film score sources")
    ctx.progress(stage="fetch", message="Fetching external scores")
    result = external_score_service.refresh_film(
        payload["film_id"],
        force=payload.get("force", False),
    )
    ctx.progress(stage="persist", message="Persisting external scores")
    ctx.progress(stage="finalize", message="External score refresh complete")
    return {
        "status": result["status"],
        "film_id": result["film_id"],
        "updated_sources": result["updated_sources"],
        "skipped_sources": result["skipped_sources"],
    }


def refresh_library_external_scores(payload: dict, ctx) -> dict:
    ctx.progress(stage="resolve_subject", message="Resolving Library score scope")
    films = [
        film
        for film in library_manager.list_films()
        if (film.get("primary_item") or {}).get("status") == "available"
    ]
    total = len(films)
    result = {"processed": 0, "updated": 0, "skipped": 0, "failed": 0}
    external_score_service._set_status(
        state="running",
        last_started_at=datetime.now(timezone.utc).isoformat(),
        last_error=None,
    )
    ctx.progress(stage="fetch", current=0, total=total, message="Fetching external scores")

    try:
        for film in films:
            ctx.raise_if_cancelled()
            result["processed"] += 1
            try:
                refresh_result = external_score_service.refresh_film(
                    film["id"],
                    force=payload.get("force", False),
                )
                if refresh_result["updated_sources"]:
                    result["updated"] += 1
                else:
                    result["skipped"] += 1
            except Exception:
                result["failed"] += 1
            ctx.progress(
                stage="fetch",
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
        ctx.progress(stage="persist", current=result["processed"], total=total, message="Persisting score refresh state")
        library_event_bus.publish_library_changed("external_scores_batch_updated", result=result)
        ctx.progress(stage="finalize", current=result["processed"], total=total, message="External score refresh complete")
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
            last_error=exc.__class__.__name__,
        )
        raise


JOB_HANDLERS: dict[str, Callable[[dict, object], dict]] = {
    "library.reconcile": reconcile_library,
    "library.scan_folder": scan_folder,
    "library.mark_path_missing": mark_path_missing,
    "library.refresh_item": refresh_item,
    "library.resolve_relink": resolve_relink,
    "metadata.scrape_library": scrape_library,
    "organizer.organize_root": organize_root,
    "organizer.confirm_root_video": confirm_root_video,
    "analysis.analyze_film": analyze_film,
    "external_scores.refresh_film": refresh_film_external_scores,
    "external_scores.refresh_library": refresh_library_external_scores,
}
