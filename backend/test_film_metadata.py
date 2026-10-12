import tempfile
import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select
from sqlalchemy.exc import SQLAlchemyError

from app.api import film_metadata as api_module
from app.database import configure_sqlite_engine
from app.main import app
from app.migrations.runner import run_migrations
from app.models import Film, FilmMetadataOverride, FilmMetadataEdit, ExternalIdentity, IdentityReview, EventRecord, FilmProfileState, Viewing, OperationSnapshot, LibraryItem
from app.services import library as library_module
from app.services.film_metadata import metadata_view
from app.services.library import library_manager
from app.services.canonical_runtime import canonical_runtime_writer, RelinkIdentityConflict
from app.services.film_metadata import update_metadata, MetadataConflict
from app.contracts.film_metadata import MetadataUpdate
from app.services.projections import projection_coordinator
from app.services import operation_snapshots as snapshots_module
from app.services.operation_snapshots import operation_snapshot_service
from app.portability import build_export_payload, _validate_payload


class FilmMetadataReadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "synthetic.db"
        self.engine = create_engine(f"sqlite:///{self.path}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, self.path, backup_required=False)
        self.patches = [patch.object(module, "engine", self.engine)
                        for module in (library_module, api_module, snapshots_module)]
        for item in self.patches:
            item.start()
        self.client = TestClient(app)
        self.observation = dict(title="Automatic title", year="1999", plot="Automatic synopsis",
            folder_name="Synthetic", tmdb_id="123")
        self.film_id = library_manager.upsert_observation(self.observation)["film_id"]

    def tearDown(self):
        self.client.close()
        for item in self.patches:
            item.stop()
        self.engine.dispose()
        self.temp.cleanup()

    def test_read_is_read_only_and_discloses_automatic_values(self):
        with self.engine.connect() as connection:
            before = "\n".join(connection.connection.driver_connection.iterdump())
        response = self.client.get(f"/films/{self.film_id}/metadata")
        self.assertEqual(response.status_code, 200)
        view = response.json()
        self.assertEqual(view["fields"]["title"]["automatic_value"], "Automatic title")
        self.assertFalse(view["fields"]["title"]["manual"])
        self.assertEqual(len(view["revision"]), 64)
        with self.engine.connect() as connection:
            self.assertEqual(before, "\n".join(connection.connection.driver_connection.iterdump()))

    def test_display_overlay_preserves_automatic_and_identity_rows_after_scan(self):
        with Session(self.engine) as session:
            identities = [row.model_dump() for row in session.exec(select(ExternalIdentity)).all()]
            reviews = [row.model_dump() for row in session.exec(select(IdentityReview)).all()]
            session.add(FilmMetadataOverride(film_id=self.film_id,
                values={"title": "Manual title", "overview": "Manual synopsis"}, revision=1))
            session.commit()
            revision = metadata_view(session, self.film_id)["revision"]
        library_manager.upsert_observation({**self.observation, "title": "New automatic title",
                                           "plot": "New automatic synopsis"})
        detail = library_manager.get_film(self.film_id)
        self.assertEqual(detail["title"], "Manual title")
        self.assertEqual(detail["overview"], "Manual synopsis")
        self.assertEqual(detail["resolved_sources"]["title"]["source_kind"], "user")
        with Session(self.engine) as session:
            self.assertEqual(session.get(Film, self.film_id).canonical_title, "New automatic title")
            view = metadata_view(session, self.film_id)
            self.assertNotEqual(view["revision"], revision)
            self.assertEqual(view["fields"]["title"]["automatic_value"], "New automatic title")
            self.assertEqual(identities, [row.model_dump() for row in session.exec(select(ExternalIdentity)).all()])
            self.assertEqual(reviews, [row.model_dump() for row in session.exec(select(IdentityReview)).all()])

    def test_invalid_missing_and_merged_film_are_distinct(self):
        self.assertEqual(self.client.get("/films/not-an-id/metadata").status_code, 422)
        self.assertEqual(self.client.get(f"/films/film_{'0' * 32}/metadata").status_code, 404)
        with Session(self.engine) as session:
            film = session.get(Film, self.film_id)
            film.lifecycle_status = "merged"
            session.add(film)
            session.commit()
        response = self.client.get(f"/films/{self.film_id}/metadata")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "metadata_film_changed")

    def test_operation_context_never_feeds_manual_data_back_into_automatic_source(self):
        with Session(self.engine) as session:
            session.add(FilmMetadataOverride(film_id=self.film_id,
                values={"title": "Correction", "overview": "Manual synopsis"}, revision=1))
            session.commit()
        context = library_manager.get_film_operation_context(self.film_id)
        self.assertEqual(context["title"], "Automatic title")
        self.assertEqual(context["plot"], "Automatic synopsis")
        library_manager.update_film_observation(self.film_id, {"scrape_status": "failed"})
        with Session(self.engine) as session:
            self.assertEqual(session.get(Film, self.film_id).canonical_title, "Automatic title")
            self.assertEqual(session.get(Film, self.film_id).overview, "Automatic synopsis")
        self.assertEqual(library_manager.get_film(self.film_id)["title"], "Correction")

    def current(self, film_id=None):
        return self.client.get(f"/films/{film_id or self.film_id}/metadata").json()

    def request(self, changes, film_id=None):
        return dict(revision=self.current(film_id)["revision"], idempotency_key=uuid4().hex, changes=changes)

    def save(self, changes, film_id=None):
        response = self.client.patch(f"/films/{film_id or self.film_id}/metadata", json=self.request(changes, film_id))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def dump(self):
        with self.engine.connect() as connection:
            return "\n".join(connection.connection.driver_connection.iterdump())

    def test_first_partial_edit_reset_and_protected_unknown_year(self):
        first = self.save({"title": {"action": "set", "value": "  Corrected  "},
                           "year": {"action": "set", "value": None}})
        self.assertEqual(first["fields"]["title"]["value"], "Corrected")
        self.assertTrue(first["fields"]["year"]["manual"])
        self.assertIsNone(library_manager.get_film(self.film_id)["year"])
        self.save({"overview": {"action": "set", "value": "  "}})
        with Session(self.engine) as session:
            film = session.get(Film, self.film_id)
            self.assertEqual((film.canonical_title, film.release_year, film.overview),
                             ("Automatic title", 1999, "Automatic synopsis"))
            receipts = session.exec(select(FilmMetadataEdit)).all()
            self.assertEqual(receipts[0].automatic_snapshot["year"]["value"], 1999)
        library_manager.upsert_observation({**self.observation, "year": 2001, "plot": "New synopsis"})
        self.assertIsNone(self.current()["fields"]["year"]["value"])
        reset = self.save({"year": {"action": "reset"}})
        self.assertEqual(reset["fields"]["year"]["value"], 2001)
        self.assertFalse(reset["fields"]["year"]["manual"])
        self.assertEqual(reset["fields"]["title"]["value"], "Corrected")
        self.assertTrue(reset["fields"]["overview"]["manual"])
        self.assertIsNone(reset["fields"]["overview"]["value"])

    def test_retry_is_durable_and_never_reapplies_over_later_edits(self):
        request = self.request({"title": {"action": "set", "value": "First"}})
        url = f"/films/{self.film_id}/metadata"
        self.assertEqual(self.client.patch(url, json=request).status_code, 200)
        self.engine.dispose()
        repeated = self.client.patch(url, json=request)
        self.assertTrue(repeated.json()["replayed"])
        self.save({"title": {"action": "set", "value": "Later"}})
        repeated = self.client.patch(url, json=request)
        self.assertEqual(repeated.json()["fields"]["title"]["value"], "Later")
        conflict = self.client.patch(url, json={**request, "changes": {"title": {"action": "set", "value": "Other"}}})
        self.assertEqual(conflict.status_code, 409)
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(FilmMetadataEdit)).all()), 2)
            self.assertEqual(len(session.exec(select(EventRecord).where(EventRecord.type == "FilmMetadataEdited")).all()), 2)

    def test_stale_edit_after_manual_or_automatic_change_is_rejected(self):
        for change in (lambda: self.save({"title": {"action": "set", "value": "New"}}),
                       lambda: library_manager.upsert_observation({**self.observation, "plot": "Changed auto"})):
            request = self.request({"overview": {"action": "set", "value": "Stale"}})
            change()
            before = self.dump()
            response = self.client.patch(f"/films/{self.film_id}/metadata", json=request)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["detail"]["code"], "metadata_stale")
            self.assertEqual(before, self.dump())

    def test_concurrent_saves_have_one_winner_and_identical_retries_commit_once(self):
        for same_key in (False, True):
            request = self.request({"overview": {"action": "set", "value": str(same_key)}})
            second = request if same_key else {**request, "idempotency_key": uuid4().hex}
            def write(payload):
                try:
                    return update_metadata(self.engine, self.film_id, MetadataUpdate(**payload))["replayed"]
                except MetadataConflict as exc:
                    return exc.code
            with ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(write, [request, second]))
            self.assertCountEqual(results, [False, True] if same_key else [False, "metadata_stale"])

    def test_invalid_payloads_do_not_mutate_anything(self):
        bad = [{}, {"tmdb_id": {"action": "set", "value": 999}}, {"rating": {"action": "set", "value": 5}},
               {"title": {"action": "set", "value": " \n "}}, {"title": {"action": "set", "value": None}},
               {"title": {"action": "set", "value": "x" * 301}}, {"overview": {"action": "set", "value": "x" * 10001}},
               {"title": {"action": "reset", "value": "bad"}}, {"title": {"action": "set"}}]
        bad += [{"year": {"action": "set", "value": value}} for value in [True, 1999.5, "1999", 0, 1869, 2101]]
        before = self.dump()
        for changes in bad:
            response = self.client.patch(f"/films/{self.film_id}/metadata", json=self.request(changes))
            self.assertEqual(response.status_code, 422, changes)
        self.assertEqual(before, self.dump())

    def test_projection_failure_rolls_back_receipt_override_event_and_allows_retry(self):
        request = self.request({"title": {"action": "set", "value": "Retry me"}})
        before = self.dump()
        with patch.object(projection_coordinator, "refresh_film", side_effect=SQLAlchemyError("synthetic failure")):
            response = self.client.patch(f"/films/{self.film_id}/metadata", json=request)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("synthetic failure", response.text)
        self.assertEqual(before, self.dump())
        self.assertEqual(self.client.patch(f"/films/{self.film_id}/metadata", json=request).status_code, 200)

    def test_busy_database_returns_retryable_response(self):
        request = self.request({"title": {"action": "set", "value": "Retry after lock"}})
        fast_engine = create_engine(f"sqlite:///{self.path}", connect_args={"timeout": 0.02})
        try:
            with self.engine.connect() as connection:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                with patch.object(api_module, "engine", fast_engine):
                    response = self.client.patch(f"/films/{self.film_id}/metadata", json=request)
                self.assertEqual(response.status_code, 503)
                connection.rollback()
            self.assertEqual(self.client.patch(f"/films/{self.film_id}/metadata", json=request).status_code, 200)
        finally:
            fast_engine.dispose()

    def test_personal_identity_and_viewing_rows_unchanged_and_export_keeps_null(self):
        with Session(self.engine) as session:
            canonical_runtime_writer.sync_user_state(session, self.film_id, rating=4, notes="Private",
                favorite=True, watched=True, fields_set={"rating", "notes", "favorite", "watched"})
            session.commit()
            before = {model.__name__: [row.model_dump() for row in session.exec(select(model)).all()]
                      for model in (Viewing, FilmProfileState, ExternalIdentity, IdentityReview)}
        self.save({"title": {"action": "set", "value": "Corrected"}, "year": {"action": "set", "value": None}})
        with Session(self.engine) as session:
            after = {model.__name__: [row.model_dump() for row in session.exec(select(model)).all()]
                     for model in (Viewing, FilmProfileState, ExternalIdentity, IdentityReview)}
        self.assertEqual(before, after)
        payload, _ = build_export_payload(self.engine)
        self.assertEqual(payload["curated_metadata"]["manual_overrides"][0]["values"], {"title": "Corrected", "year": None})
        del payload["curated_metadata"]["manual_overrides"]
        _validate_payload(payload)  # Existing v1 exports remain readable.

    def test_cross_film_reassignment_blocked_until_every_field_is_reset(self):
        source = library_manager.upsert_observation(dict(title="Unmatched", folder_name="Unmatched"))
        source_id = source["film_id"]
        self.save({"title": {"action": "set", "value": "Correction"}, "year": {"action": "set", "value": None}}, source_id)
        for act in (lambda: library_manager.validate_film_identity(source_id, {"tmdb_id": "123"}),
                    lambda: library_manager.update_film_observation(source_id, {"tmdb_id": "123"})):
            before = self.dump()
            with self.assertRaisesRegex(RelinkIdentityConflict, "Manual metadata corrections"):
                act()
            self.assertEqual(before, self.dump())
        self.save({"title": {"action": "reset"}}, source_id)
        with self.assertRaises(RelinkIdentityConflict):
            library_manager.update_film_observation(source_id, {"tmdb_id": "123"})
        self.save({"year": {"action": "reset"}}, source_id)
        result = library_manager.update_film_observation(source_id, {"tmdb_id": "123"})
        self.assertEqual(result["id"], self.film_id)
        with Session(self.engine) as session:
            self.assertEqual(session.get(LibraryItem, source["library_item_id"]).film_id, self.film_id)

    def test_automatic_metadata_undo_preserves_override_and_reset_uses_restored_value(self):
        library_manager.update_film_observation(self.film_id, {"year": 2001}, event_type="MetadataMatched")
        with Session(self.engine) as session:
            snapshot = session.exec(select(OperationSnapshot).where(OperationSnapshot.operation_kind == "metadata")).one()
            snapshot_id = snapshot.id
        self.save({"year": {"action": "set", "value": 2005}})
        preview = operation_snapshot_service.preview(snapshot_id)
        self.assertTrue(preview["current_matches_after"])
        operation_snapshot_service.restore(snapshot_id, preview["confirmation_token"])
        self.assertEqual(library_manager.get_film(self.film_id)["year"], 2005)
        self.assertEqual(self.current()["fields"]["year"]["automatic_value"], 1999)
        self.assertEqual(self.save({"year": {"action": "reset"}})["fields"]["year"]["value"], 1999)
