from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


SAMPLE_BYTES = 4 * 1024 * 1024
FOREGROUND_BUDGET_BYTES = SAMPLE_BYTES * 3


@dataclass(frozen=True)
class FileIdentityObservation:
    platform_file_id: str
    content_fingerprint: str
    content_hash: str | None
    bytes_read: int


def observe_file(path_value: str | Path) -> FileIdentityObservation | None:
    path = Path(path_value)
    try:
        stat = path.stat()
    except (FileNotFoundError, OSError):
        return None
    if not path.is_file():
        return None

    platform_file_id = f"platform-v1:{stat.st_dev}:{stat.st_ino}"
    size = stat.st_size
    if size <= FOREGROUND_BUDGET_BYTES:
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        return FileIdentityObservation(
            platform_file_id=platform_file_id,
            content_fingerprint=f"sha256-full-v1:{size}:{digest}",
            content_hash=f"sha256-v1:{digest}",
            bytes_read=len(payload),
        )

    chunks: list[bytes] = []
    offsets = (0, max(0, (size - SAMPLE_BYTES) // 2), max(0, size - SAMPLE_BYTES))
    with path.open("rb") as stream:
        for offset in offsets:
            stream.seek(offset, os.SEEK_SET)
            chunks.append(stream.read(SAMPLE_BYTES))
    digest = hashlib.sha256(
        str(size).encode("ascii") + b"\0" + b"\0".join(chunks)
    ).hexdigest()
    return FileIdentityObservation(
        platform_file_id=platform_file_id,
        content_fingerprint=f"sha256-sampled-v1:{size}:{digest}",
        content_hash=None,
        bytes_read=sum(len(chunk) for chunk in chunks),
    )


def full_content_hash(path_value: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path_value).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256-v1:{digest.hexdigest()}"
