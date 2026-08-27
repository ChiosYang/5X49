import os

from app.services.settings import get_media_dir


DEFAULT_MEDIA_DIR = os.getenv("MEDIA_DIR", "/media")
MEDIA_DIR = get_media_dir() or DEFAULT_MEDIA_DIR


def workflow_response(workflow: dict, message: str) -> dict:
    return {
        "status": "queued",
        "message": message,
        "workflow_id": workflow["id"],
        "workflow": workflow,
    }
