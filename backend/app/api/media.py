from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.settings import get_media_dir, get_media_dirs
from app.services.media_roots import root_id, safe_path, relative_media_path


router = APIRouter(prefix="/media", tags=["media"])


class MediaFileUnavailable(FileNotFoundError):
    """A public media path cannot be resolved inside the configured root."""


def resolve_media_path(media_root: str | Path | None, relative_path: str) -> Path:
    if not media_root or not relative_path or "\x00" in relative_path:
        raise MediaFileUnavailable
    if PurePosixPath(relative_path).is_absolute() or PureWindowsPath(relative_path).is_absolute():
        raise MediaFileUnavailable

    try:
        root = Path(media_root).expanduser().absolute()
        safe_path(root, root)
        if not root.is_dir():
            raise MediaFileUnavailable
        relative_media_path(relative_path)
        candidate = safe_path(root / relative_path, root)
        if not candidate.is_file():
            raise MediaFileUnavailable
    except (OSError, RuntimeError, ValueError):
        raise MediaFileUnavailable from None

    return candidate


@router.get("/{relative_path:path}", name="media-file")
def get_media_file(relative_path: str):
    try:
        if relative_path.startswith("_roots/"):
            _, identifier, relative_path = relative_path.split("/", 2)
            root = next((root for root in get_media_dirs() if root_id(root) == identifier), None)
            media_path = resolve_media_path(root, relative_path)
        else:
            media_path = resolve_media_path(get_media_dir(), relative_path)
    except (MediaFileUnavailable, ValueError):
        raise HTTPException(status_code=404, detail="Media file not found") from None
    return FileResponse(media_path, headers={"Cache-Control": "no-cache"})


__all__ = ["MediaFileUnavailable", "resolve_media_path", "router"]
