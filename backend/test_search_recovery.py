"""New explicit authorization does not erase an uncertain original call."""
from pathlib import Path
import sqlite3
import tempfile
import unittest

from app.evaluation.search_recovery import ContinuedBudget, IndexTimeoutClient, TraceSession
from app.services.search_budget import SearchAuthorization, SearchBudget
from app.services.search_index import SearchIndexStore
from app.services.search_providers import SearchProviderClient, SearchEmbeddingProvider, EgressScope
from app.services.semantic_search import SemanticError, _hash
from test_search_providers import Transport, DOCUMENTS, QUERY


class ExplicitRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'ledger.db'
        self.auth=SearchAuthorization('synthetic-recovery-grant',10,'0',2000000000)
        self.base=SearchBudget(self.path,self.auth); self.addCleanup(self.base.close)
        self.body={'input':list(DOCUMENTS),'encoding_format':'float','input_type':'passage'}
        self.input_hash=_hash([self.body,'document'])
        self.tokens=sum(len(t.encode())+256 for t in DOCUMENTS)
        self.old=self.base.reserve('document','public-evaluation.v2',input_hash=self.input_hash,tokens=self.tokens,reservation='0')
        self.base.fail(self.old,'search_provider_unavailable',20)
        self.original=self.base.summary()['receipts'][0].copy()
        self.ledger=ContinuedBudget.view(self.base)
        self.transport=Transport()
        scope=EgressScope('public-evaluation.v2',frozenset(_hash(t) for t in DOCUMENTS),frozenset({_hash(QUERY)}),True)
        self.client=SearchProviderClient(self.ledger,scope,lambda:'synthetic-key',session=self.transport)
        self.addCleanup(self.client.close); self.client.preflight()
        self.connection=sqlite3.connect(':memory:'); self.addCleanup(self.connection.close)
        self.store=SearchIndexStore(self.connection)

    def approve(self): self.ledger.authorize_repeat(self.old,self.input_hash)

    def successful_repeat(self):
        self.approve()
        native=SearchEmbeddingProvider(IndexTimeoutClient(self.client))
        values=native.embed(DOCUMENTS,query=False)
        for text,vector in zip(DOCUMENTS,values): self.store.remember_vector(text,vector,native.spec,query=False)
        self.ledger.complete_repeat(self.store,native.spec,DOCUMENTS)
        return native

    def test_no_authorization_and_wrong_batch_fail_before_any_post(self):
        with self.assertRaises(SemanticError): SearchEmbeddingProvider(self.client).embed(DOCUMENTS,query=False)
        self.approve()
        with self.assertRaises(SemanticError): SearchEmbeddingProvider(self.client).embed(DOCUMENTS[:1],query=False)
        self.assertEqual(self.transport.posts,[])
        self.assertEqual(self.base.summary()['attempts'],1)

    def test_original_unknown_and_historical_halt_survive_successful_repeat(self):
        self.successful_repeat()
        self.assertEqual(self.base.summary()['receipts'][0],self.original)
        self.assertEqual(self.base.summary()['halted'],'search_provider_unavailable')
        result=self.ledger.summary()
        self.assertIsNone(result['halted'])
        self.assertEqual(result['acknowledged_uncertain_receipts'],[self.old])
        self.assertEqual(result['requests'],2)
        self.assertIsNone(result['receipts'][0]['cost'])
        self.assertEqual(self.transport.posts[0][1]['timeout'],60)
        self.assertEqual(self.transport.posts[0][1]['json']['input'],list(DOCUMENTS))

    def test_no_later_query_until_vectors_are_durable_and_query_stays20(self):
        self.approve()
        native=SearchEmbeddingProvider(IndexTimeoutClient(self.client))
        values=native.embed(DOCUMENTS,query=False)
        with self.assertRaises(SemanticError): native.embed((QUERY,),query=True)
        with self.assertRaises(SemanticError): self.ledger.complete_repeat(self.store,native.spec,DOCUMENTS)
        for text,vector in zip(DOCUMENTS,values): self.store.remember_vector(text,vector,native.spec,query=False)
        self.ledger.complete_repeat(self.store,native.spec,DOCUMENTS)
        native.embed((QUERY,),query=True)
        self.assertEqual([options['timeout'] for _,options in self.transport.posts],[60,20])
        with self.assertRaises(SemanticError): self.base.reserve('query','public-evaluation.v2',input_hash=_hash('x'),tokens=20,reservation='0')

    def test_a_second_uncertain_attempt_stops_without_erasing_original(self):
        import requests
        self.approve(); self.transport.failure=requests.ReadTimeout()
        with self.assertRaises(SemanticError): SearchEmbeddingProvider(IndexTimeoutClient(self.client)).embed(DOCUMENTS,query=False)
        with self.assertRaises(SemanticError): SearchEmbeddingProvider(IndexTimeoutClient(self.client)).embed(DOCUMENTS,query=False)
        self.assertEqual(len(self.transport.posts),1)
        self.assertEqual([r['state'] for r in self.base.summary()['receipts']],['uncertain','uncertain'])
        self.assertEqual(self.base.summary()['receipts'][0],self.original)

    def test_unknown_original_still_consumes_total_authorization_cap(self):
        self.successful_repeat()
        native=SearchEmbeddingProvider(self.client)
        for _ in range(8): native.embed((QUERY,),query=True)
        with self.assertRaises(SemanticError): native.embed((QUERY,),query=True)
        self.assertEqual(self.ledger.summary()['attempts'],10)
        self.assertEqual(len(self.transport.posts),9)
        self.assertEqual(self.base.summary()['receipts'][0],self.original)

    def test_completed_repeat_cannot_be_dispatched_a_second_time(self):
        self.successful_repeat()
        with self.assertRaises(SemanticError): SearchEmbeddingProvider(self.client).embed(DOCUMENTS,query=False)
        self.assertEqual(len(self.transport.posts),1)

    def test_partial_http200_body_preserves_safe_trace_and_stops_new_calls(self):
        import json
        import requests
        from test_search_providers import Response
        class Partial(Response):
            headers={'Date':'Fri,23 Oct2026','CF-RAY':'synthetic-ray','Authorization':'must-not-log'}
            def iter_content(self,size):
                yield b'{"id":"synthetic-incomplete'
                raise requests.exceptions.ChunkedEncodingError('synthetic interrupted body')
        original=self.transport.post
        self.transport.post=lambda *args,**kwargs: Partial(original(*args,**kwargs).payload)
        trace=Path(self.temp.name)/'trace'; trace.mkdir()
        self.client.session=TraceSession(self.transport,self.ledger,trace)
        self.approve()
        with self.assertRaises(SemanticError): SearchEmbeddingProvider(IndexTimeoutClient(self.client)).embed(DOCUMENTS,query=False)
        events=[json.loads(line) for line in (trace/'transport-002.jsonl').read_text().splitlines()]
        self.assertEqual([e['event'] for e in events],['transport_invoked','headers_received','body_exception'])
        self.assertEqual(events[1]['status'],200)
        self.assertEqual(events[2]['exception_type'],'ChunkedEncodingError')
        self.assertNotIn('must-not-log',json.dumps(events))
        with self.assertRaises(SemanticError): SearchEmbeddingProvider(self.client).embed(DOCUMENTS,query=False)
        self.assertEqual(len(self.transport.posts),1)


if __name__=='__main__': unittest.main()
