import hashlib
import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Optional
from pathlib import Path
from uuid import uuid4
from sqlalchemy import or_
from sqlmodel import Session, select, delete
from app.database import engine, create_db_and_tables, get_session
from app.models import (
    CanonicalBackfillRun,
    Concept,
    ConceptAlias,
    Credit,
    CreditProvenance,
    EventRecord,
    ExternalIdentity,
    Film,
    FilmCountry,
    FilmCountryProvenance,
    FilmProfileState,
    FilmTitle,
    GraphEntity,
    IdentityReview,
    Job,
    LegacyMovieAlias,
    LibraryItem,
    LibraryItemLocatorHistory,
    LocalProfile,
    MediaAsset,
    Movie,
    MovieUserState,
    Person,
    StructuredMetadataReview,
    Viewing,
)
from app.services.event_store import event_store
from app.services.canonical_runtime import (
    SOURCE_INSTANCE_ID,
    AmbiguousRelink,
    canonical_runtime_writer,
)
from app.services.canonical_shadow import CanonicalShadowReader
from app.services.compatibility_reads import (
    library_read_source,
    log_orphan_fallback,
    log_shadow_report,
)
from app.services.file_identity import FileIdentityObservation, full_content_hash

# Configuration via environment variables
SEED_DATA_FILE = Path(__file__).parent.parent / "data" / "seed_movies.json"

SCAN_EVENT_FIELDS = (
    "id",
    "title",
    "title_cn",
    "year",
    "media_path",
    "folder_path",
    "folder_name",
    "video_file",
    "file_size",
    "file_mtime",
    "last_seen_at",
    "library_status",
    "metadata_source",
    "scrape_status",
    "tmdb_id",
    "imdb_id",
    "audio_tracks",
    "video_width",
    "video_height",
    "video_codec",
    "video_bitrate",
    "video_duration",
    "video_fps",
    "video_dynamic_range",
    "video_bit_depth",
    "nfo_source",
    "nfo_file",
    "nfo_path",
    "nfo_size",
    "nfo_mtime",
    "nfo_fingerprint",
)

FILE_OBSERVED_FIELDS = (
    "media_path",
    "folder_path",
    "folder_name",
    "video_file",
    "file_size",
    "file_mtime",
    "last_seen_at",
    "audio_tracks",
    "video_width",
    "video_height",
    "video_codec",
    "video_bitrate",
    "video_duration",
    "video_fps",
    "video_dynamic_range",
    "video_bit_depth",
)

NFO_SIGNATURE_FIELDS = (
    "nfo_file",
    "nfo_path",
    "nfo_size",
    "nfo_mtime",
    "nfo_fingerprint",
)

NFO_METADATA_FIELDS = (
    "id",
    "title",
    "title_cn",
    "year",
    "tmdb_id",
    "imdb_id",
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
)


class LibraryManager:
    def __init__(self):
        # We handle DB creation in main.py, but good to ensure tables exist
        pass

    def add_movies(self, movies_data: list[dict]) -> int:
        """Add multiple movies to the library (upsert)."""
        added = 0
        scan_events: list[dict] = []
        prepared = [
            (movie_dict, canonical_runtime_writer.observe_movie(movie_dict))
            for movie_dict in movies_data
        ]
        with Session(engine) as session:
            for movie_dict, observation in prepared:
                if not movie_dict.get("id"):
                    continue
                try:
                    resolution = canonical_runtime_writer.sync_movie(
                        session,
                        movie_dict,
                        file_observation=observation,
                    )
                except AmbiguousRelink as ambiguity:
                    self._queue_relink_job(session, movie_dict, ambiguity)
                    continue
                movie_id = resolution.compatibility_id
                movie_dict = {
                    **movie_dict,
                    **canonical_runtime_writer.compatibility_projection_fields(session, resolution),
                    "id": movie_id,
                }
                
                existing_movie = session.get(Movie, movie_id)
                if not existing_movie and movie_dict.get("media_path"):
                    existing_movie = self._get_by_media_path(session, movie_dict["media_path"])
                if existing_movie:
                    previous_movie = existing_movie.model_dump()
                    if existing_movie.library_status == "ignored" and movie_dict.get("library_status") == "available":
                        movie_dict = {**movie_dict, "library_status": "ignored", "missing_since": None}
                    if not existing_movie.added_at:
                        existing_movie.added_at = self._fallback_added_at(movie_dict)
                    # Update fields
                    for key, value in movie_dict.items():
                        if key == "added_at" and existing_movie.added_at:
                            continue
                        setattr(existing_movie, key, value)
                    session.add(existing_movie)
                    scan_events.extend(self._scan_events_for_existing(previous_movie, movie_dict, existing_movie.id))
                else:
                    # Create new
                    new_movie = Movie(**self._with_added_at(movie_dict))
                    session.add(new_movie)
                    added += 1
                    scan_events.append({
                        "type": "MovieDiscovered",
                        "aggregate_id": movie_id,
                        "payload": self._movie_event_payload(movie_dict),
                        "project": False,
                    })
                session.flush()
                canonical_runtime_writer.sync_user_state(session, movie_id, fields_set=set())
            session.commit()
        self._append_scan_events(scan_events)
        return added

    def upsert_movie(
        self,
        movie_data: dict,
        preserve_id: Optional[str] = None,
        *,
        command_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Insert or update one movie and return the stored record."""
        result = self.upsert_movie_with_events(
            movie_data,
            preserve_id=preserve_id,
            command_id=command_id,
            correlation_id=correlation_id,
        )
        return result["movie"] if result else None

    def upsert_movie_with_events(
        self,
        movie_data: dict,
        preserve_id: Optional[str] = None,
        *,
        command_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        _force_library_item_id: Optional[str] = None,
        _review_reason: Optional[str] = None,
        _review_context: Optional[dict] = None,
        _file_observation: Optional[FileIdentityObservation] = None,
        _candidate_hashes: Optional[dict[str, str]] = None,
        _emit_scan_events: bool = True,
    ) -> Optional[dict]:
        """Insert or update one movie and return the stored record plus emitted scan event types."""
        movie_id = preserve_id or movie_data.get("id")
        if not movie_id:
            return None

        movie_data = {**movie_data, "id": movie_id}
        observation = _file_observation or canonical_runtime_writer.observe_movie(movie_data)
        scan_events: list[dict] = []
        with Session(engine) as session:
            for asset_id, content_hash in (_candidate_hashes or {}).items():
                asset = session.get(MediaAsset, asset_id)
                if asset is not None:
                    asset.content_hash = content_hash
                    asset.updated_at = datetime.now(timezone.utc).isoformat()
                    session.add(asset)
            try:
                resolution = canonical_runtime_writer.sync_movie(
                    session,
                    movie_data,
                    preserve_id=preserve_id,
                    file_observation=observation,
                    force_library_item_id=_force_library_item_id,
                    review_reason=_review_reason,
                    review_context=_review_context,
                )
            except AmbiguousRelink as ambiguity:
                job_id = self._queue_relink_job(session, movie_data, ambiguity)
                session.commit()
                return {"movie": None, "event_types": [], "pending_relink_job_id": job_id}
            movie_id = resolution.compatibility_id
            movie_data = {
                **movie_data,
                **canonical_runtime_writer.compatibility_projection_fields(session, resolution),
                "id": movie_id,
            }
            existing_movie = session.get(Movie, movie_id)
            if not existing_movie and movie_data.get("media_path"):
                existing_movie = self._get_by_media_path(session, movie_data["media_path"])

            if existing_movie:
                previous_movie = existing_movie.model_dump()
                if existing_movie.library_status == "ignored" and movie_data.get("library_status") == "available":
                    movie_data = {**movie_data, "library_status": "ignored", "missing_since": None}
                if not existing_movie.added_at:
                    existing_movie.added_at = self._fallback_added_at(movie_data)
                for key, value in movie_data.items():
                    if key == "added_at" and existing_movie.added_at:
                        continue
                    setattr(existing_movie, key, value)
                session.add(existing_movie)
                session.flush()
                canonical_runtime_writer.sync_user_state(session, movie_id, fields_set=set())
                session.commit()
                session.refresh(existing_movie)
                stored = existing_movie.model_dump()
                scan_events.extend(self._scan_events_for_existing(previous_movie, movie_data, existing_movie.id))
                if _emit_scan_events:
                    self._append_scan_events(
                        scan_events,
                        command_id=command_id,
                        correlation_id=correlation_id,
                    )
                return {
                    "movie": stored,
                    "event_types": self._event_types(scan_events),
                }

            new_movie = Movie(**self._with_added_at(movie_data))
            session.add(new_movie)
            session.flush()
            canonical_runtime_writer.sync_user_state(session, movie_id, fields_set=set())
            session.commit()
            session.refresh(new_movie)
            scan_events.append({
                "type": "MovieDiscovered",
                "aggregate_id": movie_id,
                "payload": self._movie_event_payload(movie_data),
                "project": False,
            })
            if _emit_scan_events:
                self._append_scan_events(
                    scan_events,
                    command_id=command_id,
                    correlation_id=correlation_id,
                )
            return {
                "movie": new_movie.model_dump(),
                "event_types": self._event_types(scan_events),
            }

    def resolve_relink(self, payload: dict, *, job_id: Optional[str] = None) -> dict:
        """Resolve all pending items for one deduped fingerprint job."""
        items = list(payload.get("items") or [payload])
        processed_ids: set[str] = set()
        results: list[dict] = []
        while True:
            for item in items:
                source_item_id = str(item.get("source_item_id") or self._hash_identifier(
                    canonical_runtime_writer.source_item_key(item.get("movie") or {})
                ))
                if source_item_id in processed_ids:
                    continue
                processed_ids.add(source_item_id)
                results.append(self._resolve_relink_item({**payload, **item}))
            if not job_id:
                break
            with Session(engine) as session:
                current = session.get(Job, job_id)
                refreshed = list((current.payload or {}).get("items") or []) if current else []
            if not any(
                str(item.get("source_item_id")) not in processed_ids
                for item in refreshed
            ):
                break
            items = refreshed

        matched = sum(int(result.get("matched") or 0) for result in results)
        needs_review = sum(result.get("status") == "needs_review" for result in results)
        return {
            "status": (
                "relinked" if matched and not needs_review
                else "needs_review" if needs_review and not matched
                else "partial"
            ),
            "processed": len(results),
            "matched": matched,
            "needs_review": needs_review,
            "candidate_count": sum(int(result.get("candidate_count") or 0) for result in results),
            "fingerprint_id": payload.get("fingerprint_id"),
        }

    def _resolve_relink_item(self, payload: dict) -> dict:
        """Resolve one ambiguous quick fingerprint without exposing path data."""
        movie_data = dict(payload.get("movie") or {})
        candidate_ids = {str(value) for value in payload.get("candidate_item_ids") or []}
        content_fingerprint = payload.get("content_fingerprint")
        fingerprint_id = str(payload.get("fingerprint_id") or "unknown")
        observation = canonical_runtime_writer.observe_movie(movie_data)
        candidate_hashes: dict[str, str] = {}
        matches: set[str] = set()
        complete_hash: str | None = None

        if observation is not None:
            locator = movie_data.get("media_path") or movie_data.get("video_file")
            try:
                complete_hash = observation.content_hash or full_content_hash(locator)
            except (FileNotFoundError, OSError):
                complete_hash = None

        if complete_hash is not None:
            with Session(engine) as session:
                if content_fingerprint:
                    candidate_ids.update(
                        str(value)
                        for value in session.exec(
                            select(MediaAsset.library_item_id)
                            .where(MediaAsset.asset_kind == "video")
                            .where(MediaAsset.library_item_id.is_not(None))
                            .where(MediaAsset.content_fingerprint == content_fingerprint)
                        ).all()
                        if value
                    )
                assets = session.exec(
                    select(MediaAsset)
                    .where(MediaAsset.asset_kind == "video")
                    .where(MediaAsset.library_item_id.in_(sorted(candidate_ids)))
                ).all()
            for asset in assets:
                if not asset.library_item_id:
                    continue
                candidate_hash = asset.content_hash
                if candidate_hash is None:
                    try:
                        candidate_hash = full_content_hash(asset.locator)
                    except (FileNotFoundError, OSError):
                        continue
                    candidate_hashes[asset.id] = candidate_hash
                if candidate_hash == complete_hash:
                    matches.add(asset.library_item_id)

        force_library_item_id = next(iter(matches)) if len(matches) == 1 else None
        review_reason: str | None = None
        if observation is None or complete_hash is None:
            review_reason = "relink_file_disappeared"
            movie_data["library_status"] = "missing"
        elif len(matches) == 0:
            review_reason = "relink_full_hash_no_match"
        elif len(matches) > 1:
            review_reason = "relink_full_hash_duplicate"
        elif force_library_item_id:
            with Session(engine) as session:
                item = session.get(LibraryItem, force_library_item_id)
                if item is None or canonical_runtime_writer.has_identity_conflict(
                    session, item.film_id, movie_data
                ):
                    force_library_item_id = None
                    review_reason = "relink_identity_conflict"
                elif canonical_runtime_writer.has_live_locator_conflict(
                    session, item.id, movie_data
                ):
                    force_library_item_id = None
                    review_reason = "relink_live_copy_conflict"

        resolved_observation = (
            FileIdentityObservation(
                platform_file_id=observation.platform_file_id,
                content_fingerprint=observation.content_fingerprint,
                content_hash=complete_hash,
                bytes_read=observation.bytes_read,
            )
            if observation is not None and complete_hash is not None
            else observation
        )
        result = self.upsert_movie_with_events(
            movie_data,
            _force_library_item_id=force_library_item_id,
            _review_reason=review_reason,
            _review_context={
                "candidate_count": len(candidate_ids),
                "fingerprint_id": fingerprint_id,
                "source_instance_id": SOURCE_INSTANCE_ID,
            },
            _file_observation=resolved_observation,
            _candidate_hashes=candidate_hashes,
            _emit_scan_events=False,
        )
        if not result or not result.get("movie"):
            return {
                "status": "needs_review",
                "matched": 0,
                "candidate_count": len(candidate_ids),
                "fingerprint_id": fingerprint_id,
                "hash_id": self._hash_identifier(complete_hash),
            }
        return {
            "status": "relinked" if force_library_item_id else "needs_review",
            "matched": 1 if force_library_item_id else 0,
            "candidate_count": len(candidate_ids),
            "fingerprint_id": fingerprint_id,
            "hash_id": self._hash_identifier(complete_hash),
        }

    def get_movies(self) -> List[dict]:
        legacy = self._legacy_movies()
        source = library_read_source()
        if source == "legacy":
            return legacy
        reader = CanonicalShadowReader(engine)
        if source == "shadow":
            log_shadow_report(reader.compare_library())
            return legacy
        canonical = reader.get_movies()
        canonical_by_id = {movie["id"]: movie for movie in canonical}
        ordered: list[dict] = []
        orphans: list[dict] = []
        for legacy_movie in legacy:
            canonical_movie = canonical_by_id.pop(legacy_movie["id"], None)
            if canonical_movie is not None:
                ordered.append(canonical_movie)
            else:
                ordered.append(legacy_movie)
                orphans.append(legacy_movie)
        if orphans:
            log_orphan_fallback("library", count=len(orphans))
        remaining = sorted(
            canonical_by_id.values(),
            key=lambda movie: (
                str(movie.get("title") or "").casefold(),
                movie.get("year") or 0,
                str(movie.get("id") or ""),
            ),
        )
        return [*ordered, *remaining]

    def _legacy_movies(self) -> List[dict]:
        with Session(engine) as session:
            statement = select(Movie).order_by(Movie.title, Movie.year, Movie.id)
            results = session.exec(statement).all()
            # Convert to dicts for frontend compatibility
            return [movie.model_dump() for movie in results]

    def get_movie(self, movie_id: str) -> Optional[dict]:
        legacy = self._legacy_movie(movie_id)
        source = library_read_source()
        if source == "legacy":
            return legacy
        reader = CanonicalShadowReader(engine)
        canonical = reader.get_movie(movie_id)
        if source == "shadow":
            log_shadow_report(reader.compare_movie(movie_id))
            return legacy
        if canonical is None and legacy is not None:
            log_orphan_fallback("movie", record_id=movie_id)
        return canonical or legacy

    def _legacy_movie(self, movie_id: str) -> Optional[dict]:
        with Session(engine) as session:
            movie = session.get(Movie, movie_id)
            return movie.model_dump() if movie else None

    def mark_missing_not_seen_since(self, seen_at: str) -> int:
        """Mark available movies missing when they were not observed in a reconcile pass."""
        from datetime import datetime, timezone

        missing_at = datetime.now(timezone.utc).isoformat()
        updated = 0
        with Session(engine) as session:
            statement = select(Movie).where(Movie.library_status.not_in(["missing", "ignored", "reverted"]))
            movies = [
                movie.model_dump()
                for movie in session.exec(statement).all()
                if not movie.last_seen_at or movie.last_seen_at < seen_at
            ]
        for movie in movies:
            _, projected = event_store.append_and_project(
                "MovieMarkedMissing",
                "movie",
                movie["id"],
                {"movie_id": movie["id"], "missing_since": missing_at, "seen_at": seen_at},
            )
            if projected:
                updated += 1
        return updated

    def mark_path_missing(self, path: str) -> int:
        from datetime import datetime, timezone

        missing_at = datetime.now(timezone.utc).isoformat()
        updated = 0
        with Session(engine) as session:
            statement = select(Movie).where(or_(Movie.media_path == path, Movie.folder_path == path))
            movies = [
                movie.model_dump()
                for movie in session.exec(statement).all()
                if movie.library_status not in {"ignored", "reverted"}
            ]
        for movie in movies:
            _, projected = event_store.append_and_project(
                "MovieMarkedMissing",
                "movie",
                movie["id"],
                {"movie_id": movie["id"], "missing_since": missing_at, "path": path},
            )
            if projected:
                updated += 1
        return updated

    def ignore_movie(self, movie_id: str) -> Optional[dict]:
        """Mark one movie as ignored so it is hidden from the normal library."""
        with Session(engine) as session:
            movie = session.get(Movie, movie_id)
            if not movie:
                return None
            payload = {"movie_id": movie_id, "title": movie.title, "year": movie.year}

        _, projected = event_store.append_and_project("MovieIgnored", "movie", movie_id, payload)
        return projected

    def cleanup_missing(self) -> int:
        """Delete records already marked as missing."""
        deleted_ids: list[str] = []
        with Session(engine) as session:
            deleted_ids = [movie.id for movie in session.exec(select(Movie).where(Movie.library_status == "missing")).all()]
            if deleted_ids:
                self._retire_canonical_items(session, deleted_ids)
                session.exec(
                    delete(MovieUserState).where(MovieUserState.movie_id.in_(deleted_ids))
                )
            statement = delete(Movie).where(Movie.library_status == "missing")
            result = session.exec(statement)
            session.commit()
            deleted = result.rowcount or 0
        if deleted:
            event_store.safe_append(
                "MissingMoviesCleaned",
                "library",
                None,
                {"deleted": deleted, "movie_ids": deleted_ids[:200], "truncated": len(deleted_ids) > 200},
            )
        return deleted

    def clear_library(self):
        """Clear all movies from the library."""
        count = 0
        with Session(engine) as session:
            count = len(session.exec(select(Movie)).all())
            movie_ids = [movie.id for movie in session.exec(select(Movie)).all()]
            self._retire_canonical_items(session, movie_ids)
            session.exec(delete(MovieUserState))
            statement = delete(Movie)
            session.exec(statement)
            session.commit()
        event_store.safe_append("LibraryCleared", "library", None, {"deleted": count})

    def clear_all_data(self) -> dict:
        """Clear application data stored in the database without touching settings or media files."""
        with Session(engine) as session:
            counts = {
                "user_states": len(session.exec(select(MovieUserState.movie_id)).all()),
                "movies": len(session.exec(select(Movie.id)).all()),
                "jobs": len(session.exec(select(Job.id)).all()),
                "events": len(session.exec(select(EventRecord.id)).all()),
            }

            session.exec(delete(MovieUserState))
            session.exec(delete(Movie))
            session.exec(delete(Job))
            session.exec(delete(EventRecord))
            session.exec(delete(Viewing))
            session.exec(delete(FilmProfileState))
            session.exec(delete(StructuredMetadataReview))
            session.exec(delete(CreditProvenance))
            session.exec(delete(Credit))
            session.exec(delete(FilmCountryProvenance))
            session.exec(delete(FilmCountry))
            session.exec(delete(FilmTitle))
            session.exec(delete(ConceptAlias))
            session.exec(delete(IdentityReview))
            session.exec(delete(MediaAsset))
            session.exec(delete(LibraryItemLocatorHistory))
            session.exec(delete(LegacyMovieAlias))
            session.exec(delete(LibraryItem))
            session.exec(delete(ExternalIdentity))
            session.exec(delete(Person))
            session.exec(delete(Concept))
            session.exec(delete(Film))
            session.exec(delete(GraphEntity))
            session.exec(delete(LocalProfile))
            session.exec(delete(CanonicalBackfillRun))
            session.commit()

        return counts

    def seed_test_data(self):
        """Populates the library with mock data from external JSON file."""
        try:
            with open(SEED_DATA_FILE, 'r') as f:
                movies_list = json.load(f)
        except FileNotFoundError:
            print(f"Warning: Seed file not found at {SEED_DATA_FILE}")
            movies_list = []
        
        # Add to DB
        self.add_movies(movies_list)
        event_store.safe_append("LibrarySeeded", "library", None, {"count": len(movies_list)})
        return movies_list

    def _get_by_media_path(self, session: Session, media_path: str) -> Optional[Movie]:
        statement = select(Movie).where(Movie.media_path == media_path)
        return session.exec(statement).first()

    def _retire_canonical_items(self, session: Session, movie_ids: list[str]) -> None:
        if not movie_ids:
            return
        now = datetime.now(timezone.utc).isoformat()
        aliases = session.exec(
            select(LegacyMovieAlias).where(LegacyMovieAlias.legacy_movie_id.in_(movie_ids))
        ).all()
        item_ids = [alias.library_item_id for alias in aliases]
        if not item_ids:
            return
        for item in session.exec(select(LibraryItem).where(LibraryItem.id.in_(item_ids))).all():
            item.availability_status = "retired"
            item.retired_at = now
            item.updated_at = now
            session.add(item)
        for asset in session.exec(
            select(MediaAsset).where(MediaAsset.library_item_id.in_(item_ids))
        ).all():
            asset.availability_status = "retired"
            asset.updated_at = now
            session.add(asset)
        for history in session.exec(
            select(LibraryItemLocatorHistory)
            .where(LibraryItemLocatorHistory.library_item_id.in_(item_ids))
            .where(LibraryItemLocatorHistory.observed_to.is_(None))
        ).all():
            history.observed_to = now
            session.add(history)

    def _queue_relink_job(
        self,
        session: Session,
        movie_data: dict,
        ambiguity: AmbiguousRelink,
    ) -> str:
        fingerprint_digest = hashlib.sha256(
            ambiguity.observation.content_fingerprint.encode("utf-8")
        ).hexdigest()
        fingerprint_id = fingerprint_digest[:16]
        dedupe_key = f"library.resolve_relink:{SOURCE_INSTANCE_ID}:{fingerprint_digest}"
        source_item_id = self._hash_identifier(
            canonical_runtime_writer.source_item_key(movie_data)
        )
        pending_item = {
            "source_item_id": source_item_id,
            "movie": json.loads(json.dumps(movie_data, default=str)),
            "candidate_item_ids": ambiguity.library_item_ids,
        }
        existing = session.exec(
            select(Job)
            .where(Job.dedupe_key == dedupe_key)
            .where(Job.status.in_(("queued", "running", "cancelling")))
            .order_by(Job.created_at)
        ).first()
        if existing is not None:
            payload = dict(existing.payload or {})
            items = list(payload.get("items") or [])
            if not any(item.get("source_item_id") == source_item_id for item in items):
                items.append(pending_item)
                existing.payload = {**payload, "items": items}
                existing.updated_at = datetime.now(timezone.utc).isoformat()
                session.add(existing)
                session.flush()
            return existing.id
        now = datetime.now(timezone.utc).isoformat()
        job = Job(
            id=f"job_{uuid4().hex}",
            type="library.resolve_relink",
            payload={
                "source_instance_id": SOURCE_INSTANCE_ID,
                "fingerprint_id": fingerprint_id,
                "content_fingerprint": ambiguity.observation.content_fingerprint,
                "items": [pending_item],
            },
            dedupe_key=dedupe_key,
            max_attempts=1,
            priority=10,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.flush()
        return job.id

    @staticmethod
    def _hash_identifier(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    def _with_added_at(self, movie_data: dict) -> dict:
        if movie_data.get("added_at"):
            return movie_data
        return {**movie_data, "added_at": self._fallback_added_at(movie_data)}

    def _fallback_added_at(self, movie_data: dict) -> str:
        return (
            movie_data.get("metadata_updated_at")
            or movie_data.get("last_seen_at")
            or datetime.now(timezone.utc).isoformat()
        )

    def _movie_event_payload(self, movie_data: dict) -> dict:
        payload = {
            field: movie_data.get(field)
            for field in SCAN_EVENT_FIELDS
            if movie_data.get(field) is not None
        }
        if payload.get("id") and not payload.get("movie_id"):
            payload["movie_id"] = payload["id"]
        return payload

    def _scan_events_for_existing(self, previous_movie: dict, movie_data: dict, movie_id: str) -> list[dict]:
        events = []
        current_payload = self._movie_event_payload({**previous_movie, **movie_data, "id": movie_id})
        if previous_movie.get("library_status") == "missing" and movie_data.get("library_status") == "available":
            events.append({
                "type": "MovieRestored",
                "aggregate_id": movie_id,
                "payload": current_payload,
                "project": True,
            })

        file_changes = self._file_observation_changes(previous_movie, movie_data)
        if file_changes:
            events.append({
                "type": "MovieFileObserved",
                "aggregate_id": movie_id,
                "payload": {
                    **current_payload,
                    **file_changes,
                },
                "project": False,
            })

        nfo_changes = self._nfo_metadata_changes(previous_movie, movie_data)
        if nfo_changes:
            events.append({
                "type": "MovieMetadataParsedFromNfo",
                "aggregate_id": movie_id,
                "payload": {
                    **self._nfo_metadata_payload({**previous_movie, **movie_data, "id": movie_id}),
                    **nfo_changes,
                },
                "project": False,
            })
        return events

    def _file_observation_changes(self, previous_movie: dict, movie_data: dict) -> Optional[dict]:
        previous = {}
        current = {}
        changed_fields = []
        for field in FILE_OBSERVED_FIELDS:
            if field not in movie_data:
                continue
            previous_value = previous_movie.get(field)
            current_value = movie_data.get(field)
            if previous_value != current_value:
                changed_fields.append(field)
                previous[field] = previous_value
                current[field] = current_value

        if not changed_fields:
            return None
        return {
            "changed_fields": changed_fields,
            "previous": previous,
            "current": current,
        }

    def _nfo_metadata_changes(self, previous_movie: dict, movie_data: dict) -> Optional[dict]:
        if not movie_data.get("nfo_fingerprint"):
            return None

        previous = {}
        current = {}
        changed_fields = []
        for field in NFO_SIGNATURE_FIELDS:
            if field not in movie_data:
                continue
            previous_value = previous_movie.get(field)
            current_value = movie_data.get(field)
            if previous_value != current_value:
                changed_fields.append(field)
                previous[field] = previous_value
                current[field] = current_value

        if not changed_fields:
            return None
        return {
            "changed_fields": changed_fields,
            "previous": previous,
            "current": current,
        }

    def _nfo_metadata_payload(self, movie_data: dict) -> dict:
        payload = {
            field: movie_data.get(field)
            for field in (*NFO_METADATA_FIELDS, *NFO_SIGNATURE_FIELDS)
            if movie_data.get(field) is not None
        }
        if payload.get("id") and not payload.get("movie_id"):
            payload["movie_id"] = payload["id"]
        return payload

    def _append_scan_events(
        self,
        events: list[dict],
        *,
        command_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ):
        for event in events:
            if event.get("project"):
                event_store.append_and_project(
                    event["type"],
                    "movie",
                    event["aggregate_id"],
                    event["payload"],
                    command_id=command_id,
                    correlation_id=correlation_id,
                )
            else:
                event_store.safe_append(
                    event["type"],
                    "movie",
                    event["aggregate_id"],
                    event["payload"],
                    command_id=command_id,
                    correlation_id=correlation_id,
                )

    def _event_types(self, events: list[dict]) -> list[str]:
        return [event["type"] for event in events if event.get("type")]

library_manager = LibraryManager()
