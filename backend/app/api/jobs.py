from fastapi import APIRouter, HTTPException, Query

from app.api.common import job_response
from app.jobs import job_runtime


router = APIRouter()


@router.get("/jobs")
def list_jobs(
    status: str | None = Query(default=None),
    type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List recent background jobs."""
    return job_runtime.list(status=status, job_type=type, limit=limit)


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    """Get one background job by ID."""
    job = job_runtime.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    """Request cancellation for one background job."""
    job = job_runtime.cancel(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/retry")
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


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    """Delete a completed, failed, or cancelled background job."""
    deleted = job_runtime.delete(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found or still active")
    return {"status": "success", "deleted": True}
