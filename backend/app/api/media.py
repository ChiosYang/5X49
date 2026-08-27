from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.settings import get_media_dir


router = APIRouter(prefix="/media", tags=["media"])


class MediaFileUnavailable(FileNotFoundError):
    """A public media path cannot be resolved inside the configured root."""


def resolve_media_path(media_root: str | Path | None, relative_path: str) -> Path:
    if not media_root or not relative_path or "\x00" in relative_path:
        raise MediaFileUnavailable
    if PurePosixPath(relative_path).is_absolute() or PureWindowsPath(relative_path).is_absolute():
        raise MediaFileUnavailable

    try:
        root = Path(media_root).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise MediaFileUnavailable
        candidate = (root / relative_path).resolve(strict=True)
        candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        raise MediaFileUnavailable from None

    if not candidate.is_file():
        raise MediaFileUnavailable
    return candidate


@router.get("/{relative_path:path}", name="media-file")
def get_media_file(relative_path: str):
    try:
        media_path = resolve_media_path(get_media_dir(), relative_path)
    except MediaFileUnavailable:
        raise HTTPException(status_code=404, detail="Media file not found") from None
    return FileResponse(media_path, headers={"Cache-Control": "no-cache"})


__all__ = ["MediaFileUnavailable", "resolve_media_path", "router"]
