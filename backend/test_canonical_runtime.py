import tempfile
import unittest
from pathlib import Path

from sqlmodel import Session, create_engine, select

import app.database as database
import app.services.event_store as event_store_module
import app.services.library as library_module
import app.services.operation_snapshots as snapshots_module
import app.services.user_state as user_state_module
from app.canonical_models import (
    AssertionPredicate,
    Concept,
    Film,
    FilmProfileState,
    LibraryItem,
    Setting,
    Viewing,
)
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.services.library import library_manager
from app.services.operation_snapshots import operation_snapshot_service
from app.services.canonical_runtime import canonical_runtime_writer
from app.services.user_state import film_profile_state_manager


class FreshCanonicalRuntimeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.database_path = self.root / "library.db"
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, self.database_path, app_version="test", backup_required=False)
        self._engines = {
            module: module.engine
            for module in (
                database,
                event_store_module,
                library_module,
                snapshots_module,
                user_state_module,
            )
        }
        for module in self._engines:
            module.engine = self.engine

    def tearDown(self):
        for module, original in self._engines.items():
            module.engine = original
        self.engine.dispose()
        self._tmp.cleanup()

    def test_two_library_editions_share_one_film_and_primary_selection_is_stable(self):
        first_path = self._video("first.mkv", b"first")
        second_path = self._video("second.mkv", b"second")
        library_manager.add_observations([
            self._observation(first_path, title="Shared Film", tmdb_id="42", seen="2026-08-25T00:00:00Z"),
            self._observation(second_path, title="Shared Film", tmdb_id="42", seen="2026-08-26T00:00:00Z"),
        ])

        films = library_manager.list_films()
        self.assertEqual(len(films), 1)
        detail = library_manager.get_film(films[0]["id"])
        self.assertEqual(len(detail["editions"]), 2)
        self.assertEqual(detail["primary_item"]["video"]["locator"], str(second_path.resolve()))
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(Film)).all()), 1)
            self.assertEqual(len(session.exec(select(LibraryItem)).all()), 2)

    def test_demo_seed_is_film_centric_and_idempotent(self):
        first = library_manager.seed_test_data()
        second = library_manager.seed_test_data()

        self.assertEqual(len(first), 5)
        self.assertEqual([film["id"] for film in first], [film["id"] for film in second])
        self.assertTrue(all(film["id"].startswith("film_") for film in first))
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(Film)).all()), 5)
            self.assertEqual(len(session.exec(select(LibraryItem)).all()), 5)

    def test_ignored_only_film_is_hidden_from_list_but_available_by_id(self):
        path = self._video("ignored.mkv", b"ignored")
        library_manager.add_observations([self._observation(path, title="Ignored")])
        film = library_manager.list_films()[0]
        item_id = film["primary_item"]["id"]
        library_manager.ignore_item(item_id)

        self.assertEqual(library_manager.list_films(), [])
        detail = library_manager.get_film(film["id"])
        self.assertIsNotNone(detail)
        self.assertEqual(detail["editions"][0]["status"], "ignored")

    def test_manual_unwatch_does_not_remove_other_viewing_sources(self):
        path = self._video("viewing.mkv", b"viewing")
        library_manager.add_observations([self._observation(path, title="Viewing")])
        film_id = library_manager.list_films()[0]["id"]
        watched = film_profile_state_manager.upsert(
            film_id,
            watched=True,
            watched_at="2026-08-24",
            fields_set={"watched", "watched_at"},
        )
        self.assertTrue(watched["watched"])
        with Session(self.engine) as session:
            profile_id = canonical_runtime_writer.local_profile_id(session)
            session.add(
                Viewing(
                    id="view_diary_" + "d" * 20,
                    profile_id=profile_id,
                    film_id=film_id,
                    watched_at="2026-08-25T20:00:00Z",
                    watched_at_precision="timestamp",
                    source="diary",
                    source_record_id="diary-1",
                    review_status="confirmed",
                )
            )
            session.commit()

        unwatched = film_profile_state_manager.upsert(film_id, watched=False, fields_set={"watched"})
        self.assertTrue(unwatched["watched"])
        with Session(self.engine) as session:
            manual = session.exec(select(Viewing).where(Viewing.source == "manual")).one()
            diary = session.exec(select(Viewing).where(Viewing.source == "diary")).one()
            self.assertIsNotNone(manual.deleted_at)
            self.assertIsNone(diary.deleted_at)
        self.assertEqual(len(film_profile_state_manager.watch_history()), 1)

    def test_normal_clear_preserves_film_state_and_rescan_restores_same_item(self):
        path = self._video("restore.mkv", b"restore")
        observation = self._observation(path, title="Restore", tmdb_id="101")
        library_manager.add_observations([observation])
        film = library_manager.list_films()[0]
        film_id = film["id"]
        item_id = film["primary_item"]["id"]
        film_profile_state_manager.upsert(film_id, favorite=True, rating=5, fields_set={"favorite", "rating"})

        self.assertEqual(library_manager.clear_library(), 1)
        self.assertEqual(library_manager.list_films(), [])
        library_manager.add_observations([observation])
        restored = library_manager.list_films()[0]
        self.assertEqual(restored["id"], film_id)
        self.assertEqual(restored["primary_item"]["id"], item_id)
        self.assertTrue(restored["profile_state"]["favorite"])
        self.assertEqual(restored["profile_state"]["rating"], 5)

    def test_deep_clear_removes_domain_rows_and_preserves_reference_and_settings(self):
        path = self._video("clear.mkv", b"clear")
        library_manager.add_observations([self._observation(path, title="Clear")])
        with Session(self.engine) as session:
            session.add(Setting(key="language", value="en"))
            session.commit()

        counts = library_manager.clear_all_data()
        self.assertEqual(counts["films"], 1)
        self.assertEqual(counts["library_items"], 1)
        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(Film)).all(), [])
            self.assertEqual(session.exec(select(FilmProfileState)).all(), [])
            self.assertEqual(len(session.exec(select(AssertionPredicate)).all()), 9)
            self.assertEqual(len(session.exec(select(Concept).where(Concept.kind == "genre")).all()), 19)
            self.assertEqual(session.get(Setting, "language").value, "en")

    def test_ignore_snapshot_preview_restore_and_state_drift_conflict(self):
        path = self._video("snapshot.mkv", b"snapshot")
        library_manager.add_observations([self._observation(path, title="Snapshot")])
        item_id = library_manager.list_films()[0]["primary_item"]["id"]
        library_manager.ignore_item(item_id)
        with Session(self.engine) as session:
            snapshot_id = session.exec(select(snapshots_module.OperationSnapshot.id)).one()
        preview = operation_snapshot_service.preview(snapshot_id)
        self.assertTrue(preview["current_matches_after"])
        restored = operation_snapshot_service.restore(snapshot_id, preview["confirmation_token"])
        self.assertEqual(restored["status"], "restored")
        self.assertEqual(library_manager.get_item(item_id)["status"], "available")

    def _video(self, name: str, content: bytes) -> Path:
        folder = self.root / Path(name).stem
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_bytes(content)
        return path

    @staticmethod
    def _observation(path: Path, *, title: str, tmdb_id: str | None = None, seen: str = "2026-08-26T00:00:00Z"):
        return {
            "title": title,
            "original_title": title,
            "year": 2026,
            "tmdb_id": tmdb_id,
            "media_path": str(path.resolve()),
            "video_file": path.name,
            "folder_path": str(path.parent.resolve()),
            "folder_name": path.parent.name,
            "file_size": path.stat().st_size,
            "file_mtime": path.stat().st_mtime,
            "library_status": "available",
            "metadata_source": "filename",
            "scrape_status": "pending",
            "last_seen_at": seen,
        }


if __name__ == "__main__":
    unittest.main()
