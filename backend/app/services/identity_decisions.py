"""Conservative user decisions: no Film merges, provider changes or media writes."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote
from uuid import uuid4

from sqlalchemy import text
from sqlmodel import Session, select

from app.contracts.structured_metadata import canonical_json_hash
from app.models import FilmProfileState, IdentityReview, LibraryItem, LibraryItemLocatorHistory, MediaAsset, OperationSnapshot, utc_now_iso
from app.services.event_store import event_store
from app.services.file_identity import full_content_hash, observe_file
from app.services.identity_review import identity_review_reader


class IdentityDecisionError(ValueError):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code = code
        self.status = status


def _safe_path(locator: str, root: Path) -> Path:
    try:
        path = Path(locator).resolve()
        if not path.is_relative_to(root) or path == root:
            raise IdentityDecisionError("unsafe_locator")
        return path
    except (OSError, ValueError) as exc:
        raise IdentityDecisionError("unsafe_locator") from exc


def _validate_asset_locator(asset: MediaAsset, root: Path) -> None:
    # Scanner artwork is an application URL, despite the historical local_path
    # locator kind. Copy the reference; never interpret it as an OS absolute path.
    if asset.asset_kind in {"poster", "backdrop", "poster_thumb", "backdrop_thumb"}:
        locator = unquote(asset.locator).replace("\\", "/")
        if locator.startswith("/media/"):
            _safe_path(str(root / locator.removeprefix("/media/")), root)
            return
        if locator.startswith("/artwork-cache/"):
            name = locator.removeprefix("/artwork-cache/")
            if name and name not in {".", ".."} and "/" not in name and ":" not in name:
                return
            raise IdentityDecisionError("unsafe_locator")
    _safe_path(asset.locator, root)


class IdentityDecisionService:
    def preview(self, session: Session, review_id: str, action: str,
                target_item_id: str | None, media_root: str) -> dict:
        detail = identity_review_reader.detail(session, review_id)
        if detail is None:
            raise IdentityDecisionError("review_not_found", 404)
        if action not in detail["actions"]:
            raise IdentityDecisionError(detail["blocked_code"] or "action_unavailable")
        if (action == "reconnect") != (target_item_id is not None):
            raise IdentityDecisionError("invalid_target", 422)
        source = session.get(LibraryItem, detail["library_item"]["id"])
        root = Path(media_root).resolve()
        source_assets = self._assets(session, source.id)
        videos = [a for a in source_assets if a.asset_kind == "video"]
        if len(videos) != 1 or (action == "reconnect" and any(a.asset_kind == "video_part" for a in source_assets)):
            raise IdentityDecisionError("unsupported_edition")
        # All locators copied by reconnection must remain within the current root.
        if action == "reconnect":
            for asset in source_assets:
                _validate_asset_locator(asset, root)
        video = videos[0]
        path = _safe_path(video.locator, root)
        try:
            observed = observe_file(path)
            if observed is None:
                raise IdentityDecisionError("source_file_missing")
            if not video.content_fingerprint or observed.content_fingerprint != video.content_fingerprint:
                raise IdentityDecisionError("source_file_changed")
            current_hash = observed.content_hash or full_content_hash(path)
            if video.content_hash and current_hash != video.content_hash:
                raise IdentityDecisionError("source_file_changed")
            stat = path.stat()
            file_state = [observed.platform_file_id, current_hash, stat.st_size, stat.st_mtime_ns]
        except OSError as exc:
            raise IdentityDecisionError("source_file_unreadable") from exc
        target = None
        if action == "reconnect":
            candidate = next((c for c in detail["candidates"] if c["library_item_id"] == target_item_id), None)
            if not candidate or not candidate["library_item"] or candidate["evidence_status"] != "current":
                raise IdentityDecisionError("invalid_target")
            target = session.get(LibraryItem, target_item_id)
            if target.id == source.id or target.film_id != source.film_id or target.profile_id != source.profile_id:
                raise IdentityDecisionError("cross_film_reconnect")
            if target.availability_status not in {"available", "missing"}:
                raise IdentityDecisionError("target_unavailable")
            target_assets = self._assets(session, target.id)
            target_videos = [a for a in target_assets if a.asset_kind == "video"]
            if len(target_videos) != 1 or any(a.asset_kind == "video_part" for a in target_assets):
                raise IdentityDecisionError("unsupported_edition")
            target_path = _safe_path(target_videos[0].locator, root)
            try:
                target_path.stat()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise IdentityDecisionError("target_file_unreadable") from exc
            else:
                raise IdentityDecisionError("target_file_exists")
            if not video.content_hash or target_videos[0].content_hash != current_hash:
                raise IdentityDecisionError("full_hash_required")
        effects = {"film_id": source.film_id, "source_item_id": source.id,
                   "target_item_id": target.id if target else None,
                   "source_after": "retired" if target else source.availability_status,
                   "target_after": "available" if target else None,
                   "personal_data_unchanged": True, "files_unchanged": True,
                   "expiring_snapshot_ids": [s.id for s in self._edition_snapshots(session, source.id, target.id)] if target else []}
        token = canonical_json_hash({"revision": detail["revision"], "action": action,
            "effects": effects, "file_state": file_state, "media_root": str(root)})
        return {"review_id": review_id, "action": action, "effects": effects,
                "confirmation_token": token}

    def confirm(self, engine, review_id: str, *, action: str, target_item_id: str | None,
                confirmation_token: str, idempotency_key: str, media_root: str) -> dict:
        request_hash = canonical_json_hash({"action": action, "target_item_id": target_item_id,
                                            "confirmation_token": confirmation_token})
        with Session(engine) as session:
            # Serialize check-and-write with scans and competing confirmations.
            session.execute(text("BEGIN IMMEDIATE"))
            review = session.get(IdentityReview, review_id)
            if review is None:
                raise IdentityDecisionError("review_not_found", 404)
            if review.decision:
                if review.decision.get("idempotency_key") == idempotency_key:
                    if review.decision.get("request_hash") != request_hash:
                        raise IdentityDecisionError("idempotency_conflict")
                    return review.decision["result"]
                raise IdentityDecisionError("already_decided")
            preview = self.preview(session, review_id, action, target_item_id, media_root)
            if preview["confirmation_token"] != confirmation_token:
                raise IdentityDecisionError("stale_review")
            source = session.get(LibraryItem, review.library_item_id)
            now = utc_now_iso()
            if action == "reconnect":
                self._reconnect(session, source, session.get(LibraryItem, target_item_id), now)
            else:
                source.resolution_status = "matched" if preview["effects"]["film_id"] and (
                    identity_review_reader._film(session, source.film_id)["identities"]) else "unresolved"
                source.updated_at = now
                session.add(source)
            review.status = "resolved" if action == "reconnect" else "dismissed"
            review.updated_at = review.resolved_at = now
            event = event_store.append_in_session(session, "IdentityReviewDecided", "film", source.film_id,
                {"review_id": review.id, "action": action, "source_item_id": source.id,
                 "target_item_id": target_item_id}, actor_type="user", command_id=idempotency_key)
            result = {"review_id": review.id, "status": review.status, "action": action,
                      "film_id": source.film_id, "library_item_id": target_item_id or source.id, "event_id": event.id}
            review.decision = {"idempotency_key": idempotency_key, "request_hash": request_hash, "result": result}
            session.add(review)
            session.commit()
            return result

    @staticmethod
    def _assets(session: Session, item_id: str) -> list[MediaAsset]:
        return list(session.exec(select(MediaAsset).where(MediaAsset.library_item_id == item_id)
            .where(MediaAsset.availability_status != "retired")).all())

    def _reconnect(self, session: Session, source: LibraryItem, target: LibraryItem, now: str) -> None:
        # Old undo actions refer to the previous locator ownership. Keep their
        # complete history, but never allow them to move the reconnected file.
        for snapshot in self._edition_snapshots(session, source.id, target.id):
            snapshot.status = "expired"
            session.add(snapshot)
        source_assets = self._assets(session, source.id)
        source.availability_status = "retired"
        source.resolution_status = "matched"
        source.retired_at = source.updated_at = now
        session.add(source)
        # Release the active-source unique key before assigning it to the old ID.
        session.flush()
        for asset in self._assets(session, target.id):
            asset.availability_status = "retired"
            asset.updated_at = now
            session.add(asset)
        for asset in source_assets:
            copied = session.exec(select(MediaAsset).where(MediaAsset.library_item_id == target.id)
                .where(MediaAsset.asset_kind == asset.asset_kind)
                .where(MediaAsset.normalized_locator_hash == asset.normalized_locator_hash)).first()
            values = {**asset.model_dump(exclude={"id", "created_at"}), "library_item_id": target.id,
                      "availability_status": "present", "missing_since": None, "updated_at": now}
            if copied is None:
                copied = MediaAsset(id=f"asset_{uuid4().hex}", created_at=now, **values)
            else:
                for field, value in values.items():
                    setattr(copied, field, value)
            session.add(copied)
            asset.availability_status = "retired"
            asset.updated_at = now
            session.add(asset)
        histories = session.exec(select(LibraryItemLocatorHistory)
            .where(LibraryItemLocatorHistory.library_item_id.in_([source.id, target.id]))).all()
        target_history = None
        for history in histories:
            if history.library_item_id == target.id and history.source_item_key == source.source_item_key:
                target_history = history
            if history.observed_to is None:
                history.observed_to = now
                session.add(history)
        if target_history is None:
            target_history = LibraryItemLocatorHistory(id=f"locator_{uuid4().hex}", library_item_id=target.id,
                source_instance_id=target.source_instance_id, source_item_key=source.source_item_key,
                observed_from=now, reason="manual_reconnect")
        target_history.observed_to = None
        target_history.reason = "manual_reconnect"
        session.add(target_history)
        target.source_item_key = source.source_item_key
        target.availability_status = "available"
        target.resolution_status = "matched"
        target.missing_since = target.retired_at = None
        target.last_seen_at = source.last_seen_at
        target.updated_at = now
        session.add(target)
        for state in session.exec(select(FilmProfileState).where(FilmProfileState.film_id == source.film_id)
                                   .where(FilmProfileState.primary_item_id == source.id)).all():
            state.primary_item_id = target.id
            session.add(state)

    @staticmethod
    def _edition_snapshots(session: Session, source_id: str, target_id: str) -> list[OperationSnapshot]:
        return list(session.exec(select(OperationSnapshot)
            .where(OperationSnapshot.aggregate_type == "library_item")
            .where(OperationSnapshot.aggregate_id.in_([source_id, target_id]))
            .where(OperationSnapshot.status == "available").order_by(OperationSnapshot.id)).all())


identity_decision_service = IdentityDecisionService()
