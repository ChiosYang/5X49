import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

from app.services.event_bus import library_event_bus
from app.services.event_store import event_store
from app.services.metadata.matcher import parse_title_year
from app.services.metadata.models import MetadataSearchResult, RootOrganizeOptions, ScrapeOptions
from app.services.metadata.scraper import metadata_scraper
from app.services.settings import (
    get_media_dir,
    get_media_file_stable_seconds,
    get_organize_min_confidence,
    get_organize_rename_style,
    get_scrape_require_confirmation,
)


class RootVideoOrganizer:
    video_extensions = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".ts", ".iso"}
    sidecar_extensions = {".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx"}
    ignored_suffixes = (".part", ".tmp", ".download", ".crdownload")

    def __init__(self):
        self._lock = Lock()
        self._status = {
            "state": "idle",
            "last_started_at": None,
            "last_finished_at": None,
            "last_error": None,
            "last_result": None,
        }

    def get_status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def list_root_videos(self, media_dir: Optional[str] = None) -> list[dict]:
        root = Path(media_dir or get_media_dir()).resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Directory not found: {root}")

        videos = []
        for path in self._root_videos(root):
            lower_name = path.name.lower()
            if lower_name.endswith(self.ignored_suffixes):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size <= 0:
                continue
            parsed_title, parsed_year = parse_title_year(path.name)
            stable = self._is_usable_root_video(path, root)
            videos.append({
                "path": str(path.resolve()),
                "filename": path.name,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "stable": stable,
                "parsed_title": parsed_title,
                "parsed_year": parsed_year,
                "status": "needs_organize" if stable else "waiting_for_stability",
            })
        return videos

    def organize_root(self, media_dir: Optional[str] = None, options: Optional[RootOrganizeOptions] = None) -> dict:
        options = options or RootOrganizeOptions(rename_style=get_organize_rename_style())
        root = Path(media_dir or get_media_dir()).resolve()
        started_at = datetime.now(timezone.utc).isoformat()
        self._set_status(state="running", last_started_at=started_at, last_error=None)
        result = {
            "processed": 0,
            "organized": 0,
            "scraped": 0,
            "needs_review": 0,
            "failed": 0,
            "skipped": 0,
            "items": [],
        }

        try:
            if not root.exists() or not root.is_dir():
                raise FileNotFoundError(f"Directory not found: {root}")

            for video_path in self._root_videos(root):
                item = self.organize_file(video_path, root, options)
                result["processed"] += 1
                result["items"].append(item)
                status = item.get("status")
                if status == "success":
                    result["organized"] += 1
                    result["scraped"] += 1 if item.get("scrape_status") == "success" else 0
                elif status == "needs_review":
                    result["needs_review"] += 1
                elif status == "skipped":
                    result["skipped"] += 1
                else:
                    result["failed"] += 1

            self._set_status(
                state="idle",
                last_finished_at=datetime.now(timezone.utc).isoformat(),
                last_result=result,
            )
            if result["processed"]:
                library_event_bus.publish_library_changed("root_videos_organized", result=result)
            return result
        except Exception as exc:
            self._set_status(
                state="error",
                last_finished_at=datetime.now(timezone.utc).isoformat(),
                last_error=str(exc),
            )
            raise

    def organize_file(self, video_path: Path, root: Path, options: RootOrganizeOptions) -> dict:
        video_path = video_path.resolve()
        if not self._is_usable_root_video(video_path, root):
            return {"status": "skipped", "path": str(video_path), "message": "Not a stable root video"}

        query, year = parse_title_year(video_path.name)
        candidates = metadata_scraper.search(query, year=year, language=options.language)
        if not candidates:
            return {"status": "failed", "path": str(video_path), "message": "No TMDB matches found"}

        best = candidates[0]
        min_confidence = options.min_confidence
        if min_confidence is None:
            min_confidence = get_organize_min_confidence()
        if best.score < min_confidence:
            event_store.safe_append(
                "RootVideoOrganizationNeedsReview",
                "file",
                str(video_path),
                {
                    "path": str(video_path),
                    "reason": "Low confidence TMDB match",
                    "candidate": best.model_dump(),
                    "min_confidence": min_confidence,
                },
            )
            return {
                "status": "needs_review",
                "path": str(video_path),
                "message": "Low confidence TMDB match",
                "candidate": best.model_dump(),
            }
        if get_scrape_require_confirmation():
            event_store.safe_append(
                "RootVideoOrganizationNeedsReview",
                "file",
                str(video_path),
                {
                    "path": str(video_path),
                    "reason": "Manual confirmation required",
                    "candidate": best.model_dump(),
                },
            )
            return {
                "status": "needs_review",
                "path": str(video_path),
                "message": "Manual confirmation required",
                "candidate": best.model_dump(),
            }

        return self._organize_matched_file(video_path, root, best, year, options)

    def organize_file_confirmed(self, video_path: Path, root: Path, tmdb_id: int, options: RootOrganizeOptions) -> dict:
        video_path = video_path.resolve()
        if not self._is_usable_root_video(video_path, root):
            return {"status": "skipped", "path": str(video_path), "message": "Not a stable root video"}

        _, year = parse_title_year(video_path.name)
        details = metadata_scraper.tmdb.movie_details(
            tmdb_id,
            language=metadata_scraper._language(options.language),
            artwork_language=metadata_scraper._artwork_language(options.artwork_language),
        )
        release_year = self._release_year(details.get("release_date"))
        candidate = MetadataSearchResult(
            tmdb_id=tmdb_id,
            title=details.get("title") or details.get("original_title") or f"TMDB {tmdb_id}",
            original_title=details.get("original_title"),
            year=release_year,
            overview=details.get("overview") or "",
            poster_path=details.get("poster_path"),
            backdrop_path=details.get("backdrop_path"),
            popularity=float(details.get("popularity") or 0),
            score=100,
        )
        return self._organize_matched_file(video_path, root, candidate, year, options)

    def _organize_matched_file(
        self,
        video_path: Path,
        root: Path,
        candidate: MetadataSearchResult,
        parsed_year: int,
        options: RootOrganizeOptions,
    ) -> dict:
        target_dir = self._target_dir(root, candidate.title, candidate.year or parsed_year)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_video = target_dir / self._target_video_name(
            video_path,
            candidate.title,
            candidate.year or parsed_year,
            options.rename_style,
        )
        if target_video.exists() and not options.overwrite:
            return {
                "status": "failed",
                "path": str(video_path),
                "message": f"Target video already exists: {target_video}",
            }

        moved_sidecars = self._move_sidecars(video_path, target_dir, options.overwrite)
        shutil.move(str(video_path), str(target_video))

        from app.services.library_sync import library_sync_service

        movie = library_sync_service.scan_folder(target_dir)
        if not movie:
            return {
                "status": "failed",
                "path": str(target_video),
                "message": "Moved video but scan failed",
                "sidecars": moved_sidecars,
            }

        scrape_result = metadata_scraper.scrape_movie(
            movie["id"],
            ScrapeOptions(
                mode="manual",
                tmdb_id=candidate.tmdb_id,
                language=options.language,
                artwork_language=options.artwork_language,
                overwrite=options.overwrite,
                write_nfo=options.write_nfo,
                download_artwork=options.download_artwork,
            ),
        )

        event_store.safe_append(
            "RootVideoOrganized",
            "movie",
            movie["id"],
            {
                "movie_id": movie["id"],
                "source_path": str(video_path),
                "target_path": str(target_video),
                "target_dir": str(target_dir),
                "tmdb_id": candidate.tmdb_id,
                "score": candidate.score,
                "rename_style": options.rename_style,
                "scrape_status": scrape_result.status,
                "sidecars": moved_sidecars,
            },
        )
        return {
            "status": "success",
            "source_path": str(video_path),
            "target_path": str(target_video),
            "target_dir": str(target_dir),
            "movie_id": movie["id"],
            "tmdb_id": candidate.tmdb_id,
            "score": candidate.score,
            "scrape_status": scrape_result.status,
            "sidecars": moved_sidecars,
        }

    def _root_videos(self, root: Path) -> list[Path]:
        videos = []
        for path in root.iterdir():
            if path.is_file() and path.suffix.lower() in self.video_extensions:
                videos.append(path)
        return sorted(videos, key=lambda path: path.name.lower())

    def _is_usable_root_video(self, path: Path, root: Path) -> bool:
        if path.parent.resolve() != root:
            return False
        lower_name = path.name.lower()
        if lower_name.endswith(self.ignored_suffixes):
            return False
        try:
            stat = path.stat()
        except OSError:
            return False
        if stat.st_size <= 0:
            return False
        stable_seconds = get_media_file_stable_seconds()
        return stable_seconds <= 0 or stat.st_mtime <= time.time() - stable_seconds

    def _target_dir(self, root: Path, title: str, year: int) -> Path:
        base = self._safe_name(f"{title} ({year})" if year else title)
        return root / (base or "Unknown Movie")

    def _target_video_name(self, source: Path, title: str, year: int, style: str) -> str:
        if style == "title_year":
            base = self._safe_name(f"{title} ({year})" if year else title)
            return f"{base or source.stem}{source.suffix}"
        return source.name

    def _move_sidecars(self, source: Path, target_dir: Path, overwrite: bool) -> list[str]:
        moved = []
        for sidecar in sorted(source.parent.glob(f"{source.stem}.*"), key=lambda path: path.name.lower()):
            if sidecar == source or sidecar.suffix.lower() not in self.sidecar_extensions:
                continue
            target = target_dir / sidecar.name
            if target.exists() and not overwrite:
                continue
            shutil.move(str(sidecar), str(target))
            moved.append(str(target))
        return moved

    def _safe_name(self, value: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", value)
        cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
        return cleaned[:180]

    def _release_year(self, release_date: Optional[str]) -> int:
        if not release_date:
            return 0
        try:
            return int(str(release_date).split("-", 1)[0])
        except ValueError:
            return 0

    def _set_status(self, **updates):
        with self._lock:
            self._status.update(updates)


root_video_organizer = RootVideoOrganizer()
