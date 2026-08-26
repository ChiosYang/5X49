from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlmodel import Session, delete, select

from app.contracts.structured_metadata import (
    StructuredMetadataObservation,
    StructuredMetadataObservationDraft,
)
from app.database import engine
from app.models import (
    AnalysisResolutionReview,
    AnalysisRun,
    Assertion,
    AssertionEvidence,
    AssertionProvenance,
    Concept,
    ConceptAlias,
    Credit,
    CreditProvenance,
    EventRecord,
    ExternalIdentity,
    ExternalScoreRefreshState,
    Evidence,
    Film,
    FilmCountry,
    FilmCountryProvenance,
    FilmExternalScore,
    FilmProfileState,
    FilmTitle,
    GraphEntity,
    IdentityReview,
    Job,
    LibraryItem,
    LibraryItemLocatorHistory,
    MediaAsset,
    OperationSnapshot,
    Person,
    StructuredMetadataReview,
    Viewing,
    utc_now_iso,
)
from app.services.canonical_runtime import (
    SOURCE_INSTANCE_ID,
    AmbiguousRelink,
    RuntimeLibraryResolution,
    canonical_runtime_writer,
)
from app.services.file_identity import FileIdentityObservation, full_content_hash
from app.services.structured_metadata_sync import structured_metadata_synchronizer
from app.services.private_payloads import private_payload_store


SEED_DATA_FILE = Path(__file__).parent.parent / "data" / "seed_movies.json"


class LibraryManager:
    """Film-centric Library repository and command service."""

    def add_observations(
        self,
        observations: list[dict[str, Any]],
        *,
        structured_observations: list[
            StructuredMetadataObservation | StructuredMetadataObservationDraft | None
        ] | None = None,
    ) -> int:
        metadata = structured_observations or [None] * len(observations)
        if len(metadata) != len(observations):
            raise ValueError("structured observations must align with scan observations")
        created = 0
        with Session(engine) as session:
            for payload, structured in zip(observations, metadata, strict=True):
                source_key = canonical_runtime_writer.source_item_key(payload)
                existed = session.exec(
                    select(LibraryItem.id)
                    .where(LibraryItem.source_instance_id == SOURCE_INSTANCE_ID)
                    .where(LibraryItem.source_item_key == source_key)
                    .where(LibraryItem.availability_status != "retired")
                ).first()
                try:
                    resolution = canonical_runtime_writer.sync_observation(
                        session,
                        payload,
                        file_observation=canonical_runtime_writer.observe_item(payload),
                        structured_metadata=structured,
                    )
                except AmbiguousRelink as ambiguity:
                    self._queue_relink_job(session, payload, ambiguity)
                    continue
                if existed is None:
                    created += 1
                self._append_item_event(
                    session,
                    "LibraryItemDiscovered" if existed is None else "LibraryItemObserved",
                    resolution,
                    {"availability_status": self._item(session, resolution.library_item_id).availability_status},
                )
            session.commit()
        return created

    def upsert_observation(
        self,
        payload: dict[str, Any],
        *,
        library_item_id: str | None = None,
        command_id: str | None = None,
        correlation_id: str | None = None,
        structured_metadata: StructuredMetadataObservation | StructuredMetadataObservationDraft | None = None,
        force_library_item_id: str | None = None,
        review_reason: str | None = None,
        review_context: dict[str, Any] | None = None,
        file_observation: FileIdentityObservation | None = None,
        candidate_hashes: dict[str, str] | None = None,
        event_type: str | None = None,
        event_payload: dict[str, Any] | None = None,
        operation_before_state: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with Session(engine) as session:
            requested_item_id = force_library_item_id or library_item_id
            existing_item = (
                session.get(LibraryItem, requested_item_id) if requested_item_id else None
            )
            before_status = existing_item.availability_status if existing_item else None
            before_missing_since = existing_item.missing_since if existing_item else None
            snapshot_kind = {
                "MetadataMatched": "metadata",
                "ArtworkSelected": "artwork",
            }.get(event_type or "")
            before_snapshot = operation_before_state or (
                self._snapshot_state(session, "film", existing_item.film_id, snapshot_kind)
                if existing_item is not None and snapshot_kind is not None
                else None
            )
            for asset_id, content_hash in (candidate_hashes or {}).items():
                asset = session.get(MediaAsset, asset_id)
                if asset is not None:
                    asset.content_hash = content_hash
                    asset.updated_at = utc_now_iso()
                    session.add(asset)
            try:
                resolution = canonical_runtime_writer.sync_observation(
                    session,
                    payload,
                    preserve_id=library_item_id,
                    file_observation=file_observation or canonical_runtime_writer.observe_item(payload),
                    force_library_item_id=force_library_item_id,
                    review_reason=review_reason,
                    review_context=review_context,
                    structured_metadata=structured_metadata,
                )
            except AmbiguousRelink as ambiguity:
                job_id = self._queue_relink_job(session, payload, ambiguity)
                session.commit()
                return {"status": "pending_relink", "job_id": job_id}
            updated_item = self._item(session, resolution.library_item_id)
            restored = before_status == "missing" and updated_item.availability_status == "available"
            event = (
                self._append_event(
                    session,
                    event_type,
                    "film",
                    resolution.film_id,
                    {"library_item_id": resolution.library_item_id, **(event_payload or {})},
                    command_id=command_id,
                    correlation_id=correlation_id,
                )
                if event_type
                else self._append_item_event(
                    session,
                    "LibraryItemRestored" if restored else "LibraryItemObserved",
                    resolution,
                    {"availability_status": self._item(session, resolution.library_item_id).availability_status},
                    command_id=command_id,
                    correlation_id=correlation_id,
                )
            )
            if snapshot_kind is not None and before_snapshot is not None:
                after_snapshot = self._snapshot_state(
                    session,
                    "film",
                    resolution.film_id,
                    snapshot_kind,
                )
                if after_snapshot != before_snapshot:
                    self._add_snapshot(
                        session,
                        event,
                        "film",
                        resolution.film_id,
                        snapshot_kind,
                        before_snapshot,
                        after_snapshot,
                    )
            elif restored:
                self._add_snapshot(
                    session,
                    event,
                    "library_item",
                    resolution.library_item_id,
                    "availability",
                    {
                        "availability_status": "missing",
                        "missing_since": before_missing_since,
                    },
                    {"availability_status": "available", "missing_since": None},
                )
            session.commit()
            return {
                "film_id": resolution.film_id,
                "library_item_id": resolution.library_item_id,
                "event_id": event.id,
            }

    def resolve_relink(self, payload: dict[str, Any], *, job_id: str | None = None) -> dict[str, Any]:
        pending = list(payload.get("items") or [payload])
        processed: set[str] = set()
        results: list[dict[str, Any]] = []
        while True:
            for item in pending:
                item_key = str(item.get("source_item_id") or self._hash_identifier(
                    canonical_runtime_writer.source_item_key(item.get("observation") or {})
                ))
                if item_key in processed:
                    continue
                processed.add(item_key)
                results.append(self._resolve_relink_item({**payload, **item}))
            if not job_id:
                break
            with Session(engine) as session:
                job = session.get(Job, job_id)
                refreshed = list((job.payload or {}).get("items") or []) if job else []
            if not any(str(item.get("source_item_id")) not in processed for item in refreshed):
                break
            pending = refreshed
        matched = sum(int(item.get("matched") or 0) for item in results)
        needs_review = sum(item.get("status") == "needs_review" for item in results)
        return {
            "status": "relinked" if matched and not needs_review else "needs_review",
            "processed": len(results),
            "matched": matched,
            "needs_review": needs_review,
            "candidate_count": sum(int(item.get("candidate_count") or 0) for item in results),
            "fingerprint_id": payload.get("fingerprint_id"),
        }

    def _resolve_relink_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        private_payload = private_payload_store.get(
            payload["observation_ref"],
            "relink_observation",
        )
        observation_payload = dict(private_payload.get("observation") or {})
        candidate_ids = {
            str(value) for value in private_payload.get("candidate_item_ids") or []
        }
        observation = canonical_runtime_writer.observe_item(observation_payload)
        candidate_hashes: dict[str, str] = {}
        matches: set[str] = set()
        complete_hash: str | None = None
        if observation is not None:
            locator = observation_payload.get("media_path") or observation_payload.get("video_file")
            try:
                complete_hash = observation.content_hash or full_content_hash(locator)
            except (FileNotFoundError, OSError):
                complete_hash = None
        if complete_hash is not None:
            with Session(engine) as session:
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
        force_item = next(iter(matches)) if len(matches) == 1 else None
        reason = None
        if observation is None or complete_hash is None:
            reason = "relink_file_disappeared"
            observation_payload["library_status"] = "missing"
        elif len(matches) == 0:
            reason = "relink_full_hash_no_match"
        elif len(matches) > 1:
            reason = "relink_full_hash_duplicate"
        result = self.upsert_observation(
            observation_payload,
            force_library_item_id=force_item,
            review_reason=reason,
            review_context={
                "candidate_count": len(candidate_ids),
                "fingerprint_id": payload.get("fingerprint_id"),
                "source_instance_id": SOURCE_INSTANCE_ID,
            },
            file_observation=(
                FileIdentityObservation(
                    platform_file_id=observation.platform_file_id,
                    content_fingerprint=observation.content_fingerprint,
                    content_hash=complete_hash,
                    bytes_read=observation.bytes_read,
                )
                if observation is not None and complete_hash is not None
                else observation
            ),
            candidate_hashes=candidate_hashes,
        )
        return {
            "status": "relinked" if force_item and result else "needs_review",
            "matched": 1 if force_item and result else 0,
            "candidate_count": len(candidate_ids),
            "hash_id": self._hash_identifier(complete_hash),
        }

    def list_films(self) -> list[dict[str, Any]]:
        with Session(engine) as session:
            film_ids = sorted({
                item.film_id
                for item in session.exec(
                    select(LibraryItem).where(LibraryItem.availability_status != "retired")
                ).all()
            })
            rows = [self._film_view(session, film_id, include_editions=False) for film_id in film_ids]
        return sorted(
            [row for row in rows if row is not None],
            key=lambda row: (str(row["title"]).casefold(), row.get("year") or 0, row["id"]),
        )

    def get_film(self, film_id: str) -> dict[str, Any] | None:
        with Session(engine) as session:
            return self._film_view(session, film_id, include_editions=True)

    def get_item(self, library_item_id: str) -> dict[str, Any] | None:
        with Session(engine) as session:
            item = session.get(LibraryItem, library_item_id)
            if item is None or item.availability_status == "retired":
                return None
            return self._edition_view(session, item)

    def get_film_operation_context(self, film_id: str) -> dict[str, Any] | None:
        """Return the bounded flat input used by scan/metadata command services."""
        film = self.get_film(film_id)
        if film is None:
            return None
        item = film["primary_item"]
        video = item.get("video") or {}
        artwork = item.get("artwork") or {}
        metadata = item.get("metadata") or {}
        locator = video.get("locator")
        return {
            "id": film_id,
            "film_id": film_id,
            "library_item_id": item["id"],
            "title": film["title"],
            "original_title": film.get("original_title"),
            "title_cn": film["title"] if film["title"] != film.get("original_title") else None,
            "year": film.get("year"),
            "runtime": film.get("runtime_minutes"),
            "overview": film.get("overview"),
            "plot": film.get("overview"),
            "tmdb_id": (film.get("identities") or {}).get("tmdb"),
            "imdb_id": (film.get("identities") or {}).get("imdb"),
            "genres": film.get("genres"),
            "countries": film.get("countries"),
            "director": (film.get("directors") or [None])[0],
            "folder_name": item.get("display_name"),
            "folder_path": str(Path(locator).parent) if locator else None,
            "video_file": Path(locator).name if locator else None,
            "media_path": locator,
            "file_size": video.get("file_size"),
            "file_mtime": video.get("file_mtime"),
            "video_width": video.get("width"),
            "video_height": video.get("height"),
            "video_codec": video.get("codec"),
            "video_bitrate": video.get("bitrate"),
            "video_duration": video.get("duration_seconds"),
            "video_fps": video.get("fps"),
            "video_dynamic_range": video.get("dynamic_range"),
            "video_bit_depth": video.get("bit_depth"),
            "audio_tracks": video.get("audio_tracks"),
            "poster_local": artwork.get("poster_local"),
            "backdrop_local": artwork.get("backdrop_local"),
            "poster_thumb_local": artwork.get("poster_thumb_local"),
            "backdrop_thumb_local": artwork.get("backdrop_thumb_local"),
            "poster_path": artwork.get("poster_provider"),
            "backdrop_path": artwork.get("backdrop_provider"),
            "library_status": item.get("status"),
            "metadata_source": metadata.get("source"),
            "metadata_updated_at": metadata.get("updated_at"),
            "scrape_status": metadata.get("scrape_status"),
            "scrape_error": metadata.get("scrape_error"),
            "scraped_at": metadata.get("scraped_at"),
            "tmdb_confidence": metadata.get("match_confidence"),
        }

    def list_operation_contexts(self) -> list[dict[str, Any]]:
        return [
            context
            for film in self.list_films()
            if (context := self.get_film_operation_context(film["id"])) is not None
        ]

    def update_film_observation(
        self,
        film_id: str,
        updates: dict[str, Any],
        *,
        structured_metadata: StructuredMetadataObservation | StructuredMetadataObservationDraft | None = None,
        command_id: str | None = None,
        correlation_id: str | None = None,
        event_type: str | None = None,
        event_payload: dict[str, Any] | None = None,
        operation_before_state: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        current = self.get_film_operation_context(film_id)
        if current is None:
            return None
        result = self.upsert_observation(
            {**current, **updates},
            library_item_id=current["library_item_id"],
            structured_metadata=structured_metadata,
            command_id=command_id,
            correlation_id=correlation_id,
            event_type=event_type,
            event_payload=event_payload,
            operation_before_state=operation_before_state,
        )
        return self.get_film(film_id) if result else None

    def operation_snapshot_state(self, film_id: str, operation_kind: str) -> dict[str, Any]:
        with Session(engine) as session:
            return self._snapshot_state(session, "film", film_id, operation_kind)

    def mark_missing_not_seen_since(self, seen_at: str) -> int:
        now = utc_now_iso()
        changed = 0
        with Session(engine) as session:
            items = session.exec(
                select(LibraryItem).where(LibraryItem.availability_status == "available")
            ).all()
            for item in items:
                if item.last_seen_at and item.last_seen_at >= seen_at:
                    continue
                before = {
                    "availability_status": item.availability_status,
                    "missing_since": item.missing_since,
                }
                item.availability_status = "missing"
                item.missing_since = now
                item.updated_at = now
                session.add(item)
                self._set_item_assets_status(session, item.id, "missing", now)
                event = self._append_event(
                    session,
                    "LibraryItemMarkedMissing",
                    "library_item",
                    item.id,
                    {"film_id": item.film_id, "missing_since": now},
                )
                self._add_snapshot(
                    session,
                    event,
                    "library_item",
                    item.id,
                    "availability",
                    before,
                    {"availability_status": "missing", "missing_since": now},
                )
                changed += 1
            session.commit()
        return changed

    def mark_path_missing(self, path: str) -> int:
        normalized = str(Path(path).resolve()).replace("\\", "/")
        now = utc_now_iso()
        changed = 0
        with Session(engine) as session:
            assets = session.exec(
                select(MediaAsset)
                .where(MediaAsset.library_item_id.is_not(None))
                .where(MediaAsset.availability_status == "present")
            ).all()
            item_ids = {
                asset.library_item_id
                for asset in assets
                if asset.library_item_id and str(asset.locator).replace("\\", "/") == normalized
            }
            for item_id in sorted(item_ids):
                item = session.get(LibraryItem, item_id)
                if item is None or item.availability_status == "ignored":
                    continue
                before = {
                    "availability_status": item.availability_status,
                    "missing_since": item.missing_since,
                }
                item.availability_status = "missing"
                item.missing_since = now
                item.updated_at = now
                session.add(item)
                self._set_item_assets_status(session, item.id, "missing", now)
                event = self._append_event(
                    session,
                    "LibraryItemMarkedMissing",
                    "library_item",
                    item.id,
                    {"film_id": item.film_id, "missing_since": now},
                )
                self._add_snapshot(
                    session,
                    event,
                    "library_item",
                    item.id,
                    "availability",
                    before,
                    {"availability_status": "missing", "missing_since": now},
                )
                changed += 1
            session.commit()
        return changed

    def ignore_item(self, library_item_id: str) -> dict[str, Any] | None:
        with Session(engine) as session:
            item = session.get(LibraryItem, library_item_id)
            if item is None or item.availability_status == "retired":
                return None
            before = {"availability_status": item.availability_status}
            item.availability_status = "ignored"
            item.updated_at = utc_now_iso()
            session.add(item)
            event = self._append_event(
                session,
                "LibraryItemIgnored",
                "library_item",
                item.id,
                {"film_id": item.film_id},
            )
            self._add_snapshot(
                session,
                event,
                "library_item",
                item.id,
                "availability",
                before,
                {"availability_status": "ignored"},
            )
            session.commit()
            return self._edition_view(session, item)

    def record_file_organization(
        self,
        film_id: str,
        library_item_id: str,
        manifest_ref: str,
        *,
        command_id: str,
        tmdb_id: int,
        sidecar_count: int,
        scrape_status: str,
    ) -> str:
        with Session(engine) as session:
            item = session.get(LibraryItem, library_item_id)
            if item is None or item.film_id != film_id:
                raise ValueError("Organized LibraryItem does not match the Film")
            event = self._append_event(
                session,
                "RootVideoOrganized",
                "library_item",
                library_item_id,
                {
                    "film_id": film_id,
                    "tmdb_id": tmdb_id,
                    "sidecar_count": sidecar_count,
                    "scrape_status": scrape_status,
                    "manifest_ref": manifest_ref,
                },
                command_id=command_id,
                correlation_id=command_id,
            )
            snapshot = self._add_snapshot(
                session,
                event,
                "library_item",
                library_item_id,
                "file_organization",
                {"manifest_state": "source"},
                {"manifest_state": "target"},
                backup_manifest_ref=manifest_ref,
            )
            session.commit()
            return snapshot.id

    def cleanup_missing(self) -> int:
        now = utc_now_iso()
        with Session(engine) as session:
            items = session.exec(
                select(LibraryItem).where(LibraryItem.availability_status == "missing")
            ).all()
            for item in items:
                self._retire_item(session, item, now)
            if items:
                self._append_event(
                    session,
                    "MissingLibraryItemsRetired",
                    "library",
                    None,
                    {"count": len(items)},
                )
            session.commit()
            return len(items)

    def clear_library(self) -> int:
        now = utc_now_iso()
        with Session(engine) as session:
            items = session.exec(
                select(LibraryItem).where(LibraryItem.availability_status != "retired")
            ).all()
            for item in items:
                self._retire_item(session, item, now)
            self._append_event(session, "LibraryCleared", "library", None, {"count": len(items)})
            session.commit()
            return len(items)

    def clear_all_data(self) -> dict[str, int]:
        with Session(engine) as session:
            counts = {
                "films": len(session.exec(select(Film.id)).all()),
                "library_items": len(session.exec(select(LibraryItem.id)).all()),
                "jobs": len(session.exec(select(Job.id)).all()),
                "events": len(session.exec(select(EventRecord.id)).all()),
            }
            session.exec(delete(OperationSnapshot))
            session.exec(delete(AnalysisResolutionReview))
            session.exec(delete(AssertionEvidence))
            session.exec(delete(AssertionProvenance))
            session.exec(delete(Assertion))
            session.exec(delete(Evidence))
            session.exec(delete(AnalysisRun))
            session.exec(delete(ExternalScoreRefreshState))
            session.exec(delete(FilmExternalScore))
            session.exec(delete(Viewing))
            session.exec(delete(FilmProfileState))
            session.exec(delete(StructuredMetadataReview))
            session.exec(delete(CreditProvenance))
            session.exec(delete(Credit))
            session.exec(delete(FilmCountryProvenance))
            session.exec(delete(FilmCountry))
            session.exec(delete(FilmTitle))
            session.exec(delete(IdentityReview))
            session.exec(delete(MediaAsset))
            session.exec(delete(LibraryItemLocatorHistory))
            session.exec(delete(LibraryItem))
            session.exec(delete(ExternalIdentity))
            session.exec(delete(Person))
            reference_ids = {
                concept.id
                for concept in session.exec(select(Concept).where(Concept.kind == "genre")).all()
            }
            for alias in session.exec(select(ConceptAlias)).all():
                if alias.concept_id not in reference_ids:
                    session.delete(alias)
            removable_entity_ids = [
                concept.id
                for concept in session.exec(select(Concept)).all()
                if concept.id not in reference_ids
            ]
            if removable_entity_ids:
                session.exec(delete(Concept).where(Concept.id.in_(removable_entity_ids)))
            film_ids = list(session.exec(select(Film.id)).all())
            session.exec(delete(Film))
            if [*film_ids, *removable_entity_ids]:
                session.exec(
                    delete(GraphEntity).where(GraphEntity.id.in_([*film_ids, *removable_entity_ids]))
                )
            session.exec(delete(Job))
            session.exec(delete(EventRecord))
            session.commit()
            return counts

    def seed_test_data(self) -> list[dict[str, Any]]:
        try:
            payloads = json.loads(SEED_DATA_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            payloads = []
        self.add_observations(payloads)
        return self.list_films()

    def _film_view(
        self,
        session: Session,
        film_id: str,
        *,
        include_editions: bool,
    ) -> dict[str, Any] | None:
        film = session.get(Film, film_id)
        if film is None or film.lifecycle_status != "active":
            return None
        items = session.exec(
            select(LibraryItem)
            .where(LibraryItem.film_id == film_id)
            .where(LibraryItem.availability_status != "retired")
        ).all()
        if not items or (
            not include_editions
            and all(item.availability_status == "ignored" for item in items)
        ):
            return None
        primary = sorted(items, key=lambda item: self._primary_item_key(session, item))[0]
        identities = {
            identity.provider: identity.external_id
            for identity in session.exec(
                select(ExternalIdentity)
                .where(ExternalIdentity.entity_id == film_id)
                .where(ExternalIdentity.identity_status == "active")
            ).all()
        }
        state = canonical_runtime_writer.derived_profile_state(
            session,
            canonical_runtime_writer.local_profile_id(session),
            film_id,
        )
        latest_run = session.exec(
            select(AnalysisRun)
            .where(AnalysisRun.film_id == film_id)
            .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        ).first()
        genre_names = self._concept_names(session, film_id, "HAS_GENRE", "genre")
        micro_genres = self._concept_names(session, film_id, "HAS_MICRO_GENRE", "micro_genre")
        scores = [self._score_view(score) for score in session.exec(
            select(FilmExternalScore)
            .where(FilmExternalScore.film_id == film_id)
            .order_by(FilmExternalScore.source, FilmExternalScore.kind)
        ).all()]
        result = {
            "id": film.id,
            "title": film.canonical_title,
            "original_title": film.original_title,
            "year": film.release_year,
            "release_date": film.release_date,
            "runtime_minutes": film.runtime_minutes,
            "overview": film.overview,
            "identities": {
                "tmdb": identities.get("tmdb.movie"),
                "imdb": identities.get("imdb.title"),
            },
            "countries": list(structured_metadata_synchronizer.selected_country_codes(session, film_id)),
            "genres": genre_names,
            "directors": self._director_names(session, film_id),
            "micro_genre": micro_genres[0] if micro_genres else None,
            "primary_item": self._edition_view(session, primary),
            "profile_state": state,
            "external_scores": scores,
            "analysis": {
                "status": latest_run.status if latest_run else "pending",
                "latest_run_id": latest_run.id if latest_run else None,
                "summary": latest_run.result_summary if latest_run and latest_run.status == "succeeded" else None,
            },
        }
        if include_editions:
            result["editions"] = [
                self._edition_view(session, item)
                for item in sorted(items, key=lambda item: self._primary_item_key(session, item))
            ]
        return result

    def _edition_view(self, session: Session, item: LibraryItem) -> dict[str, Any]:
        assets = session.exec(
            select(MediaAsset)
            .where(
                (MediaAsset.library_item_id == item.id)
                | (MediaAsset.film_id == item.film_id)
            )
            .where(MediaAsset.availability_status != "retired")
            .order_by(MediaAsset.asset_kind, MediaAsset.id)
        ).all()
        video = next((asset for asset in assets if asset.library_item_id == item.id and asset.asset_kind == "video"), None)
        artwork: dict[str, str | None] = {
            "poster_local": None,
            "backdrop_local": None,
            "poster_thumb_local": None,
            "backdrop_thumb_local": None,
            "poster_provider": None,
            "backdrop_provider": None,
        }
        for asset in assets:
            if asset.asset_kind in {"poster", "backdrop", "poster_thumb", "backdrop_thumb"}:
                suffix = "provider" if asset.film_id else "local"
                key = f"{asset.asset_kind}_{suffix}"
                if key in artwork:
                    artwork[key] = asset.locator
        return {
            "id": item.id,
            "film_id": item.film_id,
            "display_name": item.display_name,
            "source_type": item.source_type,
            "status": item.availability_status,
            "added_at": item.added_at,
            "last_seen_at": item.last_seen_at,
            "missing_since": item.missing_since,
            "metadata": {
                "source": item.metadata_source,
                "updated_at": item.metadata_updated_at,
                "scrape_status": item.scrape_status,
                "scrape_error": item.scrape_error,
                "scraped_at": item.scraped_at,
                "match_confidence": item.match_confidence,
            },
            "artwork": artwork,
            "video": (
                {
                    "locator": video.locator,
                    "file_size": video.file_size,
                    "file_mtime": video.file_mtime,
                    "width": video.width,
                    "height": video.height,
                    "codec": video.codec,
                    "bitrate": video.bitrate,
                    "duration_seconds": video.duration_seconds,
                    "fps": video.fps,
                    "dynamic_range": video.dynamic_range,
                    "bit_depth": video.bit_depth,
                    "audio_tracks": video.stream_metadata,
                }
                if video
                else None
            ),
        }

    def _primary_item_key(self, session: Session, item: LibraryItem) -> tuple[Any, ...]:
        rank = {"available": 0, "missing": 1, "ignored": 2}.get(item.availability_status, 3)
        has_video = session.exec(
            select(MediaAsset.id)
            .where(MediaAsset.library_item_id == item.id)
            .where(MediaAsset.asset_kind == "video")
            .where(MediaAsset.availability_status == "present")
        ).first() is not None
        return (rank, 0 if has_video else 1, self._descending_time(item.last_seen_at), item.id)

    @staticmethod
    def _descending_time(value: str | None) -> float:
        if not value:
            return float("inf")
        try:
            return -datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return float("inf")

    @staticmethod
    def _score_view(score: FilmExternalScore) -> dict[str, Any]:
        return {
            "source": score.source,
            "label": score.label,
            "kind": score.kind,
            "value": score.value,
            "scale": score.scale,
            "rank": score.rank,
            "previous_rank": score.previous_rank,
            "votes": score.votes,
            "list_name": score.list_name or None,
            "edition": score.edition or None,
            "url": score.source_uri,
            "fetched_at": score.fetched_at,
            "expires_at": score.expires_at,
            "matched_by": score.matched_by,
            "confidence": score.confidence,
        }

    @staticmethod
    def _concept_names(session: Session, film_id: str, predicate: str, kind: str) -> list[str]:
        assertions = session.exec(
            select(Assertion)
            .where(Assertion.subject_entity_id == film_id)
            .where(Assertion.predicate == predicate)
            .where(Assertion.review_status != "rejected")
            .where(Assertion.superseded_at.is_(None))
        ).all()
        names = []
        for assertion in assertions:
            concept = session.get(Concept, assertion.object_entity_id)
            if concept is not None and concept.kind == kind and concept.lifecycle_status == "active":
                names.append(concept.canonical_name)
        return sorted(set(names), key=str.casefold)

    @staticmethod
    def _director_names(session: Session, film_id: str) -> list[str]:
        names: list[tuple[int, str]] = []
        credits = session.exec(
            select(Credit)
            .where(Credit.film_id == film_id)
            .where(Credit.department == "Directing")
            .where(Credit.job == "Director")
        ).all()
        for credit in credits:
            active = session.exec(
                select(CreditProvenance.id)
                .where(CreditProvenance.credit_id == credit.id)
                .where(CreditProvenance.superseded_at.is_(None))
            ).first()
            person = session.get(Person, credit.person_id)
            if active and person:
                names.append((credit.billing_order or 0, person.canonical_name))
        return [name for _order, name in sorted(set(names))]

    def _queue_relink_job(
        self,
        session: Session,
        observation_payload: dict[str, Any],
        ambiguity: AmbiguousRelink,
    ) -> str:
        digest = hashlib.sha256(ambiguity.observation.content_fingerprint.encode("utf-8")).hexdigest()
        dedupe_key = f"library.resolve_relink:{SOURCE_INSTANCE_ID}:{digest}"
        source_item_id = self._hash_identifier(
            canonical_runtime_writer.source_item_key(observation_payload)
        )
        pending_item = {
            "source_item_id": source_item_id,
            "candidate_count": len(ambiguity.library_item_ids),
            "observation_ref": private_payload_store.put(
                "relink_observation",
                {
                    "observation": json.loads(json.dumps(observation_payload, default=str)),
                    "candidate_item_ids": ambiguity.library_item_ids,
                },
            ),
        }
        existing = session.exec(
            select(Job)
            .where(Job.dedupe_key == dedupe_key)
            .where(Job.status.in_(("queued", "running", "cancelling")))
        ).first()
        if existing:
            current = dict(existing.payload or {})
            items = list(current.get("items") or [])
            if not any(item.get("source_item_id") == source_item_id for item in items):
                items.append(pending_item)
                existing.payload = {**current, "items": items}
                existing.updated_at = utc_now_iso()
                session.add(existing)
            session.flush()
            return existing.id
        job = Job(
            id=f"job_{uuid4().hex}",
            type="library.resolve_relink",
            payload={
                "source_instance_id": SOURCE_INSTANCE_ID,
                "content_fingerprint": ambiguity.observation.content_fingerprint,
                "fingerprint_id": digest[:16],
                "items": [pending_item],
            },
            dedupe_key=dedupe_key,
            max_attempts=1,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        session.add(job)
        session.flush()
        return job.id

    @staticmethod
    def _item(session: Session, item_id: str) -> LibraryItem:
        item = session.get(LibraryItem, item_id)
        if item is None:
            raise RuntimeError("Canonical writer returned a missing LibraryItem")
        return item

    @staticmethod
    def _set_item_assets_status(session: Session, item_id: str, status: str, now: str) -> None:
        assets = session.exec(select(MediaAsset).where(MediaAsset.library_item_id == item_id)).all()
        for asset in assets:
            asset.availability_status = status
            asset.missing_since = now if status == "missing" else None
            asset.updated_at = now
            session.add(asset)

    def _retire_item(self, session: Session, item: LibraryItem, now: str) -> None:
        item.availability_status = "retired"
        item.retired_at = now
        item.updated_at = now
        session.add(item)
        self._set_item_assets_status(session, item.id, "retired", now)
        histories = session.exec(
            select(LibraryItemLocatorHistory)
            .where(LibraryItemLocatorHistory.library_item_id == item.id)
            .where(LibraryItemLocatorHistory.observed_to.is_(None))
        ).all()
        for history in histories:
            history.observed_to = now
            session.add(history)

    def _append_item_event(
        self,
        session: Session,
        event_type: str,
        resolution: RuntimeLibraryResolution,
        payload: dict[str, Any],
        *,
        command_id: str | None = None,
        correlation_id: str | None = None,
    ) -> EventRecord:
        return self._append_event(
            session,
            event_type,
            "library_item",
            resolution.library_item_id,
            {"film_id": resolution.film_id, **payload},
            command_id=command_id,
            correlation_id=correlation_id,
        )

    @staticmethod
    def _append_event(
        session: Session,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str | None,
        payload: dict[str, Any],
        *,
        command_id: str | None = None,
        correlation_id: str | None = None,
    ) -> EventRecord:
        event = EventRecord(
            type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            command_id=command_id,
            correlation_id=correlation_id,
        )
        session.add(event)
        session.flush()
        return event

    @staticmethod
    def _snapshot_state(
        session: Session,
        aggregate_type: str,
        aggregate_id: str,
        operation_kind: str,
    ) -> dict[str, Any]:
        if aggregate_type == "library_item" and operation_kind == "availability":
            item = session.get(LibraryItem, aggregate_id)
            if item is None:
                raise RuntimeError("LibraryItem snapshot target is missing")
            return {
                "availability_status": item.availability_status,
                "missing_since": item.missing_since,
            }
        if aggregate_type != "film":
            raise RuntimeError("Unsupported operation snapshot aggregate")
        film = session.get(Film, aggregate_id)
        if film is None:
            raise RuntimeError("Film snapshot target is missing")
        if operation_kind == "metadata":
            items = session.exec(
                select(LibraryItem)
                .where(LibraryItem.film_id == aggregate_id)
                .where(LibraryItem.availability_status != "retired")
            ).all()
            return {
                "film": {
                    "canonical_title": film.canonical_title,
                    "original_title": film.original_title,
                    "release_date": film.release_date,
                    "release_year": film.release_year,
                    "runtime_minutes": film.runtime_minutes,
                    "overview": film.overview,
                },
                "library_items": [
                    {
                        "id": item.id,
                        "metadata_source": item.metadata_source,
                        "metadata_updated_at": item.metadata_updated_at,
                        "scrape_status": item.scrape_status,
                        "scrape_error": item.scrape_error,
                        "scraped_at": item.scraped_at,
                        "match_confidence": item.match_confidence,
                    }
                    for item in sorted(items, key=lambda value: value.id)
                ],
            }
        if operation_kind == "artwork":
            item_ids = session.exec(
                select(LibraryItem.id).where(LibraryItem.film_id == aggregate_id)
            ).all()
            assets = session.exec(
                select(MediaAsset).where(
                    (MediaAsset.film_id == aggregate_id)
                    | (MediaAsset.library_item_id.in_(sorted(item_ids)))
                )
            ).all()
            return {
                "assets": [
                    {"id": asset.id, "availability_status": asset.availability_status}
                    for asset in sorted(assets, key=lambda value: value.id)
                    if asset.asset_kind in {"poster", "backdrop", "poster_thumb", "backdrop_thumb"}
                ]
            }
        raise RuntimeError("Unsupported operation snapshot kind")

    @staticmethod
    def _add_snapshot(
        session: Session,
        event: EventRecord,
        aggregate_type: str,
        aggregate_id: str,
        operation_kind: str,
        before: dict[str, Any],
        after: dict[str, Any],
        *,
        backup_manifest_ref: str | None = None,
    ) -> OperationSnapshot:
        optimistic_hash = hashlib.sha256(
            json.dumps(after, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        snapshot = OperationSnapshot(
            event_id=event.id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            operation_kind=operation_kind,
            before_state=before,
            after_state=after,
            optimistic_hash=optimistic_hash,
            backup_manifest_ref=backup_manifest_ref,
        )
        session.add(snapshot)
        return snapshot

    @staticmethod
    def _hash_identifier(value: str | None) -> str | None:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16] if value else None


library_manager = LibraryManager()
