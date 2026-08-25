from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from app.contracts.structured_metadata import (
    StructuredMetadataObservation,
    StructuredMetadataObservationDraft,
)
from app.models import (
    ExternalIdentity,
    EventRecord,
    Film,
    FilmProfileState,
    GraphEntity,
    IdentityReview,
    LegacyMovieAlias,
    LibraryItem,
    LibraryItemLocatorHistory,
    LocalProfile,
    MediaAsset,
    Movie,
    MovieUserState,
    Viewing,
    utc_now_iso,
)
from app.services.file_identity import FileIdentityObservation, observe_file
from app.services.structured_metadata_sync import structured_metadata_synchronizer


SOURCE_INSTANCE_ID = "legacy.local"


@dataclass(frozen=True)
class RuntimeMovieResolution:
    compatibility_id: str
    film_id: str
    library_item_id: str


class AmbiguousRelink(RuntimeError):
    def __init__(self, observation: FileIdentityObservation, library_item_ids: list[str]):
        super().__init__("Multiple library items share the same file fingerprint")
        self.observation = observation
        self.library_item_ids = library_item_ids


class RelinkIdentityConflict(RuntimeError):
    pass


class RelinkCopyConflict(RuntimeError):
    pass


class CanonicalRuntimeWriter:
    """Synchronize canonical library rows inside the caller's transaction."""

    def sync_movie(
        self,
        session: Session,
        movie_data: dict[str, Any],
        *,
        preserve_id: str | None = None,
        file_observation: FileIdentityObservation | None = None,
        force_library_item_id: str | None = None,
        review_reason: str | None = None,
        review_context: dict[str, Any] | None = None,
        structured_metadata: (
            StructuredMetadataObservation | StructuredMetadataObservationDraft | None
        ) = None,
    ) -> RuntimeMovieResolution:
        now = utc_now_iso()
        requested_id = preserve_id or movie_data.get("id")
        existing = (
            self._resolution_for_item(session, force_library_item_id)
            if force_library_item_id
            else (self._by_alias(session, requested_id) if requested_id else None)
        )
        if file_observation is None:
            file_observation = self.observe_movie(movie_data)
        if existing is None:
            existing = self._by_source_key(session, self.source_item_key(movie_data, requested_id))
        if existing is None and file_observation is not None and review_reason is None:
            try:
                existing = self._by_file_identity(session, file_observation, movie_data)
            except RelinkIdentityConflict:
                review_reason = review_reason or "relink_identity_conflict"
            except RelinkCopyConflict:
                review_reason = review_reason or "relink_live_copy_conflict"

        if existing is not None:
            resolution = existing
            self._update_film(session, resolution.film_id, movie_data, now)
            self._update_library_item(session, resolution.library_item_id, movie_data, now)
            self._update_locator(session, resolution.library_item_id, movie_data, now)
        else:
            film_id, conflict = self._resolve_film(session, movie_data, now)
            library_item_id = f"lib_{uuid4().hex}"
            compatibility_id = (
                str(preserve_id)
                if preserve_id
                else str(requested_id)
                if requested_id
                and not movie_data.get("media_path")
                and not movie_data.get("folder_path")
                else library_item_id
            )
            resolution = RuntimeMovieResolution(compatibility_id, film_id, library_item_id)
            source_key = self.source_item_key(movie_data, compatibility_id)
            availability = self._availability(movie_data.get("library_status"))
            identities = self._identities(movie_data)
            session.add(
                LibraryItem(
                    id=library_item_id,
                    profile_id=self._profile_id(session),
                    film_id=film_id,
                    source_type=(
                        "local_nfo"
                        if movie_data.get("nfo_path") or movie_data.get("nfo_file")
                        else "local_folder"
                    ),
                    source_instance_id=SOURCE_INSTANCE_ID,
                    source_item_key=source_key,
                    display_name=movie_data.get("folder_name") or movie_data.get("title"),
                    availability_status=availability,
                    resolution_status="review_required" if conflict or review_reason else (
                        "matched" if identities else "unresolved"
                    ),
                    added_at=movie_data.get("added_at") or now,
                    last_seen_at=movie_data.get("last_seen_at"),
                    missing_since=movie_data.get("missing_since"),
                    retired_at=now if availability == "retired" else None,
                    metadata_source=movie_data.get("metadata_source"),
                    metadata_updated_at=movie_data.get("metadata_updated_at"),
                    scrape_status=movie_data.get("scrape_status") or "pending",
                    scrape_error=movie_data.get("scrape_error"),
                    scraped_at=movie_data.get("scraped_at"),
                    match_confidence=movie_data.get("tmdb_confidence"),
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
            session.add(
                LibraryItemLocatorHistory(
                    id=f"locator_{uuid4().hex}",
                    library_item_id=library_item_id,
                    source_instance_id=SOURCE_INSTANCE_ID,
                    source_item_key=source_key,
                    observed_from=now,
                    reason="runtime_discovery",
                )
            )
            session.add(
                LegacyMovieAlias(
                    legacy_movie_id=compatibility_id,
                    film_id=film_id,
                    library_item_id=library_item_id,
                    legacy_library_status=movie_data.get("library_status"),
                    created_at=now,
                    updated_at=now,
                )
            )
            if conflict or review_reason:
                session.add(
                    IdentityReview(
                        id=f"review_{uuid4().hex}",
                        legacy_movie_id=compatibility_id,
                        tmdb_film_id=conflict.get("tmdb.movie") if conflict else None,
                        imdb_film_id=conflict.get("imdb.title") if conflict else None,
                        reason=review_reason or "identity_conflict",
                        created_at=now,
                        updated_at=now,
                    )
                )
                sanitized_context = {
                    key: value
                    for key, value in (review_context or {}).items()
                    if key in {"candidate_count", "fingerprint_id", "source_instance_id"}
                }
                session.add(
                    EventRecord(
                        aggregate_type="library_item",
                        aggregate_id=library_item_id,
                        type="LibraryItemRelinkNeedsReview",
                        payload={"reason": review_reason or "identity_conflict", **sanitized_context},
                    )
                )

        self._sync_identities(session, resolution.film_id, movie_data, now)
        self._sync_assets(session, resolution, movie_data, now, file_observation)
        if structured_metadata is not None:
            bound_observation = (
                structured_metadata.bind(resolution.library_item_id)
                if isinstance(structured_metadata, StructuredMetadataObservationDraft)
                else structured_metadata
            )
            structured_metadata_synchronizer.sync(
                session,
                film_id=resolution.film_id,
                library_item_id=resolution.library_item_id,
                observation=bound_observation,
            )
        alias = session.get(LegacyMovieAlias, resolution.compatibility_id)
        if alias:
            alias.legacy_library_status = movie_data.get("library_status")
            alias.updated_at = now
            session.add(alias)
        session.flush()
        return resolution

    @staticmethod
    def observe_movie(movie_data: dict[str, Any]) -> FileIdentityObservation | None:
        locator = movie_data.get("media_path") or movie_data.get("video_file")
        return observe_file(locator) if locator else None

    def sync_user_state(
        self,
        session: Session,
        movie_id: str,
        *,
        watched: bool | None = None,
        watched_at: str | None = None,
        rating: int | None = None,
        favorite: bool | None = None,
        notes: str | None = None,
        fields_set: set[str] | None = None,
    ) -> dict[str, Any] | None:
        fields_set = fields_set or set()
        alias = session.get(LegacyMovieAlias, movie_id)
        if alias is None:
            return None
        profile_id = self._profile_id(session)
        now = utc_now_iso()

        profile_state = session.get(FilmProfileState, (profile_id, alias.film_id))
        if profile_state is None and "favorite" in fields_set:
            profile_state = FilmProfileState(
                profile_id=profile_id,
                film_id=alias.film_id,
                favorite=bool(favorite),
                created_at=now,
                updated_at=now,
            )
        elif profile_state is not None and "favorite" in fields_set and favorite is not None:
            profile_state.favorite = favorite
            profile_state.updated_at = now
        if profile_state is not None:
            session.add(profile_state)

        compatibility_sources = ("legacy_movie_user_state", "legacy_user_state_api")
        compatibility_viewings = session.exec(
            select(Viewing)
            .where(Viewing.profile_id == profile_id)
            .where(Viewing.film_id == alias.film_id)
            .where(Viewing.source.in_(compatibility_sources))
            .order_by(Viewing.updated_at.desc(), Viewing.id.desc())
        ).all()

        if "watched" in fields_set and watched is False:
            for viewing in compatibility_viewings:
                if viewing.deleted_at is None:
                    viewing.deleted_at = now
                    viewing.updated_at = now
                    session.add(viewing)
            review_fields = fields_set.intersection({"watched_at", "rating", "notes"})
            if review_fields:
                api_viewing = next(
                    (
                        viewing
                        for viewing in compatibility_viewings
                        if viewing.source == "legacy_user_state_api"
                    ),
                    None,
                )
                if api_viewing is None:
                    api_viewing = Viewing(
                        id=f"view_{uuid4().hex}",
                        profile_id=profile_id,
                        film_id=alias.film_id,
                        source="legacy_user_state_api",
                        source_record_id=alias.film_id,
                        watched_at_precision="unknown",
                        review_status="needs_review",
                        created_at=now,
                        updated_at=now,
                    )
                api_viewing.deleted_at = None
                if "watched_at" in review_fields:
                    api_viewing.watched_at = watched_at
                    api_viewing.watched_at_precision = self._watched_at_precision(watched_at)
                if "rating" in review_fields:
                    api_viewing.rating = rating
                if "notes" in review_fields:
                    api_viewing.review = notes
                api_viewing.review_status = "needs_review"
                api_viewing.updated_at = now
                session.add(api_viewing)
        elif fields_set.intersection({"watched", "watched_at", "rating", "notes"}):
            api_viewing = next(
                (viewing for viewing in compatibility_viewings if viewing.source == "legacy_user_state_api"),
                None,
            )
            had_confirmed_compatibility = any(
                viewing.review_status == "confirmed" and viewing.deleted_at is None
                for viewing in compatibility_viewings
            )
            if api_viewing is None:
                api_viewing = Viewing(
                    id=f"view_{uuid4().hex}",
                    profile_id=profile_id,
                    film_id=alias.film_id,
                    source="legacy_user_state_api",
                    source_record_id=alias.film_id,
                    watched_at_precision="unknown",
                    review_status="needs_review",
                    created_at=now,
                    updated_at=now,
                )
            api_viewing.deleted_at = None
            if "watched_at" in fields_set:
                api_viewing.watched_at = watched_at
                api_viewing.watched_at_precision = self._watched_at_precision(watched_at)
            if "rating" in fields_set:
                api_viewing.rating = rating
            if "notes" in fields_set:
                api_viewing.review = notes
            if watched is True or api_viewing.watched_at or had_confirmed_compatibility:
                api_viewing.review_status = "confirmed"
            else:
                api_viewing.review_status = "needs_review"
            api_viewing.updated_at = now
            session.add(api_viewing)

        session.flush()
        state = self._derived_user_state(session, profile_id, alias.film_id, movie_id)
        active_viewings = session.exec(
            select(Viewing)
            .where(Viewing.profile_id == profile_id)
            .where(Viewing.film_id == alias.film_id)
            .where(Viewing.deleted_at.is_(None))
        ).all()
        has_non_default_state = bool(
            (profile_state is not None and profile_state.favorite)
            or active_viewings
        )
        aliases = session.exec(
            select(LegacyMovieAlias).where(LegacyMovieAlias.film_id == alias.film_id)
        ).all()
        for compatibility_alias in aliases:
            if session.get(Movie, compatibility_alias.legacy_movie_id) is None:
                continue
            projected = session.get(MovieUserState, compatibility_alias.legacy_movie_id)
            if not has_non_default_state:
                if projected is not None:
                    session.delete(projected)
                continue
            if projected is None:
                projected = MovieUserState(movie_id=compatibility_alias.legacy_movie_id)
            projected.watched = state["watched"]
            projected.watched_at = state["watched_at"]
            projected.rating = state["rating"]
            projected.favorite = state["favorite"]
            projected.notes = state["notes"]
            projected.updated_at = state["updated_at"] or now
            session.add(projected)
        session.flush()
        return state

    def _derived_user_state(
        self,
        session: Session,
        profile_id: str,
        film_id: str,
        movie_id: str,
    ) -> dict[str, Any]:
        profile_state = session.get(FilmProfileState, (profile_id, film_id))
        viewings = session.exec(
            select(Viewing)
            .where(Viewing.profile_id == profile_id)
            .where(Viewing.film_id == film_id)
            .where(Viewing.deleted_at.is_(None))
            .order_by(Viewing.watched_at.desc(), Viewing.updated_at.desc(), Viewing.id.desc())
        ).all()
        confirmed = next((item for item in viewings if item.review_status == "confirmed"), None)
        needs_review = next((item for item in viewings if item.review_status == "needs_review"), None)
        selected = confirmed or needs_review
        updated_values = [
            value
            for value in (
                profile_state.updated_at if profile_state else None,
                selected.updated_at if selected else None,
            )
            if value
        ]
        return {
            "movie_id": movie_id,
            "watched": confirmed is not None,
            "watched_at": confirmed.watched_at if confirmed else None,
            "rating": selected.rating if selected else None,
            "favorite": bool(profile_state.favorite) if profile_state else False,
            "notes": selected.review if selected else None,
            "updated_at": max(updated_values) if updated_values else None,
        }

    @staticmethod
    def source_item_key(movie_data: dict[str, Any], fallback: str | None = None) -> str:
        raw = (
            movie_data.get("folder_path")
            or movie_data.get("media_path")
            or movie_data.get("folder_name")
            or fallback
            or f"unknown-{uuid4().hex}"
        )
        return str(raw).replace("\\", "/").rstrip("/").strip()

    def compatibility_projection_fields(
        self,
        session: Session,
        resolution: RuntimeMovieResolution,
    ) -> dict[str, Any]:
        """Return Canonical-owned values for the legacy Movie projection."""
        film = session.get(Film, resolution.film_id)
        item = session.get(LibraryItem, resolution.library_item_id)
        alias = session.get(LegacyMovieAlias, resolution.compatibility_id)
        if film is None or item is None or alias is None:
            return {}
        identities = {
            identity.provider: identity.external_id
            for identity in session.exec(
                select(ExternalIdentity)
                .where(ExternalIdentity.entity_id == film.id)
                .where(ExternalIdentity.identity_status == "active")
            ).all()
        }
        return {
            "title": film.original_title or film.canonical_title,
            "title_cn": (
                film.canonical_title
                if film.canonical_title != film.original_title
                else None
            ),
            "year": film.release_year or 0,
            "runtime": film.runtime_minutes,
            "overview": film.overview,
            "tmdb_id": identities.get("tmdb.movie"),
            "imdb_id": identities.get("imdb.title"),
            "folder_name": item.display_name,
            "folder_path": item.source_item_key,
            "library_status": (
                alias.legacy_library_status
                if alias.legacy_library_status == "reverted"
                else item.availability_status
            ),
            "added_at": item.added_at,
            "last_seen_at": item.last_seen_at,
            "missing_since": item.missing_since,
            "metadata_source": item.metadata_source,
            "metadata_updated_at": item.metadata_updated_at,
            "scrape_status": item.scrape_status,
            "scrape_error": item.scrape_error,
            "scraped_at": item.scraped_at,
            "tmdb_confidence": item.match_confidence,
        }

    def _by_alias(self, session: Session, movie_id: str | None) -> RuntimeMovieResolution | None:
        if not movie_id:
            return None
        alias = session.get(LegacyMovieAlias, movie_id)
        if alias is None:
            return None
        return RuntimeMovieResolution(alias.legacy_movie_id, alias.film_id, alias.library_item_id)

    def _by_source_key(self, session: Session, source_key: str) -> RuntimeMovieResolution | None:
        active_items = session.exec(
            select(LibraryItem)
            .where(LibraryItem.source_instance_id == SOURCE_INSTANCE_ID)
            .where(LibraryItem.source_item_key == source_key)
            .where(LibraryItem.availability_status != "retired")
        ).all()
        item = active_items[0] if len(active_items) == 1 else None
        if not active_items:
            histories = session.exec(
                select(LibraryItemLocatorHistory)
                .where(LibraryItemLocatorHistory.source_instance_id == SOURCE_INSTANCE_ID)
                .where(LibraryItemLocatorHistory.source_item_key == source_key)
            ).all()
            history_item_ids = sorted({history.library_item_id for history in histories})
            item = (
                session.get(LibraryItem, history_item_ids[0])
                if len(history_item_ids) == 1
                else None
            )
        if item is None:
            return None
        alias = session.exec(
            select(LegacyMovieAlias).where(LegacyMovieAlias.library_item_id == item.id)
        ).first()
        if alias is None:
            return None
        return RuntimeMovieResolution(alias.legacy_movie_id, item.film_id, item.id)

    def _by_file_identity(
        self,
        session: Session,
        observation: FileIdentityObservation,
        movie_data: dict[str, Any],
    ) -> RuntimeMovieResolution | None:
        platform_candidates = session.exec(
            select(MediaAsset)
            .where(MediaAsset.asset_kind == "video")
            .where(MediaAsset.library_item_id.is_not(None))
            .where(MediaAsset.platform_file_id == observation.platform_file_id)
        ).all()
        platform_ids = sorted(
            {asset.library_item_id for asset in platform_candidates if asset.library_item_id}
        )
        if platform_ids:
            return self._unique_file_match(session, platform_ids, observation, movie_data)

        fingerprint_candidates = session.exec(
            select(MediaAsset)
            .where(MediaAsset.asset_kind == "video")
            .where(MediaAsset.library_item_id.is_not(None))
            .where(MediaAsset.content_fingerprint == observation.content_fingerprint)
        ).all()
        item_ids = sorted(
            {asset.library_item_id for asset in fingerprint_candidates if asset.library_item_id}
        )
        if not item_ids:
            return None
        if observation.content_hash:
            complete_ids = sorted(
                {
                    asset.library_item_id
                    for asset in fingerprint_candidates
                    if asset.library_item_id and asset.content_hash == observation.content_hash
                }
            )
            if complete_ids:
                return self._unique_file_match(session, complete_ids, observation, movie_data)
        return self._unique_file_match(session, item_ids, observation, movie_data)

    def _unique_file_match(
        self,
        session: Session,
        item_ids: list[str],
        observation: FileIdentityObservation,
        movie_data: dict[str, Any],
    ) -> RuntimeMovieResolution:
        if len(item_ids) != 1:
            raise AmbiguousRelink(observation, item_ids)
        resolution = self._resolution_for_item(session, item_ids[0])
        if resolution is None:
            raise AmbiguousRelink(observation, item_ids)
        if self.has_live_locator_conflict(session, resolution.library_item_id, movie_data):
            raise RelinkCopyConflict("The original locator still exists")
        if self.has_identity_conflict(session, resolution.film_id, movie_data):
            raise RelinkIdentityConflict("File match conflicts with the candidate film identity")
        return resolution

    @staticmethod
    def has_live_locator_conflict(
        session: Session,
        library_item_id: str,
        movie_data: dict[str, Any],
    ) -> bool:
        incoming = movie_data.get("media_path") or movie_data.get("video_file")
        incoming_normalized = str(incoming).replace("\\", "/") if incoming else None
        assets = session.exec(
            select(MediaAsset)
            .where(MediaAsset.library_item_id == library_item_id)
            .where(MediaAsset.asset_kind == "video")
            .where(MediaAsset.availability_status != "retired")
        ).all()
        for asset in assets:
            locator_normalized = str(asset.locator).replace("\\", "/")
            if incoming_normalized and locator_normalized == incoming_normalized:
                continue
            try:
                if Path(asset.locator).is_file():
                    return True
            except OSError:
                continue
        return False

    @staticmethod
    def _resolution_for_item(
        session: Session,
        library_item_id: str | None,
    ) -> RuntimeMovieResolution | None:
        if not library_item_id:
            return None
        item = session.get(LibraryItem, library_item_id)
        if item is None:
            return None
        alias = session.exec(
            select(LegacyMovieAlias).where(LegacyMovieAlias.library_item_id == item.id)
        ).first()
        if alias is None:
            return None
        return RuntimeMovieResolution(alias.legacy_movie_id, item.film_id, item.id)

    def has_identity_conflict(
        self,
        session: Session,
        film_id: str,
        movie_data: dict[str, Any],
    ) -> bool:
        for provider, external_id in self._identities(movie_data).items():
            film_values = session.exec(
                select(ExternalIdentity.external_id)
                .where(ExternalIdentity.entity_id == film_id)
                .where(ExternalIdentity.provider == provider)
                .where(ExternalIdentity.identity_status == "active")
            ).all()
            if film_values and external_id not in {str(value) for value in film_values}:
                return True
            owner = session.exec(
                select(ExternalIdentity)
                .where(ExternalIdentity.provider == provider)
                .where(ExternalIdentity.external_id == external_id)
                .where(ExternalIdentity.identity_status == "active")
            ).first()
            if owner is not None and owner.entity_id != film_id:
                return True
        return False

    def _resolve_film(
        self,
        session: Session,
        movie_data: dict[str, Any],
        now: str,
    ) -> tuple[str, dict[str, str] | None]:
        candidates: dict[str, str] = {}
        for provider, external_id in self._identities(movie_data).items():
            identity = session.exec(
                select(ExternalIdentity)
                .where(ExternalIdentity.provider == provider)
                .where(ExternalIdentity.external_id == external_id)
                .where(ExternalIdentity.identity_status == "active")
            ).first()
            if identity:
                candidates[provider] = identity.entity_id

        candidate_ids = set(candidates.values())
        conflict = candidates if len(candidate_ids) > 1 else None
        if len(candidate_ids) == 1:
            film_id = next(iter(candidate_ids))
            self._update_film(session, film_id, movie_data, now)
            return film_id, None

        film_id = f"film_{uuid4().hex}"
        session.add(
            GraphEntity(
                id=film_id,
                entity_type="film",
                lifecycle_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            Film(
                id=film_id,
                canonical_title=str(movie_data.get("title_cn") or movie_data.get("title") or "Untitled"),
                original_title=movie_data.get("title"),
                release_year=self._year(movie_data.get("year")),
                runtime_minutes=movie_data.get("runtime"),
                overview=movie_data.get("overview") or movie_data.get("plot"),
                lifecycle_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        return film_id, conflict

    def _update_film(self, session: Session, film_id: str, movie_data: dict[str, Any], now: str) -> None:
        film = session.get(Film, film_id)
        if film is None:
            return
        film.canonical_title = str(movie_data.get("title_cn") or movie_data.get("title") or film.canonical_title)
        film.original_title = movie_data.get("title") or film.original_title
        film.release_year = self._year(movie_data.get("year"))
        film.runtime_minutes = movie_data.get("runtime")
        film.overview = movie_data.get("overview") or movie_data.get("plot")
        film.updated_at = now
        session.add(film)

    def _update_library_item(
        self,
        session: Session,
        library_item_id: str,
        movie_data: dict[str, Any],
        now: str,
    ) -> None:
        item = session.get(LibraryItem, library_item_id)
        if item is None:
            return
        item.display_name = movie_data.get("folder_name") or movie_data.get("title") or item.display_name
        item.availability_status = self._availability(movie_data.get("library_status"))
        item.last_seen_at = movie_data.get("last_seen_at") or item.last_seen_at
        item.missing_since = movie_data.get("missing_since")
        item.metadata_source = movie_data.get("metadata_source")
        item.metadata_updated_at = movie_data.get("metadata_updated_at")
        item.scrape_status = movie_data.get("scrape_status") or item.scrape_status
        item.scrape_error = movie_data.get("scrape_error")
        item.scraped_at = movie_data.get("scraped_at")
        item.match_confidence = movie_data.get("tmdb_confidence")
        item.retired_at = now if item.availability_status == "retired" else None
        item.updated_at = now
        session.add(item)

    def _update_locator(
        self,
        session: Session,
        library_item_id: str,
        movie_data: dict[str, Any],
        now: str,
    ) -> None:
        item = session.get(LibraryItem, library_item_id)
        if item is None:
            return
        source_key = self.source_item_key(movie_data, item.id)
        if source_key == item.source_item_key:
            current_history = session.exec(
                select(LibraryItemLocatorHistory)
                .where(LibraryItemLocatorHistory.library_item_id == library_item_id)
                .where(LibraryItemLocatorHistory.source_instance_id == SOURCE_INSTANCE_ID)
                .where(LibraryItemLocatorHistory.source_item_key == source_key)
                .order_by(LibraryItemLocatorHistory.observed_from.desc())
            ).first()
            if current_history is not None and current_history.observed_to is not None:
                current_history.observed_to = None
                current_history.reason = "runtime_restore"
                session.add(current_history)
            return
        current_history = session.exec(
            select(LibraryItemLocatorHistory)
            .where(LibraryItemLocatorHistory.library_item_id == library_item_id)
            .where(LibraryItemLocatorHistory.observed_to.is_(None))
        ).all()
        for history in current_history:
            history.observed_to = now
            session.add(history)
        existing_history = session.exec(
            select(LibraryItemLocatorHistory)
            .where(LibraryItemLocatorHistory.library_item_id == library_item_id)
            .where(LibraryItemLocatorHistory.source_instance_id == SOURCE_INSTANCE_ID)
            .where(LibraryItemLocatorHistory.source_item_key == source_key)
        ).first()
        if existing_history is None:
            session.add(
                LibraryItemLocatorHistory(
                    id=f"locator_{uuid4().hex}",
                    library_item_id=library_item_id,
                    source_instance_id=SOURCE_INSTANCE_ID,
                    source_item_key=source_key,
                    observed_from=now,
                    reason="runtime_relink",
                )
            )
        else:
            existing_history.observed_to = None
            existing_history.reason = "runtime_relink"
            session.add(existing_history)
        item.source_item_key = source_key
        item.availability_status = self._availability(movie_data.get("library_status"))
        item.missing_since = movie_data.get("missing_since")
        item.updated_at = now
        session.add(item)

    def _sync_identities(self, session: Session, film_id: str, movie_data: dict[str, Any], now: str) -> None:
        for provider, external_id in self._identities(movie_data).items():
            existing = session.exec(
                select(ExternalIdentity)
                .where(ExternalIdentity.provider == provider)
                .where(ExternalIdentity.external_id == external_id)
            ).first()
            if existing is not None:
                continue
            session.add(
                ExternalIdentity(
                    id=f"identity_{uuid4().hex}",
                    entity_id=film_id,
                    provider=provider,
                    external_id=external_id,
                    identity_status="active",
                    provenance_kind=movie_data.get("metadata_source") or "runtime",
                    created_at=now,
                    updated_at=now,
                )
            )

    def _sync_assets(
        self,
        session: Session,
        resolution: RuntimeMovieResolution,
        movie_data: dict[str, Any],
        now: str,
        file_observation: FileIdentityObservation | None,
    ) -> None:
        definitions = (
            ("library", "video", movie_data.get("media_path") or movie_data.get("video_file")),
            ("library", "nfo", movie_data.get("nfo_path") or movie_data.get("nfo_file")),
            ("library", "poster", movie_data.get("poster_local")),
            ("library", "backdrop", movie_data.get("backdrop_local")),
            ("film", "poster", movie_data.get("poster_path")),
            ("film", "backdrop", movie_data.get("backdrop_path")),
        )
        for owner, kind, locator_value in definitions:
            if not locator_value:
                continue
            locator = str(locator_value)
            locator_hash = self._hash(locator.replace("\\", "/"))
            statement = select(MediaAsset).where(MediaAsset.asset_kind == kind).where(
                MediaAsset.normalized_locator_hash == locator_hash
            )
            statement = statement.where(
                MediaAsset.library_item_id == resolution.library_item_id
                if owner == "library"
                else MediaAsset.film_id == resolution.film_id
            )
            asset = session.exec(statement).first()
            owner_assets = session.exec(
                select(MediaAsset).where(MediaAsset.asset_kind == kind).where(
                    MediaAsset.library_item_id == resolution.library_item_id
                    if owner == "library"
                    else MediaAsset.film_id == resolution.film_id
                )
            ).all()
            for previous in owner_assets:
                if previous.normalized_locator_hash != locator_hash and previous.availability_status != "retired":
                    previous.availability_status = "retired"
                    previous.updated_at = now
                    session.add(previous)
            if asset is None:
                asset = MediaAsset(
                    id=f"asset_{uuid4().hex}",
                    library_item_id=resolution.library_item_id if owner == "library" else None,
                    film_id=resolution.film_id if owner == "film" else None,
                    asset_kind=kind,
                    locator_kind="local_path" if owner == "library" else "provider_path",
                    locator=locator,
                    normalized_locator_hash=locator_hash,
                    availability_status=(
                        "missing" if movie_data.get("library_status") == "missing" else (
                            "present" if owner == "library" else "unknown"
                        )
                    ),
                    source=movie_data.get("metadata_source") or "runtime",
                    created_at=now,
                    updated_at=now,
                )
            if owner == "library":
                if movie_data.get("library_status") == "missing":
                    asset.availability_status = "missing"
                elif movie_data.get("library_status") in {"retired", "reverted"}:
                    asset.availability_status = "retired"
                else:
                    asset.availability_status = "present"
                asset.missing_since = movie_data.get("missing_since")
            else:
                asset.availability_status = "unknown"
            if kind == "video":
                asset.file_size = movie_data.get("file_size")
                asset.file_mtime = movie_data.get("file_mtime")
                asset.width = movie_data.get("video_width")
                asset.height = movie_data.get("video_height")
                asset.codec = movie_data.get("video_codec")
                asset.bitrate = movie_data.get("video_bitrate")
                asset.duration_seconds = movie_data.get("video_duration")
                asset.fps = movie_data.get("video_fps")
                asset.dynamic_range = movie_data.get("video_dynamic_range")
                asset.bit_depth = movie_data.get("video_bit_depth")
                asset.stream_metadata = movie_data.get("audio_tracks")
                if file_observation is not None:
                    asset.platform_file_id = file_observation.platform_file_id
                    asset.content_fingerprint = file_observation.content_fingerprint
                    asset.content_hash = file_observation.content_hash
            elif kind == "nfo":
                asset.file_size = movie_data.get("nfo_size")
                asset.file_mtime = movie_data.get("nfo_mtime")
                asset.content_fingerprint = movie_data.get("nfo_fingerprint")
            asset.last_observed_at = movie_data.get("last_seen_at") or now
            asset.updated_at = now
            session.add(asset)

    @staticmethod
    def _profile_id(session: Session) -> str:
        profile = session.exec(select(LocalProfile).where(LocalProfile.profile_key == "local")).first()
        if profile is None:
            now = utc_now_iso()
            profile = LocalProfile(
                id=f"profile_{uuid4().hex}",
                profile_key="local",
                display_name="Local Profile",
                created_at=now,
                updated_at=now,
            )
            session.add(profile)
            session.flush()
        return profile.id

    @staticmethod
    def _identities(movie_data: dict[str, Any]) -> dict[str, str]:
        identities = {}
        if movie_data.get("tmdb_id") is not None:
            identities["tmdb.movie"] = str(movie_data["tmdb_id"]).strip()
        if movie_data.get("imdb_id"):
            identities["imdb.title"] = str(movie_data["imdb_id"]).strip().casefold()
        return {provider: value for provider, value in identities.items() if value}

    @staticmethod
    def _availability(value: Any) -> str:
        if value == "reverted":
            return "retired"
        return value if value in {"available", "missing", "ignored", "retired"} else "available"

    @staticmethod
    def _year(value: Any) -> int | None:
        try:
            result = int(value)
        except (TypeError, ValueError):
            return None
        return result or None

    @staticmethod
    def _watched_at_precision(value: str | None) -> str:
        if not value:
            return "unknown"
        if len(value) == 4 and value.isdigit():
            return "year"
        if len(value) == 10:
            return "date"
        return "timestamp"

    @staticmethod
    def _hash(value: Any) -> str:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


canonical_runtime_writer = CanonicalRuntimeWriter()
