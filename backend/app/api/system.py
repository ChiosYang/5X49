from pathlib import Path
import hashlib
import logging

from fastapi import APIRouter, HTTPException, Query

from app.api.common import DEFAULT_MEDIA_DIR, job_response
from app.jobs import job_runtime
from app.services.settings import get_media_dir
from app.services.operation_manifests import OperationManifestError, operation_manifest_store


router = APIRouter()
logger = logging.getLogger(__name__)


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
    except Exception as exc:
        logger.error("Directory listing failed error_type=%s", exc.__class__.__name__)
        raise HTTPException(status_code=500, detail="Directory listing failed") from None


@router.post("/sys/scan-library")
def trigger_manual_scan():
    """Manually trigger a library scan."""
    try:
        target_dir = get_media_dir() or DEFAULT_MEDIA_DIR
        path_ref = operation_manifest_store.create_path_reference(
            Path(target_dir),
            Path(target_dir),
        )
        target_hash = hashlib.sha256(
            str(Path(target_dir).resolve()).encode("utf-8")
        ).hexdigest()[:16]
        job = job_runtime.enqueue(
            "library.reconcile",
            {"media_root_ref": path_ref},
            dedupe_key=f"library.reconcile:{target_hash}",
        )
        return job_response(job, "Library scan queued")
    except (OperationManifestError, OSError):
        raise HTTPException(status_code=500, detail="Failed to start scan") from None
