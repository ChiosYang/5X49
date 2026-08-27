import os
import hashlib
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Session

from app.api.common import DEFAULT_MEDIA_DIR, workflow_response
from app.database import engine
from app.services.analysis_runtime import analysis_runtime_persistence
from app.services.event_bus import library_event_bus
from app.services.graph_query import graph_query_service
from app.services.library import library_manager
from app.services.library_sync import library_sync_service
from app.services.metadata.organizer import root_video_organizer
from app.services.operation_manifests import OperationManifestError, operation_manifest_store
from app.services.settings import get_media_dir
from app.services.user_state import film_profile_state_manager
from app.services.watcher import library_watcher
from app.utils.security import validate_resource_id
from app.workflows import workflow_runtime


router = APIRouter()


class FilmProfileStateUpdate(BaseModel):
    watched: bool | None = None
    watched_at: str | None = None
    rating: int | None = PydanticField(default=None, ge=1, le=5)
    favorite: bool | None = None
    notes: str | None = PydanticField(default=None, max_length=10_000)


@router.get("/library/films")
def get_library_films(q: str | None = Query(default=None, max_length=200)):
    return library_manager.list_films(query=q)


@router.get("/library/films/{film_id}")
def get_library_film(film_id: str):
    _validate_id(film_id, "film")
    film = library_manager.get_film(film_id)
    if film is None:
        raise HTTPException(status_code=404, detail="Film not found")
    return film


@router.get("/films/{film_id}/profile-state")
def get_film_profile_state(film_id: str):
    _validate_id(film_id, "film")
    state = film_profile_state_manager.get(film_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Film not found")
    return state


@router.put("/films/{film_id}/profile-state")
def update_film_profile_state(film_id: str, request: FilmProfileStateUpdate):
    _validate_id(film_id, "film")
    state = film_profile_state_manager.upsert(
        film_id,
        watched=request.watched,
        watched_at=request.watched_at,
        rating=request.rating,
        favorite=request.favorite,
        notes=request.notes,
        fields_set=request.model_fields_set,
    )
    if state is None:
        raise HTTPException(status_code=404, detail="Film not found")
    library_event_bus.publish_library_changed("profile_state_updated", film_id=film_id)
    return state


@router.get("/profile/watch-history")
def get_watch_history():
    return film_profile_state_manager.watch_history()


@router.get("/library/root-videos")
def get_library_root_videos():
    try:
        return root_video_organizer.list_root_videos(get_media_dir() or DEFAULT_MEDIA_DIR)
    except FileNotFoundError:
        return []
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/library/seed")
def seed_library():
    films = library_manager.seed_test_data()
    library_event_bus.publish_library_changed("seed", count=len(films))
    return films


@router.post("/library/scan")
@router.post("/library/reconcile")
def reconcile_library(media_dir: str = Query(default=None)):
    target_dir = media_dir or get_media_dir() or DEFAULT_MEDIA_DIR
    if not os.path.exists(target_dir):
        raise HTTPException(status_code=400, detail=f"Directory not found: {target_dir}")
    try:
        path_ref = operation_manifest_store.create_path_reference(
            Path(target_dir),
            Path(target_dir),
        )
    except OperationManifestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    target_hash = hashlib.sha256(str(Path(target_dir).resolve()).encode("utf-8")).hexdigest()[:16]
    workflow = workflow_runtime.enqueue(
        "library.reconcile",
        {"media_root_ref": path_ref},
        dedupe_key=f"library.reconcile:{target_hash}",
    )
    return workflow_response(workflow, "Library reconcile queued")


@router.post("/library/scan-folder")
def scan_library_folder(folder_path: str):
    if not Path(folder_path).exists():
        raise HTTPException(status_code=404, detail="Movie folder or video file not found")
    try:
        path_ref = operation_manifest_store.create_path_reference(
            Path(get_media_dir() or DEFAULT_MEDIA_DIR),
            Path(folder_path),
        )
    except OperationManifestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path_hash = hashlib.sha256(str(Path(folder_path).resolve()).encode("utf-8")).hexdigest()[:16]
    workflow = workflow_runtime.enqueue(
        "library.scan_folder",
        {"path_ref": path_ref},
        dedupe_key=f"library.scan_folder:{path_hash}",
    )
    return workflow_response(workflow, "Folder scan queued")


@router.post("/library/items/{library_item_id}/refresh")
def refresh_library_item(library_item_id: str):
    _validate_id(library_item_id, "library item")
    if library_manager.get_item(library_item_id) is None:
        raise HTTPException(status_code=404, detail="Library item not found")
    workflow = workflow_runtime.enqueue(
        "library.refresh_item",
        {"library_item_id": library_item_id},
        dedupe_key=f"library.refresh_item:{library_item_id}",
    )
    return workflow_response(workflow, "Library item refresh queued")


@router.post("/library/items/{library_item_id}/ignore")
def ignore_library_item(library_item_id: str):
    _validate_id(library_item_id, "library item")
    item = library_manager.ignore_item(library_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Library item not found")
    library_event_bus.publish_library_changed(
        "ignored",
        film_id=item["film_id"],
        library_item_id=library_item_id,
    )
    return {"status": "success", "edition": item}


@router.get("/library/sync/status")
def get_library_sync_status():
    return {"sync": library_sync_service.get_status(), "watcher": library_watcher.status()}


@router.post("/films/{film_id}/analysis-runs")
def trigger_analysis(film_id: str):
    _validate_id(film_id, "film")
    if library_manager.get_film(film_id) is None:
        raise HTTPException(status_code=404, detail="Film not found")
    workflow = workflow_runtime.enqueue(
        "analysis.analyze_film",
        {"film_id": film_id},
        dedupe_key=f"analysis.analyze_film:{film_id}",
    )
    return workflow_response(workflow, f"Analysis queued for {film_id}")


@router.get("/films/{film_id}/analysis")
def get_film_analysis(film_id: str):
    _validate_id(film_id, "film")
    if library_manager.get_film(film_id) is None:
        raise HTTPException(status_code=404, detail="Film not found")
    with Session(engine) as session:
        return analysis_runtime_persistence.get_analysis(session, film_id)


@router.get("/films/{film_id}/graph")
def get_film_graph(film_id: str):
    _validate_id(film_id, "film")
    graph = graph_query_service.get_film_graph(film_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Film not found")
    return graph


@router.delete("/library")
def clear_library():
    retired = library_manager.clear_library()
    library_event_bus.publish_library_changed("clear", retired=retired)
    return {"message": "Library cleared", "retired": retired}


@router.delete("/library/data")
def clear_library_data():
    deleted = library_manager.clear_all_data()
    library_event_bus.publish_library_changed("data_clear", deleted=deleted)
    return {"status": "success", "message": "Library data cleared", "deleted": deleted}


@router.delete("/library/missing")
def cleanup_missing_library_items():
    deleted = library_manager.cleanup_missing()
    if deleted:
        library_event_bus.publish_library_changed("missing_cleanup", deleted=deleted)
    return {"status": "success", "deleted": deleted}


def _validate_id(value: str, label: str) -> None:
    prefix = "film" if label == "film" else "lib"
    if not validate_resource_id(value, prefix):
        raise HTTPException(status_code=400, detail=f"Invalid {label} ID format")
