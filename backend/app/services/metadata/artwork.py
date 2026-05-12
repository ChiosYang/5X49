from pathlib import Path
from typing import Optional

import requests


class ArtworkDownloader:
    def download(self, url: Optional[str], destination: Path, overwrite: bool = False) -> Optional[Path]:
        if not url:
            return None
        if destination.exists() and not overwrite:
            return destination

        response = requests.get(url, timeout=30)
        response.raise_for_status()

        temp_path = destination.with_suffix(destination.suffix + ".tmp")
        temp_path.write_bytes(response.content)
        temp_path.replace(destination)
        return destination
