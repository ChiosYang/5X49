import hashlib
import json
from pathlib import Path

from sqlmodel import Session, select

from app.canonical_models import (
    Film,
    LibraryItem,
    MediaAsset,
    OperationSnapshot,
    canonical_utc_now_iso,
)
from app.database import engine
from app.services.event_store import event_store
from app.services.operation_manifests import OperationManifestError, operation_manifest_store


class OperationConflict(RuntimeError):
    pass


class OperationSnapshotService:
    ITEM_FIELDS = frozenset({"availability_status", "missing_since", "retired_at"})
    FILM_METADATA_FIELDS = frozenset(
        {
            "canonical_title",
            "original_title",
            "release_date",
            "release_year",
            "runtime_minutes",
            "overview",
        }
    )
    ITEM_METADATA_FIELDS = frozenset(
        {
            "metadata_source",
            "metadata_updated_at",
            "scrape_status",
            "scrape_error",
            "scraped_at",
            "match_confidence",
        }
    )

    def preview(self, snapshot_id: str) -> dict | None:
        with Session(engine) as session:
            snapshot = session.get(OperationSnapshot, snapshot_id)
            if snapshot is None:
                return None
            current = self._current_state(session, snapshot)
            current_hash = self._state_hash(current)
            is_current = current_hash == snapshot.optimistic_hash
            return {
                "snapshot_id": snapshot.id,
                "aggregate_type": snapshot.aggregate_type,
                "aggregate_id": snapshot.aggregate_id,
                "operation_kind": snapshot.operation_kind,
                "status": snapshot.status,
                "before": snapshot.before_state,
                "after": snapshot.after_state,
                "current_matches_after": is_current,
                "confirmation_token": self._confirmation_token(snapshot, current_hash)
                if snapshot.status == "available" and is_current
                else None,
            }

    def restore(self, snapshot_id: str, confirmation_token: str) -> dict:
        with Session(engine) as session:
            snapshot = session.get(OperationSnapshot, snapshot_id)
            if snapshot is None:
                raise LookupError("Operation snapshot not found")
            if snapshot.status != "available":
                raise OperationConflict("Operation snapshot is no longer restorable")
            current = self._current_state(session, snapshot)
            current_hash = self._state_hash(current)
            if current_hash != snapshot.optimistic_hash:
                raise OperationConflict("Current state has changed since this operation")
            if confirmation_token != self._confirmation_token(snapshot, current_hash):
                raise OperationConflict("Confirmation token is missing or stale")
            self._apply_before_state(session, snapshot)
            event_store.append_in_session(
                session,
                "OperationRestored",
                snapshot.aggregate_type,
                snapshot.aggregate_id,
                {
                    "snapshot_id": snapshot.id,
                    "operation_kind": snapshot.operation_kind,
                },
                actor_type="user",
                causation_id=snapshot.event_id,
            )
            snapshot.status = "restored"
            snapshot.restored_at = canonical_utc_now_iso()
            session.add(snapshot)
            session.commit()
            return {
                "status": "restored",
                "snapshot_id": snapshot.id,
                "aggregate_type": snapshot.aggregate_type,
                "aggregate_id": snapshot.aggregate_id,
            }

    def _current_state(self, session: Session, snapshot: OperationSnapshot) -> dict:
        if snapshot.aggregate_type == "library_item":
            if snapshot.operation_kind == "file_organization":
                if not snapshot.backup_manifest_ref:
                    return {"manifest_state": "invalid"}
                try:
                    state = operation_manifest_store.state(snapshot.backup_manifest_ref)
                except OperationManifestError:
                    state = "invalid"
                return {"manifest_state": state}
            item = session.get(LibraryItem, snapshot.aggregate_id)
            if item is None:
                return {}
            return {
                field: getattr(item, field)
                for field in snapshot.after_state
                if field in self.ITEM_FIELDS
            }
        if snapshot.aggregate_type == "film" and snapshot.operation_kind == "metadata":
            film = session.get(Film, snapshot.aggregate_id)
            if film is None:
                return {}
            item_ids = [item["id"] for item in snapshot.after_state.get("library_items", [])]
            items = [session.get(LibraryItem, item_id) for item_id in item_ids]
            return {
                "film": {
                    field: getattr(film, field)
                    for field in snapshot.after_state.get("film", {})
                    if field in self.FILM_METADATA_FIELDS
                },
                "library_items": [
                    {
                        "id": item.id,
                        **{
                            field: getattr(item, field)
                            for field in snapshot.after_state.get("library_items", [])[index]
                            if field in self.ITEM_METADATA_FIELDS
                        },
                    }
                    for index, item in enumerate(items)
                    if item is not None
                ],
            }
        if snapshot.aggregate_type == "film" and snapshot.operation_kind == "artwork":
            asset_ids = [item["id"] for item in snapshot.after_state.get("assets", [])]
            assets = [session.get(MediaAsset, asset_id) for asset_id in asset_ids]
            return {
                "assets": [
                    {"id": asset.id, "availability_status": asset.availability_status}
                    for asset in assets
                    if asset is not None
                ]
            }
        return {}

    def _apply_before_state(self, session: Session, snapshot: OperationSnapshot) -> None:
        now = canonical_utc_now_iso()
        if snapshot.aggregate_type == "library_item":
            item = session.get(LibraryItem, snapshot.aggregate_id)
            if item is None:
                raise OperationConflict("Library item no longer exists")
            if snapshot.operation_kind == "file_organization":
                if not snapshot.backup_manifest_ref:
                    raise OperationConflict("File operation manifest is unavailable")
                try:
                    manifest = operation_manifest_store.load(snapshot.backup_manifest_ref)
                    operation_manifest_store.restore(snapshot.backup_manifest_ref)
                except OperationManifestError as exc:
                    raise OperationConflict(str(exc)) from exc
                source = str(Path(manifest["source"]).resolve())
                target = str(Path(manifest["target"]).resolve())
                assets = session.exec(
                    select(MediaAsset)
                    .where(MediaAsset.library_item_id == item.id)
                    .where(MediaAsset.asset_kind == "video")
                ).all()
                for asset in assets:
                    if str(Path(asset.locator).resolve()) == target:
                        asset.locator = source
                        asset.normalized_locator_hash = hashlib.sha256(
                            source.replace("\\", "/").encode("utf-8")
                        ).hexdigest()
                        asset.availability_status = "present"
                        asset.updated_at = now
                        session.add(asset)
                item.source_item_key = source.replace("\\", "/")
                item.display_name = Path(source).name
                item.updated_at = now
                session.add(item)
                return
            for field, value in snapshot.before_state.items():
                if field in self.ITEM_FIELDS:
                    setattr(item, field, value)
            item.updated_at = now
            session.add(item)
            return
        if snapshot.aggregate_type != "film":
            raise OperationConflict("This operation kind is not restorable")
        film = session.get(Film, snapshot.aggregate_id)
        if film is None:
            raise OperationConflict("Film no longer exists")
        if snapshot.operation_kind == "metadata":
            for field, value in snapshot.before_state.get("film", {}).items():
                if field in self.FILM_METADATA_FIELDS:
                    setattr(film, field, value)
            film.updated_at = now
            session.add(film)
            for state in snapshot.before_state.get("library_items", []):
                item = session.get(LibraryItem, state.get("id"))
                if item is None or item.film_id != film.id:
                    raise OperationConflict("Metadata snapshot LibraryItem no longer exists")
                for field, value in state.items():
                    if field in self.ITEM_METADATA_FIELDS:
                        setattr(item, field, value)
                item.updated_at = now
                session.add(item)
            return
        if snapshot.operation_kind == "artwork":
            desired = {
                state["id"]: state["availability_status"]
                for state in snapshot.before_state.get("assets", [])
            }
            current_ids = {
                state["id"] for state in snapshot.after_state.get("assets", [])
            }
            for asset_id in sorted(current_ids | set(desired)):
                asset = session.get(MediaAsset, asset_id)
                if asset is None:
                    raise OperationConflict("Artwork asset no longer exists")
                asset.availability_status = desired.get(asset_id, "retired")
                asset.updated_at = now
                session.add(asset)
            return
        raise OperationConflict("This operation kind is not restorable")

    @staticmethod
    def _state_hash(value: dict) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _confirmation_token(snapshot: OperationSnapshot, current_hash: str) -> str:
        return hashlib.sha256(
            f"{snapshot.id}:{snapshot.event_id}:{snapshot.optimistic_hash}:{current_hash}".encode("utf-8")
        ).hexdigest()


operation_snapshot_service = OperationSnapshotService()


__all__ = ["OperationConflict", "OperationSnapshotService", "operation_snapshot_service"]
