"""Rule/algorithm regressions. Handwritten vectors test contracts, NOT model quality."""
from dataclasses import replace
import math
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from app.services.retrieval_policy import (LexicalIndex, RetrievalIndex, RetrievalPolicy,
    features, substantive)
from app.services.semantic_search import ContentDocument, ContentSource, ProviderSpec, SemanticError

SPEC = ProviderSpec("synthetic/policy-contract", "v1", 3)


def fid(n):
    return "film_" + f"{n:032x}"


def doc(n, text, title=None, aliases=()):
    return ContentDocument(fid(n), title or f"Film {n}", aliases,
                           (ContentSource("overview", text, "rule"),))


def vec(cosine):
    return [cosine, math.sqrt(1 - cosine ** 2), 0.]


def index(docs, cosines, policy=None):
    return RetrievalIndex(docs, {d.film_id: vec(c) for d, c in zip(docs, cosines)}, SPEC, policy)


class RetrievalPolicyTests(unittest.TestCase):
    def test_policy_bounds_finite_values_and_version_fingerprint(self):
        original = RetrievalPolicy()
        self.assertNotEqual(original.fingerprint, replace(original, candidate_k=10).fingerprint)
        for name, value in (("candidate_k", True), ("candidate_k", 101), ("candidate_k", 0),
                            ("k1", float("nan")), ("b", 1.1), ("theme_coverage", True),
                            ("rrf_k", 0), ("theme_supported", .9)):
            with self.subTest(name=name), self.assertRaises(SemanticError):
                replace(original, **{name: value})

    def test_idf_rare_evidence_outweighs_repeated_common_word(self):
        lex = LexicalIndex({"a": "family " * 30, "b": "family observatory",
                            "c": "family work", "d": "family holiday"},
                           {key: set() for key in "abcd"}, RetrievalPolicy())
        self.assertGreater(lex.idf("w:observatory"), lex.idf("w:family"))
        self.assertGreater(lex.evidence("family observatory", "b").bm25,
                           lex.evidence("family observatory", "a").bm25)
        self.assertGreater(lex.evidence("family observatory", "b").coverage,
                           lex.evidence("family observatory", "a").coverage)

    def test_bm25_saturates_repetition_and_normalizes_length(self):
        lex = LexicalIndex({"a": "observatory", "b": "observatory " * 100,
                            "c": "observatory " + "routine " * 100},
                           {key: set() for key in "abc"}, RetrievalPolicy())
        once = lex.evidence("observatory", "a").bm25
        self.assertLess(lex.evidence("observatory", "b").bm25, once * 3)
        self.assertGreater(once, lex.evidence("observatory", "c").bm25)

    def test_coverage_is_reproducible_across_process_hash_seeds(self):
        script = '''
from dataclasses import asdict
import json
from app.services.retrieval_policy import LexicalIndex,RetrievalPolicy
texts={str(i): ' '.join('word'+str(n) for n in range(i+1)) for i in range(20)}
index=LexicalIndex(texts,{key:set() for key in texts},RetrievalPolicy())
print(json.dumps([asdict(index.evidence(' '.join('word'+str(n) for n in range(23)),key)) for key in texts],sort_keys=True))
'''
        results = [subprocess.check_output([sys.executable, "-X", "utf8", "-c", script],
                    env={**os.environ, "PYTHONHASHSEED": str(seed)}) for seed in (1, 19, 997)]
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0], results[2])

    def test_cjk_bigrams_character_fallback_and_fullwidth_normalization(self):
        terms = features("陪伴与记忆ＡＩ")
        self.assertIn("b:陪伴", terms)
        self.assertIn("b:记忆", terms)
        self.assertIn("c:忆", terms)
        self.assertIn("w:ai", terms)
        self.assertNotIn("b:伴与", terms)
        self.assertNotIn("b:电影", substantive(features("电影")))
        self.assertEqual(features("ROBOT families"), features("robot family"))

    def test_short_exact_titles_and_aliases_survive_generic_terms_no_fuzzy_identity(self):
        docs = (doc(1, "An unrelated memory.", "It", ("它", "In")),
                doc(2, "An unrelated memory.", "Its"),
                doc(3, "An unrelated memory.", "It"))
        engine = index(docs, [.1, .99, .2])
        for title in ("ＩＴ", "in", "它"):
            result = engine.search(title, eligible_ids=[d.film_id for d in docs],
                query_vector=[1, 0, 0], strategy="hybrid")
            expected = {fid(1), fid(3)} if title == "ＩＴ" else {fid(1)}
            self.assertEqual(set(result.displayed_ids), expected)
            self.assertTrue(all(c.reason == "exact_identity" for c in result.candidates if c.admitted))

    def test_generic_only_query_cannot_pass_through_high_cosine_or_rrf(self):
        docs = (doc(1, "A film movie story. 电影影片故事。"),)
        engine = index(docs, [.99])
        for q in ("find movies", "电影故事", "the film"):
            for mode in ("factual", "exploratory"):
                result = engine.search(q, eligible_ids=[fid(1)], query_vector=[1, 0, 0], mode=mode)
                self.assertTrue(result.candidates)
                self.assertEqual(result.displayed_ids, [])

    def test_wide_recall_keeps_subthreshold_candidate_without_auto_display(self):
        docs = (doc(1, "Technology changes memory and companionship."),
                doc(2, "A completely different voyage."))
        engine = index(docs, [.326, .20])
        wide = engine.search("technology and memory", eligible_ids=[fid(1), fid(2)],
                             query_vector=[1, 0, 0], strategy="dense", stage="candidates")
        self.assertEqual(len(wide.candidates), 2)
        self.assertEqual(wide.displayed_ids, [])
        final = engine.search("technology and memory", eligible_ids=[fid(1), fid(2)],
            query_vector=[1, 0, 0], strategy="dense", mode="exploratory")
        self.assertEqual(final.displayed_ids, [fid(1)])
        self.assertEqual(final.candidates[0].reason, "theme_semantic_anchor")

    def test_theme_paraphrase_anchor_does_not_require_literal_majority(self):
        docs = (doc(1, "An observatory beside a lake."), doc(2, "A distant voyage."))
        engine = index(docs, [.32, .1])
        question = "observatory longing companionship identity meaning everyday uncertainty reconciliation"
        result = engine.search(question, eligible_ids=[fid(1), fid(2)], query_vector=[1, 0, 0],
                               mode="exploratory")
        self.assertEqual(result.displayed_ids, [fid(1)])
        self.assertLess(result.candidates[0].lexical.coverage, .12)
        strict = engine.search(question, eligible_ids=[fid(1), fid(2)], query_vector=[1, 0, 0])
        self.assertEqual(strict.displayed_ids, [])

    def test_multiple_rare_anchors_can_support_literal_results_without_semantics(self):
        docs = (doc(1, "An observatory orbital voyage."), *[doc(n, "A daily routine.") for n in range(2, 13)])
        engine = index(docs, [.1] * len(docs))
        result = engine.search("observatory orbital memory identity reconciliation", strategy="lexical",
                               eligible_ids=[d.film_id for d in docs])
        self.assertEqual(result.displayed_ids, [fid(1)])
        self.assertEqual(result.candidates[0].reason, "factual_lexical_anchor_bundle")
        self.assertLess(result.candidates[0].lexical.coverage, .70)

    def test_weak_lexical_only_rank_never_buys_admission(self):
        docs = (doc(1, "Daily life around a motel."),)
        engine = index(docs, [.1])
        for strategy in ("lexical", "hybrid"):
            result = engine.search("repeated daily work and meaningful routine", eligible_ids=[fid(1)],
                query_vector=[1, 0, 0], strategy=strategy, mode="exploratory")
            self.assertGreater(result.candidates[0].rrf, 0)
            self.assertEqual(result.displayed_ids, [])

    def test_strict_fact_clauses_require_all_evidence_broad_theme_is_separate(self):
        docs = (doc(1, "A family faces economic hardship."),
                doc(2, "A family faces hardship aboard an orbital station."))
        engine = index(docs, [.8, .4])
        request = "family hardship and orbital station"
        strict = engine.search(request, eligible_ids=[fid(1), fid(2)], query_vector=[1, 0, 0])
        self.assertEqual(strict.displayed_ids, [fid(2)])
        broad = engine.search(request, eligible_ids=[fid(1), fid(2)], query_vector=[1, 0, 0],
                              mode="exploratory")
        self.assertIn(fid(1), broad.displayed_ids)
        self.assertEqual(strict.candidates[0].reason, "factual_incomplete_evidence")

    def test_char_only_overlap_cannot_admit_factual_query(self):
        docs = (doc(1, "午夜的灯照着港口。"),)
        engine = index(docs, [.9])
        result = engine.search("木星法庭", eligible_ids=[fid(1)], query_vector=[1, 0, 0])
        self.assertEqual(result.displayed_ids, [])

    def test_reference_uses_different_distribution_excludes_self_no_query_vector(self):
        docs = (doc(1, "A family memory."), doc(2, "A distant voyage."),
                doc(3, "A family memory."))
        # Unit axes make reference/doc and natural-language/doc distinct.
        engine = RetrievalIndex(docs, {fid(1): [1, 0, 0], fid(2): vec(.4), fid(3): vec(.8)}, SPEC)
        result = engine.search("similar to Film 1", reference_id=fid(1),
                               eligible_ids=[fid(1), fid(2), fid(3)], strategy="dense")
        self.assertNotIn(fid(1), [c.film_id for c in result.candidates])
        self.assertEqual(result.mode, "reference")
        self.assertEqual(result.displayed_ids, [fid(3)])
        with self.assertRaisesRegex(SemanticError, "reference_missing_content"):
            engine.search("similar", reference_id=fid(99), eligible_ids=[fid(1)])

    def test_hard_eligibility_precedes_bounded_topk_and_reapplies_without_any_api(self):
        docs = tuple(doc(n, "An observatory family voyage.") for n in range(1, 6))
        engine = index(docs, [.9, .8, .7, .6, .5], RetrievalPolicy(candidate_k=1))
        with patch("socket.create_connection", side_effect=AssertionError("no network")):
            restricted = engine.search("observatory family voyage", eligible_ids=[fid(5)],
                                       query_vector=[1, 0, 0], strategy="dense")
            empty = engine.search("observatory family voyage", eligible_ids=[], strategy="dense")
            enlarged = engine.search("observatory family voyage", eligible_ids=[fid(1), fid(5)],
                                     query_vector=[1, 0, 0], strategy="dense")
        self.assertEqual(restricted.displayed_ids, [fid(5)])
        self.assertEqual(restricted.dense_ids, (fid(5),))
        self.assertEqual(empty.candidates, ())
        self.assertEqual(enlarged.dense_ids, (fid(1),))

    def test_candidates_are_bounded_deterministic_and_accepted_is_a_subset(self):
        docs = tuple(doc(n, "A family memory and work.") for n in range(1, 20))
        engine = index(docs, [.5] * len(docs), RetrievalPolicy(candidate_k=3))
        args = dict(eligible_ids={d.film_id for d in docs}, query_vector=[1, 0, 0])
        result = engine.search("family work", **args)
        self.assertEqual(result, engine.search("family work", **args))
        self.assertLessEqual(len(result.candidates), 6)
        self.assertLessEqual(len(result.dense_ids), 3)
        self.assertLessEqual(len(result.lexical_ids), 3)
        self.assertLessEqual(set(result.displayed_ids), {c.film_id for c in result.candidates})

    def test_private_queries_and_invalid_vectors_modes_ids_fail_before_retrieval(self):
        engine = index((doc(1, "Public family memory."),), [.5])
        for q in ("Movies//My Private Film.mkv", "`/private.mkv`", "~/Movies/private.mkv"):
            with self.assertRaisesRegex(SemanticError, "private_input"):
                engine.search(q, eligible_ids=[fid(1)], query_vector=[1, 0, 0])
        for kwargs in ({"query_vector": [1, 0]}, {"query_vector": [True, 0, 1]},
                       {"query_vector": [float("nan"), 0, 1]}, {"mode": "auto-ai"},
                       {"stage": "unknown"}, {"eligible_ids": ["invalid"]},
                       {"mode": []}, {"strategy": []}, {"stage": []}):
            with self.subTest(kwargs=kwargs), self.assertRaises(SemanticError):
                engine.search("family memory", **{"eligible_ids": [fid(1)], "query_vector": [1, 0, 0], **kwargs})

    def test_lexical_mode_never_uses_query_vector_for_admission(self):
        engine = index((doc(1, "Memory alone."),), [.9])
        args = dict(eligible_ids=[fid(1)], mode="exploratory", strategy="lexical")
        one = engine.search("technology memory companionship", **args)
        two = engine.search("technology memory companionship", query_vector=[1, 0, 0], **args)
        self.assertEqual(one, two)
        self.assertIsNone(one.candidates[0].cosine)


if __name__ == "__main__":
    unittest.main()
