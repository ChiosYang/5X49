import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlmodel import SQLModel, Session, create_engine, select

import app.database as database
import app.services.analysis as analysis_module
import app.services.event_store as event_store_module
import app.services.library as library_module
from app.models import EventRecord
from app.services.analysis import analysis_service
from app.services.library import library_manager


class EventSourcedCommandTests(unittest.TestCase):
    def setUp(self):
        self._original_analysis_engine = analysis_module.engine
        self._original_database_engine = database.engine
        self._original_event_store_engine = event_store_module.engine
        self._original_library_engine = library_module.engine
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.engine = create_engine(f"sqlite:///{self.tmp_path / 'library.db'}")
        analysis_module.engine = self.engine
        database.engine = self.engine
        event_store_module.engine = self.engine
        library_module.engine = self.engine
        SQLModel.metadata.create_all(self.engine)

    def tearDown(self):
        analysis_module.engine = self._original_analysis_engine
        database.engine = self._original_database_engine
        event_store_module.engine = self._original_event_store_engine
        library_module.engine = self._original_library_engine
        self.engine.dispose()
        self._tmp.cleanup()

    def test_ignore_movie_updates_state_through_event_projection(self):
        library_manager.add_movies([self._movie("local_ignore")])

        projected = library_manager.ignore_movie("local_ignore")

        self.assertIsNotNone(projected)
        self.assertEqual(projected["library_status"], "ignored")
        stored = library_manager.get_movie("local_ignore")
        self.assertEqual(stored["library_status"], "ignored")
        event = self._latest_event("MovieIgnored")
        self.assertEqual(event.aggregate_id, "local_ignore")

    def test_mark_missing_updates_state_through_event_projection(self):
        library_manager.add_movies([{
            **self._movie("local_missing"),
            "last_seen_at": "2026-05-20T00:00:00+00:00",
        }])

        updated = library_manager.mark_missing_not_seen_since("2026-05-21T00:00:00+00:00")

        self.assertEqual(updated, 1)
        stored = library_manager.get_movie("local_missing")
        self.assertEqual(stored["library_status"], "missing")
        self.assertIsNotNone(stored["missing_since"])
        event = self._latest_event("MovieMarkedMissing")
        self.assertEqual(event.aggregate_id, "local_missing")

    def test_analysis_updates_state_through_events(self):
        library_manager.add_movies([self._movie("local_analysis")])

        with patch.object(
            analysis_service.historian,
            "analyze_genealogy",
            return_value={"micro_genre": "Digital noir - Reality-bending cyber thriller"},
        ):
            analysis_service.analyze_movie("local_analysis")

        stored = library_manager.get_movie("local_analysis")
        self.assertEqual(stored["analysis_status"], "completed")
        self.assertEqual(stored["micro_genre"], "Digital noir")
        self.assertEqual(stored["micro_genre_definition"], "Reality-bending cyber thriller")
        self.assertIsNotNone(self._latest_event("AnalysisStarted"))
        self.assertIsNotNone(self._latest_event("AnalysisCompleted"))

    def _latest_event(self, event_type: str) -> EventRecord:
        with Session(self.engine) as session:
            return session.exec(
                select(EventRecord)
                .where(EventRecord.type == event_type)
                .order_by(EventRecord.occurred_at.desc(), EventRecord.id.desc())
            ).first()

    def _movie(self, movie_id: str) -> dict:
        return {
            "id": movie_id,
            "title": movie_id,
            "title_cn": movie_id,
            "year": 2026,
            "library_status": "available",
            "metadata_source": "filename",
            "scrape_status": "pending",
        }


if __name__ == "__main__":
    unittest.main()
