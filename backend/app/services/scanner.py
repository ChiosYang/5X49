"""
NFO File Scanner for tinyMediaManager (TMM) scraped movies.
Parses .nfo XML files to extract rich metadata.
"""
import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.services.artwork_cache import artwork_cache
from app.services.video_probe import video_probe_service
from app.contracts.structured_metadata import (
    CountryObservation,
    CreditObservation,
    GenreObservation,
    ObservationIssue,
    StructuredMetadataObservationDraft,
    TitleObservation,
)


@dataclass(frozen=True)
class FilmObservation:
    film: dict
    structured_metadata: StructuredMetadataObservationDraft | None = None


class NFOScanner:
    """Scans a directory for TMM-scraped movie folders and parses .nfo files."""

    video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.m4v', '.ts', '.iso']
    video_probe_fields = (
        "video_width",
        "video_height",
        "video_codec",
        "video_bitrate",
        "video_duration",
        "video_fps",
        "video_dynamic_range",
        "video_bit_depth",
    )
    ignored_file_suffixes = (
        ".part",
        ".tmp",
        ".download",
        ".crdownload",
    )

    def __init__(self, media_dir: str, video_probe_cache: Optional[dict[str, dict]] = None):
        self.media_dir = Path(media_dir)
        self.video_probe_cache = video_probe_cache or {}

    def scan(self) -> list[dict]:
        """Scan all subdirectories for movies and parse metadata when available."""
        return [item.film for item in self.scan_observed()]

    def scan_observed(self) -> list[FilmObservation]:
        """Scan movies while retaining the internal structured metadata observation."""
        movies = []
        
        if not self.media_dir.exists():
            print("Media directory not found")
            return movies
        
        for folder in self.media_dir.iterdir():
            if not folder.is_dir() or folder.name.startswith('.'):
                continue
            
            observed = self.scan_folder_observed(folder)
            if observed:
                movies.append(observed)
                print("  Parsed movie")
        
        print(f"\nTotal movies scanned: {len(movies)}")
        return movies

    def scan_folder(self, folder: Path | str) -> Optional[dict]:
        """Scan a single movie folder, using NFO when present and filename fallback otherwise."""
        observed = self.scan_folder_observed(folder)
        return observed.film if observed else None

    def scan_folder_observed(self, folder: Path | str) -> Optional[FilmObservation]:
        """Scan one folder into Film and structured metadata observations."""
        folder = Path(folder)
        if not folder.exists() or not folder.is_dir():
            return None

        video_file = self._find_video_file(folder)

        nfo_file = self._find_nfo_file(folder, video_file)
        if nfo_file:
            return self._parse_nfo_observed(nfo_file, folder)

        if not video_file:
            return None

        file_title, file_year = self._parse_title_year(video_file.name)

        film_observation = {
            "id": self._build_source_record_id(None, None, file_year, folder, video_file),
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
        film_observation = self._with_file_info(film_observation, folder, video_file)
        return FilmObservation(
            film=film_observation,
            structured_metadata=StructuredMetadataObservationDraft(
                origin_kind="filename",
                source_instance_id="local",
                observed_at=film_observation["metadata_updated_at"],
                complete_fields=frozenset({"titles"}),
                titles=(
                    TitleObservation(file_title, "canonical", "und"),
                    TitleObservation(file_title, "original", "und"),
                ),
            ),
        )

    def parse_nfo(self, nfo_path: Path, folder: Path) -> Optional[dict]:
        """Parse a single .nfo XML file and return standardized movie dict."""
        observed = self._parse_nfo_observed(nfo_path, folder)
        return observed.film if observed else None

    def _parse_nfo_observed(self, nfo_path: Path, folder: Path) -> Optional[FilmObservation]:
        """Parse one NFO into Film and structured metadata observations."""
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
            
            # Directors can be flat Kodi elements or nested tinyMediaManager elements.
            director_observations = self._director_observations(root)
            director = director_observations[0].name if director_observations else ""
            
            # Ratings
            imdb_rating = None
            for rating in root.findall('.//rating'):
                if rating.get('name') == 'imdb':
                    val = rating.findtext('value')
                    if val:
                        imdb_rating = float(val)
                        break
            
            # Actors (top 5)
            structured_actors, actor_issues = self._actor_observations(root)
            actors = [
                {"name": actor.name, "role": actor.character}
                for actor in structured_actors[:5]
            ]
            
            # Image paths (local files)
            folder_name = folder.name
            poster_local = self._find_image(folder, "-poster")
            fanart_local = self._find_image(folder, "-fanart")
            poster_thumb_local = artwork_cache.generate(folder / poster_local, "poster") if poster_local else None
            backdrop_thumb_local = artwork_cache.generate(folder / fanart_local, "backdrop") if fanart_local else None
            
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
            source_record_id = self._build_source_record_id(tmdb_id, imdb_id, year, folder, video_file)
            generator = root.findtext('generator') or ""
            nfo_source = "tmdb" if generator.strip().lower() == "5x49" else "tmm"
            
            film_observation = {
                "id": source_record_id,
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
                "poster_thumb_local": poster_thumb_local,
                "backdrop_thumb_local": backdrop_thumb_local,
                # TMDB CDN fallbacks
                "poster_path": self._extract_tmdb_path(poster_url),
                "backdrop_path": self._extract_tmdb_path(fanart_url),
                # Folder info
                "folder_name": folder_name,
                "video_file": video_file.name if video_file else None,
                "nfo_source": nfo_source,
                "metadata_source": nfo_source,
                "scrape_status": "matched",
                **self.nfo_signature(nfo_path),
            }
            film_observation = self._with_file_info(film_observation, folder, video_file)
            title_value = (root.findtext("title") or title).strip()
            original_value = (root.findtext("originaltitle") or title).strip()
            title_locale = self._title_locale(root.findtext("language"))
            original_locale = self._title_locale(root.findtext("originallanguage"))
            titles = [
                TitleObservation(title_value, "canonical", title_locale),
                TitleObservation(original_value, "original", original_locale),
            ]
            if title_value != original_value:
                titles.append(TitleObservation(title_value, "localized", title_locale))
            genre_observations = []
            for element in root.findall("genre"):
                value = (element.text or "").strip()
                if not value:
                    continue
                raw_id = element.get("tmdbid") or element.get("tmdb_id")
                tmdb_genre_id = int(raw_id) if raw_id and raw_id.isdigit() else None
                genre_observations.append(
                    GenreObservation(value=value, tmdb_id=tmdb_genre_id, locale="und")
                )
            observation = StructuredMetadataObservationDraft(
                origin_kind="nfo",
                source_instance_id="local",
                observed_at=film_observation["metadata_updated_at"],
                titles=tuple(titles),
                countries=tuple(CountryObservation(value) for value in countries),
                credits=tuple((*director_observations, *structured_actors)),
                genres=tuple(genre_observations),
                issues=tuple(actor_issues),
            )
            return FilmObservation(film=film_observation, structured_metadata=observation)

        except ET.ParseError as e:
            print(f"  NFO XML parse error: {e}")
            return None
        except Exception as e:
            print(f"  NFO parse error: {type(e).__name__}")
            return None

    def _director_observations(self, root: ET.Element) -> list[CreditObservation]:
        directors: list[CreditObservation] = []
        for index, element in enumerate(root.findall("director")):
            name = (element.findtext("name") or element.text or "").strip()
            if not name:
                continue
            external_id = element.get("tmdbid") or element.findtext("tmdbid")
            directors.append(
                CreditObservation(
                    name=name,
                    department="Directing",
                    job="Director",
                    billing_order=index,
                    provider="tmdb.person" if external_id else None,
                    external_id=external_id.strip() if external_id else None,
                )
            )
        return directors

    def _actor_observations(
        self,
        root: ET.Element,
    ) -> tuple[list[CreditObservation], list[ObservationIssue]]:
        actors: list[CreditObservation] = []
        issues: list[ObservationIssue] = []
        for index, element in enumerate(root.findall("actor")[:10]):
            name = (element.findtext("name") or "").strip()
            if not name:
                issues.append(
                    ObservationIssue(
                        "credit",
                        "credit_invalid",
                        {"index": index, "has_name": False},
                    )
                )
                continue
            role = (element.findtext("role") or "").strip()
            raw_order = (element.findtext("order") or "").strip()
            billing_order = int(raw_order) if raw_order.isdigit() else index
            external_id = element.get("tmdbid") or element.findtext("tmdbid")
            actors.append(
                CreditObservation(
                    name=name,
                    department="Acting",
                    job="Actor",
                    character=role,
                    billing_order=billing_order,
                    provider="tmdb.person" if external_id else None,
                    external_id=external_id.strip() if external_id else None,
                )
            )
        return actors, issues

    @staticmethod
    def _title_locale(value: Optional[str]) -> str:
        if not value or not value.strip():
            return "und"
        normalized = value.strip().replace("_", "-")
        if normalized.casefold() in {"zh", "zh-cn", "zh-hans"}:
            return "zh-CN"
        return normalized

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

    def nfo_signature(self, nfo_path: Path) -> dict:
        stat = nfo_path.stat()
        return {
            "nfo_file": nfo_path.name,
            "nfo_path": str(nfo_path.resolve()),
            "nfo_size": stat.st_size,
            "nfo_mtime": stat.st_mtime,
            "nfo_fingerprint": self._file_sha256(nfo_path),
        }

    def _file_sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

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

    def _build_source_record_id(
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

    def _with_file_info(self, film_observation: dict, folder: Path, video_file: Optional[Path]) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        film_observation.update({
            "folder_name": folder.name,
            "folder_path": str(folder.resolve()),
            "last_seen_at": now,
            "missing_since": None,
            "library_status": "available",
            "metadata_updated_at": now,
        })

        if video_file:
            stat = video_file.stat()
            media_path = str(video_file.resolve())
            film_observation.update({
                "media_path": media_path,
                "video_file": video_file.name,
                "file_size": stat.st_size,
                "file_mtime": stat.st_mtime,
            })
            probe_data = self._cached_video_probe(media_path, stat.st_size, stat.st_mtime)
            if not probe_data:
                probe_data = video_probe_service.probe(video_file)
            if probe_data:
                if film_observation.get("audio_tracks"):
                    probe_data.pop("audio_tracks", None)
                film_observation.update(probe_data)

        return film_observation

    def _cached_video_probe(self, media_path: str, file_size: int, file_mtime: float) -> dict:
        cached = self.video_probe_cache.get(media_path)
        if not cached:
            return {}
        if cached.get("file_size") != file_size or cached.get("file_mtime") != file_mtime:
            return {}

        probe_data = {
            field: cached.get(field)
            for field in self.video_probe_fields
            if cached.get(field) is not None
        }
        if cached.get("audio_tracks"):
            probe_data["audio_tracks"] = cached["audio_tracks"]
        return probe_data

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
