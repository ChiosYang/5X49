from pathlib import Path
import logging

from fastapi import APIRouter, HTTPException, Query



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
    from app.api.library import reconcile_library
    return reconcile_library(media_dir=None)
