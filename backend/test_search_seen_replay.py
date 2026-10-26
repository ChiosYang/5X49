import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.evaluation.search_seen_replay import RecordedClient, RecordedEmbedding
from app.services.search_providers import DECISION, RERANK, RerankProvider
from app.services.semantic_search import SemanticError, _hash


class SeenReplayTests(unittest.TestCase):
    def setUp(self):
        self.body = {"query": "a family reunion", "documents": ["First public plot", "Second public plot"], "top_n": 2}
        self.response = {"id": "recorded-1", "model": RERANK.model, "provider": RERANK.provider_name,
            "usage": {"cost": 0}, "results": [{"index": 1, "relevance_score": .2}, {"index": 0, "relevance_score": .8}]}
        self.receipt = {"number": 1, "purpose": "rerank", "input_hash": _hash([self.body, "rerank"]),
            "state": "reported", "scope": "public-evaluation.v2", "cost": "0",
            "evidence": json.dumps({k: v for k, v in self.response.items() if k != "results"})}
        self.client = RecordedClient([self.receipt], {1: self.response})

    def test_exact_candidate_order_restores_real_index_mapping_without_transport(self):
        with patch("requests.sessions.Session.request", side_effect=AssertionError("No HTTP")), patch(
                "socket.socket.connect", side_effect=AssertionError("No network")):
            self.assertEqual(RerankProvider(self.client).rank(self.body["query"], self.body["documents"]), [.8, .2])
        self.assertTrue(self.client.events[0]["verified_recording"])

    def test_changed_text_candidate_order_or_count_cannot_reuse_a_recording(self):
        for query, docs in (("different text", self.body["documents"]),
                            (self.body["query"], list(reversed(self.body["documents"]))),
                            (self.body["query"], self.body["documents"][:1])):
            with self.subTest(query=query, docs=docs), self.assertRaisesRegex(SemanticError, "missing_response"):
                RerankProvider(self.client).rank(query, docs)
        self.assertTrue(all(not e["verified_recording"] for e in self.client.events))

    def test_endpoint_and_identity_mismatch_are_not_model_success(self):
        with self.assertRaisesRegex(SemanticError, "endpoint_mismatch"):
            self.client.request(DECISION, self.body, purpose="rerank", validate=lambda x: x)
        for key, value in (("model", DECISION.model), ("provider", "Unapproved"), ("id", "other-request")):
            response = {**self.response, key: value}
            client = RecordedClient([self.receipt], {1: response})
            with self.subTest(key=key), self.assertRaisesRegex(SemanticError, "evidence_mismatch"):
                RerankProvider(client).rank(self.body["query"], self.body["documents"])

    def test_unknown_missing_and_malformed_outputs_are_unverified(self):
        for receipts, responses in (([{**self.receipt, "state": "uncertain"}], {1: self.response}),
                                    ([self.receipt], {})):
            with self.assertRaisesRegex(SemanticError, "missing_response"):
                RerankProvider(RecordedClient(receipts, responses)).rank(self.body["query"], self.body["documents"])
        self.response["results"][0]["relevance_score"] = float("nan")
        with self.assertRaisesRegex(SemanticError, "rerank_invalid"):
            RerankProvider(self.client).rank(self.body["query"], self.body["documents"])
        self.assertFalse(self.client.events[-1]["verified_recording"])

    def test_missing_vector_is_not_replaced_or_generated(self):
        store = SimpleNamespace(cached_vector=Mock(return_value=None))
        embedding = RecordedEmbedding(store, "fixed-spec")
        with self.assertRaisesRegex(SemanticError, "missing_vector"):
            embedding.embed(["unseen text"], query=True)
        store.cached_vector.assert_called_once_with("unseen text", "fixed-spec", query=True)
        self.assertFalse(embedding.events[0]["verified_recording"])


if __name__ == "__main__":
    unittest.main()
