from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.event_backfill import movie_discovered_backfill, movie_replay_backfill
from app.services.event_bus import library_event_bus
from app.services.event_store import event_store
from app.services.library import library_manager
from app.services.nfo_signature_dry_run import nfo_signature_dry_run
from app.services.operation_dry_run import operation_dry_run
from app.services.operation_restore import operation_restore
from app.services.projections.movie_rebuild import ProjectionRebuildBlocked, movie_projection_dry_run
from app.services.projections.movie_timeline import movie_timeline_dry_run
from app.services.timeline_restore import TimelineRestoreBlocked, movie_timeline_restore
from app.utils.security import validate_movie_id


router = APIRouter()


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


@router.get("/library/events")
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


@router.get("/library/audit-events")
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


@router.get("/library/{movie_id}/audit-events")
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


@router.get("/library/{movie_id}/timeline/state")
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


@router.get("/library/{movie_id}/timeline/restore-preview")
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


@router.post("/library/{movie_id}/timeline/restore")
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


@router.get("/library/operations/dry-run")
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


@router.post("/library/operations/restore")
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


@router.post("/library/projections/movie/rebuild")
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


@router.post("/library/events/backfill/movie-discovered")
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


@router.post("/library/events/backfill/movie-replay")
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


@router.post("/library/events/dry-run/nfo-signatures")
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
