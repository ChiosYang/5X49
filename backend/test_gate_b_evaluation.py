import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from app.contracts.analysis_v2 import (
    AnalysisEvaluationHumanReview,
    AnalysisV2Output,
    GeneratedAnalysisV2Output,
)
from app.evaluation.gate_b import (
    GateBBlocked,
    _assertion_target_matches,
    _exit_code,
    _synthetic_case_results,
    assertion_match_key,
    assertion_match_keys,
    create_review_template,
    dataset_hash,
    load_dataset,
    load_policy,
    prediction_hash,
    run_live,
    run_pilot,
    run_rehearsal,
    score_evaluation,
    validate_dataset,
)


BACKEND_ROOT = Path(__file__).resolve().parent
DATASET_PATH = BACKEND_ROOT / "fixtures" / "analysis_v2" / "gate-b-v1.json"
POLICY_PATH = BACKEND_ROOT / "fixtures" / "analysis_v2" / "gate-b-policy-v2.json"
RUNS_ROOT = BACKEND_ROOT / "data" / "analysis-v2" / "gate-b" / "runs"


class GateBEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = load_dataset(DATASET_PATH)
        cls.policy = load_policy(POLICY_PATH)

    def test_fixed_dataset_meets_coverage_and_is_frozen(self):
        validation = validate_dataset(self.dataset, self.policy)

        self.assertEqual(len(self.dataset.cases), 36)
        self.assertEqual(validation["validation_status"], "passed")
        self.assertTrue(validation["adjudication_ready"])
        self.assertEqual(
            dataset_hash(self.dataset),
            "fbfc9a1a481aef302fdac048250fae3225e335c6c228a1ee051db223c71be684",
        )
        self.assertTrue(all(case.adjudication_status == "adjudicated" for case in self.dataset.cases))
        self.assertTrue(all(case.annotator_count == 1 for case in self.dataset.cases))
        influence_gold = sum(
            item.predicate.value == "INFLUENCED_BY"
            and item.label in {"required", "acceptable"}
            for case in self.dataset.cases
            for item in case.expected_assertions
        )
        self.assertGreaterEqual(influence_gold, 12)
        self.assertEqual(
            next(
                item["status"]
                for item in validation["checks"]
                if item["id"] == "dataset-predicate-coverage"
            ),
            "passed",
        )

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

    def test_analysis_output_caps_assertions_and_evidence_candidates(self):
        base = {
            "subject_film_id": "film_" + "a" * 32,
            "summary": "Bounded summary.",
            "assertions": [
                {
                    "predicate": "HAS_THEME",
                    "target": {
                        "entity_type": "concept",
                        "display_name": f"Theme {index}",
                    },
                    "rationale": "Bounded rationale.",
                }
                for index in range(9)
            ],
        }
        with self.assertRaises(ValidationError):
            GeneratedAnalysisV2Output.model_validate(base)

        base["assertions"] = [{
            **base["assertions"][0],
            "evidence_candidates": [
                {
                    "source_title": f"Source {index}",
                    "source_uri": f"https://example.com/{index}",
                    "claim": "Bounded claim.",
                }
                for index in range(3)
            ],
        }]
        with self.assertRaises(ValidationError):
            GeneratedAnalysisV2Output.model_validate(base)

    def test_concept_aliases_match_one_gold_target_and_remain_duplicates(self):
        expected = next(
            item
            for case in self.dataset.cases
            for item in case.expected_assertions
            if item.label == "required" and item.target_aliases
        )
        alias_candidate = expected.model_dump(
            mode="json",
            exclude={"label", "note", "target_aliases"},
            exclude_none=True,
        )
        alias_candidate["target"]["display_name"] = expected.target_aliases[0]
        self.assertIn(assertion_match_key(alias_candidate), assertion_match_keys(expected))

        concept = SimpleNamespace(
            id="concept_alias_target",
            kind="visual_style",
            canonical_name=expected.target.display_name,
        )
        alias = SimpleNamespace(concept_id=concept.id)
        session = SimpleNamespace(
            get=lambda *_args: concept,
            exec=lambda *_args: SimpleNamespace(first=lambda: alias),
        )
        assertion = SimpleNamespace(
            subject_entity_id="film_subject",
            object_entity_id=concept.id,
        )
        self.assertTrue(
            _assertion_target_matches(
                session,
                assertion,
                alias_candidate,
                "film_subject",
            )
        )
        self.assertTrue(
            _assertion_target_matches(
                session,
                assertion,
                {
                    "predicate": "HAS_VISUAL_STYLE",
                    "target": {"entity_type": "concept", "entity_id": concept.id},
                },
                "film_subject",
            )
        )

        results = _synthetic_case_results(self.dataset, self.policy)
        result = next(item for item in results if item["case_id"] == "eval_hero_2002")
        canonical_prediction = result["predictions"][0]
        alias_prediction = {
            **canonical_prediction,
            "candidate": alias_candidate,
            "prediction_hash": prediction_hash(alias_candidate),
        }
        result["predictions"].append(alias_prediction)
        scored = score_evaluation(
            results,
            policy=self.policy,
            human_review=self._human_review(results),
            operational_metrics=self._passing_operational_metrics(),
        )
        self.assertEqual(scored["status"], "failed")
        self.assertGreater(scored["metrics"]["semantic_duplicate_rate"], 0)

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

    def test_scorer_detects_identity_conflicts_and_qualifier_policy_violations(self):
        results = _synthetic_case_results(self.dataset, self.policy)
        review = self._human_review(results)
        operational = self._passing_operational_metrics()
        prediction = results[0]["predictions"][0]
        prediction["identity_consistent"] = False
        prediction["candidate"]["qualifiers"] = {"period_start_year": 2006}

        scored = score_evaluation(
            results,
            policy=self.policy,
            human_review=review,
            operational_metrics=operational,
        )
        self.assertEqual(scored["metrics"]["resolved_identity_conflict_count"], 1)
        self.assertEqual(scored["metrics"]["qualifier_policy_violation_count"], 1)
        self.assertEqual(scored["status"], "failed")

        prediction["resolution_status"] = "review"
        prediction["identity_consistent"] = None
        prediction["review_reason"] = "identity_conflict"
        prediction["review_created"] = True
        captured = score_evaluation(
            results,
            policy=self.policy,
            human_review=review,
            operational_metrics=operational,
        )
        self.assertEqual(captured["metrics"]["resolved_identity_conflict_count"], 0)
        self.assertEqual(captured["metrics"]["identity_conflict_review_capture_rate"], 1.0)

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
            self.assertNotIn("live-preflight-dataset-awaiting-human-adjudication", check_ids)
            self.assertIn("live-preflight-openrouter-key-missing", check_ids)
            self.assertIn("live-preflight-public-network-not-authorized", check_ids)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_live_preflight_blocks_when_evidence_network_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory)
            fixture_root = isolated_root / "fixtures" / "analysis_v2"
            fixture_root.mkdir(parents=True)
            dataset_path = fixture_root / DATASET_PATH.name
            policy_path = fixture_root / POLICY_PATH.name
            shutil.copy2(DATASET_PATH, dataset_path)
            shutil.copy2(POLICY_PATH, policy_path)
            pricing_path = isolated_root / "data" / "analysis-v2" / "gate-b" / "input" / "pricing.json"
            pricing_path.parent.mkdir(parents=True)
            pricing_path.write_text(
                json.dumps({
                    "format_version": "gate-b-pricing.v1",
                    "provider": "openrouter",
                    "model": "stealth/ox-alpha",
                    "currency": "USD",
                    "input_usd_per_million": 0,
                    "output_usd_per_million": 0,
                    "effective_at": "2026-08-26T06:39:28Z",
                    "source_uri": "https://openrouter.ai/stealth/ox-alpha",
                }),
                encoding="utf-8",
            )
            run_dir = (
                isolated_root
                / "data"
                / "analysis-v2"
                / "gate-b"
                / "runs"
                / "test-evidence-preflight"
            )
            with (
                patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}),
                patch("app.evaluation.gate_b._backend_root", return_value=isolated_root),
                patch(
                    "app.evaluation.gate_b.evidence_retriever.preflight",
                    return_value="evidence_network_boundary_blocked",
                ),
            ):
                report = run_live(
                    dataset_path,
                    run_dir,
                    provider="openrouter",
                    model="stealth/ox-alpha",
                    pricing_path=pricing_path,
                    allow_public_network=True,
                )
            self.assertEqual(report["overall_status"], "blocked")
            self.assertFalse((run_dir / "work" / "gate-b.db").exists())
            self.assertIn(
                "live-preflight-evidence-network-boundary-blocked",
                {item["id"] for item in report["checks"]},
            )

    def test_pilot_is_always_marked_as_diagnostic(self):
        expected = {"overall_status": "blocked", "diagnostic_status": "passed"}
        with patch("app.evaluation.gate_b.run_live", return_value=expected) as live:
            report = run_pilot(
                DATASET_PATH,
                RUNS_ROOT / "pilot-wrapper",
                provider="openrouter",
                model="stealth/ox-alpha",
                pricing_path=BACKEND_ROOT / "data" / "analysis-v2" / "gate-b" / "input" / "pricing.json",
                allow_public_network=True,
                case_limit=6,
                reasoning_effort="low",
                max_output_tokens=8192,
            )
        self.assertEqual(report, expected)
        self.assertTrue(live.call_args.kwargs["diagnostic"])
        self.assertEqual(live.call_args.kwargs["case_limit"], 6)

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
            with closing(sqlite3.connect(database_path)) as connection:
                version = connection.execute(
                    "SELECT MAX(version) FROM schema_migrations WHERE status='applied'"
                ).fetchone()[0]
                self.assertEqual(version, 4)
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
