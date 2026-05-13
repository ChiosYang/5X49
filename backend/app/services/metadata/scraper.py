from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

from app.services.event_bus import library_event_bus
from app.services.library import library_manager
from app.services.metadata.artwork import ArtworkDownloader
from app.services.metadata.matcher import generate_search_queries, parse_title_year, score_candidates
from app.services.metadata.models import BatchScrapeOptions, MetadataSearchResult, ScrapeOptions, ScrapeResult
from app.services.metadata.nfo_writer import NFOWriter
from app.services.metadata.tmdb import TMDBClient
from app.services.settings import get_language, get_scrape_require_confirmation


class MetadataScraper:
    def __init__(self):
        self.tmdb = TMDBClient()
        self.artwork = ArtworkDownloader()
        self.nfo_writer = NFOWriter()
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

    def search(self, query: str, year: Optional[int] = None, language: Optional[str] = None) -> list[MetadataSearchResult]:
        target_language = self._language(language)
        candidates_by_id: dict[int, MetadataSearchResult] = {}
        for search_query in generate_search_queries(query):
            results = self.tmdb.search_movies(search_query, year=year, language=target_language)
            if not results and year:
                results = self.tmdb.search_movies(search_query, language=target_language)

            for candidate in score_candidates(search_query, year or 0, results):
                existing = candidates_by_id.get(candidate.tmdb_id)
                if not existing or (candidate.score, candidate.popularity) > (existing.score, existing.popularity):
                    candidates_by_id[candidate.tmdb_id] = candidate

        candidates = list(candidates_by_id.values())
        candidates.sort(key=lambda candidate: (candidate.score, candidate.popularity), reverse=True)
        return candidates

    def scrape_movie(self, movie_id: str, options: ScrapeOptions) -> ScrapeResult:
        movie = library_manager.get_movie(movie_id)
        if not movie:
            return ScrapeResult(status="failed", movie_id=movie_id, message="Movie not found")

        folder = self._movie_folder(movie)
        if not folder:
            return self._mark_failed(movie_id, "Movie does not have an existing folder path")

        language = self._language(options.language)
        try:
            require_confirmation = get_scrape_require_confirmation()
            if options.tmdb_id:
                selected_id = options.tmdb_id
                candidates = []
            elif movie.get("tmdb_id"):
                selected_id = int(movie["tmdb_id"])
                if require_confirmation:
                    candidate = self._candidate_from_existing_movie(movie, selected_id)
                    self._update_scrape_state(
                        movie_id,
                        scrape_status="needs_review",
                        tmdb_confidence=candidate.score,
                        scrape_error="Manual confirmation required",
                    )
                    return ScrapeResult(
                        status="needs_review",
                        movie_id=movie_id,
                        message="Choose a TMDB match to continue",
                        movie=library_manager.get_movie(movie_id),
                        candidates=[candidate],
                    )
                candidates = []
            else:
                query, year = self._query_from_movie(movie)
                candidates = self.search(query, year=year, language=language)
                if not candidates:
                    return self._mark_failed(movie_id, "No TMDB matches found")

                best = candidates[0]
                if require_confirmation:
                    self._update_scrape_state(
                        movie_id,
                        scrape_status="needs_review",
                        tmdb_confidence=best.score,
                        scrape_error="Manual confirmation required",
                    )
                    return ScrapeResult(
                        status="needs_review",
                        movie_id=movie_id,
                        message="Choose a TMDB match to continue",
                        movie=library_manager.get_movie(movie_id),
                        candidates=candidates[:5],
                    )
                if options.mode == "auto" and best.score < 80:
                    self._update_scrape_state(
                        movie_id,
                        scrape_status="needs_review",
                        tmdb_confidence=best.score,
                        scrape_error="Low confidence TMDB match",
                    )
                    return ScrapeResult(
                        status="needs_review",
                        movie_id=movie_id,
                        message="Choose a TMDB match to continue",
                        movie=library_manager.get_movie(movie_id),
                        candidates=candidates[:5],
                    )
                selected_id = best.tmdb_id

            details = self.tmdb.movie_details(selected_id, language=language)
            poster_url = self.tmdb.image_url(details.get("poster_path"), "original")
            backdrop_url = self.tmdb.image_url(details.get("backdrop_path"), "original")
            filename_prefix = self._filename_prefix(movie, folder)

            if options.download_artwork:
                self.artwork.download(poster_url, folder / f"{filename_prefix}-poster.jpg", overwrite=options.overwrite)
                self.artwork.download(backdrop_url, folder / f"{filename_prefix}-fanart.jpg", overwrite=options.overwrite)

            if options.write_nfo:
                self.nfo_writer.write_movie_nfo(
                    folder,
                    details,
                    poster_url=poster_url,
                    backdrop_url=backdrop_url,
                    filename_prefix=filename_prefix,
                    overwrite=options.overwrite,
                )

            from app.services.library_sync import library_sync_service

            updated_movie = library_sync_service.scan_folder(folder, preserve_id=movie_id)
            if not updated_movie:
                return self._mark_failed(movie_id, "Scrape completed but folder rescan failed")

            enriched = {
                **updated_movie,
                "overview": details.get("overview") or updated_movie.get("overview"),
                "metadata_source": "tmdb",
                "nfo_source": "tmdb" if options.write_nfo else updated_movie.get("nfo_source"),
                "scrape_status": "matched",
                "scrape_error": None,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "tmdb_confidence": candidates[0].score if candidates else 100,
            }
            stored = library_manager.upsert_movie(enriched, preserve_id=movie_id)
            library_event_bus.publish_library_changed("metadata_scraped", movie_id=movie_id)
            return ScrapeResult(
                status="success",
                movie_id=movie_id,
                message="Metadata scraped",
                movie=stored,
                candidates=candidates[:5] if candidates else [],
            )
        except Exception as exc:
            return self._mark_failed(movie_id, str(exc))

    def scrape_library(self, options: BatchScrapeOptions) -> dict:
        started_at = datetime.now(timezone.utc).isoformat()
        self._set_status(state="running", last_started_at=started_at, last_error=None)
        result = {"processed": 0, "succeeded": 0, "needs_review": 0, "failed": 0, "skipped": 0}
        try:
            for movie in library_manager.get_movies():
                if not self._in_scope(movie, options):
                    continue
                result["processed"] += 1
                scrape_result = self.scrape_movie(
                    movie["id"],
                    ScrapeOptions(
                        mode="auto",
                        language=options.language,
                        overwrite=options.overwrite,
                        write_nfo=options.write_nfo,
                        download_artwork=options.download_artwork,
                    ),
                )
                if scrape_result.status == "success":
                    result["succeeded"] += 1
                elif scrape_result.status == "needs_review":
                    result["needs_review"] += 1
                elif scrape_result.status == "skipped":
                    result["skipped"] += 1
                else:
                    result["failed"] += 1

            self._set_status(
                state="idle",
                last_finished_at=datetime.now(timezone.utc).isoformat(),
                last_result=result,
            )
            library_event_bus.publish_library_changed("metadata_batch_scraped", result=result)
            return result
        except Exception as exc:
            self._set_status(
                state="error",
                last_finished_at=datetime.now(timezone.utc).isoformat(),
                last_error=str(exc),
            )
            raise

    def _in_scope(self, movie: dict, options: BatchScrapeOptions) -> bool:
        if movie.get("library_status") in {"missing", "ignored"}:
            return False
        if options.scope == "selected":
            return bool(options.movie_ids and movie.get("id") in options.movie_ids)
        if options.scope == "all":
            return True
        if options.scope == "missing_artwork":
            return not movie.get("poster_local") or not movie.get("backdrop_local")
        return (
            movie.get("metadata_source") == "filename"
            and movie.get("scrape_status") in {None, "pending", "failed"}
        )

    def _query_from_movie(self, movie: dict) -> tuple[str, int]:
        if movie.get("video_file"):
            parsed_title, parsed_year = parse_title_year(movie["video_file"])
            return parsed_title, parsed_year

        if movie.get("media_path"):
            parsed_title, parsed_year = parse_title_year(Path(movie["media_path"]).name)
            return parsed_title, parsed_year

        if movie.get("folder_name"):
            parsed_title, parsed_year = parse_title_year(movie["folder_name"])
            return parsed_title, parsed_year

        return movie.get("title") or "", int(movie.get("year") or 0)

    def _candidate_from_existing_movie(self, movie: dict, tmdb_id: int) -> MetadataSearchResult:
        return MetadataSearchResult(
            tmdb_id=tmdb_id,
            title=movie.get("title") or movie.get("original_title") or f"TMDB {tmdb_id}",
            original_title=movie.get("original_title"),
            year=int(movie.get("year") or 0),
            overview=movie.get("overview") or "",
            score=100,
        )

    def _movie_folder(self, movie: dict) -> Optional[Path]:
        folder_path = movie.get("folder_path")
        if folder_path:
            folder = Path(folder_path).resolve()
            if folder.exists() and folder.is_dir():
                return folder
        media_path = movie.get("media_path")
        if media_path:
            folder = Path(media_path).resolve().parent
            if folder.exists() and folder.is_dir():
                return folder
        return None

    def _filename_prefix(self, movie: dict, folder: Path) -> str:
        video_file = movie.get("video_file")
        if video_file:
            return Path(video_file).stem

        media_path = movie.get("media_path")
        if media_path:
            return Path(media_path).stem

        first_video = self._first_video_file(folder)
        if first_video:
            return first_video.stem

        return folder.name

    def _first_video_file(self, folder: Path) -> Optional[Path]:
        video_extensions = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".ts", ".iso"}
        try:
            videos = [
                path
                for path in folder.iterdir()
                if path.is_file() and path.suffix.lower() in video_extensions
            ]
        except OSError:
            return None
        return sorted(videos, key=lambda path: path.name.lower())[0] if videos else None

    def _mark_failed(self, movie_id: str, message: str) -> ScrapeResult:
        self._update_scrape_state(movie_id, scrape_status="failed", scrape_error=message)
        return ScrapeResult(
            status="failed",
            movie_id=movie_id,
            message=message,
            movie=library_manager.get_movie(movie_id),
        )

    def _update_scrape_state(self, movie_id: str, **updates):
        movie = library_manager.get_movie(movie_id)
        if not movie:
            return
        library_manager.upsert_movie({**movie, **updates}, preserve_id=movie_id)
        library_event_bus.publish_library_changed("metadata_scrape_status", movie_id=movie_id)

    def _language(self, value: Optional[str]) -> str:
        if value:
            return value
        return "zh-CN" if get_language() == "zh" else "en-US"

    def _set_status(self, **updates):
        with self._lock:
            self._status.update(updates)


metadata_scraper = MetadataScraper()
