import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlmodel import Session, create_engine, select

from app import database
from app.api import identity_review as api_module
from app.database import configure_sqlite_engine
from app.main import app
from app.migrations.runner import run_migrations
from app.migrations.versions import MIGRATIONS
from app.models import EventRecord, FilmProfileState, IdentityReview, LibraryItem, MediaAsset, Viewing
from app.services import library as library_module
from app.services.canonical_runtime import canonical_runtime_writer
from app.services.identity_review import REASONS, identity_review_reader
from app.services.library import library_manager
from app.services.identity_decisions import identity_decision_service, IdentityDecisionError
from app.services.identity_review import seal_source_evidence
from app.services.library_sync import library_sync_service
from app.services import operation_snapshots as snapshots_module
from app.services.operation_snapshots import OperationConflict, operation_snapshot_service
from types import SimpleNamespace


class IdentityReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        roots_patch = patch("app.services.settings.get_media_dirs", return_value=[str(self.root)])
        roots_patch.start()
        self.addCleanup(roots_patch.stop)
        self.path = self.root / "synthetic.db"
        self.engine = create_engine(f"sqlite:///{self.path}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, self.path, backup_required=False)
        self.patches = [patch.object(module, "engine", self.engine) for module in (database, library_module, api_module, snapshots_module)]
        self.patches.append(patch.object(api_module, "get_media_dirs", return_value=[str(self.root)]))
        for item in self.patches:
            item.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        for item in self.patches:
            item.stop()
        self.engine.dispose()
        self.temp.cleanup()

    def observation(self, name, content=b"synthetic video", **identities):
        path = self.root / name
        path.write_bytes(content)
        return {"title": name, "folder_name": name, "media_path": str(path), **identities}

    def duplicate(self):
        library_manager.add_observations([self.observation("original.mkv")])
        library_manager.add_observations([self.observation("copy.mkv")])
        with Session(self.engine) as session:
            return session.exec(select(IdentityReview)).one().id

    def dump(self):
        with self.engine.connect() as connection:
            return "\n".join(connection.connection.driver_connection.iterdump())

    def test_candidate_preview_is_read_only_and_preserves_personal_data(self):
        review_id = self.duplicate()
        with Session(self.engine) as session:
            review = session.get(IdentityReview, review_id)
            candidate_id = review.candidate_snapshot["candidates"][0]["film_id"]
            canonical_runtime_writer.sync_user_state(session, candidate_id, rating=4, notes="Private notes",
                favorite=True, watched=True, fields_set={"rating", "notes", "favorite", "watched"})
            session.commit()
        before = self.dump()
        page = self.client.get("/library/identity-reviews").json()
        self.assertEqual(page["total"], 1)
        for _ in range(2):
            response = self.client.get(f"/library/identity-reviews/{review_id}")
            self.assertEqual(response.status_code, 200)
            detail = response.json()
            self.assertEqual(detail["actions"], ["keep_separate"])
            self.assertEqual(detail["reason_code"], "relink_live_copy_conflict")
            candidate = detail["candidates"][0]
            self.assertEqual(candidate["evidence_status"], "current")
            self.assertEqual(candidate["film"]["personal_data"], {
                "viewings": 1, "has_rating": True, "has_notes": True, "favorite": True})
            for private in (str(self.root), "Private notes", "source_item_key", "content_fingerprint", "source_ref"):
                self.assertNotIn(private, response.text)
        self.assertEqual(before, self.dump())

    def test_identity_conflict_retains_both_provider_candidates(self):
        library_manager.add_observations([
            self.observation("tmdb.mkv", b"one", tmdb_id="10"),
            self.observation("imdb.mkv", b"two", imdb_id="tt20"),
            self.observation("conflict.mkv", b"three", tmdb_id="10", imdb_id="tt20"),
        ])
        with Session(self.engine) as session:
            review = session.exec(select(IdentityReview)).one()
            detail = identity_review_reader.detail(session, review.id)
            self.assertEqual(review.reason_code, "identity_conflict")
            self.assertEqual(detail["incoming_identities"], {"tmdb.movie": "10", "imdb.title": "tt20"})
            self.assertEqual(len(detail["candidates"]), 2)
            self.assertTrue(all(c["evidence_status"] == "current" for c in detail["candidates"]))

    def test_candidate_ownership_and_availability_changes_are_visible(self):
        review_id = self.duplicate()
        before = self.client.get(f"/library/identity-reviews/{review_id}").json()
        with Session(self.engine) as session:
            candidate = session.get(LibraryItem, before["candidates"][0]["library_item_id"])
            candidate.availability_status = "retired"
            session.add(candidate)
            session.commit()
        after = self.client.get(f"/library/identity-reviews/{review_id}").json()
        self.assertEqual(after["candidates"][0]["evidence_status"], "changed")
        self.assertNotEqual(before["revision"], after["revision"])

    def test_all_reasons_legacy_unknown_pagination_validation_and_no_write_route(self):
        with Session(self.engine) as session:
            for index, reason in enumerate([*sorted(REASONS), "unsafe/private/path"]):
                session.add(IdentityReview(source_instance_id="local", source_ref="private/path",
                    reason_code=reason, candidate_hash="a" * 64, review_key=str(index)))
            session.commit()
        page = self.client.get("/library/identity-reviews?limit=2&offset=2").json()
        self.assertEqual(page["total"], 7)
        self.assertEqual(len(page["items"]), 2)
        self.assertEqual(self.client.get("/library/identity-reviews?status=resolved").json()["total"], 0)
        all_rows = self.client.get("/library/identity-reviews?status=all").json()["items"]
        self.assertIn("unknown", [row["reason_code"] for row in all_rows])
        for row in all_rows:
            detail = self.client.get(f"/library/identity-reviews/{row['id']}").json()
            self.assertFalse(detail["evidence_available"])
            self.assertEqual(detail["candidates"], [])
        self.assertEqual(self.client.get("/library/identity-reviews/invalid").status_code, 422)
        self.assertEqual(self.client.get("/library/identity-reviews/irev_" + "f" * 32).status_code, 404)
        for query in ("limit=101", "offset=-1", "status=invalid"):
            self.assertEqual(self.client.get("/library/identity-reviews?" + query).status_code, 422)
        self.assertEqual(self.client.post("/library/identity-reviews/" + all_rows[0]["id"], json={}).status_code, 405)

    def test_repeated_copy_scan_keeps_one_review_and_all_facts(self):
        review_id = self.duplicate()
        with Session(self.engine) as session:
            film_id = session.get(IdentityReview, review_id).film_id
            canonical_runtime_writer.sync_user_state(session, film_id, watched=True, notes="keep",
                fields_set={"watched", "notes"})
            session.commit()
        for _ in range(2):
            library_manager.add_observations([{"title": "copy.mkv", "folder_name": "copy.mkv",
                "media_path": str(self.root / "copy.mkv")}])
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(IdentityReview)).all()), 1)
            self.assertEqual(session.exec(select(FilmProfileState)).one().notes, "keep")
            self.assertEqual(session.exec(select(Viewing)).one().film_id, film_id)
            self.assertEqual(len(session.exec(select(LibraryItem)).all()), 2)
            snapshot = session.get(IdentityReview, review_id).candidate_snapshot
            self.assertNotIn(str(self.root), json.dumps(snapshot))
            for event in session.exec(select(EventRecord)).all():
                self.assertNotIn("candidate_item_ids", event.payload)

    def preview(self, review_id, action="keep_separate", target=None):
        return self.client.post(f"/library/identity-reviews/{review_id}/preview",
            json={"action": action, "target_item_id": target})

    def confirm(self, review_id, preview, key="test-idempotency-key-0001"):
        return self.client.post(f"/library/identity-reviews/{review_id}/confirm", json={
            "action": preview["action"], "target_item_id": preview["effects"]["target_item_id"],
            "confirmation_token": preview["confirmation_token"], "idempotency_key": key})

    def reconnect_fixture(self):
        original = self.observation("old.mkv", tmdb_id="42")
        old = library_manager.upsert_observation(original)
        (self.root / "old.mkv").unlink()
        with Session(self.engine) as session:
            item = session.get(LibraryItem, old["library_item_id"])
            item.availability_status = "missing"
            session.add(item)
            session.commit()
        incoming = self.observation("moved.mkv", tmdb_id="42")
        new = library_manager.upsert_observation(incoming, review_reason="relink_full_hash_duplicate",
            review_context={"candidate_item_ids": [old["library_item_id"]]})
        with Session(self.engine) as session:
            review_id = session.exec(select(IdentityReview).where(IdentityReview.library_item_id == new["library_item_id"])).one().id
        return old, new, review_id, incoming

    def test_keep_separate_is_idempotent_atomic_and_survives_rescan(self):
        review_id = self.duplicate()
        before = self.dump()
        preview_response = self.preview(review_id)
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        preview = preview_response.json()
        self.assertEqual(before, self.dump())
        result = self.confirm(review_id, preview)
        self.assertEqual(result.status_code, 200, result.text)
        after = self.dump()
        self.assertEqual(self.confirm(review_id, preview).json(), result.json())
        self.assertEqual(self.dump(), after)
        changed = {**preview, "confirmation_token": "0" * 64}
        self.assertEqual(self.confirm(review_id, changed).json()["detail"]["code"], "idempotency_conflict")
        for _ in range(2):
            library_manager.add_observations([{"title": "copy.mkv", "folder_name": "copy.mkv", "media_path": str(self.root / "copy.mkv")}])
        self.assertEqual(self.client.get("/library/identity-reviews").json()["total"], 0)
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(IdentityReview)).all()), 1)
            self.assertEqual(len(session.exec(select(LibraryItem)).all()), 2)
            self.assertEqual(len(session.exec(select(EventRecord).where(EventRecord.type == "IdentityReviewDecided")).all()), 1)
        self.assertTrue((self.root / "original.mkv").is_file())
        self.assertTrue((self.root / "copy.mkv").is_file())

    def test_same_film_reconnect_preserves_facts_and_old_id_and_stays_closed_on_scan(self):
        old, new, review_id, incoming = self.reconnect_fixture()
        with Session(self.engine) as session:
            canonical_runtime_writer.sync_user_state(session, old["film_id"], rating=5, notes="Keep exactly",
                favorite=True, watched=True, fields_set={"rating", "notes", "favorite", "watched"})
            state = session.exec(select(FilmProfileState)).one()
            state.primary_item_id = new["library_item_id"]
            session.add(state)
            session.commit()
            session.refresh(state)
            state_before = state.model_dump(exclude={"primary_item_id"})
            view_before = session.exec(select(Viewing)).one().model_dump()
        preview_response = self.preview(review_id, "reconnect", old["library_item_id"])
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        result = self.confirm(review_id, preview_response.json())
        self.assertEqual(result.status_code, 200, result.text)
        for _ in range(2):
            library_manager.add_observations([incoming])
        self.assertEqual(self.client.get("/library/identity-reviews").json()["total"], 0)
        with Session(self.engine) as session:
            self.assertEqual(session.get(LibraryItem, old["library_item_id"]).availability_status, "available")
            self.assertEqual(session.get(LibraryItem, new["library_item_id"]).availability_status, "retired")
            state = session.exec(select(FilmProfileState)).one()
            self.assertEqual(state.model_dump(exclude={"primary_item_id"}), state_before)
            self.assertEqual(state.primary_item_id, old["library_item_id"])
            self.assertEqual(session.exec(select(Viewing)).one().model_dump(), view_before)
            self.assertEqual(len(session.exec(select(LibraryItem)).all()), 2)
        self.assertEqual((self.root / "moved.mkv").read_bytes(), b"synthetic video")

    def test_confirm_rechecks_file_and_candidate_and_rolls_back(self):
        old, new, review_id, _ = self.reconnect_fixture()
        preview = self.preview(review_id, "reconnect", old["library_item_id"]).json()
        before = self.dump()
        (self.root / "old.mkv").write_bytes(b"returned")
        result = self.confirm(review_id, preview)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.json()["detail"]["code"], "target_file_exists")
        self.assertEqual(before, self.dump())
        (self.root / "old.mkv").unlink()
        (self.root / "moved.mkv").write_bytes(b"changed")
        self.assertEqual(self.confirm(review_id, preview).json()["detail"]["code"], "source_file_changed")
        self.assertEqual(before, self.dump())
        (self.root / "moved.mkv").unlink()
        self.assertEqual(self.confirm(review_id, preview).json()["detail"]["code"], "source_file_missing")

    def test_same_film_reconnect_across_two_roots_rechecks_removed_root(self):
        first, second = self.root / 'first', self.root / 'second'
        first.mkdir(); second.mkdir()
        roots = [str(first), str(second)]
        with patch('app.services.settings.get_media_dirs', return_value=roots), patch.object(api_module, 'get_media_dirs', return_value=roots):
            old = library_manager.upsert_observation(self.observation('first/old.mkv', tmdb_id='42'))
            (first / 'old.mkv').unlink()
            with Session(self.engine) as session:
                item = session.get(LibraryItem, old['library_item_id'])
                item.availability_status = 'missing'; session.add(item); session.commit()
            incoming = self.observation('second/new.mkv', tmdb_id='42')
            new = library_manager.upsert_observation(incoming, review_reason='relink_full_hash_duplicate',
                review_context={'candidate_item_ids': [old['library_item_id']]})
            with Session(self.engine) as session:
                review_id = session.exec(select(IdentityReview).where(IdentityReview.library_item_id == new['library_item_id'])).one().id
            preview = self.preview(review_id, 'reconnect', old['library_item_id'])
            self.assertEqual(preview.status_code, 200, preview.text)
            with patch.object(api_module, 'get_media_dirs', return_value=[str(second)]):
                self.assertEqual(self.confirm(review_id, preview.json()).json()['detail']['code'], 'unsafe_locator')
            result = self.confirm(review_id, preview.json())
            self.assertEqual(result.status_code, 200, result.text)
            library_manager.add_observations([incoming])
            with Session(self.engine) as session:
                self.assertEqual(session.get(LibraryItem, old['library_item_id']).availability_status, 'available')
                self.assertEqual(session.get(LibraryItem, new['library_item_id']).availability_status, 'retired')
    def test_candidate_drift_cross_film_and_outside_root_are_rejected(self):
        review_id = self.duplicate()
        detail = self.client.get(f"/library/identity-reviews/{review_id}").json()
        target = detail["candidates"][0]["library_item_id"]
        self.assertEqual(self.preview(review_id, "reconnect", target).status_code, 409)
        preview = self.preview(review_id).json()
        with patch.object(api_module, "get_media_dirs", return_value=[str(self.root / "other")]):
            self.assertEqual(self.confirm(review_id, preview).json()["detail"]["code"], "unsafe_locator")
        with Session(self.engine) as session:
            item = session.get(LibraryItem, target)
            item.availability_status = "retired"
            session.add(item)
            session.commit()
        before = self.dump()
        self.assertEqual(self.confirm(review_id, preview).json()["detail"]["code"], "stale_review")
        self.assertEqual(before, self.dump())

    def test_decision_failure_rolls_back_every_change(self):
        old, new, review_id, _ = self.reconnect_fixture()
        preview = self.preview(review_id, "reconnect", old["library_item_id"]).json()
        before = self.dump()
        with patch("app.services.identity_decisions.event_store.append_in_session", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                self.confirm(review_id, preview)
        self.assertEqual(before, self.dump())

    def test_concurrent_replays_commit_once(self):
        review_id = self.duplicate()
        preview = self.preview(review_id).json()
        def submit():
            return identity_decision_service.confirm(self.engine, review_id, action="keep_separate",
                target_item_id=None, confirmation_token=preview["confirmation_token"],
                idempotency_key="concurrent-request-0001", media_root=str(self.root))
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: submit(), range(2)))
        self.assertEqual(results[0], results[1])
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(EventRecord).where(EventRecord.type == "IdentityReviewDecided")).all()), 1)

    def test_existing_item_conflict_scan_preserves_data_and_deduplicates_review(self):
        observation = self.observation("film.mkv", tmdb_id="42")
        original = library_manager.upsert_observation(observation)
        changed = {**observation, "tmdb_id": "99", "title": "Do not overwrite"}
        for _ in range(2):
            library_manager.add_observations([changed])
        with Session(self.engine) as session:
            rows = session.exec(select(IdentityReview)).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].reason_code, "identity_conflict")
            detail = identity_review_reader.detail(session, rows[0].id)
            self.assertEqual(detail["actions"], [])
            self.assertEqual(detail["film"]["identities"], {"tmdb.movie": "42"})
            self.assertEqual(detail["film"]["title"], "film.mkv")
        self.assertEqual(library_manager.get_film(original["film_id"])["title"], "film.mkv")

    def test_full_reconcile_keeps_observed_identity_conflict_available(self):
        observation = self.observation("conflicting.mkv", tmdb_id="42")
        original = library_manager.upsert_observation(observation)
        from app.models import utc_now_iso
        changed = {**observation, "tmdb_id": "99", "last_seen_at": utc_now_iso()}
        def scanned(_self):
            changed["last_seen_at"] = utc_now_iso()
            return [SimpleNamespace(film=changed, structured_metadata=None)]
        with patch("app.services.library_sync.NFOScanner.scan_observed", scanned), patch("app.services.library_sync.event_store.safe_append"):
            self.assertEqual(library_sync_service.reconcile(str(self.root))["missing"], 0)
            self.assertEqual(library_sync_service.reconcile(str(self.root))["missing"], 0)
        with Session(self.engine) as session:
            self.assertEqual(session.get(LibraryItem, original["library_item_id"]).availability_status, "available")
            self.assertEqual(len(session.exec(select(IdentityReview)).all()), 1)

    def test_reconnection_reuses_shared_nfo_artwork_and_retains_source_assets(self):
        old, new, review_id, _ = self.reconnect_fixture()
        from app.contracts.structured_metadata import canonical_json_hash
        from uuid import uuid4
        with Session(self.engine) as session:
            for item_id in (old["library_item_id"], new["library_item_id"]):
                for kind, locator in [("nfo", str(self.root / "movie.nfo")),
                        ("poster", "/media/poster.jpg"), ("poster_thumb", "/artwork-cache/test-poster.jpg")]:
                    session.add(MediaAsset(id="asset_" + uuid4().hex, library_item_id=item_id,
                        asset_kind=kind, locator_kind="local_path", locator=locator,
                        normalized_locator_hash=canonical_json_hash(locator), availability_status="present", source="test"))
            session.flush()
            review = session.get(IdentityReview, review_id)
            from app.services.identity_review import capture_candidates
            review.candidate_snapshot = capture_candidates(session, item_id=new["library_item_id"],
                incoming={"tmdb.movie": "42"}, file_observation=None, candidate_item_ids=[old["library_item_id"]])
            seal_source_evidence(session, review)
            session.commit()
        preview = self.preview(review_id, "reconnect", old["library_item_id"])
        self.assertEqual(preview.status_code, 200, preview.text)
        result = self.confirm(review_id, preview.json())
        self.assertEqual(result.status_code, 200, result.text)
        with Session(self.engine) as session:
            target_assets = session.exec(select(MediaAsset).where(MediaAsset.library_item_id == old["library_item_id"])).all()
            self.assertEqual(len(target_assets), 5)  # old+new video, reused NFO and both artwork references
            source_assets = session.exec(select(MediaAsset).where(MediaAsset.library_item_id == new["library_item_id"])).all()
            self.assertEqual(len(source_assets), 4)
            self.assertTrue(all(a.availability_status == "retired" for a in source_assets))

    def test_large_file_rescan_retains_complete_hash_and_detects_changed_stat(self):
        from app.services.file_identity import FileIdentityObservation, observe_file, full_content_hash
        large = b"x" * (13 * 1024 * 1024)
        original = self.observation("large-old.mkv", large, tmdb_id="42")
        old_path = self.root / "large-old.mkv"
        original.update(file_size=old_path.stat().st_size, file_mtime=old_path.stat().st_mtime)
        observed = observe_file(old_path)
        hashed = FileIdentityObservation(observed.platform_file_id, observed.content_fingerprint,
            full_content_hash(old_path), observed.bytes_read)
        old = library_manager.upsert_observation(original, file_observation=hashed)
        old_path.unlink()
        incoming = self.observation("large-new.mkv", large, tmdb_id="42")
        new_path = self.root / "large-new.mkv"
        incoming.update(file_size=new_path.stat().st_size, file_mtime=new_path.stat().st_mtime)
        observed = observe_file(new_path)
        hashed = FileIdentityObservation(observed.platform_file_id, observed.content_fingerprint,
            full_content_hash(new_path), observed.bytes_read)
        new = library_manager.upsert_observation(incoming, file_observation=hashed,
            review_reason="relink_full_hash_duplicate", review_context={"candidate_item_ids": [old["library_item_id"]]})
        with Session(self.engine) as session:
            review_id = session.exec(select(IdentityReview).where(IdentityReview.library_item_id == new["library_item_id"])).one().id
        for _ in range(2):
            library_manager.add_observations([incoming])
            self.assertEqual(self.preview(review_id, "reconnect", old["library_item_id"]).status_code, 200)
        changed = {**incoming, "file_mtime": incoming["file_mtime"] + 1}
        library_manager.add_observations([changed])
        self.assertEqual(self.preview(review_id, "reconnect", old["library_item_id"]).status_code, 409)

    def test_scan_and_confirmation_serialize_before_reading_edition_ownership(self):
        old, new, review_id, incoming = self.reconnect_fixture()
        preview = self.preview(review_id, "reconnect", old["library_item_id"]).json()
        entered, release, confirmation_attempted = Event(), Event(), Event()
        def before_sql(_connection, _cursor, statement, _parameters, _context, _many):
            if statement == "BEGIN IMMEDIATE" and entered.is_set():
                confirmation_attempted.set()
        original = canonical_runtime_writer._resolve_existing_identity
        def paused(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise AssertionError("scan gate timeout")
            return original(*args, **kwargs)
        def submit():
            return identity_decision_service.confirm(self.engine, review_id, action="reconnect",
                target_item_id=old["library_item_id"], confirmation_token=preview["confirmation_token"],
                idempotency_key="scan-concurrency-0001", media_root=str(self.root))
        event.listen(self.engine, "before_cursor_execute", before_sql)
        try:
            with patch.object(canonical_runtime_writer, "_resolve_existing_identity", paused), ThreadPoolExecutor(max_workers=2) as pool:
                scan = pool.submit(library_manager.add_observations, [incoming])
                try:
                    self.assertTrue(entered.wait(5))
                    confirmation = pool.submit(submit)
                    self.assertTrue(confirmation_attempted.wait(5))
                    self.assertFalse(confirmation.done())
                finally:
                    release.set()
                self.assertEqual(scan.result(), 0)
                self.assertEqual(confirmation.result()["status"], "resolved")
        finally:
            event.remove(self.engine, "before_cursor_execute", before_sql)
        library_manager.add_observations([incoming])
        with Session(self.engine) as session:
            self.assertEqual(session.get(LibraryItem, new["library_item_id"]).availability_status, "retired")
            self.assertEqual(session.get(LibraryItem, old["library_item_id"]).availability_status, "available")

    def test_missing_scans_wait_for_reconnect_then_read_current_asset_ownership(self):
        old, new, review_id, _ = self.reconnect_fixture()
        snapshot_ids = [library_manager.record_file_organization(new["film_id"], item["library_item_id"],
            "synthetic-manifest", command_id="synthetic-organization", tmdb_id=42,
            sidecar_count=0, scrape_status="success") for item in (old, new)]
        with patch.object(snapshots_module.operation_manifest_store, "state", return_value="target"):
            undo_token = operation_snapshot_service.preview(snapshot_ids[1])["confirmation_token"]
        self.assertIsNotNone(undo_token)
        with Session(self.engine) as session:
            source = session.get(LibraryItem, new["library_item_id"])
            source.last_seen_at = "2026-10-12T00:00:00+00:00"
            session.add(source)
            session.commit()
        preview = self.preview(review_id, "reconnect", old["library_item_id"]).json()
        self.assertEqual(set(preview["effects"]["expiring_snapshot_ids"]), set(snapshot_ids))
        entered, release, scans_attempted = Event(), Event(), Event()
        attempts = []
        def before_sql(_connection, _cursor, statement, _parameters, _context, _many):
            if statement == "BEGIN IMMEDIATE" and entered.is_set():
                attempts.append(statement)
                if len(attempts) == 6:
                    scans_attempted.set()
        original = identity_decision_service._reconnect
        def paused(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise AssertionError("confirm gate timeout")
            return original(*args, **kwargs)
        def submit():
            return identity_decision_service.confirm(self.engine, review_id, action="reconnect",
                target_item_id=old["library_item_id"], confirmation_token=preview["confirmation_token"],
                idempotency_key="missing-concurrency-0001", media_root=str(self.root))
        event.listen(self.engine, "before_cursor_execute", before_sql)
        try:
            with patch.object(identity_decision_service, "_reconnect", paused), patch.object(snapshots_module.operation_manifest_store, "restore") as restore_files, ThreadPoolExecutor(max_workers=7) as pool:
                confirmation = pool.submit(submit)
                try:
                    self.assertTrue(entered.wait(5))
                    full_scan = pool.submit(library_manager.mark_missing_not_seen_since, "0000")
                    watch = pool.submit(library_manager.mark_path_missing, str(self.root / "old.mkv"))
                    ignored = pool.submit(library_manager.ignore_item, new["library_item_id"])
                    preferred = pool.submit(library_manager.select_primary_item, new["film_id"], new["library_item_id"])
                    cleanup = pool.submit(library_manager.cleanup_missing)
                    undo = pool.submit(operation_snapshot_service.restore, snapshot_ids[1], undo_token)
                    self.assertTrue(scans_attempted.wait(5))
                    self.assertFalse(full_scan.done())
                    self.assertFalse(watch.done())
                    self.assertFalse(ignored.done())
                    self.assertFalse(preferred.done())
                    self.assertFalse(cleanup.done())
                    self.assertFalse(undo.done())
                finally:
                    release.set()
                self.assertEqual(confirmation.result()["status"], "resolved")
                self.assertEqual(full_scan.result(), 0)
                self.assertEqual(watch.result(), 0)
                self.assertIsNone(ignored.result())
                with self.assertRaises(ValueError):
                    preferred.result()
                self.assertEqual(cleanup.result(), 0)
                with self.assertRaises(OperationConflict):
                    undo.result()
                restore_files.assert_not_called()
        finally:
            event.remove(self.engine, "before_cursor_execute", before_sql)
        with Session(self.engine) as session:
            self.assertEqual(session.get(LibraryItem, new["library_item_id"]).availability_status, "retired")
            self.assertEqual(session.get(LibraryItem, old["library_item_id"]).availability_status, "available")
            from app.models import OperationSnapshot
            for snapshot_id in snapshot_ids:
                snapshot = session.get(OperationSnapshot, snapshot_id)
                self.assertEqual(snapshot.status, "expired")
                self.assertEqual(snapshot.backup_manifest_ref, "synthetic-manifest")
                self.assertEqual(snapshot.before_state, {"manifest_state": "source"})
        with self.assertRaises(ValueError):
            library_manager.record_file_organization(new["film_id"], new["library_item_id"],
                "synthetic-late-manifest", command_id="synthetic-late", tmdb_id=42,
                sidecar_count=0, scrape_status="success")

    def test_restore_before_confirmation_invalidates_its_edition_evidence(self):
        from app.models import OperationSnapshot
        old, new, review_id, _ = self.reconnect_fixture()
        with Session(self.engine) as session:
            audit = EventRecord(type="LibraryItemRestored", aggregate_type="library_item",
                aggregate_id=new["library_item_id"], payload={})
            session.add(audit)
            session.flush()
            after = {"availability_status": "available"}
            snapshot = OperationSnapshot(event_id=audit.id, aggregate_type="library_item",
                aggregate_id=new["library_item_id"], operation_kind="availability",
                before_state={"availability_status": "missing"}, after_state=after,
                optimistic_hash=operation_snapshot_service._state_hash(after))
            session.add(snapshot)
            session.commit()
            snapshot_id = snapshot.id
        preview = self.preview(review_id, "reconnect", old["library_item_id"]).json()
        undo = operation_snapshot_service.preview(snapshot_id)
        self.assertEqual(operation_snapshot_service.restore(snapshot_id, undo["confirmation_token"])["status"], "restored")
        self.assertEqual(self.confirm(review_id, preview).json()["detail"]["code"], "stale_review")
        with Session(self.engine) as session:
            self.assertEqual(session.get(IdentityReview, review_id).status, "open")
            self.assertNotEqual(session.get(LibraryItem, new["library_item_id"]).availability_status, "retired")
        self.assertEqual((self.root / "moved.mkv").read_bytes(), b"synthetic video")

    def test_new_review_seals_candidates_after_same_film_provider_identity_sync(self):
        library_manager.add_observations([self.observation("same-original.mkv", tmdb_id="42")])
        incoming = self.observation("same-copy.mkv", tmdb_id="42", imdb_id="tt42")
        library_manager.add_observations([incoming])
        with Session(self.engine) as session:
            review_id = session.exec(select(IdentityReview)).one().id
            detail = identity_review_reader.detail(session, review_id)
            self.assertIsNone(detail["blocked_code"])
            self.assertEqual(detail["candidates"][0]["evidence_status"], "current")
        preview = self.preview(review_id).json()
        library_manager.add_observations([incoming])
        self.assertEqual(self.confirm(review_id, preview).status_code, 200)

    def test_v6_upgrade_keeps_historical_review_and_facts_without_inventing_evidence(self):
        path = self.root / "v6.db"
        engine = create_engine(f"sqlite:///{path}")
        try:
            run_migrations(engine, path, migrations=MIGRATIONS[:6], backup_required=False)
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO identity_review (id,source_instance_id,source_ref,reason_code,"
                    "candidate_hash,review_key,status,created_at,updated_at) VALUES "
                    "('irev_old','local','private-ref','identity_conflict','hash','key','dismissed','then','then')"))
            result = run_migrations(engine, path, backup_dir=self.root / "backups")
            self.assertEqual(result.applied_versions, (7, 8, 9, 10, 11, 12))
            self.assertIsNotNone(result.backup)
            with engine.connect() as connection:
                row = connection.execute(text("SELECT status,candidate_hash,candidate_snapshot FROM identity_review")).one()
                self.assertEqual(tuple(row), ("dismissed", "hash", None))
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
