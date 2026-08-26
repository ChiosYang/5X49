import tempfile
import unittest
from pathlib import Path

from sqlmodel import Session, create_engine, select

import app.database as database
import app.services.event_store as event_store_module
import app.services.external_scores.service as score_module
import app.services.library as library_module
from app.canonical_models import ExternalScoreRefreshState, FilmExternalScore
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.models import EventRecord
from app.services.external_scores.service import ExternalScoreService
from app.services.external_scores.tspdt import TSPDTDataset, normalize_director, normalize_title
from app.services.library import library_manager


class ExternalScoresTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        path = self.root / "library.db"
        self.engine = create_engine(f"sqlite:///{path}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, path, app_version="test", backup_required=False)
        self.modules = (database, event_store_module, library_module, score_module)
        self.original = {module: module.engine for module in self.modules}
        for module in self.modules:
            module.engine = self.engine
        dataset_path = self.root / "tspdt.csv"
        dataset_path.write_text(
            '\n'.join([
                '"Pos","2025","Title","Director","Year","Country","Mins"',
                '"6","6","Godfather, The","Coppola, Francis Ford","1972","USA","175"',
            ]),
            encoding="utf-8",
        )
        self.service = ExternalScoreService(TSPDTDataset(dataset_path))

    def tearDown(self):
        for module, engine in self.original.items():
            module.engine = engine
        self.engine.dispose()
        self._tmp.cleanup()

    def test_normalizes_tspdt_title_and_director(self):
        self.assertEqual(normalize_title("Godfather, The"), normalize_title("The Godfather"))
        self.assertEqual(normalize_director("Coppola, Francis Ford"), "Francis Ford Coppola")

    def test_refresh_film_writes_normalized_score_state_and_bounded_event(self):
        film_id = self._add_film("The Godfather", 1972, "Francis Ford Coppola")
        result = self.service.refresh_film(film_id)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["updated_sources"], ["tspdt"])
        self.assertEqual(result["film"]["external_scores"][0]["rank"], 6)
        with Session(self.engine) as session:
            score = session.exec(select(FilmExternalScore)).one()
            state = session.exec(select(ExternalScoreRefreshState)).one()
            event = session.exec(select(EventRecord).where(EventRecord.type == "ExternalScoresRefreshed")).one()
        self.assertEqual(score.film_id, film_id)
        self.assertEqual(score.kind, "rank")
        self.assertEqual(state.status, "succeeded")
        self.assertEqual(event.aggregate_type, "film")
        self.assertEqual(event.aggregate_id, film_id)
        self.assertNotIn("title", event.payload)

    def test_unmatched_film_records_refresh_state_without_fake_score(self):
        film_id = self._add_film("Unknown", 2026, "Nobody")
        result = self.service.refresh_film(film_id)
        self.assertEqual(result["status"], "skipped")
        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(FilmExternalScore)).all(), [])
            self.assertEqual(session.exec(select(ExternalScoreRefreshState)).one().status, "succeeded")

    def _add_film(self, title: str, year: int, director: str) -> str:
        media = self.root / f"{title}.mkv"
        media.write_bytes(title.encode("utf-8"))
        library_manager.add_observations([{
            "title": title,
            "original_title": title,
            "year": year,
            "director": director,
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
        return library_manager.list_films()[-1]["id"]


if __name__ == "__main__":
    unittest.main()
