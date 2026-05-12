"""
NFO File Scanner for tinyMediaManager (TMM) scraped movies.
Parses .nfo XML files to extract rich metadata.
"""
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone


class NFOScanner:
    """Scans a directory for TMM-scraped movie folders and parses .nfo files."""

    video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.m4v', '.ts', '.iso']
    ignored_file_suffixes = (
        ".part",
        ".tmp",
        ".download",
        ".crdownload",
    )

    def __init__(self, media_dir: str):
        self.media_dir = Path(media_dir)

    def scan(self) -> list[dict]:
        """Scan all subdirectories for movies and parse metadata when available."""
        movies = []
        
        if not self.media_dir.exists():
            print(f"❌ Media directory not found: {self.media_dir}")
            return movies
        
        for folder in self.media_dir.iterdir():
            if not folder.is_dir() or folder.name.startswith('.'):
                continue
            
            movie_data = self.scan_folder(folder)
            if movie_data:
                movies.append(movie_data)
                print(f"  ✅ Parsed: {movie_data['title']} ({movie_data['year']})")
        
        print(f"\n📚 Total movies scanned: {len(movies)}")
        return movies

    def scan_folder(self, folder: Path | str) -> Optional[dict]:
        """Scan a single movie folder, using NFO when present and filename fallback otherwise."""
        folder = Path(folder)
        if not folder.exists() or not folder.is_dir():
            return None

        video_file = self._find_video_file(folder)

        nfo_file = self._find_nfo_file(folder, video_file)
        if nfo_file:
            return self.parse_nfo(nfo_file, folder)

        if not video_file:
            return None

        file_title, file_year = self._parse_title_year(video_file.name)

        movie_data = {
            "id": self._build_movie_id(None, None, file_year, folder, video_file),
            "title": file_title,
            "title_cn": file_title,
            "year": file_year,
            "genres": [],
            "actors": [],
            "folder_name": folder.name,
            "video_file": video_file.name,
            "nfo_source": "filename",
            "metadata_source": "filename",
            "scrape_status": "pending",
            "poster_local": None,
            "backdrop_local": None,
            "poster_path": None,
            "backdrop_path": None,
        }
        return self._with_file_info(movie_data, folder, video_file)

    def parse_nfo(self, nfo_path: Path, folder: Path) -> Optional[dict]:
        """Parse a single .nfo XML file and return standardized movie dict."""
        try:
            tree = ET.parse(nfo_path)
            root = tree.getroot()
            
            # Extract core fields
            title = root.findtext('originaltitle') or root.findtext('title') or "Unknown"
            title_cn = root.findtext('title') or title
            year = int(root.findtext('year') or 0)
            tmdb_id = root.findtext('tmdbid')
            imdb_id = root.findtext('id')
            plot = root.findtext('plot') or root.findtext('outline') or ""
            runtime = int(root.findtext('runtime') or 0)
            
            # Genres (multiple <genre> tags)
            genres = [g.text for g in root.findall('genre') if g.text]
            countries = [c.text for c in root.findall('country') if c.text]
            audio_tracks = self._parse_audio_tracks(root)
            
            # Director
            director = root.findtext('director') or ""
            
            # Ratings
            imdb_rating = None
            for rating in root.findall('.//rating'):
                if rating.get('name') == 'imdb':
                    val = rating.findtext('value')
                    if val:
                        imdb_rating = float(val)
                        break
            
            # Actors (top 5)
            actors = []
            for actor in root.findall('actor')[:5]:
                name = actor.findtext('name')
                role = actor.findtext('role')
                if name:
                    actors.append({"name": name, "role": role or ""})
            
            # Image paths (local files)
            folder_name = folder.name
            poster_local = self._find_image(folder, "-poster")
            fanart_local = self._find_image(folder, "-fanart")
            
            # Also get TMDB URLs as fallback
            poster_url = None
            for thumb in root.findall('thumb'):
                if thumb.get('aspect') == 'poster' and thumb.text:
                    poster_url = thumb.text
                    break
            
            fanart_url = None
            fanart_elem = root.find('fanart/thumb')
            if fanart_elem is not None and fanart_elem.text:
                fanart_url = fanart_elem.text
            
            video_file = self._find_video_file(folder)
            movie_id = self._build_movie_id(tmdb_id, imdb_id, year, folder, video_file)
            generator = root.findtext('generator') or ""
            nfo_source = "tmdb" if generator.strip().lower() == "5x49" else "tmm"
            
            movie_data = {
                "id": movie_id,
                "title": title,
                "title_cn": title_cn,
                "year": year,
                "tmdb_id": tmdb_id,
                "imdb_id": imdb_id,
                "plot": plot,
                "runtime": runtime,
                "countries": countries,
                "audio_tracks": audio_tracks,
                "genres": genres,
                "director": director,
                "imdb_rating": imdb_rating,
                "actors": actors,
                # Local paths (relative to media mount point)
                "poster_local": f"/media/{folder_name}/{poster_local}" if poster_local else None,
                "backdrop_local": f"/media/{folder_name}/{fanart_local}" if fanart_local else None,
                # TMDB CDN fallbacks
                "poster_path": self._extract_tmdb_path(poster_url),
                "backdrop_path": self._extract_tmdb_path(fanart_url),
                # Folder info
                "folder_name": folder_name,
                "video_file": video_file.name if video_file else None,
                "nfo_source": nfo_source,
                "metadata_source": nfo_source,
                "scrape_status": "matched",
            }
            return self._with_file_info(movie_data, folder, video_file)

        except ET.ParseError as e:
            print(f"  ❌ XML Parse Error in {nfo_path}: {e}")
            return None
        except Exception as e:
            print(f"  ❌ Error parsing {nfo_path}: {e}")
            return None

    def _find_image(self, folder: Path, suffix: str) -> Optional[str]:
        """Find an image file with the given suffix (-poster, -fanart, etc.)."""
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            matches = sorted(folder.glob(f"*{suffix}{ext}"), key=lambda path: path.name.lower())
            if matches:
                return matches[0].name

        fallback_names = {
            "-poster": ["poster"],
            "-fanart": ["fanart", "thumb"],
        }.get(suffix, [])
        for name in fallback_names:
            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                image_path = folder / f"{name}{ext}"
                if image_path.exists():
                    return image_path.name

        return None

    def _find_nfo_file(self, folder: Path, video_file: Optional[Path]) -> Optional[Path]:
        if video_file:
            preferred = folder / f"{video_file.stem}.nfo"
            if preferred.exists():
                return preferred

        movie_nfo = folder / "movie.nfo"
        if movie_nfo.exists():
            return movie_nfo

        nfo_files = sorted(folder.glob("*.nfo"), key=lambda path: path.name.lower())
        return nfo_files[0] if nfo_files else None

    def _parse_audio_tracks(self, root: ET.Element) -> list[dict]:
        """Extract compact audio stream metadata from TMM/Kodi-style NFO."""
        tracks = []
        for audio in root.findall('.//streamdetails/audio'):
            codec = audio.findtext('codec') or ""
            language = audio.findtext('language') or ""
            channels = audio.findtext('channels') or ""
            if codec or language or channels:
                tracks.append({
                    "codec": codec,
                    "language": language,
                    "channels": channels,
                })
        return tracks

    def _build_movie_id(
        self,
        tmdb_id: Optional[str],
        imdb_id: Optional[str],
        year: int,
        folder: Path,
        video_file: Optional[Path],
    ) -> str:
        """Build a stable ASCII ID suitable for URL path segments."""
        tmdb_part = self._sanitize_id_part(tmdb_id)
        if tmdb_part:
            return f"{tmdb_part}_{year}" if year else tmdb_part

        imdb_part = self._sanitize_id_part(imdb_id)
        if imdb_part:
            return f"{imdb_part}_{year}" if year else imdb_part

        source_path = video_file.resolve() if video_file else folder.resolve()
        digest = hashlib.sha256(str(source_path).encode("utf-8")).hexdigest()[:16]
        return f"local_{digest}"

    def _sanitize_id_part(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None

        cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "", value.strip())
        return cleaned or None

    def _find_video_file(self, folder: Path) -> Optional[Path]:
        """Find the primary video file in a movie folder."""
        for ext in self.video_extensions:
            videos = list(folder.glob(f"*{ext}")) + list(folder.glob(f"*{ext.upper()}"))
            usable_videos = [video for video in videos if self._is_usable_video_file(video)]
            if usable_videos:
                return sorted(usable_videos, key=lambda path: path.name.lower())[0]
        return None

    def _is_usable_video_file(self, path: Path) -> bool:
        lower_name = path.name.lower()
        if lower_name.endswith(self.ignored_file_suffixes):
            return False
        try:
            return path.is_file() and path.stat().st_size > 0
        except OSError:
            return False

    def _with_file_info(self, movie_data: dict, folder: Path, video_file: Optional[Path]) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        movie_data.update({
            "folder_name": folder.name,
            "folder_path": str(folder.resolve()),
            "last_seen_at": now,
            "missing_since": None,
            "library_status": "available",
            "metadata_updated_at": now,
        })

        if video_file:
            stat = video_file.stat()
            movie_data.update({
                "media_path": str(video_file.resolve()),
                "video_file": video_file.name,
                "file_size": stat.st_size,
                "file_mtime": stat.st_mtime,
            })

        return movie_data

    def _parse_title_year(self, name: str) -> tuple[str, int]:
        """Extract a usable title and year from a folder or filename."""
        import re

        stem = Path(name).stem
        match = re.search(r"(19\d{2}|20\d{2})", stem)
        year = int(match.group(1)) if match else 0
        title_part = stem[:match.start()] if match else stem
        title = re.sub(r"[\._\-\[\]\(\)]+", " ", title_part).strip()
        title = re.sub(r"\s+", " ", title) or stem
        return title, year

    def _extract_tmdb_path(self, url: Optional[str]) -> Optional[str]:
        """Extract TMDB path from full URL for use with image.tmdb.org prefix."""
        if not url:
            return None
        # URL format: https://image.tmdb.org/t/p/original/xxx.jpg
        # We want to extract: /xxx.jpg
        if "image.tmdb.org" in url:
            parts = url.split("/original")
            if len(parts) > 1:
                return parts[1]
        return None


# Test scanner if run directly
if __name__ == "__main__":
    import json
    test_dir = "/Users/alicolia/Projects/movies-nfo-test"
    scanner = NFOScanner(test_dir)
    movies = scanner.scan()
    print(json.dumps(movies[:2], indent=2, ensure_ascii=False))
