from fastapi import APIRouter, HTTPException, Query

from app.api.common import workflow_response
from app.workflows import workflow_runtime


router = APIRouter()


@router.get("/workflows")
def list_workflows(
    status: str | None = Query(default=None),
    type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    return workflow_runtime.list(status=status, workflow_type=type, limit=limit)


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str):
    workflow = workflow_runtime.get(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.post("/workflows/{workflow_id}/cancel")
def cancel_workflow(workflow_id: str):
    workflow = workflow_runtime.cancel(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.post("/workflows/{workflow_id}/retry")
def retry_workflow(workflow_id: str):
    current = workflow_runtime.get(workflow_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if current["status"] not in {"failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Only failed or cancelled workflows can be retried")
    workflow = workflow_runtime.retry(workflow_id)
    return workflow_response(workflow, "Workflow retry queued")
