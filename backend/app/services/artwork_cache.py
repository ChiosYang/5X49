import hashlib
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps


ARTWORK_CACHE_DIR = Path("data") / "artwork-cache"


class ArtworkCache:
    variants = {
        "poster": (500, 750),
        "backdrop": (960, 540),
    }

    def generate(self, source: Optional[Path], variant: str) -> Optional[str]:
        if not source or variant not in self.variants:
            return None

        try:
            source = source.resolve()
            stat = source.stat()
        except OSError:
            return None

        cache_key = "|".join(
            [
                str(source),
                variant,
                str(stat.st_mtime_ns),
                str(stat.st_size),
            ]
        )
        filename = f"{variant}-{hashlib.sha256(cache_key.encode('utf-8')).hexdigest()[:24]}.jpg"
        destination = ARTWORK_CACHE_DIR / filename

        if destination.exists():
            return f"/artwork-cache/{filename}"

        temp_path = None
        try:
            ARTWORK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with Image.open(source) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail(self.variants[variant], Image.Resampling.LANCZOS)
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                elif image.mode == "L":
                    image = image.convert("RGB")

                with tempfile.NamedTemporaryFile(
                    delete=False,
                    dir=ARTWORK_CACHE_DIR,
                    suffix=".tmp",
                ) as temp_file:
                    temp_path = Path(temp_file.name)
                image.save(temp_path, format="JPEG", quality=82, optimize=True, progressive=True)
                temp_path.replace(destination)
        except Exception as exc:
            if temp_path:
                temp_path.unlink(missing_ok=True)
            print(f"Warning: failed to generate {variant} thumbnail for {source}: {exc}")
            return None

        return f"/artwork-cache/{filename}"


artwork_cache = ArtworkCache()
