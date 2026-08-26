import hashlib
import os
import shutil
import sqlite3
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from app.contracts.analysis_v2 import AnalysisEvaluationHumanReview
from app.evaluation.gate_b import (
    GateBBlocked,
    _exit_code,
    _synthetic_case_results,
    assertion_match_key,
    create_review_template,
    dataset_hash,
    load_dataset,
    load_policy,
    prediction_hash,
    run_live,
    run_rehearsal,
    score_evaluation,
    validate_dataset,
)


BACKEND_ROOT = Path(__file__).resolve().parent
DATASET_PATH = BACKEND_ROOT / "fixtures" / "analysis_v2" / "gate-b-v1.json"
POLICY_PATH = BACKEND_ROOT / "fixtures" / "analysis_v2" / "gate-b-policy-v1.json"
RUNS_ROOT = BACKEND_ROOT / "data" / "analysis-v2" / "gate-b" / "runs"


class GateBEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = load_dataset(DATASET_PATH)
        cls.policy = load_policy(POLICY_PATH)

    def test_fixed_dataset_meets_coverage_and_remains_draft(self):
        validation = validate_dataset(self.dataset, self.policy)

        self.assertEqual(len(self.dataset.cases), 36)
        self.assertEqual(validation["validation_status"], "passed")
        self.assertFalse(validation["adjudication_ready"])
        self.assertEqual(
            dataset_hash(self.dataset),
            "94eb0d52459a58a70e5df5b577aa038b35b54a89cfd3b0e915b090064587b51d",
        )
        self.assertTrue(all(case.adjudication_status == "draft" for case in self.dataset.cases))
        self.assertTrue(all(case.annotator_count == 0 for case in self.dataset.cases))

    def test_match_key_includes_direction_identity_and_qualifiers(self):
        base = {
            "predicate": "INFLUENCED_BY",
            "target": {
                "entity_type": "film",
                "provider": "tmdb.movie",
                "external_id": "123",
            },
        }
        reverse = {**base, "direction": "target_to_subject"}
        qualified = {**base, "qualifiers": {"relationship_type": "visual"}}

        self.assertNotEqual(assertion_match_key(base), assertion_match_key(reverse))
        self.assertNotEqual(assertion_match_key(base), assertion_match_key(qualified))
        self.assertEqual(assertion_match_key(base), assertion_match_key(dict(reversed(list(base.items())))))

    def test_scorer_requires_human_labels_and_rejects_forbidden_edges(self):
        results = _synthetic_case_results(self.dataset, self.policy)
        operational = self._passing_operational_metrics()
        review = self._human_review(results)
        passing = score_evaluation(
            results,
            policy=self.policy,
            human_review=review,
            operational_metrics=operational,
        )
        self.assertEqual(passing["status"], "passed")

        forbidden = next(
            item
            for result in results
            for item in result["expected_assertions"]
            if item["label"] == "forbidden"
        )
        candidate = {
            key: value
            for key, value in forbidden.items()
            if key not in {"label", "note"}
        }
        results[0]["predictions"].append({
            "prediction_hash": prediction_hash(candidate),
            "candidate": candidate,
            "expected_label": "forbidden",
            "resolution_status": "resolved",
            "resolution_correct": True,
            "review_created": False,
            "invented_entity": False,
            "evidence": [],
        })
        failed = score_evaluation(
            results,
            policy=self.policy,
            human_review=review,
            operational_metrics=operational,
        )
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["metrics"]["forbidden_or_harmful_count"], 1)
        self.assertEqual(failed["metrics"]["resolution_decision_accuracy"], 1.0)

        novel = {
            "predicate": "HAS_THEME",
            "target": {"entity_type": "concept", "display_name": "Novel bounded theme"},
            "rationale": "A novel prediction requires explicit human disposition.",
        }
        novel_hash = prediction_hash(novel)
        results[1]["predictions"].append({
            "prediction_hash": novel_hash,
            "candidate": novel,
            "expected_label": None,
            "resolution_status": "resolved",
            "resolution_correct": True,
            "review_created": False,
            "invented_entity": False,
            "evidence": [],
        })
        blocked = score_evaluation(
            results,
            policy=self.policy,
            human_review=review,
            operational_metrics=operational,
        )
        self.assertEqual(blocked["metrics"]["missing_human_prediction_labels"], 1)

    def test_live_preflight_blocks_without_strict_evidence(self):
        run_dir = self._new_run_dir("preflight")
        pricing_path = BACKEND_ROOT / "data" / "analysis-v2" / "gate-b" / "input" / "missing.json"
        try:
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
                report = run_live(
                    DATASET_PATH,
                    run_dir,
                    provider="openrouter",
                    model="exact/model-snapshot",
                    pricing_path=pricing_path,
                    allow_public_network=False,
                )
            self.assertEqual(report["overall_status"], "blocked")
            self.assertEqual(report["live_status"], "blocked")
            self.assertFalse((run_dir / "work" / "gate-b.db").exists())
            check_ids = {item["id"] for item in report["checks"]}
            self.assertIn("live-preflight-dataset-awaiting-human-adjudication", check_ids)
            self.assertIn("live-preflight-openrouter-key-missing", check_ids)
            self.assertIn("live-preflight-public-network-not-authorized", check_ids)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_offline_rehearsal_is_isolated_restorable_and_strictly_blocked(self):
        run_dir = self._new_run_dir("rehearsal")
        user_database = BACKEND_ROOT / "data" / "library.db"
        user_hash_before = self._file_hash(user_database)
        try:
            report = run_rehearsal(DATASET_PATH, run_dir)
            self.assertEqual(report["tool_status"], "passed")
            self.assertEqual(report["live_status"], "blocked")
            self.assertEqual(report["human_status"], "blocked")
            self.assertEqual(report["overall_status"], "blocked")
            self.assertTrue(report["operational_metrics"]["restore_equal"])
            self.assertEqual(report["operational_metrics"]["privacy_leak_count"], 0)

            database_path = run_dir / "work" / "gate-b.db"
            with sqlite3.connect(database_path) as connection:
                version = connection.execute(
                    "SELECT MAX(version) FROM schema_migrations WHERE status='applied'"
                ).fetchone()[0]
                self.assertEqual(version, 10)
                for case in self.dataset.cases:
                    for provider, external_id in case.input.external_identities.items():
                        entity_id = connection.execute(
                            "SELECT entity_id FROM external_identity "
                            "WHERE provider=? AND external_id=? AND identity_status='active'",
                            (provider, external_id),
                        ).fetchone()[0]
                        self.assertEqual(entity_id, case.input.film_id)

            with self.assertRaises(GateBBlocked):
                create_review_template(run_dir / "run-report.json", run_dir / "human-review.json")
            self.assertEqual(user_hash_before, self._file_hash(user_database))
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_exit_code_contract_is_strict(self):
        self.assertEqual(_exit_code("passed"), 0)
        self.assertEqual(_exit_code("failed"), 2)
        self.assertEqual(_exit_code("blocked"), 3)

    @staticmethod
    def _passing_operational_metrics():
        return {
            "replay_new_row_count": 0,
            "rejected_reactivation_count": 0,
            "review_field_change_count": 0,
            "revoked_link_reactivation_count": 0,
            "restore_equal": True,
            "privacy_leak_count": 0,
        }

    def _human_review(self, results):
        return AnalysisEvaluationHumanReview.model_validate({
            "run_id": "synthetic-gate-b",
            "dataset_id": self.dataset.dataset_id,
            "dataset_hash": dataset_hash(self.dataset),
            "reviewer_count": 1,
            "cases": [
                {
                    "case_id": result["case_id"],
                    "summary_helpfulness": 4,
                    "novel_predictions": [],
                }
                for result in results
            ],
        })

    @staticmethod
    def _new_run_dir(label: str) -> Path:
        RUNS_ROOT.mkdir(parents=True, exist_ok=True)
        return RUNS_ROOT / f"test-{label}-{uuid.uuid4().hex}"

    @staticmethod
    def _file_hash(path: Path):
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


if __name__ == "__main__":
    unittest.main()
