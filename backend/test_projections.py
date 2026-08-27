import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session, create_engine, delete, select

import app.database as database
import app.services.event_store as event_store_module
import app.services.library as library_module
import app.services.operation_snapshots as snapshots_module
import app.services.user_state as user_state_module
from app.canonical_models import (
    Film,
    FilmDetailReadModel,
    LibraryFilmReadModel,
    ProjectionState,
)
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.services.library import library_manager
from app.services.projections import (
    PROJECTION_VERSIONS,
    ProjectionUnavailable,
    projection_coordinator,
    projection_reader,
)


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.database_path = self.root / "library.db"
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, self.database_path, app_version="test", backup_required=False)
        projection_coordinator.bootstrap(self.engine)
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

    def test_domain_commit_refreshes_read_models_and_redacts_locator(self):
        film_id = self._seed("Projected Film")
        rows = projection_reader.list_films(self.engine)
        self.assertEqual([row["id"] for row in rows], [film_id])
        self.assertEqual(rows[0]["primary_item"]["video"]["file_name"], "projected.mkv")
        self.assertNotIn("locator", rows[0]["primary_item"]["video"])
        self.assertIn("resolved_sources", rows[0])
        with Session(self.engine) as session:
            self.assertIsNotNone(session.get(LibraryFilmReadModel, film_id))
            self.assertIsNotNone(session.get(FilmDetailReadModel, film_id))
            self.assertTrue(projection_coordinator.is_ready(session))

    def test_search_projection_and_missing_state_have_strict_behavior(self):
        film_id = self._seed("Searchable Cinema")
        self.assertEqual(
            [row["id"] for row in projection_reader.list_films(self.engine, query="searchable")],
            [film_id],
        )
        self.assertEqual(projection_reader.list_films(self.engine, query="absent"), [])
        with Session(self.engine) as session:
            session.exec(delete(ProjectionState).where(ProjectionState.name == "library"))
            session.commit()
        with self.assertRaises(ProjectionUnavailable):
            projection_reader.list_films(self.engine)

    def test_projection_failure_rolls_back_domain_write(self):
        with patch.object(
            projection_coordinator,
            "_upsert_detail",
            side_effect=RuntimeError("projection failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "projection failed"):
                library_manager.add_observations([self._observation("Rollback")])
        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(Film)).all(), [])
            self.assertEqual(session.exec(select(LibraryFilmReadModel)).all(), [])

    def test_rebuild_is_repeatable_and_verifies_hashes(self):
        self._seed("Digest")
        with Session(self.engine) as session:
            first = projection_coordinator.rebuild_all(session)
            session.commit()
        with Session(self.engine) as session:
            second = projection_coordinator.rebuild_all(session)
            session.commit()
            self.assertEqual(
                {key: value["digest"] for key, value in first["checks"].items()},
                {key: value["digest"] for key, value in second["checks"].items()},
            )
            for name, version in PROJECTION_VERSIONS.items():
                self.assertEqual(session.get(ProjectionState, name).projection_version, version)

    def _seed(self, title: str) -> str:
        library_manager.add_observations([self._observation(title)])
        with Session(self.engine) as session:
            return session.exec(select(Film.id)).one()

    def _observation(self, title: str) -> dict:
        folder = self.root / title.replace(" ", "-")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "projected.mkv"
        path.write_bytes(title.encode("utf-8"))
        return {
            "title": title,
            "original_title": title,
            "year": 2026,
            "media_path": str(path.resolve()),
            "video_file": path.name,
            "folder_path": str(path.parent.resolve()),
            "folder_name": path.parent.name,
            "file_size": path.stat().st_size,
            "file_mtime": path.stat().st_mtime,
            "library_status": "available",
            "metadata_source": "filename",
            "scrape_status": "pending",
            "last_seen_at": "2026-08-27T00:00:00Z",
        }


if __name__ == "__main__":
    unittest.main()
