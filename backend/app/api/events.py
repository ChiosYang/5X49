from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.event_bus import library_event_bus
from app.services.event_store import event_store
from app.services.operation_snapshots import OperationConflict, operation_snapshot_service
from app.utils.security import validate_resource_id


router = APIRouter()


class OperationRestoreRequest(BaseModel):
    confirmation_token: str = Field(min_length=64, max_length=64)


@router.get("/library/events")
async def get_library_events(request: Request):
    return StreamingResponse(
        library_event_bus.subscribe(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/activity/events")
def get_activity_events(
    aggregate_type: str | None = Query(default=None),
    aggregate_id: str | None = Query(default=None),
    type: str | None = Query(default=None),
    command_id: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    if aggregate_id and not validate_resource_id(aggregate_id):
        raise HTTPException(status_code=400, detail="Invalid aggregate ID format")
    return event_store.list(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=type,
        command_id=command_id,
        correlation_id=correlation_id,
        limit=limit,
    )


@router.get("/operations/{snapshot_id}/preview")
def preview_operation(snapshot_id: str):
    if not validate_resource_id(snapshot_id, "snap"):
        raise HTTPException(status_code=400, detail="Invalid snapshot ID format")
    preview = operation_snapshot_service.preview(snapshot_id)
    if preview is None:
        raise HTTPException(status_code=404, detail="Operation snapshot not found")
    return preview


@router.post("/operations/{snapshot_id}/restore")
def restore_operation(snapshot_id: str, request: OperationRestoreRequest):
    if not validate_resource_id(snapshot_id, "snap"):
        raise HTTPException(status_code=400, detail="Invalid snapshot ID format")
    try:
        result = operation_snapshot_service.restore(snapshot_id, request.confirmation_token)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OperationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    library_event_bus.publish_library_changed(
        "operation_restored",
        aggregate_type=result["aggregate_type"],
        aggregate_id=result["aggregate_id"],
    )
    return result
