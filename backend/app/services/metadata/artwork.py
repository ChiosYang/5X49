from pathlib import Path
from threading import local
from typing import Callable, Optional

import requests


class ArtworkDownloader:
    def __init__(self, session_factory: Callable[[], requests.Session] = requests.Session):
        self._session_factory = session_factory
        self._thread_local = local()

    def download(self, url: Optional[str], destination: Path, overwrite: bool = False) -> Optional[Path]:
        if not url:
            return None
        if destination.exists() and not overwrite:
            return destination

        response = self._session().get(url, timeout=30)
        response.raise_for_status()

        temp_path = destination.with_suffix(destination.suffix + ".tmp")
        temp_path.write_bytes(response.content)
        temp_path.replace(destination)
        return destination

    def _session(self) -> requests.Session:
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = self._session_factory()
            self._thread_local.session = session
        return session
