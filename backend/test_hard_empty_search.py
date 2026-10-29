"""No provider runs when strict current metadata proves no eligible films."""
from dataclasses import replace
import unittest
import test_integrated_search as integration
from app.services.rerank_admission import VOYAGE_MODEL
from app.services.semantic_search import SemanticError


class HardEmptySearchTests(unittest.TestCase):
    setUp=integration.IntegratedSearchTests.setUp

    def test_hard_empty_is_proven_locally_even_with_an_uncalibrated_model(self):
        self.engine.policy=replace(self.engine.policy,rerank_model=VOYAGE_MODEL)
        self.engine.eligible=lambda plan,ids:[]
        q='films about a person building a house, before 1910'
        r=self.engine.submit(q)
        self.assertEqual(r['status'],'ready',r)
        self.assertEqual(r['source'],'local')
        self.assertEqual(r['results']['total'],0)
        self.assertEqual(r['semantic']['no_match_basis'],'strict_metadata_eligibility')
        self.assertEqual(r['plan']['year_max'],1909)
        self.decision.decide.assert_not_called();self.reranker.rank.assert_not_called()
        self.assertEqual(self.embedding.calls,[])
        self.assertEqual(self.engine.resume(q,r['snapshot'])['results'],r['results'])

    def test_relaxation_or_new_eligible_metadata_invalidates_empty_proof(self):
        self.engine.policy=replace(self.engine.policy,rerank_model=VOYAGE_MODEL)
        self.engine.eligible=lambda plan,ids:[]
        q='films about a person building a house, before 1910'
        r=self.engine.submit(q)
        self.engine.eligible=lambda plan,ids:[self.docs[0].film_id]
        with self.assertRaisesRegex(SemanticError,'search_snapshot_requires_submit'):
            self.engine.resume(q,r['snapshot'])
        self.decision.decide.assert_not_called();self.reranker.rank.assert_not_called()
        self.assertEqual(self.embedding.calls,[])

    def test_no_empty_shortcut_for_an_unresolved_person(self):
        self.engine.eligible=lambda plan,ids:[]
        self.engine.resolve_hard=lambda plan,ids:{
            'status':'needs_clarification','reason':'ambiguous_person',
            'constraints':[],'issues':[],'people_ids':{}}
        r=self.engine.submit('films directed by Unknown Person about a voyage')
        self.assertEqual(r.get('status'),'needs_clarification',r)
        self.assertIsNone(r.get('results'))
        self.decision.decide.assert_not_called();self.reranker.rank.assert_not_called()

    def test_unresolved_or_malformed_sql_evidence_is_not_a_correct_empty(self):
        self.engine.policy=replace(self.engine.policy,rerank_model=VOYAGE_MODEL)
        for value in ({"status":"needs_clarification","eligible_ids":[]},
                      {"status":"unavailable","eligible_ids":[]}, None,
                      {"status":"ready","eligible_ids":None}):
            with self.subTest(value=value):
                self.engine.eligible=lambda plan,ids:value
                r=self.engine.submit("films about family")
                self.assertEqual(r["status"],"unavailable",r)
                self.assertIsNone(r["results"])
        self.decision.decide.assert_not_called();self.reranker.rank.assert_not_called()

    def test_nonempty_scope_retains_the_uncalibrated_model_guard(self):
        self.engine.policy=replace(self.engine.policy,rerank_model=VOYAGE_MODEL)
        self.engine.eligible=lambda plan,ids:[self.docs[0].film_id]
        r=self.engine.submit('films about family')
        self.assertEqual(r['reason'],'search_rerank_uncalibrated')
        self.assertIsNone(r['results'])
        self.decision.decide.assert_not_called();self.reranker.rank.assert_not_called()
        self.assertEqual(self.embedding.calls,[])


if __name__=='__main__':unittest.main()

