import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session, create_engine, select

import app.database as database
import app.services.event_store as event_store_module
import app.services.library as library_module
import app.services.operation_snapshots as snapshots_module
import app.services.user_state as user_state_module
from app.canonical_models import FilmProfileState, LibraryItem, MediaAsset, OperationSnapshot
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.models import EventRecord
from app.services.library import library_manager
from app.services.operation_snapshots import OperationConflict, operation_snapshot_service
from app.services.operation_manifests import OperationManifestStore
from app.services.user_state import film_profile_state_manager


class CanonicalCommandEventTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.path = self.root / "library.db"
        self.engine = create_engine(f"sqlite:///{self.path}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, self.path, app_version="test", backup_required=False)
        self.modules = (
            database,
            event_store_module,
            library_module,
            snapshots_module,
            user_state_module,
        )
        self.original = {module: module.engine for module in self.modules}
        for module in self.modules:
            module.engine = self.engine
        media = self.root / "event.mkv"
        media.write_bytes(b"event")
        self.media = media
        library_manager.add_observations([{
            "title": "Event Film",
            "year": 2026,
            "media_path": str(media.resolve()),
            "video_file": media.name,
            "folder_path": str(self.root.resolve()),
            "folder_name": self.root.name,
            "file_size": media.stat().st_size,
            "file_mtime": media.stat().st_mtime,
            "library_status": "available",
            "metadata_source": "filename",
            "scrape_status": "pending",
        }])
        film = library_manager.list_films()[0]
        self.film_id = film["id"]
        self.item_id = film["primary_item"]["id"]

    def tearDown(self):
        for module, engine in self.original.items():
            module.engine = engine
        self.engine.dispose()
        self._tmp.cleanup()

    def test_profile_state_and_event_commit_atomically(self):
        with patch.object(event_store_module.event_store, "append_in_session", side_effect=RuntimeError("event failed")):
            with self.assertRaises(RuntimeError):
                film_profile_state_manager.upsert(self.film_id, favorite=True, fields_set={"favorite"})
        with Session(self.engine) as session:
            state = session.exec(select(FilmProfileState).where(FilmProfileState.film_id == self.film_id)).first()
            self.assertTrue(state is None or not state.favorite)
            self.assertEqual(
                session.exec(select(EventRecord).where(EventRecord.type == "FilmProfileStateUpdated")).all(),
                [],
            )

    def test_ignore_creates_bounded_event_and_snapshot_in_one_commit(self):
        library_manager.ignore_item(self.item_id)
        with Session(self.engine) as session:
            event = session.exec(select(EventRecord).where(EventRecord.type == "LibraryItemIgnored")).one()
            snapshot = session.exec(select(OperationSnapshot).where(OperationSnapshot.event_id == event.id)).one()
        self.assertEqual(event.aggregate_type, "library_item")
        self.assertEqual(event.aggregate_id, self.item_id)
        self.assertEqual(event.payload, {"film_id": self.film_id})
        self.assertEqual(snapshot.before_state, {"availability_status": "available"})
        self.assertEqual(snapshot.after_state, {"availability_status": "ignored"})

    def test_snapshot_restore_rejects_state_drift_and_is_single_use(self):
        library_manager.ignore_item(self.item_id)
        with Session(self.engine) as session:
            snapshot = session.exec(select(OperationSnapshot)).one()
            snapshot_id = snapshot.id
            item = session.get(LibraryItem, self.item_id)
            item.availability_status = "missing"
            session.add(item)
            session.commit()
        preview = operation_snapshot_service.preview(snapshot_id)
        self.assertFalse(preview["current_matches_after"])
        with self.assertRaises(OperationConflict):
            operation_snapshot_service.restore(snapshot_id, "stale")

    def test_file_organization_restore_uses_only_a_controlled_manifest_reference(self):
        store = OperationManifestStore(self.root / "manifests")
        manifest_ref = store.create(self.root, self.media)
        target_dir = self.root / "Event Film (2026)"
        target_dir.mkdir()
        target = target_dir / self.media.name
        self.media.replace(target)
        store.finalize(manifest_ref, target=target, sidecars=[])
        with Session(self.engine) as session:
            item = session.get(LibraryItem, self.item_id)
            item.source_item_key = str(target).replace("\\", "/")
            session.add(item)
            asset = session.exec(
                select(MediaAsset)
                .where(MediaAsset.library_item_id == self.item_id)
                .where(MediaAsset.asset_kind == "video")
            ).one()
            asset.locator = str(target.resolve())
            session.add(asset)
            session.commit()

        snapshot_id = library_manager.record_file_organization(
            self.film_id,
            self.item_id,
            manifest_ref,
            command_id="job_fixture",
            tmdb_id=42,
            sidecar_count=0,
            scrape_status="success",
        )
        with patch.object(snapshots_module, "operation_manifest_store", store):
            preview = operation_snapshot_service.preview(snapshot_id)
            self.assertTrue(preview["current_matches_after"])
            operation_snapshot_service.restore(snapshot_id, preview["confirmation_token"])

        self.assertTrue(self.media.is_file())
        self.assertFalse(target.exists())
        with Session(self.engine) as session:
            event = session.exec(
                select(EventRecord).where(EventRecord.type == "RootVideoOrganized")
            ).one()
            asset = session.exec(
                select(MediaAsset)
                .where(MediaAsset.library_item_id == self.item_id)
                .where(MediaAsset.asset_kind == "video")
            ).one()
        self.assertEqual(event.aggregate_type, "library_item")
        self.assertNotIn(str(self.root.resolve()), str(event.payload))
        self.assertEqual(Path(asset.locator).resolve(), self.media.resolve())


if __name__ == "__main__":
    unittest.main()
