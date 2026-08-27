import os


DEFAULT_MEDIA_DIR = os.getenv("MEDIA_DIR", "/media")


def workflow_response(workflow: dict, message: str) -> dict:
    return {
        "status": "queued",
        "message": message,
        "workflow_id": workflow["id"],
        "workflow": workflow,
    }
