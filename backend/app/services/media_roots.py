"""Shared, host-native media boundaries. Configuration never grants parent access."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import quote


class MediaBoundaryError(ValueError):
    pass


def root_id(root: str | Path) -> str:
    return hashlib.sha256(os.path.normcase(os.path.abspath(root)).encode()).hexdigest()[:24]


def is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def safe_path(path: str | Path, root: str | Path) -> Path:
    """Check lexical containment and every component, including missing paths.

    Do not resolve links before checking: even an in-root link is not traversed.
    Permission errors propagate instead of masquerading as absence.
    """
    root = Path(os.path.abspath(root))
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise MediaBoundaryError("Media path is outside configured roots")
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        raise MediaBoundaryError("Media path is outside configured roots") from None
    current = root
    for part in (None, *parts):
        if part is not None:
            current = current / part
        if is_link(current):
            raise MediaBoundaryError("Media links are not traversed")
    # Also catch a root whose ancestor was replaced with a link after saving.
    if any(is_link(parent) for parent in root.parents):
        raise MediaBoundaryError("Media root has changed")
    return path


def configured_root(path: str | Path, roots: list[str] | None = None) -> Path:
    if roots is None:
        from app.services.settings import get_media_dirs
        roots = get_media_dirs()
    for root in roots:
        try:
            safe_path(path, root)
            return Path(root)
        except MediaBoundaryError:
            continue
    raise MediaBoundaryError("Media path is outside configured roots or contains a link")


def normalize_roots(values: list[str]) -> list[str]:
    if len(values) > 32:
        raise MediaBoundaryError("At most 32 media directories are supported")
    result: list[Path] = []
    for value in values:
        if not isinstance(value, str) or not value.strip() or "\x00" in value:
            raise MediaBoundaryError("Media directory cannot be empty")
        path = Path(value.strip()).expanduser()
        if not path.is_absolute():
            raise MediaBoundaryError("Media directories must be absolute host paths")
        # A root selected by the user is canonicalized once, not followed on scan.
        path = path.resolve()
        if path in result:
            continue
        if any(path.is_relative_to(other) or other.is_relative_to(path) for other in result):
            raise MediaBoundaryError("Media directories must not overlap")
        result.append(path)
    return [str(path) for path in result]


def directory_status(root: str) -> dict:
    result = {"id": root_id(root), "path": root, "state": "unavailable"}
    try:
        path = safe_path(root, root)
        with os.scandir(path) as entries:
            next(entries, None)
        result["state"] = "accessible"
    except FileNotFoundError:
        result["state"] = "offline"
    except PermissionError:
        result["state"] = "permission_denied"
    except (OSError, ValueError, RuntimeError):
        pass
    return result


def relative_media_path(value: str) -> str:
    # Check both grammars on both OSes: drive-relative paths and backslashes are
    # not valid portable URL components, even when POSIX treats them literally.
    if (not value or "\x00" in value or "\\" in value or ":" in value
            or PureWindowsPath(value).drive or PurePosixPath(value).is_absolute()
            or ".." in PurePosixPath(value).parts):
        raise MediaBoundaryError("Invalid media path")
    return value


def media_url(path: Path, root: Path) -> str:
    path = safe_path(path, root)
    return f"/media/_roots/{root_id(root)}/{quote(path.relative_to(root).as_posix(), safe='/')}"


def explicitly_absent(path: str | Path, root: str | Path) -> bool:
    """Absence requires successful enumeration of the nearest existing parent.

    A disconnected root, denied subtree, replacement link or existing-but-unparsed
    file is not evidence of deletion. No filesystem writes are made.
    """
    try:
        path = safe_path(path, root)
        root = Path(root)
        if directory_status(str(root))["state"] != "accessible" or path == root:
            return False
        current = root
        for part in path.relative_to(root).parts:
            with os.scandir(current) as entries:
                names = {os.path.normcase(entry.name) for entry in entries}
            if os.path.normcase(part) not in names:
                return True
            current = current / part
        return False
    except (OSError, ValueError, RuntimeError):
        return False
