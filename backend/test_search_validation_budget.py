"""Synthetic continuation tests: no network, actual data, or credentials."""
import json
from pathlib import Path
import tempfile
import unittest

from app.evaluation.search_validation_budget import ValidationBudget, PREFIX
from app.services.search_budget import SearchAuthorization, SearchBudget
from app.services.semantic_search import SemanticError, _hash


class BoundedValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'ledger.db'
        # Deliberately expired original grant. Only the supplementary view can act.
        self.auth = SearchAuthorization('synthetic-expired-original', 320, '0', 10)
        self.budget = ValidationBudget(self.path, self.auth, clock=lambda:100)
        self.addCleanup(self.budget.close)
        with self.budget.db:
            for n in range(1, 138):
                self.budget.db.execute('INSERT INTO search_budget_receipts VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (n,'document','persistent-test-library.v1' if n==137 else 'public-evaluation.v2',
                     _hash(str(n)),100,'0','uncertain' if n in {50,137} else 'reported','{}',
                     None if n in {50,137} else '0',1.0))
            self.budget.db.execute('INSERT INTO search_budget_meta VALUES (?,?)',('halted','search_provider_unavailable'))
        self.rows = self.budget._rows()
        self.batches = [_hash(str(137)), *[_hash(f'batch-{i}') for i in range(3)]]
        self.grant = {'version':'bounded-validation-grant.v1','original_grant':self.auth.fingerprint,
            'baseline':137,'max_attempts':191,'issued':99,'expires':200,
            'original_rows_sha256':_hash(self.rows),'historical_meta_sha256':_hash(self.budget.historical_meta()),
            'document_batches':self.batches}

    def reserve(self, purpose='document', scope='persistent-test-library.v1', digest=None):
        return self.budget.reserve(purpose, scope, input_hash=digest or self.batches[0],tokens=100,reservation='0')

    def settled_repeat(self):
        self.budget.activate(self.grant); number = self.reserve()
        self.budget.capture(number,{'id':'gen-synthetic','usage':{'total_tokens':10,'cost':0}})
        self.budget.settle(number,{'usage':{'total_tokens':10,'cost':0}},1)
        # Isolate accounting tests from vector storage; real completion is tested separately.
        with self.budget.db:
            self.budget.db.execute('INSERT INTO search_budget_meta VALUES (?,?)',(PREFIX+'repeat_complete','synthetic'))

    def test_no_activation_and_wrong_first_batch_or_query_do_not_reserve(self):
        with self.assertRaises(SemanticError): self.reserve()
        self.budget.activate(self.grant)
        for purpose, scope, digest in [('document','persistent-test-library.v1',self.batches[1]),
            ('query','public-evaluation.v2',_hash('q'))]:
            with self.assertRaises(SemanticError): self.reserve(purpose,scope,digest)
        self.assertEqual(len(self.budget._rows()),137)

    def test_repeat_once_and_standard_budget_still_blocked(self):
        self.settled_repeat()
        with self.assertRaises(SemanticError): self.reserve()
        self.assertEqual(self.budget.db.execute("SELECT value FROM search_budget_meta WHERE key='halted'").fetchone()[0], 'search_provider_unavailable')
        standard=SearchBudget(self.path,self.auth);self.addCleanup(standard.close)
        with self.assertRaises(SemanticError):standard.reserve('query','public-evaluation.v2',input_hash=_hash('x'),tokens=1,reservation='0')
        self.assertEqual(self.budget._rows()[:137],self.rows)

    def test_uncertain_repeat_blocks_all_future_dispatch_without_retry(self):
        self.budget.activate(self.grant); n=self.reserve();self.budget.fail(n,'search_provider_unavailable',2)
        for _ in range(2):
            with self.assertRaises(SemanticError):self.reserve()
        self.assertEqual(len(self.budget._rows()),138)
        self.assertEqual(self.budget._rows()[:137],self.rows)

    def test_new_rerank_rate_limit_stops_both_scopes_after_successful_repeat(self):
        self.settled_repeat()
        n = self.reserve('rerank', 'public-evaluation.v2', _hash('bounded candidates'))
        self.budget.fail(n, 'provider_http_429', .3)
        for scope in ('public-evaluation.v2', 'persistent-test-library.v1'):
            with self.assertRaises(SemanticError):
                self.reserve('query', scope, _hash('next query'))
        self.assertEqual(len(self.budget._rows()), 139)
        self.assertEqual(self.budget._rows()[:137], self.rows)
        summary = self.budget.summary()
        self.assertEqual(summary['halted'], 'provider_http_429')
        self.assertFalse(summary['total_cost_finalized'])
        self.assertIsNone(self.budget._rows()[-1]['cost'])

    def test_phase_restart_after_new_failure_never_reads_credential_or_calls_provider(self):
        from unittest.mock import patch
        from app.evaluation import search_validation_resume as runner
        self.settled_repeat()
        n = self.reserve('rerank', 'public-evaluation.v2', _hash('bounded candidates'))
        self.budget.fail(n, 'provider_http_429', .3)
        with patch.object(runner, 'accounting', return_value=self.budget.summary()), \
             patch.object(runner, 'manifest_runtime') as runtime, \
             patch.object(runner, 'client_for') as client, \
             patch.object(runner, 'existing_credential') as credential:
            for phase in (runner.library, runner.seen):
                with self.assertRaisesRegex(SemanticError, 'search_budget_blocked'):
                    phase(None, self.grant, {})
            runtime.assert_not_called()
            client.assert_not_called()
            credential.assert_not_called()

    def test_changed_historical_metadata_cannot_be_hidden_by_supplement(self):
        self.settled_repeat()
        with self.budget.db:
            self.budget.db.execute("UPDATE search_budget_meta SET value='changed' WHERE key='halted'")
        with self.assertRaises(SemanticError):
            self.reserve('query', 'public-evaluation.v2', _hash('query'))
        self.assertEqual(len(self.budget._rows()), 138)

    def test_changed_grant_or_historical_receipt_rejected(self):
        self.budget.activate(self.grant)
        with self.assertRaises(SemanticError):self.budget.activate({**self.grant,'max_attempts':192})
        with self.budget.db:self.budget.db.execute("UPDATE search_budget_receipts SET cost='0' WHERE number=50")
        with self.assertRaises(SemanticError):self.reserve()

    def test_expiry_and_missing_durable_repeat_proof_block(self):
        self.budget.activate(self.grant);n=self.reserve()
        self.budget.capture(n,{'usage':{'total_tokens':1,'cost':0}});self.budget.settle(n,{'usage':{'total_tokens':1,'cost':0}},1)
        with self.assertRaises(SemanticError):self.reserve('query','public-evaluation.v2',_hash('q'))
        self.budget.clock=lambda:201
        with self.assertRaises(SemanticError):self.reserve()

    def test_stage_and_total_caps_are_shared_and_keep_unknowns(self):
        self.settled_repeat()
        def settle(n):self.budget.settle(n,{'usage':{'total_tokens':1,'cost':0}},1)
        for digest in self.batches[1:]:settle(self.reserve(digest=digest))
        for scope,cap in [('persistent-test-library.v1',30),('public-evaluation.v2',20)]:
            for i in range(cap):settle(self.reserve('query',scope,_hash(str(i))))
            with self.assertRaises(SemanticError):self.reserve('query',scope,_hash('extra'))
        self.assertEqual(len(self.budget._rows()),191)
        self.assertEqual(self.budget._rows()[:137],self.rows)

    def test_completion_requires_saved_vectors_and_preserves_original(self):
        import sqlite3
        from app.services.search_index import SearchIndexStore
        from app.services.search_providers import EMBEDDING,embedding_spec
        texts=['Public synthetic overview.']
        digest=_hash([{'input':texts,'encoding_format':'float','input_type':'passage'},'document'])
        with self.budget.db:self.budget.db.execute('UPDATE search_budget_receipts SET input_hash=? WHERE number=137',(digest,))
        self.rows=self.budget._rows();self.batches[0]=digest
        self.grant.update(original_rows_sha256=_hash(self.rows),document_batches=self.batches)
        self.budget.activate(self.grant);n=self.reserve()
        self.budget.capture(n,{'id':'gen-safe-synthetic','model':EMBEDDING.model,'provider':EMBEDDING.provider_name,'usage':{'total_tokens':1,'cost':0}})
        self.budget.settle(n,{'usage':{'total_tokens':1,'cost':0}},1)
        db=sqlite3.connect(':memory:');self.addCleanup(db.close)
        store=SearchIndexStore(db);spec=embedding_spec()
        with self.assertRaises(SemanticError):self.budget.complete_repeat(store,spec,texts)
        store.remember_vector(texts[0],[1.]+[0.]*4095,spec,query=False)
        proof=self.budget.complete_repeat(store,spec,texts)
        self.assertEqual(proof['repeat_number'],138)
        self.assertIsNone(self.budget.summary()['halted'])
        self.assertEqual(self.budget._rows()[:137],self.rows)
        with self.assertRaises(SemanticError):self.budget.complete_repeat(store,spec,texts)


if __name__=='__main__':unittest.main()
