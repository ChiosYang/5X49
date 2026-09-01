import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session, create_engine, select

import app.database as database
import app.services.event_store as event_store_module
import app.services.library as library_module
import app.services.user_state as user_state_module
import app.services.viewings as viewings_module
from app.canonical_models import Film, LocalProfile, Viewing
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.models import EventRecord
from app.services.canonical_runtime import canonical_runtime_writer
from app.services.library import library_manager
from app.services.user_state import film_profile_state_manager
from app.services.viewings import (
    ViewingDateError,
    ViewingNotFound,
    ViewingReadOnly,
    normalize_watched_at,
    viewing_manager,
)


class ViewingDateContractTests(unittest.TestCase):
    def test_supported_date_precisions_are_normalized(self):
        self.assertEqual(normalize_watched_at("2026-08-31"), ("2026-08-31", "date"))
        self.assertEqual(normalize_watched_at("2026"), ("2026", "year"))
        timestamp, precision = normalize_watched_at("2026-08-31T20:15:00+08:00")
        self.assertEqual(timestamp, "2026-08-31T20:15:00+08:00")
        self.assertEqual(precision, "timestamp")
        self.assertEqual(normalize_watched_at(None), (None, "unknown"))

    def test_invalid_dates_and_timezone_less_timestamps_are_rejected(self):
        for value in ("2026-02-30", "0000", "2026-08-31T20:15:00", "not-a-date"):
            with self.subTest(value=value), self.assertRaises(ViewingDateError):
                normalize_watched_at(value)


class DiaryServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.database_path = self.root / "library.db"
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, self.database_path, app_version="test", backup_required=False)
        self.modules = (database, event_store_module, library_module, user_state_module, viewings_module)
        self.original_engines = {module: module.engine for module in self.modules}
        for module in self.modules:
            module.engine = self.engine

        media = self.root / "diary.mkv"
        media.write_bytes(b"diary")
        library_manager.add_observations([{
            "title": "Diary Film",
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
        self.film_id = library_manager.list_films()[0]["id"]

    def tearDown(self):
        for module, original in self.original_engines.items():
            module.engine = original
        self.engine.dispose()
        self._tmp.cleanup()

    def test_multiple_same_day_viewings_remain_independent_and_paginate(self):
        first = viewing_manager.create(self.film_id, "2026-08-30")
        second = viewing_manager.create(self.film_id, "2026-08-30")
        unknown = viewing_manager.create(self.film_id, None)

        self.assertNotEqual(first["id"], second["id"])
        film_viewings = viewing_manager.list_film(self.film_id)
        self.assertEqual(len(film_viewings), 3)
        self.assertEqual(film_viewings[-1]["id"], unknown["id"])
        page = viewing_manager.list_profile(limit=2, offset=0)
        self.assertEqual(page["total"], 3)
        self.assertEqual(page["next_offset"], 2)
        last_page = viewing_manager.list_profile(limit=2, offset=2)
        self.assertIsNone(last_page["next_offset"])
        filtered = viewing_manager.list_profile(limit=100, offset=0, film_id=self.film_id)
        self.assertEqual(filtered["total"], 3)

    def test_recent_view_selects_one_per_film_before_pagination(self):
        viewing_manager.create(self.film_id, "2024-01-01")
        latest = viewing_manager.create(self.film_id, "2026-08-31")
        viewing_manager.create(self.film_id, None)
        second_root = self.root / "second-film"
        second_root.mkdir()
        second_media = second_root / "second.mkv"
        second_media.write_bytes(b"second")
        library_manager.add_observations([{
            "title": "Second Diary Film",
            "year": 2025,
            "media_path": str(second_media.resolve()),
            "video_file": second_media.name,
            "folder_path": str(second_root.resolve()),
            "folder_name": second_root.name,
            "file_size": second_media.stat().st_size,
            "file_mtime": second_media.stat().st_mtime,
            "library_status": "available",
            "metadata_source": "filename",
            "scrape_status": "pending",
        }])
        second_film_id = next(
            film["id"] for film in library_manager.list_films() if film["id"] != self.film_id
        )
        second_latest = viewing_manager.create(second_film_id, "2025")

        first_page = viewing_manager.list_profile(view="recent", limit=1, offset=0)
        second_page = viewing_manager.list_profile(view="recent", limit=1, offset=1)
        filtered = viewing_manager.list_profile(view="recent", film_id=self.film_id)

        self.assertEqual(first_page["total"], 2)
        self.assertEqual(first_page["next_offset"], 1)
        self.assertEqual(first_page["items"][0]["viewing"]["id"], latest["id"])
        self.assertEqual(second_page["items"][0]["viewing"]["id"], second_latest["id"])
        self.assertIsNone(second_page["next_offset"])
        self.assertEqual(filtered["total"], 1)
        self.assertEqual(filtered["items"][0]["viewing"]["id"], latest["id"])

    def test_create_update_delete_write_bounded_events_and_delete_is_idempotent(self):
        created = viewing_manager.create(self.film_id, "2026")
        updated = viewing_manager.update(created["id"], "2026-08-31")
        first_delete = viewing_manager.delete(created["id"])
        second_delete = viewing_manager.delete(created["id"])

        self.assertEqual(updated["watched_at_precision"], "date")
        self.assertTrue(first_delete["changed"])
        self.assertFalse(second_delete["changed"])
        self.assertEqual(first_delete["viewing_id"], second_delete["viewing_id"])
        with Session(self.engine) as session:
            events = session.exec(
                select(EventRecord)
                .where(EventRecord.aggregate_id == created["id"])
                .order_by(EventRecord.occurred_at, EventRecord.id)
            ).all()
            self.assertEqual(
                [event.type for event in events],
                ["ViewingCreated", "ViewingUpdated", "ViewingDeleted"],
            )
            self.assertNotIn(str(self.root.resolve()), str([event.payload for event in events]))

    def test_external_source_is_read_only(self):
        with Session(self.engine) as session:
            profile_id = canonical_runtime_writer.local_profile_id(session)
            viewing = Viewing(
                id="view_" + "e" * 32,
                profile_id=profile_id,
                film_id=self.film_id,
                watched_at="2025",
                watched_at_precision="year",
                source="import",
                source_record_id="external-1",
                review_status="confirmed",
            )
            session.add(viewing)
            session.commit()
            viewing_id = viewing.id

        with self.assertRaises(ViewingReadOnly):
            viewing_manager.update(viewing_id, "2026")
        with self.assertRaises(ViewingReadOnly):
            viewing_manager.delete(viewing_id)

    def test_manual_delete_preserves_diary_and_derived_state(self):
        film_profile_state_manager.upsert(self.film_id, watched=True, fields_set={"watched"})
        diary = viewing_manager.create(self.film_id, "2026-08-31")
        before = film_profile_state_manager.get(self.film_id)
        self.assertTrue(before["watched"])
        self.assertTrue(before["manual_watched"])

        with Session(self.engine) as session:
            manual_id = session.exec(
                select(Viewing.id)
                .where(Viewing.film_id == self.film_id)
                .where(Viewing.source == "manual")
            ).one()
        viewing_manager.delete(manual_id)

        after = film_profile_state_manager.get(self.film_id)
        self.assertTrue(after["watched"])
        self.assertFalse(after["manual_watched"])
        self.assertEqual(viewing_manager.list_film(self.film_id)[0]["id"], diary["id"])
        viewing_manager.delete(diary["id"])
        self.assertFalse(film_profile_state_manager.get(self.film_id)["watched"])

    def test_recent_view_is_scoped_to_the_local_profile(self):
        viewing_manager.create(self.film_id, "2026-08-31")
        with Session(self.engine) as session:
            other = LocalProfile(
                id="profile_" + "f" * 32,
                profile_key="other",
                display_name="Other",
            )
            session.add(other)
            session.add(
                Viewing(
                    id="view_" + "f" * 32,
                    profile_id=other.id,
                    film_id=self.film_id,
                    watched_at="2027-01-01",
                    watched_at_precision="date",
                    source="diary",
                    source_record_id="other-1",
                    review_status="confirmed",
                )
            )
            session.commit()

        recent = viewing_manager.list_profile(view="recent")
        self.assertEqual(recent["total"], 1)
        self.assertEqual(recent["items"][0]["viewing"]["watched_at"], "2026-08-31")

    def test_event_failure_rolls_back_viewing_and_projection(self):
        before = library_manager.get_film(self.film_id)["profile_state"]
        with patch.object(
            event_store_module.event_store,
            "append_in_session",
            side_effect=RuntimeError("event failed"),
        ):
            with self.assertRaises(RuntimeError):
                viewing_manager.create(self.film_id, "2026-08-31")

        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(Viewing)).all(), [])
            self.assertEqual(
                session.exec(select(EventRecord).where(EventRecord.type == "ViewingCreated")).all(),
                [],
            )
        self.assertEqual(library_manager.get_film(self.film_id)["profile_state"], before)

    def test_projection_failure_rolls_back_viewing_and_event(self):
        with patch(
            "app.services.projections.projection_coordinator.refresh_film",
            side_effect=RuntimeError("projection failed"),
        ):
            with self.assertRaises(RuntimeError):
                viewing_manager.create(self.film_id, "2026-08-31")

        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(Viewing)).all(), [])
            self.assertEqual(
                session.exec(select(EventRecord).where(EventRecord.type == "ViewingCreated")).all(),
                [],
            )

    def test_library_clear_preserves_viewings_and_deep_clear_removes_them(self):
        viewing_manager.create(self.film_id, "2026-08-31")
        library_manager.clear_library()
        page = viewing_manager.list_profile()
        self.assertEqual(page["total"], 1)
        self.assertFalse(page["items"][0]["film"]["in_library"])
        recent = viewing_manager.list_profile(view="recent")
        self.assertEqual(recent["total"], 1)
        self.assertFalse(recent["items"][0]["film"]["in_library"])

        library_manager.clear_all_data()
        self.assertEqual(viewing_manager.list_profile()["total"], 0)

    def test_missing_or_deleted_viewing_is_not_exposed(self):
        missing = "view_" + "0" * 32
        with self.assertRaises(ViewingNotFound):
            viewing_manager.update(missing, "2026")
        with self.assertRaises(ViewingNotFound):
            viewing_manager.delete(missing)
        self.assertIsNone(viewing_manager.list_film("film_" + "0" * 32))


if __name__ == "__main__":
    unittest.main()
