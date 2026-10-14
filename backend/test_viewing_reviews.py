"""Viewing reviews stay independent, migrate empty, and reject stale or duplicate writes."""
import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine, select

import app.services.viewings as viewings_module
import app.services.user_state as user_state_module
from app.canonical_models import FilmProfileState, Viewing, ViewingWriteReceipt
from app.models import EventRecord
from app.api.library import router
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.migrations.versions import MIGRATIONS
from app.migrations.versions.v0001_fresh_canonical_baseline import LOCAL_PROFILE_ID
from app.portability import PortabilityError, build_export_payload, export_package, validate_package, _validate_payload


FILM_ID = "film_" + "a" * 32
NOW = "2026-10-12T00:00:00+00:00"
DATES = [("2025", "year"), ("2026-10-11", "date"),
         ("2026-10-11T22:30:00+08:00", "timestamp"), (None, "unknown")]


class ViewingReviewStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "synthetic.db"
        self.engine = create_engine(f"sqlite:///{self.path}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, self.path, migrations=MIGRATIONS[:8], backup_required=False)
        # Insert into the actual v8 schema: no new ORM fields may leak into this fixture.
        with self.engine.begin() as connection:
            connection.execute(text("INSERT INTO graph_entity "
                "(id,entity_type,lifecycle_status,created_at,updated_at) "
                "VALUES (:film,'film','active',:now,:now)"), {"film": FILM_ID, "now": NOW})
            connection.execute(text("INSERT INTO film "
                "(id,canonical_title,lifecycle_status,created_at,updated_at) "
                "VALUES (:film,'Synthetic Rewatch','active',:now,:now)"), {"film": FILM_ID, "now": NOW})
            connection.execute(text("INSERT INTO film_profile_state "
                "(profile_id,film_id,favorite,rating,notes,created_at,updated_at) "
                "VALUES (:profile,:film,1,3,'Historical Film note',:now,:now)"),
                {"profile": LOCAL_PROFILE_ID, "film": FILM_ID, "now": NOW})
            for index, (date, precision) in enumerate(DATES):
                connection.execute(text("INSERT INTO viewing "
                    "(id,profile_id,film_id,watched_at,watched_at_precision,source,source_record_id,"
                    "review_status,created_at,updated_at) "
                    "VALUES (:id,:profile,:film,:date,:precision,'diary',:id,'confirmed',:now,:now)"),
                    {"id": f"view_{index:032x}", "profile": LOCAL_PROFILE_ID,
                     "film": FILM_ID, "date": date, "precision": precision, "now": NOW})

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def upgrade(self):
        return run_migrations(self.engine, self.path, backup_required=False)

    def client(self):
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_api_independent_create_edit_clear_dates_and_strict_validation(self):
        self.upgrade()
        with patch.object(viewings_module, "engine", self.engine), self.client() as client:
            url = f"/films/{FILM_ID}/viewings"
            payload = {"watched_at": DATES[2][0], "rating": 5, "notes": "Private first impression",
                       "idempotency_key": "create-review-0001"}
            created = client.post(url, json=payload)
            self.assertEqual(created.status_code, 200, created.text)
            row = created.json()
            endpoint = f"/viewings/{row['id']}"
            # Neither unversioned old clients nor stale new clients can overwrite reviews.
            self.assertEqual(client.patch(endpoint, json={"watched_at": "2020"}).status_code, 409)
            self.assertEqual(client.delete(endpoint).status_code, 409)
            changed = client.patch(endpoint, json={"notes": "Second thought", "revision": row["revision"],
                "idempotency_key": "update-review-0001"}).json()
            self.assertEqual((changed["rating"], changed["watched_at"], changed["watched_at_precision"]), (5, DATES[2][0], "timestamp"))
            self.assertEqual(client.patch(endpoint, json={"rating": 1, "revision": row["revision"],
                "idempotency_key": "stale-review-00001"}).status_code, 409)
            self.assertEqual(client.delete(endpoint, params={"revision": row["revision"]}).status_code, 409)
            cleared = client.patch(endpoint, json={"rating": None, "notes": " \n ", "revision": changed["revision"],
                "idempotency_key": "clear-review-00001"}).json()
            self.assertIsNone(cleared["rating"])
            self.assertIsNone(cleared["notes"])
            for date, precision in DATES:
                date_write = client.patch(endpoint, json={"watched_at": date, "revision": cleared["revision"]})
                self.assertEqual(date_write.status_code, 200, date_write.text)
                cleared = date_write.json()
                self.assertEqual(cleared["watched_at_precision"], precision)
            for bad in [{"rating": True}, {"rating": 2.5}, {"rating": "4"}, {"rating": 0}, {"rating": 6},
                        {"notes": 3}, {"notes": "a\0b"}, {"notes": "x" * 10001}, {"extra": True}]:
                response = client.post(url, json={**payload, **bad})
                self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(client.post(url, json={"watched_at": None, "rating": 5}).status_code, 422)
            self.assertEqual(client.patch(endpoint, json={"revision": cleared["revision"]}).status_code, 422)
            self.assertEqual(client.delete(endpoint, params={"revision": cleared["revision"]}).status_code, 200)
            self.assertEqual(client.delete(endpoint, params={"revision": cleared["revision"]}).status_code, 200)
        with Session(self.engine) as session:
            state = session.get(FilmProfileState, (LOCAL_PROFILE_ID, FILM_ID))
            self.assertEqual((state.rating, state.notes), (3, "Historical Film note"))
            events = session.exec(select(EventRecord)).all()
            self.assertNotIn("Private first impression", str([e.payload for e in events]))
            self.assertNotIn("Second thought", str([e.payload for e in events]))

    def test_retry_receipts_survive_restart_and_concurrent_requests_commit_once(self):
        self.upgrade()
        manager = viewings_module.viewing_manager
        key = "concurrent-create-001"
        with patch.object(viewings_module, "engine", self.engine):
            def create():
                return manager.create(FILM_ID, "2025", rating=4, notes="One watch", idempotency_key=key)
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: create(), range(2)))
            self.assertEqual(results[0]["id"], results[1]["id"])
            self.engine.dispose()
            replay = create()
            self.assertTrue(replay["replayed"])
            with self.assertRaises(viewings_module.ViewingConflict):
                manager.create(FILM_ID, "2025", rating=1, idempotency_key=key)
            original = results[0]
            def edit(value):
                try:
                    return manager.update(original["id"], changes={"rating": value}, revision=original["revision"],
                        idempotency_key=f"concurrent-edit-{value}")
                except viewings_module.ViewingConflict:
                    return None
            with ThreadPoolExecutor(max_workers=2) as pool:
                edits = list(pool.map(edit, [1, 5]))
            self.assertEqual(sum(row is not None for row in edits), 1)
            latest = next(row for row in edits if row)
            # A lost create response replay must never overwrite a subsequent edit.
            with self.assertRaises(viewings_module.ViewingConflict):
                create()
            manager.delete(latest["id"], revision=latest["revision"])
            with self.assertRaises(viewings_module.ViewingConflict):
                create()
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(Viewing)).all()), 5)
            self.assertEqual(len(session.exec(select(ViewingWriteReceipt)).all()), 2)

    def test_event_failure_rolls_back_review_and_receipt_then_same_request_retries(self):
        self.upgrade()
        manager = viewings_module.viewing_manager
        with patch.object(viewings_module, "engine", self.engine):
            before = manager.list_film(FILM_ID)[0]
            args = dict(changes={"rating": 5, "notes": "Atomic"}, revision=before["revision"], idempotency_key="atomic-update-0001")
            with patch.object(viewings_module.event_store, "append_in_session", side_effect=RuntimeError("synthetic failure")):
                with self.assertRaises(RuntimeError):
                    manager.update(before["id"], **args)
            self.assertEqual(manager.list_film(FILM_ID)[0], before)
            with Session(self.engine) as session:
                self.assertEqual(session.exec(select(ViewingWriteReceipt)).all(), [])
            after = manager.update(before["id"], **args)
            self.assertEqual((after["rating"], after["notes"]), (5, "Atomic"))
            self.assertTrue(manager.update(before["id"], **args)["replayed"])

    def test_v8_upgrade_leaves_reviews_unassigned_and_preserves_every_existing_column(self):
        with self.engine.connect() as connection:
            before = [dict(row) for row in connection.execute(text("SELECT * FROM viewing ORDER BY id")).mappings()]
            profile_before = dict(connection.execute(text("SELECT * FROM film_profile_state")).mappings().one())
        self.assertNotIn("rating", {column["name"] for column in inspect(self.engine).get_columns("viewing")})
        self.assertEqual(self.upgrade().applied_versions, (9, 10))
        self.assertEqual(self.upgrade().applied_versions, ())
        with self.engine.connect() as connection:
            after = [dict(row) for row in connection.execute(text("SELECT * FROM viewing ORDER BY id")).mappings()]
            self.assertEqual(dict(connection.execute(text("SELECT * FROM film_profile_state")).mappings().one()), profile_before)
        for old, new in zip(before, after, strict=True):
            self.assertIsNone(new.pop("rating"))
            self.assertIsNone(new.pop("notes"))
            self.assertEqual(old, new)

    def test_independent_reviews_survive_reopening_and_are_read_without_changing_film_state(self):
        self.upgrade()
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE viewing SET rating=4,notes='First impression' WHERE id=:id"), {"id": "view_" + "0" * 32})
            connection.execute(text("UPDATE viewing SET rating=5,notes='Second impression' WHERE id=:id"), {"id": f"view_{1:032x}"})
        self.engine.dispose()
        with patch.object(viewings_module, "engine", self.engine):
            rows = {row["id"]: row for row in viewings_module.viewing_manager.list_film(FILM_ID)}
            timeline = viewings_module.viewing_manager.list_profile()
            # The existing date-only update must preserve the stored new fields.
            updated = viewings_module.viewing_manager.update(f"view_{1:032x}", "2024")
        self.assertEqual((updated["rating"], updated["notes"]), (5, "Second impression"))
        self.assertEqual((rows["view_" + "0" * 32]["rating"], rows[f"view_{1:032x}"]["rating"]), (4, 5))
        self.assertEqual(rows[f"view_{1:032x}"]["notes"], "Second impression")
        self.assertIsNone(rows[f"view_{2:032x}"]["rating"])
        for item in timeline["items"]:
            self.assertEqual(item["profile_state"]["rating"], 3)
            self.assertEqual(item["profile_state"]["notes"], "Historical Film note")
            self.assertEqual(item["viewing"], rows[item["viewing"]["id"]])
        with Session(self.engine) as session:
            state = session.get(FilmProfileState, (LOCAL_PROFILE_ID, FILM_ID))
            self.assertEqual((state.rating, state.notes), (3, "Historical Film note"))
            self.assertEqual(session.get(Viewing, f"view_{2:032x}").watched_at, DATES[2][0])

    def test_database_constraints_reject_invalid_values_and_allow_clear(self):
        self.upgrade()
        for field, value in [("rating", 0), ("rating", 6), ("rating", 2.5), ("rating", "bad"),
                             ("notes", "x" * 10001), ("notes", b"\xff"), ("notes", "a\0" + "x" * 10001)]:
            with self.subTest(field=field, value=str(value)[:20]), self.assertRaises(IntegrityError):
                with self.engine.begin() as connection:
                    connection.execute(text(f"UPDATE viewing SET {field}=:value"), {"value": value})
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE viewing SET rating=5,notes=:notes"), {"notes": "观影" * 5000})
            connection.execute(text("UPDATE viewing SET rating=NULL,notes=NULL"))

    def test_watched_toggle_restores_same_manual_review_without_creating_diary_rows(self):
        self.upgrade()
        manager = user_state_module.film_profile_state_manager
        with patch.object(user_state_module, "engine", self.engine):
            manager.upsert(FILM_ID, watched=True, watched_at="2025", fields_set={"watched", "watched_at"})
            with Session(self.engine) as session:
                manual = session.exec(select(Viewing).where(Viewing.source == "manual")).one()
                manual_id = manual.id
                manual.rating, manual.notes = 4, "Keep the original manual impression"
                session.add(manual)
                session.commit()
            off = manager.upsert(FILM_ID, watched=False, fields_set={"watched"})
            self.assertFalse(off["manual_watched"])
            on = manager.upsert(FILM_ID, watched=True, fields_set={"watched"})
            self.assertTrue(on["manual_watched"])
        with Session(self.engine) as session:
            rows = session.exec(select(Viewing)).all()
            self.assertEqual(len(rows), 5)
            self.assertEqual(len([row for row in rows if row.source == "diary"]), 4)
            restored = session.exec(select(Viewing).where(Viewing.source == "manual")).one()
            self.assertEqual(restored.id, manual_id)
            self.assertEqual((restored.rating, restored.notes), (4, "Keep the original manual impression"))
            self.assertEqual((restored.watched_at, restored.watched_at_precision), ("2025", "year"))
            self.assertIsNone(restored.deleted_at)
        with patch.object(viewings_module, "engine", self.engine), patch.object(user_state_module, "engine", self.engine):
            viewings_module.viewing_manager.update(manual_id, None)
            manager.upsert(FILM_ID, watched=False, fields_set={"watched"})
            manager.upsert(FILM_ID, watched=True, fields_set={"watched"})
            restored = next(row for row in viewings_module.viewing_manager.list_film(FILM_ID) if row["id"] == manual_id)
            self.assertEqual((restored["watched_at"], restored["watched_at_precision"]), (None, "unknown"))
            self.assertEqual((restored["rating"], restored["notes"]), (4, "Keep the original manual impression"))

    def test_export_reviews_and_legacy_validation_are_compatible(self):
        self.upgrade()
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE viewing SET rating=4,notes='Per-viewing note'"))
        payload, _schema_version = build_export_payload(database_engine=self.engine)
        _validate_payload(payload)
        self.assertEqual(payload["profile_states"][0]["rating"], 3)
        self.assertEqual(payload["viewings"][0]["rating"], 4)
        self.assertEqual(payload["viewings"][0]["notes"], "Per-viewing note")
        package = Path(self.tmp.name) / "reviews.zip"
        export_package(package, database_engine=self.engine)
        self.assertEqual(validate_package(package)["status"], "passed")
        legacy = copy.deepcopy(payload)
        for row in legacy["viewings"]:
            row.pop("rating")
            row.pop("notes")
        _validate_payload(legacy)
        for field in ("rating", "notes"):
            optional = copy.deepcopy(payload)
            optional["viewings"][0].pop(field)
            _validate_payload(optional)
            optional["viewings"][0][field] = None
            _validate_payload(optional)
        for field, value in [("rating", True), ("rating", 4.5), ("rating", 0), ("notes", 123),
                             ("notes", "x" * 10001), ("notes", "a\0b"), ("unexpected", "bad")]:
            invalid = copy.deepcopy(payload)
            invalid["viewings"][0][field] = value
            with self.subTest(field=field, value=str(value)[:20]), self.assertRaises(PortabilityError):
                _validate_payload(invalid)


if __name__ == "__main__":
    unittest.main()
