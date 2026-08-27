import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlmodel import SQLModel, Session, create_engine, select

from app.canonical_models import (
    AnalysisResolutionReview,
    AnalysisRun,
    Assertion,
    AssertionEvidence,
    AssertionPredicate,
    AssertionProvenance,
    Evidence,
    Film,
    FilmProfileState,
    GraphEntity,
    LibraryItem,
    LocalProfile,
)
from app.contracts.analysis_persistence import predicate_seed_rows
from app.contracts.analysis_v2 import AnalysisV2Output
from app.models import EventRecord
from app.services.analysis import AnalysisExecutionError, AnalysisService
from app.services.analysis_evidence import EvidenceBatchResult, VerifiedEvidenceCandidate
from app.services.analysis_runtime import AnalysisRuntimePersistence
from app.services.historian import AnalysisGenerationResult, AnalysisModelConfiguration

SUBJECT_ID = "film_11111111111111111111111111111111"
ANCESTOR_ID = "film_22222222222222222222222222222222"
DESCENDANT_ID = "film_33333333333333333333333333333333"


class _Historian:
    def __init__(self, output: AnalysisV2Output, *, fail: Exception | None = None):
        self.output = output
        self.fail = fail
        self.calls = 0

    def analysis_configuration(self):
        return AnalysisModelConfiguration("openrouter", "fixture-model")

    def analyze_v2(self, _analysis_input, *, configuration=None):
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        return AnalysisGenerationResult(self.output, 10, 20, 0.01, "USD")


class _Evidence:
    def __init__(self, result: EvidenceBatchResult | None = None):
        self.result = result or EvidenceBatchResult((), ())
        self.candidates = None

    def verify(self, candidates):
        self.candidates = candidates
        return self.result


class _Tmdb:
    @staticmethod
    def is_configured():
        return False


class AnalysisRuntimeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self._tmp.name) / 'library.db'}")
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add_all([AssertionPredicate(**row) for row in predicate_seed_rows()])
            session.add(
                LocalProfile(
                    id="profile_local",
                    profile_key="local",
                    display_name="Local",
                )
            )
            self._add_film(session, SUBJECT_ID, "Subject Film", 2000)
            self._add_film(session, ANCESTOR_ID, "Earlier Film", 1970)
            self._add_film(session, DESCENDANT_ID, "Later Film", 2020)
            session.add(
                LibraryItem(
                    id="lib_subject",
                    film_id=SUBJECT_ID,
                    profile_id="profile_local",
                    source_type="local",
                    source_instance_id="local",
                    source_item_key="private/path/subject.mkv",
                    availability_status="available",
                )
            )
            session.add(
                FilmProfileState(
                    id="fps_subject",
                    profile_id="profile_local",
                    film_id=SUBJECT_ID,
                    favorite=True,
                    notes="private note must never enter analysis input",
                )
            )
            session.commit()

    def tearDown(self):
        self.engine.dispose()
        self._tmp.cleanup()

    @staticmethod
    def _add_film(session: Session, film_id: str, title: str, year: int):
        session.add(GraphEntity(id=film_id, entity_type="film"))
        session.add(Film(id=film_id, canonical_title=title, release_year=year))

    @staticmethod
    def _output() -> AnalysisV2Output:
        return AnalysisV2Output.model_validate(
            {
                "subject_film_id": SUBJECT_ID,
                "summary": "A bounded public summary.",
                "assertions": [
                    {
                        "predicate": "INFLUENCED_BY",
                        "target": {"entity_type": "film", "entity_id": ANCESTOR_ID},
                        "rationale": "The earlier film shaped its visual grammar.",
                        "evidence_candidates": [
                            {
                                "source_title": "Public source",
                                "source_uri": "https://example.com/source",
                                "claim": "A public source identifies the influence.",
                            }
                        ],
                    },
                    {
                        "predicate": "INFLUENCED_BY",
                        "direction": "target_to_subject",
                        "target": {"entity_type": "film", "entity_id": DESCENDANT_ID},
                        "rationale": "The later film reuses its central device.",
                    },
                    {
                        "predicate": "HAS_MICRO_GENRE",
                        "target": {"entity_type": "concept", "display_name": "Unknown concept"},
                        "rationale": "This must enter review rather than invent an entity.",
                    },
                ],
            }
        )

    def test_canonical_input_excludes_library_locator_and_profile_state(self):
        with Session(self.engine) as session:
            data = AnalysisRuntimePersistence().build_input(
                session, SUBJECT_ID
            ).model_dump(mode="json")
        serialized = str(data)
        self.assertEqual(data["canonical_title"], "Subject Film")
        self.assertNotIn("private/path", serialized)
        self.assertNotIn("private note", serialized)
        self.assertNotIn("favorite", serialized)

    def test_runtime_persists_structured_view_and_reuses_successful_run(self):
        output = self._output()
        verified = VerifiedEvidenceCandidate(
            candidate_key="a000:e000",
            candidate=output.assertions[0].evidence_candidates[0],
            source_uri="https://example.com/source",
            content_hash="a" * 64,
            retrieved_at="2026-08-25T00:00:00+00:00",
        )
        historian = _Historian(output)
        service = AnalysisService(
            database_engine=self.engine,
            historian=historian,
            tmdb=_Tmdb(),
            evidence=_Evidence(EvidenceBatchResult((verified,), ())),
        )

        first = service.analyze_film(SUBJECT_ID)
        second = service.analyze_film(SUBJECT_ID)

        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(historian.calls, 1)
        self.assertEqual(first["analysis"]["summary"], "A bounded public summary.")
        self.assertEqual(
            {relation["direction"] for relation in first["analysis"]["relations"]},
            {"subject_to_target", "target_to_subject"},
        )
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(AnalysisRun)).all()), 1)
            self.assertEqual(len(session.exec(select(Assertion)).all()), 2)
            self.assertEqual(len(session.exec(select(AssertionProvenance)).all()), 2)
            self.assertEqual(len(session.exec(select(Evidence)).all()), 1)
            self.assertEqual(len(session.exec(select(AssertionEvidence)).all()), 1)
            reviews = session.exec(select(AnalysisResolutionReview)).all()
            completed = session.exec(
                select(EventRecord).where(EventRecord.type == "AnalysisCompleted")
            ).one()
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].reason_code, "unresolved_reference")
        self.assertEqual(completed.aggregate_type, "analysis_run")
        self.assertNotIn("summary", completed.payload)
        self.assertNotIn("source_uri", completed.payload)
        self.assertNotIn("evidence_candidates", completed.payload)

    def test_user_rejection_survives_a_new_model_run(self):
        output = AnalysisV2Output.model_validate(
            {
                "subject_film_id": SUBJECT_ID,
                "summary": "Summary",
                "assertions": [
                    {
                        "predicate": "INFLUENCED_BY",
                        "target": {"entity_type": "film", "entity_id": ANCESTOR_ID},
                        "rationale": "Model rationale.",
                    }
                ],
            }
        )
        AnalysisService(
            database_engine=self.engine,
            historian=_Historian(output),
            tmdb=_Tmdb(),
            evidence=_Evidence(),
        ).analyze_film(SUBJECT_ID)
        with Session(self.engine) as session:
            assertion = session.exec(select(Assertion)).one()
            assertion.review_status = "rejected"
            assertion.review_method = "user"
            assertion.reviewed_by_profile_id = "profile_local"
            assertion.reviewed_at = "2026-08-25T00:00:00+00:00"
            assertion.rationale = "User-owned rationale."
            session.add(assertion)
            session.commit()

        second_historian = _Historian(output)
        second_historian.analysis_configuration = lambda: AnalysisModelConfiguration(
            "openrouter", "fixture-model-v2"
        )
        AnalysisService(
            database_engine=self.engine,
            historian=second_historian,
            tmdb=_Tmdb(),
            evidence=_Evidence(),
        ).analyze_film(SUBJECT_ID)

        with Session(self.engine) as session:
            assertion = session.exec(select(Assertion)).one()
            provenance = session.exec(select(AssertionProvenance)).all()
        self.assertEqual(assertion.review_status, "rejected")
        self.assertEqual(assertion.rationale, "User-owned rationale.")
        self.assertEqual(len(provenance), 2)

    def test_policy_critic_rejects_identity_conflict_before_evidence_or_assertion_write(self):
        output = AnalysisV2Output.model_validate(
            {
                "subject_film_id": SUBJECT_ID,
                "summary": "Summary",
                "assertions": [
                    {
                        "predicate": "INFLUENCED_BY",
                        "target": {
                            "entity_type": "film",
                            "entity_id": ANCESTOR_ID,
                            "display_name": "Wrong title",
                            "release_year": 1970,
                        },
                        "rationale": "Candidate must be reviewed.",
                        "evidence_candidates": [
                            {
                                "source_title": "Public source",
                                "source_uri": "https://example.com/should-not-fetch",
                                "claim": "This candidate is inconsistent.",
                            }
                        ],
                    }
                ],
            }
        )
        evidence = _Evidence()
        result = AnalysisService(
            database_engine=self.engine,
            historian=_Historian(output),
            tmdb=_Tmdb(),
            evidence=evidence,
        ).analyze_film(SUBJECT_ID)

        self.assertEqual(evidence.candidates, {})
        self.assertEqual(result["assertions"], 0)
        self.assertEqual(result["evidence"], 0)
        self.assertEqual(result["reviews"], 1)
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(Assertion)).all()), 0)
            review = session.exec(select(AnalysisResolutionReview)).one()
        self.assertEqual(review.reason_code, "identity_conflict")

    def test_completion_failure_rolls_back_and_records_safe_failure(self):
        service = AnalysisService(
            database_engine=self.engine,
            historian=_Historian(self._output()),
            tmdb=_Tmdb(),
            evidence=_Evidence(),
        )
        with patch.object(
            AnalysisRuntimePersistence,
            "_upsert_assertion",
            side_effect=RuntimeError("secret database detail"),
        ):
            with self.assertRaisesRegex(AnalysisExecutionError, "persistence failed"):
                service.analyze_film(SUBJECT_ID)

        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(Assertion)).all(), [])
            run = session.exec(select(AnalysisRun)).one()
            failed = session.exec(
                select(EventRecord).where(EventRecord.type == "AnalysisFailed")
            ).one()
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.error_code, "analysis_persistence_failed")
        self.assertNotIn("secret", run.error_message or "")
        self.assertNotIn("secret", str(failed.payload))


if __name__ == "__main__":
    unittest.main()
