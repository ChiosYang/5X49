"""Hand-computed rank-separation tests; no claim of relevance calibration."""
from dataclasses import replace
from types import SimpleNamespace
import unittest

import test_integrated_search as integration
from app.services.integrated_search import IntegratedSearchPolicy
from app.services.rerank_admission import LEGACY_MODEL, VOYAGE_MODEL, admitted_ids, separated_head
from app.services.semantic_search import SemanticError


class AdmissionTests(unittest.TestCase):
    def test_separation_is_not_an_absolute_probability_threshold(self):
        scores = {"a": .95, "b": .9, "c": .2, "d": .1}
        result = separated_head(scores)
        self.assertEqual(result.ids, ("a", "b"))  # gap .7 > half-range .425
        self.assertFalse(result.relevance_calibrated)
        self.assertFalse(result.noanswer_determined)
        for offset, scale in ((.1, .7), (0, .1), (.4, .2)):
            transformed = {key: offset + scale*value for key, value in scores.items()}
            self.assertEqual(separated_head(transformed).ids, result.ids)

    def test_flat_sparse_or_gradual_scores_do_not_invent_noanswer(self):
        for scores, reason in (({}, "insufficient_comparison"), ({"a": .99}, "insufficient_comparison"),
                               ({"a": .9, "b": .9}, "flat_scores"),
                               ({"a": .9, "b": .6, "c": .3}, "no_dominant_separation")):
            result = separated_head(scores)
            self.assertEqual(result.ids, ())
            self.assertEqual(result.reason, reason)
            self.assertFalse(result.noanswer_determined)
            self.assertFalse(result.relevance_calibrated)

    def test_cap_ties_and_bad_values(self):
        scores = {str(i): .9 if i < 6 else .1 for i in range(10)}
        self.assertEqual(separated_head(scores).reason, "head_exceeds_cap")
        tied = {"b": .8, "a": .8, "c": .2}
        self.assertEqual(separated_head(tied).ids, ("a", "b"))
        for value in (float("nan"), float("inf"), -.1, 1.1, True):
            with self.subTest(value=value), self.assertRaises(SemanticError):
                separated_head({"a": value})
        with self.assertRaises(SemanticError):
            separated_head({str(i): .5 for i in range(21)})
        for maximum in (0, 21, True, "5"):
            with self.subTest(maximum=maximum), self.assertRaises(SemanticError):
                separated_head(tied, maximum=maximum)

    def test_legacy_threshold_is_model_bound_and_result_count_is_finite(self):
        candidates = [SimpleNamespace(film_id=str(i), rrf=1/(i+1), admitted=False) for i in range(20)]
        scores = {str(i): .3 for i in range(20)}
        result = admitted_ids(candidates, scores, model=LEGACY_MODEL, threshold=.09, maximum=5)
        self.assertEqual(result, [str(i) for i in range(5)])
        for model in (VOYAGE_MODEL, "unreviewed/model"):
            with self.subTest(model=model), self.assertRaisesRegex(SemanticError, "search_rerank_uncalibrated"):
                admitted_ids(candidates, scores, model=model, threshold=.09, maximum=5)

    def test_missing_native_scores_use_existing_local_evidence(self):
        candidates = [SimpleNamespace(film_id="a", rrf=.3, admitted=True),
                      SimpleNamespace(film_id="b", rrf=.2, admitted=False),
                      SimpleNamespace(film_id="c", rrf=.1, admitted=False)]
        self.assertEqual(admitted_ids(candidates, {"c": .9}, model=LEGACY_MODEL, threshold=.09, maximum=5), ["c", "a"])


class ModelContractTests(unittest.TestCase):
    setUp = integration.IntegratedSearchTests.setUp

    def test_unknown_score_scale_stops_before_any_provider_and_is_not_empty(self):
        self.engine.policy = replace(self.engine.policy, rerank_model=VOYAGE_MODEL)
        result = self.engine.submit("films about a family reunion")
        self.assertEqual(result["status"], "unavailable", result)
        self.assertEqual(result["reason"], "search_rerank_uncalibrated")
        self.assertIsNone(result["results"])
        self.decision.decide.assert_not_called()
        self.reranker.rank.assert_not_called()
        self.assertEqual(self.embedding.calls, [])

    def test_declared_model_cannot_reuse_another_models_profile(self):
        self.reranker.model_id = VOYAGE_MODEL
        result = self.engine.submit("films about family")
        self.assertEqual(result["reason"], "search_rerank_uncalibrated")
        self.decision.decide.assert_not_called()
        self.reranker.rank.assert_not_called()

    def test_cap_is_part_of_snapshot_contract_and_restore_never_infers(self):
        self.engine.policy = replace(self.engine.policy, max_results=1)
        result = self.engine.submit("films about a family reunion")
        self.assertEqual(result["results"]["total"], 1)
        self.assertEqual(result["semantic"]["result_cap"], 1)
        self.assertEqual(self.engine.resume("films about a family reunion", result["snapshot"])["results"], result["results"])
        self.engine.policy = replace(self.engine.policy, max_results=2)
        with self.assertRaisesRegex(SemanticError, "search_snapshot_requires_submit"):
            self.engine.resume("films about a family reunion", result["snapshot"])
        for values in ({"max_results": 0}, {"max_results": True}, {"rerank_model": None}):
            with self.subTest(values=values), self.assertRaises(SemanticError):
                IntegratedSearchPolicy(**values)


if __name__ == "__main__":
    unittest.main()
