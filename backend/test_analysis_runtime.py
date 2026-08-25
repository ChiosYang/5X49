import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlmodel import SQLModel, Session, create_engine, select

import app.database as database
import app.services.analysis as analysis_module
import app.services.event_store as event_store_module
import app.services.library as library_module
from app.canonical_models import (
    AnalysisResolutionReview,
    AnalysisRun,
    Assertion,
    AssertionEvidence,
    AssertionPredicate,
    AssertionProvenance,
    Evidence,
    ExternalIdentity,
    Film,
    LegacyMovieAlias,
    LibraryItem,
    LocalProfile,
)
from app.contracts.analysis_persistence import predicate_seed_rows
from app.contracts.analysis_v2 import AnalysisV2Output
from app.models import EventRecord, Movie
from app.services.analysis import AnalysisExecutionError, analysis_service
from app.services.analysis_evidence import (
    EvidenceBatchResult,
    VerifiedEvidenceCandidate,
)
from app.services.historian import AnalysisGenerationResult, AnalysisModelConfiguration
from app.services.library import library_manager


class AnalysisRuntimeTests(unittest.TestCase):
    def setUp(self):
        self._original_analysis_engine = analysis_module.engine
        self._original_database_engine = database.engine
        self._original_event_engine = event_store_module.engine
        self._original_library_engine = library_module.engine
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self._tmp.name) / 'library.db'}")
        analysis_module.engine = self.engine
        database.engine = self.engine
        event_store_module.engine = self.engine
        library_module.engine = self.engine
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add_all([AssertionPredicate(**row) for row in predicate_seed_rows()])
            session.commit()

    def tearDown(self):
        analysis_module.engine = self._original_analysis_engine
        database.engine = self._original_database_engine
        event_store_module.engine = self._original_event_engine
        library_module.engine = self._original_library_engine
        self.engine.dispose()
        self._tmp.cleanup()

    def test_runtime_persists_directional_assertions_evidence_reviews_and_cache(self):
        library_manager.add_movies([
            self._movie("subject", "Subject Film", 2000, "100"),
            self._movie("ancestor", "Earlier Film", 1970, "200"),
            self._movie("descendant", "Later Film", 2020, "300"),
        ])
        subject_id = self._film_id("subject")
        ancestor_id = self._film_id("ancestor")
        descendant_id = self._film_id("descendant")
        output = AnalysisV2Output.model_validate({
            "subject_film_id": subject_id,
            "summary": "A bounded public summary.",
            "assertions": [
                {
                    "predicate": "INFLUENCED_BY",
                    "target": {"entity_type": "film", "entity_id": ancestor_id},
                    "rationale": "The earlier film shaped its visual grammar.",
                    "evidence_candidates": [{
                        "source_title": "Public source",
                        "source_uri": "https://example.com/source",
                        "claim": "The director identified the earlier film as an influence.",
                    }],
                },
                {
                    "predicate": "INFLUENCED_BY",
                    "direction": "target_to_subject",
                    "target": {"entity_type": "film", "entity_id": descendant_id},
                    "rationale": "The later film reuses its central device.",
                },
                {
                    "predicate": "HAS_MICRO_GENRE",
                    "target": {"entity_type": "concept", "display_name": "Digital noir"},
                    "rationale": "Reality-bending cyber thriller.",
                },
            ],
        })
        verified = VerifiedEvidenceCandidate(
            candidate_key="a000:e000",
            candidate=output.assertions[0].evidence_candidates[0],
            source_uri="https://example.com/source",
            content_hash="a" * 64,
            retrieved_at="2026-08-25T00:00:00+00:00",
        )
        with (
            patch.object(
                analysis_service.historian,
                "analysis_configuration",
                return_value=AnalysisModelConfiguration("openrouter", "test-model"),
            ),
            patch.object(
                analysis_service.historian,
                "analyze_v2",
                return_value=AnalysisGenerationResult(output, 10, 20, 0.01, "USD"),
            ) as generate,
            patch.object(
                analysis_service.evidence,
                "verify",
                return_value=EvidenceBatchResult((verified,), ()),
            ),
        ):
            first = analysis_service.analyze_movie("subject")
            second = analysis_service.analyze_movie("subject")

        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(generate.call_count, 1)
        with Session(self.engine) as session:
            runs = session.exec(select(AnalysisRun)).all()
            assertions = session.exec(select(Assertion)).all()
            reviews = session.exec(select(AnalysisResolutionReview)).all()
            evidence = session.exec(select(Evidence)).all()
            links = session.exec(select(AssertionEvidence)).all()
            movie = session.get(Movie, "subject")
            completed_event = session.exec(
                select(EventRecord)
                .where(EventRecord.type == "AnalysisCompleted")
                .order_by(EventRecord.occurred_at.desc())
            ).first()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].status, "succeeded")
        self.assertEqual(runs[0].input_tokens, 10)
        self.assertEqual(len(assertions), 2)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].reason_code, "unresolved_reference")
        self.assertEqual(len(evidence), 1)
        self.assertEqual(len(links), 1)
        self.assertEqual(movie.analysis_status, "completed")
        self.assertEqual(movie.analysis_data["ancestors"][0]["title"], "Earlier Film")
        self.assertEqual(movie.analysis_data["descendants"][0]["title"], "Later Film")
        self.assertEqual(movie.micro_genre, "Digital noir")
        self.assertNotIn("thought_chain", movie.analysis_data)
        self.assertNotIn("evidence_candidates", completed_event.payload["analysis_data"])

    def test_user_rejection_survives_new_model_version_and_is_hidden_from_projection(self):
        library_manager.add_movies([
            self._movie("subject_reject", "Subject", 2000, "110"),
            self._movie("target_reject", "Target", 1980, "210"),
        ])
        subject_id = self._film_id("subject_reject")
        target_id = self._film_id("target_reject")
        output = AnalysisV2Output.model_validate({
            "subject_film_id": subject_id,
            "summary": "Summary",
            "assertions": [{
                "predicate": "INFLUENCED_BY",
                "target": {"entity_type": "film", "entity_id": target_id},
                "rationale": "Model rationale.",
            }],
        })
        self._run_with_output("subject_reject", output, model="model-v1")
        with Session(self.engine) as session:
            assertion = session.exec(select(Assertion)).one()
            profile = session.exec(select(LocalProfile)).first()
            assertion.review_status = "rejected"
            assertion.review_method = "user"
            assertion.reviewed_by_profile_id = profile.id
            assertion.reviewed_at = "2026-08-25T00:00:00+00:00"
            assertion.rationale = "User-owned rationale."
            session.add(assertion)
            session.commit()

        self._run_with_output("subject_reject", output, model="model-v2")
        with Session(self.engine) as session:
            assertion = session.exec(select(Assertion)).one()
            movie = session.get(Movie, "subject_reject")
            provenance = session.exec(select(AssertionProvenance)).all()
        self.assertEqual(assertion.review_status, "rejected")
        self.assertEqual(assertion.rationale, "User-owned rationale.")
        self.assertEqual(len(provenance), 2)
        self.assertEqual(movie.analysis_data["ancestors"], [])

    def test_persistence_failure_rolls_back_completion_and_records_safe_failure(self):
        library_manager.add_movies([
            self._movie("subject_fail", "Subject", 2000, "120"),
            self._movie("target_fail", "Target", 1980, "220"),
        ])
        output = AnalysisV2Output.model_validate({
            "subject_film_id": self._film_id("subject_fail"),
            "summary": "Summary",
            "assertions": [{
                "predicate": "INFLUENCED_BY",
                "target": {"entity_type": "film", "entity_id": self._film_id("target_fail")},
                "rationale": "Rationale.",
            }],
        })
        with (
            patch.object(
                analysis_service.historian,
                "analysis_configuration",
                return_value=AnalysisModelConfiguration("openrouter", "failure-model"),
            ),
            patch.object(
                analysis_service.historian,
                "analyze_v2",
                return_value=AnalysisGenerationResult(output),
            ),
            patch.object(
                analysis_service.evidence,
                "verify",
                return_value=EvidenceBatchResult((), ()),
            ),
            patch(
                "app.services.analysis_runtime.AnalysisRuntimePersistence._upsert_assertion",
                side_effect=RuntimeError("secret database detail"),
            ),
        ):
            with self.assertRaisesRegex(AnalysisExecutionError, "persistence failed"):
                analysis_service.analyze_movie("subject_fail")

        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(Assertion)).all(), [])
            run = session.exec(select(AnalysisRun)).one()
            movie = session.get(Movie, "subject_fail")
            failed = session.exec(select(EventRecord).where(EventRecord.type == "AnalysisFailed")).one()
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.error_code, "analysis_persistence_failed")
        self.assertNotIn("secret", run.error_message)
        self.assertEqual(movie.analysis_status, "failed")
        self.assertNotIn("secret", str(failed.payload))

    def test_verified_tmdb_identity_creates_non_owned_film(self):
        library_manager.add_movies([self._movie("subject_tmdb", "Subject", 2000, "130")])
        output = AnalysisV2Output.model_validate({
            "subject_film_id": self._film_id("subject_tmdb"),
            "summary": "Summary",
            "assertions": [{
                "predicate": "INFLUENCED_BY",
                "target": {
                    "entity_type": "film",
                    "provider": "tmdb.movie",
                    "external_id": "999",
                    "display_name": "Verified Target",
                    "release_year": 1975,
                },
                "rationale": "Rationale.",
            }],
        })
        details = {
            "id": 999,
            "title": "Verified Target",
            "original_title": "Verified Target",
            "original_language": "en",
            "release_date": "1975-01-01",
            "runtime": 101,
            "overview": "Overview",
            "external_ids": {"imdb_id": "tt0000999"},
            "production_countries": [{"iso_3166_1": "US"}],
            "genres": [{"id": 18, "name": "Drama"}],
            "credits": {"crew": [], "cast": []},
        }
        with (
            patch.object(
                analysis_service.historian,
                "analysis_configuration",
                return_value=AnalysisModelConfiguration("openrouter", "tmdb-model"),
            ),
            patch.object(
                analysis_service.historian,
                "analyze_v2",
                return_value=AnalysisGenerationResult(output),
            ),
            patch.object(analysis_service.tmdb, "is_configured", return_value=True),
            patch.object(analysis_service.tmdb, "movie_details", return_value=details),
            patch.object(
                analysis_service.evidence,
                "verify",
                return_value=EvidenceBatchResult((), ()),
            ),
        ):
            analysis_service.analyze_movie("subject_tmdb")

        with Session(self.engine) as session:
            identity = session.exec(
                select(ExternalIdentity)
                .where(ExternalIdentity.provider == "tmdb.movie")
                .where(ExternalIdentity.external_id == "999")
            ).one()
            film = session.get(Film, identity.entity_id)
            item = session.exec(select(LibraryItem).where(LibraryItem.film_id == film.id)).first()
        self.assertEqual(film.canonical_title, "Verified Target")
        self.assertIsNone(item)

    def test_failed_run_is_reused_for_a_successful_retry(self):
        library_manager.add_movies([
            self._movie("subject_retry", "Subject", 2000, "140"),
            self._movie("target_retry", "Target", 1980, "240"),
        ])
        output = AnalysisV2Output.model_validate({
            "subject_film_id": self._film_id("subject_retry"),
            "summary": "Summary",
            "assertions": [{
                "predicate": "INFLUENCED_BY",
                "target": {"entity_type": "film", "entity_id": self._film_id("target_retry")},
                "rationale": "Rationale.",
            }],
        })
        configuration = AnalysisModelConfiguration("openrouter", "retry-model")
        with (
            patch.object(
                analysis_service.historian,
                "analysis_configuration",
                return_value=configuration,
            ),
            patch.object(
                analysis_service.historian,
                "analyze_v2",
                side_effect=ValueError("raw provider output"),
            ),
        ):
            with self.assertRaises(AnalysisExecutionError):
                analysis_service.analyze_movie("subject_retry")
        with (
            patch.object(
                analysis_service.historian,
                "analysis_configuration",
                return_value=configuration,
            ),
            patch.object(
                analysis_service.historian,
                "analyze_v2",
                return_value=AnalysisGenerationResult(output),
            ),
            patch.object(
                analysis_service.evidence,
                "verify",
                return_value=EvidenceBatchResult((), ()),
            ),
        ):
            result = analysis_service.analyze_movie("subject_retry")
        with Session(self.engine) as session:
            runs = session.exec(select(AnalysisRun)).all()
        self.assertFalse(result["cached"])
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].status, "succeeded")
        self.assertEqual(runs[0].attempt_count, 2)

    def test_missing_tmdb_key_and_ambiguous_local_title_create_reviews(self):
        library_manager.add_movies([
            self._movie("subject_review", "Subject", 2000, "150"),
            self._movie("duplicate_one", "Duplicate", 1985, "250"),
            self._movie("duplicate_two", "Duplicate", 1985, "251"),
        ])
        output = AnalysisV2Output.model_validate({
            "subject_film_id": self._film_id("subject_review"),
            "summary": "Summary survives unresolved relationship candidates.",
            "assertions": [
                {
                    "predicate": "INFLUENCED_BY",
                    "target": {
                        "entity_type": "film",
                        "provider": "tmdb.movie",
                        "external_id": "9999",
                        "display_name": "Remote Film",
                        "release_year": 1970,
                    },
                    "rationale": "Remote identity needs provider verification.",
                },
                {
                    "predicate": "INFLUENCED_BY",
                    "target": {
                        "entity_type": "film",
                        "display_name": "Duplicate",
                        "release_year": 1985,
                    },
                    "rationale": "A name-only reference must be unique.",
                },
            ],
        })
        with (
            patch.object(
                analysis_service.historian,
                "analysis_configuration",
                return_value=AnalysisModelConfiguration("openrouter", "review-model"),
            ),
            patch.object(
                analysis_service.historian,
                "analyze_v2",
                return_value=AnalysisGenerationResult(output),
            ),
            patch.object(analysis_service.tmdb, "is_configured", return_value=False),
            patch.object(
                analysis_service.evidence,
                "verify",
                return_value=EvidenceBatchResult((), ()),
            ),
        ):
            result = analysis_service.analyze_movie("subject_review")

        with Session(self.engine) as session:
            run = session.exec(select(AnalysisRun)).one()
            assertions = session.exec(select(Assertion)).all()
            reviews = session.exec(select(AnalysisResolutionReview)).all()
            movie = session.get(Movie, "subject_review")
        self.assertEqual(run.status, "succeeded")
        self.assertEqual(assertions, [])
        self.assertEqual(
            {review.reason_code for review in reviews},
            {"unresolved_reference", "ambiguous_reference"},
        )
        self.assertEqual(result["reviews"], 2)
        self.assertEqual(movie.analysis_data["influence_impact"], output.summary)

    def _run_with_output(self, movie_id, output, *, model):
        with (
            patch.object(
                analysis_service.historian,
                "analysis_configuration",
                return_value=AnalysisModelConfiguration("openrouter", model),
            ),
            patch.object(
                analysis_service.historian,
                "analyze_v2",
                return_value=AnalysisGenerationResult(output),
            ),
            patch.object(
                analysis_service.evidence,
                "verify",
                return_value=EvidenceBatchResult((), ()),
            ),
        ):
            return analysis_service.analyze_movie(movie_id)

    def _film_id(self, movie_id):
        with Session(self.engine) as session:
            return session.get(LegacyMovieAlias, movie_id).film_id

    @staticmethod
    def _movie(movie_id, title, year, tmdb_id):
        return {
            "id": movie_id,
            "title": title,
            "title_cn": title,
            "year": year,
            "tmdb_id": tmdb_id,
            "library_status": "available",
            "metadata_source": "tmdb",
            "scrape_status": "matched",
        }


if __name__ == "__main__":
    unittest.main()
