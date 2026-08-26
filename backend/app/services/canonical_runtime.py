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
    canonical_json_hash,
)
from app.models import (
    ExternalIdentity,
    EventRecord,
    Film,
    FilmProfileState,
    GraphEntity,
    IdentityReview,
    LibraryItem,
    LibraryItemLocatorHistory,
    LocalProfile,
    MediaAsset,
    Viewing,
    utc_now_iso,
)
from app.services.file_identity import FileIdentityObservation, observe_file
from app.services.structured_metadata_sync import structured_metadata_synchronizer


SOURCE_INSTANCE_ID = "local"


@dataclass(frozen=True)
class RuntimeLibraryResolution:
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

    def sync_observation(
        self,
        session: Session,
        observation: dict[str, Any],
        *,
        preserve_id: str | None = None,
        file_observation: FileIdentityObservation | None = None,
        force_library_item_id: str | None = None,
        review_reason: str | None = None,
        review_context: dict[str, Any] | None = None,
        structured_metadata: (
            StructuredMetadataObservation | StructuredMetadataObservationDraft | None
        ) = None,
    ) -> RuntimeLibraryResolution:
        now = utc_now_iso()
        requested_id = preserve_id or observation.get("library_item_id")
        existing = (
            self._resolution_for_item(session, force_library_item_id)
            if force_library_item_id
            else (self._resolution_for_item(session, requested_id) if requested_id else None)
        )
        if file_observation is None:
            file_observation = self.observe_item(observation)
        if existing is None:
            existing = self._by_source_key(session, self.source_item_key(observation, requested_id))
        if existing is None and file_observation is not None and review_reason is None:
            try:
                existing = self._by_file_identity(session, file_observation, observation)
            except RelinkIdentityConflict:
                review_reason = review_reason or "relink_identity_conflict"
            except RelinkCopyConflict:
                review_reason = review_reason or "relink_live_copy_conflict"

        if existing is not None:
            resolution = existing
            self._update_film(session, resolution.film_id, observation, now)
            self._update_library_item(session, resolution.library_item_id, observation, now)
            self._update_locator(session, resolution.library_item_id, observation, now)
        else:
            film_id, conflict = self._resolve_film(session, observation, now)
            library_item_id = f"lib_{uuid4().hex}"
            resolution = RuntimeLibraryResolution(film_id, library_item_id)
            source_key = self.source_item_key(observation, library_item_id)
            availability = self._availability(observation.get("library_status"))
            identities = self._identities(observation)
            session.add(
                LibraryItem(
                    id=library_item_id,
                    profile_id=self.local_profile_id(session),
                    film_id=film_id,
                    source_type=(
                        "local_nfo"
                        if observation.get("nfo_path") or observation.get("nfo_file")
                        else "local_folder"
                    ),
                    source_instance_id=SOURCE_INSTANCE_ID,
                    source_item_key=source_key,
                    display_name=observation.get("folder_name") or observation.get("title"),
                    availability_status=availability,
                    resolution_status="review_required" if conflict or review_reason else (
                        "matched" if identities else "unresolved"
                    ),
                    added_at=observation.get("added_at") or now,
                    last_seen_at=observation.get("last_seen_at"),
                    missing_since=observation.get("missing_since"),
                    retired_at=now if availability == "retired" else None,
                    metadata_source=observation.get("metadata_source"),
                    metadata_updated_at=observation.get("metadata_updated_at"),
                    scrape_status=observation.get("scrape_status") or "pending",
                    scrape_error=observation.get("scrape_error"),
                    scraped_at=observation.get("scraped_at"),
                    match_confidence=observation.get("tmdb_confidence"),
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
            if conflict or review_reason:
                review_payload = {
                    "film_id": film_id,
                    "library_item_id": library_item_id,
                    "source_instance_id": SOURCE_INSTANCE_ID,
                    "source_ref": library_item_id,
                    "reason_code": review_reason or "identity_conflict",
                    "candidates": conflict or {},
                }
                candidate_hash = canonical_json_hash(review_payload["candidates"])
                session.add(
                    IdentityReview(
                        film_id=film_id,
                        library_item_id=library_item_id,
                        source_instance_id=SOURCE_INSTANCE_ID,
                        source_ref=library_item_id,
                        reason_code=review_reason or "identity_conflict",
                        candidate_hash=candidate_hash,
                        review_key=canonical_json_hash({**review_payload, "candidate_hash": candidate_hash}),
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

        self._sync_identities(session, resolution.film_id, observation, now)
        self._sync_assets(session, resolution, observation, now, file_observation)
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
        session.flush()
        return resolution

    @staticmethod
    def observe_item(observation: dict[str, Any]) -> FileIdentityObservation | None:
        locator = observation.get("media_path") or observation.get("video_file")
        return observe_file(locator) if locator else None

    def sync_user_state(
        self,
        session: Session,
        film_id: str,
        *,
        watched: bool | None = None,
        watched_at: str | None = None,
        rating: int | None = None,
        favorite: bool | None = None,
        notes: str | None = None,
        fields_set: set[str] | None = None,
    ) -> dict[str, Any] | None:
        fields_set = fields_set or set()
        if session.get(Film, film_id) is None:
            return None
        profile_id = self.local_profile_id(session)
        now = utc_now_iso()

        profile_state = session.get(FilmProfileState, (profile_id, film_id))
        state_fields = fields_set.intersection({"favorite", "rating", "notes"})
        if profile_state is None and state_fields:
            profile_state = FilmProfileState(
                profile_id=profile_id,
                film_id=film_id,
                favorite=bool(favorite),
                rating=rating if "rating" in fields_set else None,
                notes=notes if "notes" in fields_set else None,
                created_at=now,
                updated_at=now,
            )
        elif profile_state is not None and state_fields:
            if "favorite" in fields_set and favorite is not None:
                profile_state.favorite = favorite
            if "rating" in fields_set:
                profile_state.rating = rating
            if "notes" in fields_set:
                profile_state.notes = notes
            profile_state.updated_at = now
        if profile_state is not None:
            session.add(profile_state)

        manual_viewing = session.exec(
            select(Viewing)
            .where(Viewing.profile_id == profile_id)
            .where(Viewing.film_id == film_id)
            .where(Viewing.source == "manual")
            .where(Viewing.source_record_id == film_id)
            .order_by(Viewing.updated_at.desc(), Viewing.id.desc())
        ).first()

        if "watched" in fields_set and watched is False:
            if manual_viewing is not None and manual_viewing.deleted_at is None:
                manual_viewing.deleted_at = now
                manual_viewing.updated_at = now
                session.add(manual_viewing)
        elif watched is True or ("watched_at" in fields_set and watched_at is not None):
            if manual_viewing is None:
                manual_viewing = Viewing(
                    id=f"view_{uuid4().hex}",
                    profile_id=profile_id,
                    film_id=film_id,
                    source="manual",
                    source_record_id=film_id,
                    review_status="confirmed",
                    created_at=now,
                    updated_at=now,
                )
            manual_viewing.deleted_at = None
            if "watched_at" in fields_set:
                manual_viewing.watched_at = watched_at
            elif manual_viewing.watched_at is None:
                manual_viewing.watched_at = now
            manual_viewing.watched_at_precision = self._watched_at_precision(manual_viewing.watched_at)
            manual_viewing.review_status = "confirmed"
            manual_viewing.updated_at = now
            session.add(manual_viewing)

        session.flush()
        return self.derived_profile_state(session, profile_id, film_id)

    def derived_profile_state(
        self,
        session: Session,
        profile_id: str,
        film_id: str,
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
        updated_values = [
            value
            for value in (
                profile_state.updated_at if profile_state else None,
                confirmed.updated_at if confirmed else None,
            )
            if value
        ]
        return {
            "film_id": film_id,
            "watched": confirmed is not None,
            "watched_at": confirmed.watched_at if confirmed else None,
            "rating": profile_state.rating if profile_state else None,
            "favorite": bool(profile_state.favorite) if profile_state else False,
            "notes": profile_state.notes if profile_state else None,
            "updated_at": max(updated_values) if updated_values else None,
        }

    @staticmethod
    def source_item_key(observation: dict[str, Any], fallback: str | None = None) -> str:
        raw = (
            observation.get("folder_path")
            or observation.get("media_path")
            or observation.get("folder_name")
            or fallback
            or f"unknown-{uuid4().hex}"
        )
        return str(raw).replace("\\", "/").rstrip("/").strip()

    def _by_source_key(self, session: Session, source_key: str) -> RuntimeLibraryResolution | None:
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
        return RuntimeLibraryResolution(item.film_id, item.id)

    def _by_file_identity(
        self,
        session: Session,
        file_identity: FileIdentityObservation,
        observation: dict[str, Any],
    ) -> RuntimeLibraryResolution | None:
        platform_candidates = session.exec(
            select(MediaAsset)
            .where(MediaAsset.asset_kind == "video")
            .where(MediaAsset.library_item_id.is_not(None))
            .where(MediaAsset.platform_file_id == file_identity.platform_file_id)
        ).all()
        platform_ids = sorted(
            {asset.library_item_id for asset in platform_candidates if asset.library_item_id}
        )
        if platform_ids:
            return self._unique_file_match(session, platform_ids, file_identity, observation)

        fingerprint_candidates = session.exec(
            select(MediaAsset)
            .where(MediaAsset.asset_kind == "video")
            .where(MediaAsset.library_item_id.is_not(None))
            .where(MediaAsset.content_fingerprint == file_identity.content_fingerprint)
        ).all()
        item_ids = sorted(
            {asset.library_item_id for asset in fingerprint_candidates if asset.library_item_id}
        )
        if not item_ids:
            return None
        if file_identity.content_hash:
            complete_ids = sorted(
                {
                    asset.library_item_id
                    for asset in fingerprint_candidates
                    if asset.library_item_id and asset.content_hash == file_identity.content_hash
                }
            )
            if complete_ids:
                return self._unique_file_match(session, complete_ids, file_identity, observation)
        return self._unique_file_match(session, item_ids, file_identity, observation)

    def _unique_file_match(
        self,
        session: Session,
        item_ids: list[str],
        file_identity: FileIdentityObservation,
        observation: dict[str, Any],
    ) -> RuntimeLibraryResolution:
        if len(item_ids) != 1:
            raise AmbiguousRelink(file_identity, item_ids)
        resolution = self._resolution_for_item(session, item_ids[0])
        if resolution is None:
            raise AmbiguousRelink(file_identity, item_ids)
        if self.has_live_locator_conflict(session, resolution.library_item_id, observation):
            raise RelinkCopyConflict("The original locator still exists")
        if self.has_identity_conflict(session, resolution.film_id, observation):
            raise RelinkIdentityConflict("File match conflicts with the candidate film identity")
        return resolution

    @staticmethod
    def has_live_locator_conflict(
        session: Session,
        library_item_id: str,
        observation: dict[str, Any],
    ) -> bool:
        incoming = observation.get("media_path") or observation.get("video_file")
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
    ) -> RuntimeLibraryResolution | None:
        if not library_item_id:
            return None
        item = session.get(LibraryItem, library_item_id)
        if item is None:
            return None
        return RuntimeLibraryResolution(item.film_id, item.id)

    def has_identity_conflict(
        self,
        session: Session,
        film_id: str,
        observation: dict[str, Any],
    ) -> bool:
        for provider, external_id in self._identities(observation).items():
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
        observation: dict[str, Any],
        now: str,
    ) -> tuple[str, dict[str, str] | None]:
        candidates: dict[str, str] = {}
        for provider, external_id in self._identities(observation).items():
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
            self._update_film(session, film_id, observation, now)
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
                canonical_title=str(observation.get("title_cn") or observation.get("title") or "Untitled"),
                original_title=observation.get("title"),
                release_year=self._year(observation.get("year")),
                runtime_minutes=observation.get("runtime"),
                overview=observation.get("overview") or observation.get("plot"),
                lifecycle_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        return film_id, conflict

    def _update_film(self, session: Session, film_id: str, observation: dict[str, Any], now: str) -> None:
        film = session.get(Film, film_id)
        if film is None:
            return
        film.canonical_title = str(observation.get("title_cn") or observation.get("title") or film.canonical_title)
        film.original_title = observation.get("title") or film.original_title
        film.release_year = self._year(observation.get("year"))
        film.runtime_minutes = observation.get("runtime")
        film.overview = observation.get("overview") or observation.get("plot")
        film.updated_at = now
        session.add(film)

    def _update_library_item(
        self,
        session: Session,
        library_item_id: str,
        observation: dict[str, Any],
        now: str,
    ) -> None:
        item = session.get(LibraryItem, library_item_id)
        if item is None:
            return
        item.display_name = observation.get("folder_name") or observation.get("title") or item.display_name
        incoming_availability = self._availability(observation.get("library_status"))
        item.availability_status = (
            "ignored"
            if item.availability_status == "ignored" and incoming_availability == "available"
            else incoming_availability
        )
        item.last_seen_at = observation.get("last_seen_at") or item.last_seen_at
        item.missing_since = observation.get("missing_since")
        item.metadata_source = observation.get("metadata_source")
        item.metadata_updated_at = observation.get("metadata_updated_at")
        item.scrape_status = observation.get("scrape_status") or item.scrape_status
        item.scrape_error = observation.get("scrape_error")
        item.scraped_at = observation.get("scraped_at")
        item.match_confidence = observation.get("tmdb_confidence")
        item.retired_at = now if item.availability_status == "retired" else None
        item.updated_at = now
        session.add(item)

    def _update_locator(
        self,
        session: Session,
        library_item_id: str,
        observation: dict[str, Any],
        now: str,
    ) -> None:
        item = session.get(LibraryItem, library_item_id)
        if item is None:
            return
        source_key = self.source_item_key(observation, item.id)
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
        incoming_availability = self._availability(observation.get("library_status"))
        item.availability_status = (
            "ignored"
            if item.availability_status == "ignored" and incoming_availability == "available"
            else incoming_availability
        )
        item.missing_since = observation.get("missing_since")
        item.updated_at = now
        session.add(item)

    def _sync_identities(self, session: Session, film_id: str, observation: dict[str, Any], now: str) -> None:
        for provider, external_id in self._identities(observation).items():
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
                    provenance_kind=observation.get("metadata_source") or "runtime",
                    created_at=now,
                    updated_at=now,
                )
            )

    def _sync_assets(
        self,
        session: Session,
        resolution: RuntimeLibraryResolution,
        observation: dict[str, Any],
        now: str,
        file_observation: FileIdentityObservation | None,
    ) -> None:
        definitions = (
            ("library", "video", observation.get("media_path") or observation.get("video_file")),
            ("library", "nfo", observation.get("nfo_path") or observation.get("nfo_file")),
            ("library", "poster", observation.get("poster_local")),
            ("library", "backdrop", observation.get("backdrop_local")),
            ("library", "poster_thumb", observation.get("poster_thumb_local")),
            ("library", "backdrop_thumb", observation.get("backdrop_thumb_local")),
            ("film", "poster", observation.get("poster_path")),
            ("film", "backdrop", observation.get("backdrop_path")),
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
                        "missing" if observation.get("library_status") == "missing" else (
                            "present" if owner == "library" else "unknown"
                        )
                    ),
                    source=observation.get("metadata_source") or "runtime",
                    created_at=now,
                    updated_at=now,
                )
            if owner == "library":
                if observation.get("library_status") == "missing":
                    asset.availability_status = "missing"
                elif observation.get("library_status") in {"retired", "reverted"}:
                    asset.availability_status = "retired"
                else:
                    asset.availability_status = "present"
                asset.missing_since = observation.get("missing_since")
            else:
                asset.availability_status = "unknown"
            if kind == "video":
                asset.file_size = observation.get("file_size")
                asset.file_mtime = observation.get("file_mtime")
                asset.width = observation.get("video_width")
                asset.height = observation.get("video_height")
                asset.codec = observation.get("video_codec")
                asset.bitrate = observation.get("video_bitrate")
                asset.duration_seconds = observation.get("video_duration")
                asset.fps = observation.get("video_fps")
                asset.dynamic_range = observation.get("video_dynamic_range")
                asset.bit_depth = observation.get("video_bit_depth")
                asset.stream_metadata = observation.get("audio_tracks")
                if file_observation is not None:
                    asset.platform_file_id = file_observation.platform_file_id
                    asset.content_fingerprint = file_observation.content_fingerprint
                    asset.content_hash = file_observation.content_hash
            elif kind == "nfo":
                asset.file_size = observation.get("nfo_size")
                asset.file_mtime = observation.get("nfo_mtime")
                asset.content_fingerprint = observation.get("nfo_fingerprint")
            asset.last_observed_at = observation.get("last_seen_at") or now
            asset.updated_at = now
            session.add(asset)

    @staticmethod
    def local_profile_id(session: Session) -> str:
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
    def _identities(observation: dict[str, Any]) -> dict[str, str]:
        identities = {}
        if observation.get("tmdb_id") is not None:
            identities["tmdb.movie"] = str(observation["tmdb_id"]).strip()
        if observation.get("imdb_id"):
            identities["imdb.title"] = str(observation["imdb_id"]).strip().casefold()
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
