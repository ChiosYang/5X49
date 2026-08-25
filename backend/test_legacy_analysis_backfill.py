import tempfile
import unittest
from pathlib import Path

from sqlmodel import SQLModel, Session, create_engine, select

import app.database as database
import app.services.event_store as event_store_module
import app.services.library as library_module
from app.canonical_models import (
    AnalysisResolutionReview,
    AnalysisRun,
    Assertion,
    AssertionPredicate,
    Evidence,
    LegacyMovieAlias,
)
from app.contracts.analysis_persistence import predicate_seed_rows
from app.models import Movie
from app.services.legacy_analysis_backfill import backfill_legacy_analysis, parse_legacy_analysis
from app.services.library import library_manager


class LegacyAnalysisBackfillTests(unittest.TestCase):
    def setUp(self):
        self._original_database_engine = database.engine
        self._original_event_engine = event_store_module.engine
        self._original_library_engine = library_module.engine
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self._tmp.name) / 'library.db'}")
        database.engine = self.engine
        event_store_module.engine = self.engine
        library_module.engine = self.engine
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add_all([AssertionPredicate(**row) for row in predicate_seed_rows()])
            session.commit()

    def tearDown(self):
        database.engine = self._original_database_engine
        event_store_module.engine = self._original_event_engine
        library_module.engine = self._original_library_engine
        self.engine.dispose()
        self._tmp.cleanup()

    def test_backfill_migrates_resolved_edges_and_reviews_without_copying_raw_output(self):
        library_manager.add_movies([
            self._movie("legacy_subject", "Subject", 2000),
            self._movie("legacy_ancestor", "Known Ancestor", 1970),
        ])
        legacy_payload = {
            "thought_chain": "must not be copied",
            "micro_genre": "Digital noir - Reality-bending thriller",
            "influence_impact": "A bounded legacy summary.",
            "ancestors": [{
                "title": "Known Ancestor",
                "year": 1970,
                "type": "Visual",
                "reason": "A shared visual grammar.",
            }],
            "descendants": [{
                "title": "Unknown Descendant",
                "year": 2020,
                "type": "Theme",
                "reason": "A later thematic echo.",
            }],
            "tmdb_metadata": {"title": "Subject"},
        }
        with Session(self.engine) as session:
            movie = session.get(Movie, "legacy_subject")
            movie.analysis_status = "completed"
            movie.analysis_data = legacy_payload
            session.add(movie)
            session.commit()

        with self.engine.begin() as connection:
            first = backfill_legacy_analysis(connection)
        with self.engine.begin() as connection:
            second = backfill_legacy_analysis(connection)

        self.assertEqual(first.counts["runs_created"], 1)
        self.assertEqual(first.counts["assertions_created"], 1)
        self.assertGreaterEqual(first.counts["reviews_created"], 2)
        self.assertEqual(first.counts["dropped_fields"], 1)
        self.assertEqual(second.counts["runs_created"], 0)
        with Session(self.engine) as session:
            run = session.exec(select(AnalysisRun)).one()
            assertion = session.exec(select(Assertion)).one()
            reviews = session.exec(select(AnalysisResolutionReview)).all()
            evidence = session.exec(select(Evidence)).all()
            movie = session.get(Movie, "legacy_subject")
        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.result_summary, "A bounded legacy summary.")
        self.assertEqual(assertion.predicate, "INFLUENCED_BY")
        self.assertTrue(any(item.predicate == "HAS_MICRO_GENRE" for item in reviews))
        self.assertEqual(evidence, [])
        self.assertEqual(movie.analysis_data, legacy_payload)
        self.assertNotIn("thought_chain", str(run.model_dump()))
        self.assertNotIn("must not be copied", str([item.model_dump() for item in reviews]))

    def test_invalid_legacy_output_creates_failed_run_and_bounded_review(self):
        library_manager.add_movies([self._movie("legacy_invalid", "Invalid", 2001)])
        with Session(self.engine) as session:
            movie = session.get(Movie, "legacy_invalid")
            movie.analysis_status = "completed"
            movie.analysis_data = {"thought_chain": "private", "ancestors": "bad"}
            session.add(movie)
            session.commit()
        with self.engine.begin() as connection:
            report = backfill_legacy_analysis(connection)
        with Session(self.engine) as session:
            run = session.exec(select(AnalysisRun)).one()
            review = session.exec(select(AnalysisResolutionReview)).one()
        self.assertEqual(report.counts["runs_failed"], 1)
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.error_code, "legacy_output_invalid")
        self.assertEqual(review.candidate_summary, {})

    def test_parser_bounds_lists_and_rejects_missing_summary(self):
        film_id = "film_" + "f" * 32
        self.assertIsNone(parse_legacy_analysis({}, film_id).output)
        payload = {
            "influence_impact": "Summary",
            "ancestors": [
                {"title": f"Film {index}", "year": 1900 + index, "reason": "Reason"}
                for index in range(40)
            ],
        }
        parsed = parse_legacy_analysis(payload, film_id)
        self.assertIsNotNone(parsed.output)
        self.assertEqual(len(parsed.output.assertions), 24)

    def _film_id(self, movie_id):
        with Session(self.engine) as session:
            return session.get(LegacyMovieAlias, movie_id).film_id

    @staticmethod
    def _movie(movie_id, title, year):
        return {
            "id": movie_id,
            "title": title,
            "title_cn": title,
            "year": year,
            "library_status": "available",
            "metadata_source": "legacy",
            "scrape_status": "pending",
        }


if __name__ == "__main__":
    unittest.main()
