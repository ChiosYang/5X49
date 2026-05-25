import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlmodel import SQLModel, create_engine
from sqlmodel import Session, select

import app.database as database
import app.services.event_store as event_store_module
import app.services.library as library_module
from app.models import EventRecord
from app.services.external_scores.service import ExternalScoreService
from app.services.external_scores.tspdt import TSPDTDataset, normalize_director, normalize_title
from app.services.library import library_manager


class ExternalScoresTests(unittest.TestCase):
    def setUp(self):
        self._original_database_engine = database.engine
        self._original_event_store_engine = event_store_module.engine
        self._original_library_engine = library_module.engine
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.engine = create_engine(f"sqlite:///{self.tmp_path / 'library.db'}")
        database.engine = self.engine
        event_store_module.engine = self.engine
        library_module.engine = self.engine
        SQLModel.metadata.create_all(self.engine)

        self.dataset_path = self.tmp_path / "tspdt.csv"
        self.dataset_path.write_text(
            "\n".join(
                [
                    '"Pos","2025","Title","Director","Year","Country","Mins"',
                    '"6","6","Godfather, The","Coppola, Francis Ford","1972","USA","175"',
                    '"997","1039","Lady Windermere\'s Fan","Lubitsch, Ernst","1925","USA","120"',
                ]
            ),
            encoding="utf-8",
        )
        self.service = ExternalScoreService(TSPDTDataset(self.dataset_path))

    def tearDown(self):
        database.engine = self._original_database_engine
        event_store_module.engine = self._original_event_store_engine
        library_module.engine = self._original_library_engine
        self.engine.dispose()
        self._tmp.cleanup()

    def test_normalizes_tspdt_title_and_director(self):
        self.assertEqual(normalize_title("Godfather, The"), normalize_title("The Godfather"))
        self.assertEqual(normalize_director("Coppola, Francis Ford"), "Francis Ford Coppola")

    def test_refresh_movie_adds_tspdt_rank(self):
        library_manager.add_movies(
            [
                {
                    "id": "238_1972",
                    "title": "The Godfather",
                    "title_cn": "The Godfather",
                    "year": 1972,
                    "director": "Francis Ford Coppola",
                    "library_status": "available",
                }
            ]
        )

        with patch("app.services.external_scores.service.library_manager.upsert_movie") as upsert_movie:
            result = self.service.refresh_movie("238_1972")

        self.assertEqual(result["status"], "success")
        upsert_movie.assert_not_called()
        self.assertEqual(result["updated_sources"], ["tspdt"])
        stored = library_manager.get_movie("238_1972")
        self.assertIsNotNone(stored)
        self.assertEqual(stored["external_scores"][0]["source"], "tspdt")
        self.assertEqual(stored["external_scores"][0]["rank"], 6)
        self.assertEqual(stored["external_scores"][0]["previous_rank"], 6)
        self.assertEqual(stored["external_scores"][0]["matched_by"], "title_year_director")
        self.assertGreaterEqual(stored["external_scores"][0]["confidence"], 0.95)
        with Session(self.engine) as session:
            event = session.exec(
                select(EventRecord).where(EventRecord.type == "ExternalScoresRefreshed")
            ).one()
        self.assertEqual(event.payload["changed_fields"], ["external_scores", "external_scores_updated_at"])
        self.assertIsNone(event.payload["previous"]["external_scores"])
        self.assertEqual(event.payload["current"]["external_scores"][0]["source"], "tspdt")
        self.assertIsNone(event.payload["current"]["external_scores_error"])

    def test_refresh_movie_does_not_succeed_when_projection_fails(self):
        library_manager.add_movies(
            [
                {
                    "id": "238_1972",
                    "title": "The Godfather",
                    "title_cn": "The Godfather",
                    "year": 1972,
                    "director": "Francis Ford Coppola",
                    "library_status": "available",
                }
            ]
        )

        with patch("app.services.external_scores.service.event_store.append_and_project", return_value=({}, None)):
            with self.assertRaises(RuntimeError):
                self.service.refresh_movie("238_1972")

        stored = library_manager.get_movie("238_1972")
        self.assertIsNone(stored["external_scores"])

    def test_refresh_movie_skips_unmatched_movie(self):
        library_manager.add_movies(
            [
                {
                    "id": "local_unknown",
                    "title": "Unknown Local Movie",
                    "title_cn": "Unknown Local Movie",
                    "year": 2024,
                    "director": "Unknown Director",
                    "library_status": "available",
                }
            ]
        )

        result = self.service.refresh_movie("local_unknown")

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["skipped_sources"], ["tspdt"])
        stored = library_manager.get_movie("local_unknown")
        self.assertIsNone(stored["external_scores"])


if __name__ == "__main__":
    unittest.main()
