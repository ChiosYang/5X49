import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import test_analysis_runtime as fixture
import app.services.analysis_review as review_module
import app.services.user_state as state_module
from app.api.analysis_review import router, AssertionDecision, ResolutionDecision
from app.canonical_models import Assertion, AssertionEvidence, Concept, GraphEntity, AnalysisResolutionReview, AnalysisRun
from app.models import EventRecord
from app.services.analysis import AnalysisService
from app.services.analysis_review import analysis_review_service as reviews, ReviewError
from app.services.historian import AnalysisModelConfiguration
from app.services.projections import projection_coordinator


class AnalysisReviewTests(unittest.TestCase):
    _add_film = staticmethod(fixture.AnalysisRuntimeTests._add_film)

    def setUp(self):
        fixture.AnalysisRuntimeTests.setUp(self)
        self.patch_engine = patch.object(review_module, "engine", self.engine)
        self.patch_engine.start()
        self.addCleanup(self.patch_engine.stop)
        self._analyze()
        projection_coordinator.bootstrap(self.engine)
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    tearDown = fixture.AnalysisRuntimeTests.tearDown

    def _analyze(self, model="fixture-model"):
        historian = fixture._Historian(fixture.AnalysisRuntimeTests._output())
        historian.analysis_configuration = lambda: AnalysisModelConfiguration("openrouter", model)
        return AnalysisService(database_engine=self.engine, historian=historian,
                               tmdb=fixture._Tmdb(), evidence=fixture._Evidence()).analyze_film(fixture.SUBJECT_ID)

    def _relation(self):
        return next(row for row in reviews.list(fixture.SUBJECT_ID)["relations"]
                    if row["target"]["entity_id"] == fixture.ANCESTOR_ID)

    def _decide(self, row, decision, correction=None):
        return reviews.decide(fixture.SUBJECT_ID, row["id"], AssertionDecision(
            revision=row["revision"], decision=decision, correction=correction))

    def test_reject_reaccept_and_replay_preserve_user_decisions(self):
        row = self._relation()
        self._decide(row, "rejected")
        self._analyze("second-model")
        rejected = self._relation()
        self.assertEqual(rejected["review_status"], "rejected")
        self._decide(rejected, "accepted")
        self._analyze("third-model")
        self.assertEqual(self._relation()["review_status"], "accepted")
        # Factual visibility remains unchanged even after user acceptance.
        import app.services.graph_query as graph
        with patch.object(graph, "engine", self.engine):
            self.assertEqual(graph.graph_query_service.get_film_graph(fixture.SUBJECT_ID)["edges"], [])

    def test_stale_decisions_are_rejected_and_repeat_current_decision_is_noop(self):
        row = self._relation()
        self._decide(row, "accepted")
        with self.assertRaisesRegex(ReviewError, "stale_review"):
            self._decide(row, "rejected")
        self._decide(self._relation(), "accepted")
        with Session(self.engine) as session:
            events = session.exec(select(EventRecord).where(EventRecord.type == "AnalysisAssertionReviewed")).all()
            self.assertEqual(len(events), 1)

    def test_correction_rejects_original_and_does_not_copy_rationale_or_evidence(self):
        row = self._relation()
        correction = {"predicate": "REMAKE_OF", "target_entity_id": fixture.ANCESTOR_ID}
        result = self._decide(row, "rejected", correction)
        with Session(self.engine) as session:
            replacement = session.get(Assertion, result["replacement_id"])
            self.assertEqual(replacement.review_status, "accepted")
            self.assertEqual(replacement.source_scope, "curated")
            self.assertIsNone(replacement.rationale)
            self.assertEqual(session.exec(select(AssertionEvidence).where(AssertionEvidence.assertion_id == replacement.id)).all(), [])
            self.assertEqual(session.get(Assertion, row["id"]).review_status, "rejected")
        self._analyze("second-model")
        after = {item["id"]: item for item in reviews.list(fixture.SUBJECT_ID)["relations"]}
        self.assertEqual(after[row["id"]]["review_status"], "rejected")
        self.assertEqual(after[result["replacement_id"]]["review_status"], "accepted")

    def test_invalid_self_type_and_missing_targets_do_not_change_original(self):
        row = self._relation()
        for target, predicate in [(fixture.SUBJECT_ID, "REMAKE_OF"),
                                  (fixture.ANCESTOR_ID, "HAS_THEME"),
                                  ("film_" + "f" * 32, "REMAKE_OF")]:
            with self.subTest(target=target, predicate=predicate), self.assertRaises(ReviewError):
                self._decide(row, "rejected", {"predicate": predicate, "target_entity_id": target})
        self.assertEqual(self._relation()["review_status"], "proposed")

    def test_correction_cannot_overwrite_previously_rejected_relation(self):
        existing = next(item for item in reviews.list(fixture.SUBJECT_ID)["relations"]
                        if item["direction"] == "target_to_subject")
        self._decide(existing, "rejected")
        with self.assertRaisesRegex(ReviewError, "target_relation_conflict"):
            self._decide(self._relation(), "rejected", {
                "predicate": "INFLUENCED_BY", "target_entity_id": fixture.DESCENDANT_ID,
                "direction": "target_to_subject"})
        self.assertEqual(self._relation()["review_status"], "proposed")

    def test_event_failure_rolls_back_both_correction_and_rejection(self):
        row = self._relation()
        with patch.object(review_module.event_store, "append_in_session", side_effect=RuntimeError("fail")):
            with self.assertRaises(RuntimeError):
                self._decide(row, "rejected", {"predicate": "REMAKE_OF", "target_entity_id": fixture.ANCESTOR_ID})
        self.assertEqual(self._relation()["revision"], row["revision"])
        self.assertEqual(len(reviews.list(fixture.SUBJECT_ID)["relations"]), 2)

    def test_projection_failure_rolls_back_decision_and_event(self):
        row = self._relation()
        with patch.object(projection_coordinator, "refresh_film", side_effect=RuntimeError("projection fail")):
            with self.assertRaises(RuntimeError):
                self._decide(row, "accepted")
        self.assertEqual(self._relation()["revision"], row["revision"])

    def test_resolution_dismiss_reopen_and_manual_concept_selection(self):
        review = reviews.list(fixture.SUBJECT_ID)["reviews"][0]
        reviews.resolve(fixture.SUBJECT_ID, review["id"], ResolutionDecision(revision=review["revision"], action="dismiss"))
        self._analyze("second-model")
        self.assertTrue(all(row["status"] == "dismissed" for row in reviews.list(fixture.SUBJECT_ID)["reviews"]))
        closed = next(row for row in reviews.list(fixture.SUBJECT_ID)["reviews"] if row["id"] == review["id"])
        self.assertEqual(closed["status"], "dismissed")
        reviews.resolve(fixture.SUBJECT_ID, closed["id"], ResolutionDecision(revision=closed["revision"], action="reopen"))
        concept_id = "concept_" + "a" * 32
        with Session(self.engine) as session:
            session.add(GraphEntity(id=concept_id, entity_type="concept"))
            session.flush()
            session.add(Concept(id=concept_id, kind="micro_genre", canonical_name="Known", canonical_key="known"))
            session.commit()
        reopened = next(row for row in reviews.list(fixture.SUBJECT_ID)["reviews"] if row["id"] == review["id"])
        reviews.resolve(fixture.SUBJECT_ID, reopened["id"], ResolutionDecision(
            revision=reopened["revision"], action="resolve",
            correction={"predicate": "HAS_MICRO_GENRE", "target_entity_id": concept_id}))
        with Session(self.engine) as session:
            self.assertEqual(session.get(AnalysisResolutionReview, reopened["id"]).resolved_entity_id, concept_id)
        self.assertTrue(any(row["target"]["entity_id"] == concept_id for row in reviews.list(fixture.SUBJECT_ID)["relations"]))

    def test_api_validation_scope_and_target_search(self):
        path = f"/films/{fixture.SUBJECT_ID}"
        response = self.client.get(path + "/analysis-review?limit=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["next_offset"], 1)
        self.assertEqual(self.client.get(path + "/analysis-review?limit=101").status_code, 422)
        self.assertEqual(self.client.get("/films/bad/analysis-review").status_code, 400)
        targets = self.client.get(path + "/analysis-review/targets", params={"predicate": "INFLUENCED_BY", "q": "earlier"}).json()
        self.assertEqual([item["entity_id"] for item in targets], [fixture.ANCESTOR_ID])
        self.assertEqual(self.client.get(path + "/analysis-review/targets", params={"predicate": "INFLUENCED_BY", "q": "%"}).json(), [])
        row = self._relation()
        request = {"revision": row["revision"], "decision": "accepted"}
        self.assertEqual(self.client.put(f"/films/{fixture.DESCENDANT_ID}/assertions/{row['id']}/review", json=request).status_code, 404)
        self.assertEqual(self.client.put(path + f"/assertions/{row['id']}/review", json={**request, "extra": True}).status_code, 422)
        self.assertEqual(self.client.put(path + f"/assertions/{row['id']}/review", json=request).status_code, 200)

    def test_personal_notes_are_not_copied_into_activity_or_analysis(self):
        with patch.object(state_module, "engine", self.engine):
            saved = state_module.film_profile_state_manager.upsert(
                fixture.SUBJECT_ID, rating=5, notes="PRIVATE_CANARY", fields_set={"rating", "notes"})
            self.assertEqual(saved["notes"], "PRIVATE_CANARY")
            cleared = state_module.film_profile_state_manager.upsert(
                fixture.SUBJECT_ID, rating=None, notes=None, fields_set={"rating", "notes"})
            self.assertIsNone(cleared["rating"])
            self.assertIsNone(cleared["notes"])
            self.assertTrue(cleared["favorite"])
        with Session(self.engine) as session:
            events = session.exec(select(EventRecord).where(EventRecord.type == "FilmProfileStateUpdated")).all()
            self.assertNotIn("PRIVATE_CANARY", str([row.payload for row in events]))

    def test_reference_resolution_does_not_create_edge_and_evidence_cannot_be_verified(self):
        from app.services.analysis_runtime import AnalysisRuntimePersistence
        with Session(self.engine) as session:
            run = session.exec(select(AnalysisRun)).first()
            for kind in ("entity_reference", "evidence"):
                AnalysisRuntimePersistence()._upsert_review(
                    session, run=run, predicate=None, candidate_kind=kind,
                    reason_code="unresolved_reference" if kind == "entity_reference" else "evidence_retrieval_failed",
                    candidate_summary={"target": {"entity_type": "film", "display_name": "Earlier Film", "release_year": 1970}},
                    now="2026-09-28T00:00:00+00:00")
            session.commit()
        rows = reviews.list(fixture.SUBJECT_ID)["reviews"]
        for kind in ("entity_reference", "evidence"):
            row = next(item for item in rows if item["candidate_kind"] == kind)
            request = ResolutionDecision(revision=row["revision"], action="resolve", correction={
                "predicate": "INFLUENCED_BY", "target_entity_id": fixture.ANCESTOR_ID})
            if kind == "evidence":
                with self.assertRaisesRegex(ReviewError, "review_cannot_be_resolved"):
                    reviews.resolve(fixture.SUBJECT_ID, row["id"], request)
            else:
                self.assertEqual(reviews.resolve(fixture.SUBJECT_ID, row["id"], request)["status"], "resolved")
        self.assertEqual(len(reviews.list(fixture.SUBJECT_ID)["relations"]), 2)

    def test_inactive_targets_are_excluded_and_rejected_on_accept(self):
        row = self._relation()
        with Session(self.engine) as session:
            target = session.get(GraphEntity, fixture.ANCESTOR_ID)
            target.lifecycle_status = "tombstoned"
            session.add(target)
            session.commit()
        self.assertEqual(reviews.targets(fixture.SUBJECT_ID, "INFLUENCED_BY", "Earlier"), [])
        with self.assertRaisesRegex(ReviewError, "target_unavailable"):
            self._decide(self._relation(), "accepted")
        self.assertEqual(self._relation()["revision"], row["revision"])


if __name__ == "__main__":
    unittest.main()
