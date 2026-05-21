from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional
from uuid import uuid4

from app.services.event_bus import library_event_bus
from app.services.event_store import event_store
from app.services.library import library_manager
from app.services.metadata.artwork import ArtworkDownloader
from app.services.metadata.matcher import generate_search_queries, parse_title_year, score_candidates
from app.services.metadata.models import (
    ArtworkImage,
    ArtworkSelection,
    BatchScrapeOptions,
    MetadataSearchResult,
    MovieArtworkOptions,
    ScrapeOptions,
    ScrapeResult,
)
from app.services.metadata.nfo_writer import NFOWriter
from app.services.metadata.tmdb import TMDBClient
from app.services.settings import get_artwork_language, get_language, get_media_dir, get_scrape_require_confirmation


REVIEW_CANDIDATE_LIMIT = 20

METADATA_MATCH_FIELDS = (
    "title",
    "title_cn",
    "year",
    "tmdb_id",
    "imdb_id",
    "overview",
    "plot",
    "runtime",
    "countries",
    "audio_tracks",
    "genres",
    "director",
    "imdb_rating",
    "actors",
    "poster_local",
    "backdrop_local",
    "poster_thumb_local",
    "backdrop_thumb_local",
    "poster_path",
    "backdrop_path",
    "nfo_source",
    "metadata_source",
    "scrape_status",
    "scrape_error",
    "scraped_at",
    "tmdb_confidence",
)

ARTWORK_SELECTION_FIELDS = (
    "poster_local",
    "backdrop_local",
    "poster_thumb_local",
    "backdrop_thumb_local",
    "poster_path",
    "backdrop_path",
    "metadata_updated_at",
)


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

    def get_candidate(self, tmdb_id: int, language: Optional[str] = None) -> MetadataSearchResult:
        details = self.tmdb.movie_details(tmdb_id, language=self._language(language))
        return MetadataSearchResult(
            tmdb_id=tmdb_id,
            title=details.get("title") or details.get("original_title") or f"TMDB {tmdb_id}",
            original_title=details.get("original_title"),
            year=self._release_year(details.get("release_date")),
            overview=details.get("overview") or "",
            poster_path=details.get("poster_path"),
            backdrop_path=details.get("backdrop_path"),
            popularity=float(details.get("popularity") or 0),
            score=100,
        )

    def artwork_options(
        self,
        movie_id: str,
        language: Optional[str] = None,
        artwork_language: Optional[str] = None,
    ) -> MovieArtworkOptions:
        movie = library_manager.get_movie(movie_id)
        if not movie:
            raise LookupError("Movie not found")
        tmdb_id = self._movie_tmdb_id(movie)
        if not tmdb_id:
            raise ValueError("Movie does not have a TMDB ID")

        target_language = self._language(language)
        target_artwork_language = self._artwork_language(artwork_language)
        details = self.tmdb.movie_details(
            tmdb_id,
            language=target_language,
            artwork_language=target_artwork_language,
        )

        images = details.get("images", {})
        return MovieArtworkOptions(
            movie_id=movie_id,
            tmdb_id=tmdb_id,
            posters=self._artwork_images(images.get("posters", []), limit=40),
            backdrops=self._artwork_images(images.get("backdrops", []), limit=40),
            current_poster_path=movie.get("poster_path") or details.get("poster_path"),
            current_backdrop_path=movie.get("backdrop_path") or details.get("backdrop_path"),
        )

    def apply_artwork(self, movie_id: str, selection: ArtworkSelection) -> dict:
        operation_command_id = self._new_command_id("artwork")
        movie = library_manager.get_movie(movie_id)
        if not movie:
            raise LookupError("Movie not found")
        tmdb_id = self._movie_tmdb_id(movie)
        if not tmdb_id:
            raise ValueError("Movie does not have a TMDB ID")
        if not selection.poster_path and not selection.backdrop_path:
            raise ValueError("Choose a poster or backdrop")

        folder = self._movie_folder(movie)
        if not folder:
            raise ValueError("Movie does not have an existing folder path")

        details = self.tmdb.movie_details(
            tmdb_id,
            language=self._language(None),
            artwork_language=self._artwork_language(None),
        )
        images = details.get("images", {})
        poster_paths = self._image_paths(images.get("posters", []))
        backdrop_paths = self._image_paths(images.get("backdrops", []))

        if selection.poster_path and selection.poster_path not in poster_paths:
            raise ValueError("Selected poster is not available for this movie")
        if selection.backdrop_path and selection.backdrop_path not in backdrop_paths:
            raise ValueError("Selected backdrop is not available for this movie")

        filename_prefix = self._filename_prefix(movie, folder)
        poster_url = self.tmdb.image_url(selection.poster_path, "original") if selection.poster_path else None
        backdrop_url = self.tmdb.image_url(selection.backdrop_path, "original") if selection.backdrop_path else None

        if poster_url:
            self._download_artwork_with_event(
                movie_id,
                tmdb_id,
                "poster",
                selection.poster_path,
                poster_url,
                folder / f"{filename_prefix}-poster.jpg",
                overwrite=True,
                command_id=operation_command_id,
                correlation_id=operation_command_id,
                operation="apply_artwork",
            )
        if backdrop_url:
            self._download_artwork_with_event(
                movie_id,
                tmdb_id,
                "backdrop",
                selection.backdrop_path,
                backdrop_url,
                folder / f"{filename_prefix}-fanart.jpg",
                overwrite=True,
                command_id=operation_command_id,
                correlation_id=operation_command_id,
                operation="apply_artwork",
            )

        self._update_nfo_artwork_with_event(
            movie_id,
            tmdb_id,
            folder,
            poster_url=poster_url,
            backdrop_url=backdrop_url,
            filename_prefix=filename_prefix,
            command_id=operation_command_id,
            correlation_id=operation_command_id,
            operation="apply_artwork",
        )

        from app.services.library_sync import library_sync_service

        updated_movie = library_sync_service.scan_folder(
            folder,
            preserve_id=movie_id,
            command_id=operation_command_id,
            correlation_id=operation_command_id,
        )
        if not updated_movie:
            raise ValueError("Artwork saved but folder rescan failed")

        file_fields = (
            "folder_name",
            "video_file",
            "media_path",
            "folder_path",
            "file_size",
            "file_mtime",
            "last_seen_at",
            "missing_since",
            "library_status",
        )
        artwork_fields = (
            "poster_thumb_local",
            "backdrop_thumb_local",
        )
        enriched = {**movie}
        for field in (*file_fields, *artwork_fields):
            if field in updated_movie:
                enriched[field] = updated_movie[field]

        enriched.update(
            {
                "poster_local": (
                    f"/media/{folder.name}/{filename_prefix}-poster.jpg"
                    if selection.poster_path
                    else updated_movie.get("poster_local") or movie.get("poster_local")
                ),
                "backdrop_local": (
                    f"/media/{folder.name}/{filename_prefix}-fanart.jpg"
                    if selection.backdrop_path
                    else updated_movie.get("backdrop_local") or movie.get("backdrop_local")
                ),
                "poster_path": selection.poster_path or updated_movie.get("poster_path") or movie.get("poster_path"),
                "backdrop_path": selection.backdrop_path or updated_movie.get("backdrop_path") or movie.get("backdrop_path"),
                "metadata_updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        stored = library_manager.upsert_movie(
            enriched,
            preserve_id=movie_id,
            command_id=operation_command_id,
            correlation_id=operation_command_id,
        )
        artwork_changes = self._field_changes(movie, stored or enriched, ARTWORK_SELECTION_FIELDS)
        event_store.safe_append(
            "ArtworkSelected",
            "movie",
            movie_id,
            {
                "movie_id": movie_id,
                "tmdb_id": tmdb_id,
                "poster_path": selection.poster_path,
                "backdrop_path": selection.backdrop_path,
                "poster_local": enriched["poster_local"],
                "backdrop_local": enriched["backdrop_local"],
                **artwork_changes,
            },
            command_id=operation_command_id,
            correlation_id=operation_command_id,
            context={"operation": "apply_artwork"},
        )
        library_event_bus.publish_library_changed("artwork_updated", movie_id=movie_id)
        return {
            "status": "success",
            "movie_id": movie_id,
            "movie": stored,
            "poster_path": enriched["poster_path"],
            "backdrop_path": enriched["backdrop_path"],
        }

    def scrape_movie(
        self,
        movie_id: str,
        options: ScrapeOptions,
        *,
        command_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> ScrapeResult:
        operation_command_id = command_id or self._new_command_id("metadata_scrape")
        operation_correlation_id = correlation_id or operation_command_id
        movie = library_manager.get_movie(movie_id)
        if not movie:
            return ScrapeResult(status="failed", movie_id=movie_id, message="Movie not found")

        folder = self._movie_folder(movie)
        if not folder:
            return self._mark_failed(
                movie_id,
                "Movie does not have an existing folder path",
                command_id=operation_command_id,
                correlation_id=operation_correlation_id,
            )

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
                    self._record_match_suggested(
                        movie_id,
                        [candidate],
                        "Manual confirmation required",
                        command_id=operation_command_id,
                        correlation_id=operation_correlation_id,
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
                    return self._mark_failed(
                        movie_id,
                        "No TMDB matches found",
                        command_id=operation_command_id,
                        correlation_id=operation_correlation_id,
                    )

                best = candidates[0]
                if require_confirmation:
                    self._update_scrape_state(
                        movie_id,
                        scrape_status="needs_review",
                        tmdb_confidence=best.score,
                        scrape_error="Manual confirmation required",
                    )
                    self._record_match_suggested(
                        movie_id,
                        candidates,
                        "Manual confirmation required",
                        command_id=operation_command_id,
                        correlation_id=operation_correlation_id,
                    )
                    return ScrapeResult(
                        status="needs_review",
                        movie_id=movie_id,
                        message="Choose a TMDB match to continue",
                        movie=library_manager.get_movie(movie_id),
                        candidates=candidates[:REVIEW_CANDIDATE_LIMIT],
                    )
                if options.mode == "auto" and best.score < 80:
                    self._update_scrape_state(
                        movie_id,
                        scrape_status="needs_review",
                        tmdb_confidence=best.score,
                        scrape_error="Low confidence TMDB match",
                    )
                    self._record_match_suggested(
                        movie_id,
                        candidates,
                        "Low confidence TMDB match",
                        command_id=operation_command_id,
                        correlation_id=operation_correlation_id,
                    )
                    return ScrapeResult(
                        status="needs_review",
                        movie_id=movie_id,
                        message="Choose a TMDB match to continue",
                        movie=library_manager.get_movie(movie_id),
                        candidates=candidates[:REVIEW_CANDIDATE_LIMIT],
                    )
                selected_id = best.tmdb_id

            artwork_language = self._artwork_language(options.artwork_language)
            details = self.tmdb.movie_details(selected_id, language=language, artwork_language=artwork_language)
            poster_path = self._select_image_path(details, "posters", details.get("poster_path"), artwork_language, language)
            backdrop_path = self._select_image_path(details, "backdrops", details.get("backdrop_path"), artwork_language, language)
            poster_url = self.tmdb.image_url(poster_path, "original")
            backdrop_url = self.tmdb.image_url(backdrop_path, "original")
            filename_prefix = self._filename_prefix(movie, folder)

            if options.download_artwork:
                self._download_artwork_with_event(
                    movie_id,
                    selected_id,
                    "poster",
                    poster_path,
                    poster_url,
                    folder / f"{filename_prefix}-poster.jpg",
                    overwrite=options.overwrite,
                    command_id=operation_command_id,
                    correlation_id=operation_correlation_id,
                    operation="scrape_movie",
                )
                self._download_artwork_with_event(
                    movie_id,
                    selected_id,
                    "backdrop",
                    backdrop_path,
                    backdrop_url,
                    folder / f"{filename_prefix}-fanart.jpg",
                    overwrite=options.overwrite,
                    command_id=operation_command_id,
                    correlation_id=operation_correlation_id,
                    operation="scrape_movie",
                )

            if options.write_nfo:
                self._write_nfo_with_event(
                    movie_id,
                    selected_id,
                    folder,
                    details,
                    poster_url=poster_url,
                    backdrop_url=backdrop_url,
                    filename_prefix=filename_prefix,
                    overwrite=options.overwrite,
                    command_id=operation_command_id,
                    correlation_id=operation_correlation_id,
                    operation="scrape_movie",
                )

            from app.services.library_sync import library_sync_service

            updated_movie = library_sync_service.scan_folder(
                folder,
                preserve_id=movie_id,
                command_id=operation_command_id,
                correlation_id=operation_correlation_id,
            )
            if not updated_movie:
                return self._mark_failed(
                    movie_id,
                    "Scrape completed but folder rescan failed",
                    command_id=operation_command_id,
                    correlation_id=operation_correlation_id,
                )

            enriched = {
                **updated_movie,
                **self._movie_updates_from_details(
                    details,
                    selected_id,
                    poster_path=poster_path,
                    backdrop_path=backdrop_path,
                    language=language,
                ),
                "metadata_source": "tmdb",
                "nfo_source": "tmdb" if options.write_nfo else updated_movie.get("nfo_source"),
                "scrape_status": "matched",
                "scrape_error": None,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "tmdb_confidence": candidates[0].score if candidates else 100,
            }
            stored = library_manager.upsert_movie(
                enriched,
                preserve_id=movie_id,
                command_id=operation_command_id,
                correlation_id=operation_correlation_id,
            )
            metadata_changes = self._field_changes(movie, stored or enriched, METADATA_MATCH_FIELDS)
            event_store.safe_append(
                "MetadataMatched",
                "movie",
                movie_id,
                {
                    "movie_id": movie_id,
                    "tmdb_id": selected_id,
                    "imdb_id": details.get("imdb_id") or details.get("external_ids", {}).get("imdb_id"),
                    "title": details.get("title") or details.get("original_title"),
                    "year": self._release_year(details.get("release_date")),
                    "confidence": candidates[0].score if candidates else 100,
                    "mode": options.mode,
                    "language": language,
                    "artwork_language": artwork_language,
                    "write_nfo": options.write_nfo,
                    "download_artwork": options.download_artwork,
                    "poster_path": poster_path,
                    "backdrop_path": backdrop_path,
                    **metadata_changes,
                },
                command_id=operation_command_id,
                correlation_id=operation_correlation_id,
                context={"operation": "scrape_movie"},
            )
            library_event_bus.publish_library_changed("metadata_scraped", movie_id=movie_id)
            return ScrapeResult(
                status="success",
                movie_id=movie_id,
                message="Metadata scraped",
                movie=stored,
                candidates=candidates[:REVIEW_CANDIDATE_LIMIT] if candidates else [],
            )
        except Exception as exc:
            return self._mark_failed(
                movie_id,
                str(exc),
                command_id=operation_command_id,
                correlation_id=operation_correlation_id,
            )

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
                        artwork_language=options.artwork_language,
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

    def _release_year(self, release_date: Optional[str]) -> int:
        if not release_date:
            return 0
        try:
            return int(str(release_date).split("-", 1)[0])
        except ValueError:
            return 0

    def _movie_updates_from_details(
        self,
        details: dict,
        tmdb_id: int,
        *,
        poster_path: Optional[str],
        backdrop_path: Optional[str],
        language: str,
    ) -> dict:
        title = details.get("title") or details.get("original_title")
        original_title = details.get("original_title") or title
        release_year = self._release_year(details.get("release_date"))
        updates = {
            "title": original_title or title,
            "tmdb_id": str(tmdb_id),
            "imdb_id": details.get("imdb_id") or details.get("external_ids", {}).get("imdb_id"),
            "overview": details.get("overview"),
            "plot": details.get("overview"),
            "runtime": details.get("runtime"),
            "countries": [
                country.get("name")
                for country in details.get("production_countries", [])
                if country.get("name")
            ],
            "genres": [
                genre.get("name")
                for genre in details.get("genres", [])
                if genre.get("name")
            ],
            "director": self._director_from_details(details),
            "actors": self._actors_from_details(details),
            "poster_path": poster_path,
            "backdrop_path": backdrop_path,
        }
        if release_year:
            updates["year"] = release_year
        if language.startswith("zh") and title:
            updates["title_cn"] = title
        return {key: value for key, value in updates.items() if value not in (None, "", [])}

    def _director_from_details(self, details: dict) -> Optional[str]:
        for person in details.get("credits", {}).get("crew", []):
            if person.get("job") == "Director" and person.get("name"):
                return person["name"]
        return None

    def _actors_from_details(self, details: dict) -> list[dict]:
        return [
            {"name": actor.get("name"), "role": actor.get("character")}
            for actor in details.get("credits", {}).get("cast", [])[:10]
            if actor.get("name")
        ]

    def _download_artwork_with_event(
        self,
        movie_id: str,
        tmdb_id: int,
        asset_type: str,
        image_path: Optional[str],
        url: Optional[str],
        destination: Path,
        *,
        overwrite: bool,
        command_id: str,
        correlation_id: str,
        operation: str,
    ) -> Optional[Path]:
        before = self._file_snapshot(destination)
        downloaded = self.artwork.download(url, destination, overwrite=overwrite)
        after = self._file_snapshot(destination)
        if downloaded and self._snapshot_changed(before, after):
            event_store.safe_append(
                "ArtworkDownloaded",
                "movie",
                movie_id,
                {
                    "movie_id": movie_id,
                    "tmdb_id": tmdb_id,
                    "asset_type": asset_type,
                    "image_path": image_path,
                    "url": url,
                    "destination": str(destination),
                    "overwrite": overwrite,
                    "before": before,
                    "after": after,
                },
                command_id=command_id,
                correlation_id=correlation_id,
                context={"operation": operation},
            )
        return downloaded

    def _write_nfo_with_event(
        self,
        movie_id: str,
        tmdb_id: int,
        folder: Path,
        details: dict,
        *,
        poster_url: Optional[str],
        backdrop_url: Optional[str],
        filename_prefix: str,
        overwrite: bool,
        command_id: str,
        correlation_id: str,
        operation: str,
    ) -> Path:
        nfo_path = folder / f"{filename_prefix}.nfo"
        before = self._file_snapshot(nfo_path)
        written = self.nfo_writer.write_movie_nfo(
            folder,
            details,
            poster_url=poster_url,
            backdrop_url=backdrop_url,
            filename_prefix=filename_prefix,
            overwrite=overwrite,
        )
        after = self._file_snapshot(written)
        self._record_nfo_written(
            movie_id,
            tmdb_id,
            "write_metadata",
            written,
            before,
            after,
            overwrite=overwrite,
            poster_url=poster_url,
            backdrop_url=backdrop_url,
            command_id=command_id,
            correlation_id=correlation_id,
            operation=operation,
        )
        return written

    def _update_nfo_artwork_with_event(
        self,
        movie_id: str,
        tmdb_id: int,
        folder: Path,
        *,
        poster_url: Optional[str],
        backdrop_url: Optional[str],
        filename_prefix: str,
        command_id: str,
        correlation_id: str,
        operation: str,
    ) -> Optional[Path]:
        nfo_path = self.nfo_writer.movie_nfo_path(folder, filename_prefix)
        before = self._file_snapshot(nfo_path) if nfo_path else None
        written = self.nfo_writer.update_movie_artwork(
            folder,
            poster_url=poster_url,
            backdrop_url=backdrop_url,
            filename_prefix=filename_prefix,
        )
        if not written:
            return None
        after = self._file_snapshot(written)
        self._record_nfo_written(
            movie_id,
            tmdb_id,
            "update_artwork",
            written,
            before or {"path": str(written), "exists": False},
            after,
            overwrite=True,
            poster_url=poster_url,
            backdrop_url=backdrop_url,
            command_id=command_id,
            correlation_id=correlation_id,
            operation=operation,
        )
        return written

    def _record_nfo_written(
        self,
        movie_id: str,
        tmdb_id: int,
        action: str,
        path: Path,
        before: dict,
        after: dict,
        *,
        overwrite: bool,
        poster_url: Optional[str],
        backdrop_url: Optional[str],
        command_id: str,
        correlation_id: str,
        operation: str,
    ):
        if not self._snapshot_changed(before, after):
            return
        event_store.safe_append(
            "NfoWritten",
            "movie",
            movie_id,
            {
                "movie_id": movie_id,
                "tmdb_id": tmdb_id,
                "action": action,
                "path": str(path),
                "overwrite": overwrite,
                "poster_url": poster_url,
                "backdrop_url": backdrop_url,
                "before": before,
                "after": after,
            },
            command_id=command_id,
            correlation_id=correlation_id,
            context={"operation": operation},
        )

    def _file_snapshot(self, path: Path) -> dict:
        try:
            stat = path.stat()
        except OSError:
            return {"path": str(path), "exists": False}
        return {
            "path": str(path),
            "filename": path.name,
            "exists": True,
            "size": stat.st_size,
            "mtime": stat.st_mtime,
        }

    def _snapshot_changed(self, before: dict, after: dict) -> bool:
        return any(
            before.get(field) != after.get(field)
            for field in ("exists", "size", "mtime", "path")
        )

    def _movie_folder(self, movie: dict) -> Optional[Path]:
        folder_path = movie.get("folder_path")
        if folder_path:
            folder = Path(folder_path).resolve()
            if folder.exists() and folder.is_dir():
                return folder

        folder_name = movie.get("folder_name")
        media_dir = get_media_dir()
        if folder_name and media_dir:
            folder = (Path(media_dir) / folder_name).resolve()
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

    def _movie_tmdb_id(self, movie: dict) -> Optional[int]:
        try:
            return int(movie["tmdb_id"]) if movie.get("tmdb_id") else None
        except (TypeError, ValueError):
            return None

    def _artwork_images(self, images: object, limit: int) -> list[ArtworkImage]:
        if not isinstance(images, list):
            return []

        candidates = [
            image
            for image in images
            if isinstance(image, dict) and image.get("file_path")
        ]
        candidates.sort(
            key=lambda image: (
                float(image.get("vote_average") or 0),
                int(image.get("vote_count") or 0),
                int(image.get("width") or 0) * int(image.get("height") or 0),
            ),
            reverse=True,
        )

        return [
            ArtworkImage(
                file_path=image["file_path"],
                url=self.tmdb.image_url(image["file_path"], "original") or "",
                thumbnail_url=self.tmdb.image_url(image["file_path"], "w500") or "",
                width=int(image.get("width") or 0),
                height=int(image.get("height") or 0),
                aspect_ratio=float(image.get("aspect_ratio") or 0),
                language=image.get("iso_639_1"),
                vote_average=float(image.get("vote_average") or 0),
                vote_count=int(image.get("vote_count") or 0),
            )
            for image in candidates[:limit]
        ]

    def _image_paths(self, images: object) -> set[str]:
        if not isinstance(images, list):
            return set()
        return {
            image["file_path"]
            for image in images
            if isinstance(image, dict) and image.get("file_path")
        }

    def _mark_failed(
        self,
        movie_id: str,
        message: str,
        *,
        command_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> ScrapeResult:
        self._update_scrape_state(movie_id, scrape_status="failed", scrape_error=message)
        event_store.safe_append(
            "MetadataScrapeFailed",
            "movie",
            movie_id,
            {"movie_id": movie_id, "message": message},
            command_id=command_id,
            correlation_id=correlation_id,
            context={"operation": "scrape_movie"},
        )
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

    def _record_match_suggested(
        self,
        movie_id: str,
        candidates: list[MetadataSearchResult],
        reason: str,
        *,
        command_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ):
        event_store.safe_append(
            "MetadataMatchSuggested",
            "movie",
            movie_id,
            {
                "movie_id": movie_id,
                "reason": reason,
                "candidates": [candidate.model_dump() for candidate in candidates[:REVIEW_CANDIDATE_LIMIT]],
            },
            command_id=command_id,
            correlation_id=correlation_id,
            context={"operation": "scrape_movie"},
        )

    def _new_command_id(self, operation: str) -> str:
        return f"{operation}_{uuid4().hex}"

    def _field_changes(self, previous: dict, current: dict, fields: tuple[str, ...]) -> dict:
        changed_fields = []
        previous_values = {}
        current_values = {}
        for field in fields:
            previous_value = previous.get(field)
            current_value = current.get(field)
            if previous_value != current_value:
                changed_fields.append(field)
                previous_values[field] = previous_value
                current_values[field] = current_value
        return {
            "changed_fields": changed_fields,
            "previous": previous_values,
            "current": current_values,
        }

    def _language(self, value: Optional[str]) -> str:
        if value:
            return value
        return "zh-CN" if get_language() == "zh" else "en-US"

    def _artwork_language(self, value: Optional[str]) -> str:
        if value in {"metadata", "zh", "en", "none"}:
            return value
        return get_artwork_language()

    def _select_image_path(
        self,
        details: dict,
        image_type: str,
        default_path: Optional[str],
        artwork_language: str,
        metadata_language: str,
    ) -> Optional[str]:
        if artwork_language == "metadata":
            return default_path

        images = details.get("images", {}).get(image_type, [])
        if not isinstance(images, list):
            return default_path

        preferred_languages = [artwork_language]
        if artwork_language != "none":
            preferred_languages.append("none")

        for language in preferred_languages:
            candidate = self._best_image(images, language)
            if candidate:
                return candidate

        metadata_lang = (metadata_language or "").split("-", 1)[0]
        return self._best_image(images, metadata_lang) or default_path

    def _best_image(self, images: list[dict], language: str) -> Optional[str]:
        iso_value = None if language == "none" else language
        candidates = [
            image
            for image in images
            if image.get("file_path") and image.get("iso_639_1") == iso_value
        ]
        if not candidates:
            return None

        best = max(
            candidates,
            key=lambda image: (
                float(image.get("vote_average") or 0),
                int(image.get("vote_count") or 0),
                int(image.get("width") or 0) * int(image.get("height") or 0),
            ),
        )
        return best.get("file_path")

    def _set_status(self, **updates):
        with self._lock:
            self._status.update(updates)


metadata_scraper = MetadataScraper()
