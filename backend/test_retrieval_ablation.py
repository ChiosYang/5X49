"""Offline ablation accounting/fixture tests; no semantic model-quality claims."""
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from app.evaluation import public_movie_pilot as historical
from app.evaluation import retrieval_ablation as ablation
from app.evaluation.public_movies import load_fixture
from app.services.semantic_search import ProviderSpec


class ContractVectors:
    """Constant handwritten vectors exercise plumbing, not language relevance."""
    spec = ProviderSpec("synthetic/ablation-contract", "v1", 3)

    def __init__(self, fixture):
        self.allowed = set(fixture.inputs())
        self.seen = set()

    def embed(self, texts, *, query):
        keys = {(text, query) for text in texts}
        if not keys <= self.allowed:
            raise AssertionError("unexpected encoding")
        self.seen |= keys
        return [[1., 0., 0.] for _ in texts]


class RetrievalAblationTests(unittest.TestCase):
    def test_metrics_exclude_no_answer_from_pure_ranking_and_separate_abstention(self):
        rows = [dict(expected_ids=["a"], actual_ids=[], kind="theme", top1_hit=False,
            recall_at_3=0., ndcg_at_10=0., elapsed_ms=1, hard_condition_violations=[],
            candidate_recall_at_5=1., candidate_recall_at_10=1., candidate_recall_at_20=1.,
            candidate_union_recall=1.),
            dict(expected_ids=[], actual_ids=[], kind="no_answer", top1_hit=True,
            recall_at_3=1., ndcg_at_10=1., elapsed_ms=2, hard_condition_violations=[],
            candidate_recall_at_5=None, candidate_recall_at_10=None, candidate_recall_at_20=None,
            candidate_union_recall=None)]
        stats = ablation.aggregate(rows)
        self.assertEqual(stats["pure_ranking"]["top1_hit"], 0)
        self.assertEqual(stats["pure_ranking"]["recall_at_3"], 0)
        self.assertEqual(stats["pure_ranking"]["ndcg_at_10"], 0)
        self.assertEqual(stats["answerable_false_abstentions"], 1)
        self.assertEqual(stats["no_answer_false_positives"], 0)
        self.assertEqual(stats["candidate_union_recall"], 1)
        only_no = ablation.aggregate(rows[1:])
        self.assertIsNone(only_no["pure_ranking"]["top1_hit"])

    def test_full_offline_contract_all_stages_methods_without_network_or_fixture_writes(self):
        fixture = load_fixture(historical.FIXTURE)
        before = {p: sha256(p.read_bytes()).hexdigest() for p in
                  (historical.FIXTURE, historical.EVIDENCE, historical.LOCK, ablation.HISTORICAL_RESULTS)}
        vectors = ContractVectors(fixture)
        with patch("requests.sessions.Session.request", side_effect=AssertionError("no HTTP")), \
                patch("socket.create_connection", side_effect=AssertionError("no sockets")), \
                patch.object(historical, "existing_credential", side_effect=AssertionError("no credentials")):
            baseline = historical.evaluate_fixture(fixture, vectors, ":memory:")["methods"]
            result = ablation.evaluate(fixture, vectors, baseline)
        self.assertEqual(set(result["stages"]), set(ablation.STAGES))
        for stage in result["stages"].values():
            for method in stage.values():
                self.assertEqual(method["all_semantic"]["answerable_cases"], 14)
                self.assertEqual(method["all_semantic"]["no_answer_cases"], 2)
                self.assertEqual(len(method["results"]), 16)
                self.assertEqual(method["all_semantic"]["hard_condition_violations"], 0)
                for row in method["results"]:
                    self.assertLessEqual(set(row["actual_ids"]), set(row["candidate_ids"]))
                    self.assertIn("not NLP", row["intent_source"])
        self.assertEqual(len(result["shared_local_cases"]["results"]), 8)
        self.assertTrue(all(r["exact_set"] for r in result["shared_local_cases"]["results"]))
        self.assertEqual(len(vectors.seen), 38)
        self.assertEqual(before, {p: sha256(p.read_bytes()).hexdigest() for p in before})

    def test_no_remote_or_accounting_entrypoint_in_new_cli(self):
        with patch.object(ablation, "experiment", return_value={"model_new_calls": 0}) as replay, \
                patch("builtins.print") as output:
            self.assertEqual(ablation.main(), 0)
        replay.assert_called_once_with()
        self.assertEqual(json.loads(output.call_args.args[0])["model_new_calls"], 0)

    def test_missing_saved_vectors_stops_without_network_or_accounting(self):
        with patch.object(ablation, "experiment", side_effect=FileNotFoundError("local artifact")), \
                patch("builtins.print") as output:
            self.assertEqual(ablation.main(), 1)
        self.assertEqual(json.loads(output.call_args.args[0]),
            {"status": "stopped", "reason": "offline_input_unavailable", "new_model_calls": 0})


if __name__ == "__main__":
    unittest.main()
