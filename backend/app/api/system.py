from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.api.common import DEFAULT_MEDIA_DIR, job_response
from app.jobs import job_runtime
from app.services.settings import get_media_dir


router = APIRouter()


@router.get("/sys/list-dirs")
def list_directories(path: str = Query(default="/")):
    """
    List subdirectories in the given path.
    Used for the frontend file browser.
    """
    target_path = Path(path).resolve()

    if not target_path.exists():
        target_path = Path("/")

    if not target_path.is_dir():
        target_path = target_path.parent

    dirs = []
    try:
        for item in target_path.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                dirs.append({
                    "name": item.name,
                    "path": str(item.resolve()),
                })

        dirs.sort(key=lambda x: x["name"].lower())

        return {
            "current_path": str(target_path),
            "parent_path": str(target_path.parent) if target_path != target_path.parent else None,
            "directories": dirs,
        }
    except Exception as e:
        print(f"Error listing directories at {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sys/scan-library")
def trigger_manual_scan():
    """Manually trigger a library scan."""
    try:
        target_dir = get_media_dir() or DEFAULT_MEDIA_DIR
        job = job_runtime.enqueue(
            "library.reconcile",
            {"media_dir": target_dir},
            dedupe_key=f"library.reconcile:{target_dir}",
        )
        return job_response(job, "Library scan queued")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start scan: {str(e)}")
