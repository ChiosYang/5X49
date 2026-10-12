from contextlib import contextmanager
import sqlite3
from fastapi import APIRouter, HTTPException, Path, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from app.services.maintenance_backup import BackupError, maintenance_backups

router = APIRouter(prefix="/maintenance/backups", tags=["maintenance"])


class BackupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$")


@contextmanager
def errors():
    try:
        yield
    except BackupError as exc:
        raise HTTPException(409 if exc.code == "backup_busy" else 410, detail={"code": exc.code}) from None
    except (OSError, RuntimeError, sqlite3.Error):
        raise HTTPException(503, detail={"code": "backup_storage_unavailable"}) from None


@router.get("")
def status(response: Response):
    response.headers["Cache-Control"] = "no-store"
    with errors():
        return maintenance_backups.status()


@router.post("", status_code=202)
def create(payload: BackupRequest, response: Response):
    response.headers["Cache-Control"] = "no-store"
    with errors():
        return maintenance_backups.create(payload.request_id)


@router.get("/{backup_id}/download")
def download(backup_id: str = Path(pattern=r"^[0-9a-f]{32}$")):
    with errors():
        handle, record = maintenance_backups.download(backup_id)
    def stream():
        try:
            yield from iter(lambda: handle.read(256 * 1024), b"")
        finally:
            handle.close()
    class DownloadResponse(StreamingResponse):
        async def __call__(self, scope, receive, send):
            try:
                await super().__call__(scope, receive, send)
            finally:
                handle.close()  # Also close when disconnected before the iterator starts.
    return DownloadResponse(stream(), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{record["filename"]}"',
        "Content-Length": str(record["size_bytes"]), "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })


@router.get("/{backup_id}")
def get(response: Response, backup_id: str = Path(pattern=r"^[0-9a-f]{32}$")):
    response.headers["Cache-Control"] = "no-store"
    with errors():
        return maintenance_backups.get(backup_id)


@router.post("/{backup_id}/download-triggered")
def acknowledge(backup_id: str = Path(pattern=r"^[0-9a-f]{32}$")):
    with errors():
        return maintenance_backups.acknowledge(backup_id)
