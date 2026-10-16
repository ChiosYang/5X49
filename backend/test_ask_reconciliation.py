import copy
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import httpx
from openai import OpenAI
from app.services.ask import AskError

from app.evaluation.ask import (
    AUTHORIZATION, BASE_URL, CANONICAL_MODEL, MODEL, POLICY, PROVIDER, PaidClient,
    live, official_preflight, reconcile_canary, verify_generation_identity, verify_reconciliation,
)
from app.evaluation.ask_budget import BudgetLedger, BudgetStop


class AskReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'budget.sqlite3'
        self.ledger = BudgetLedger(self.path)
        self.attempt_id = self.ledger.reserve('original-run', 'ask-01', 8000, 1600)
        with self.assertRaises(BudgetStop):
            self.ledger.settle(self.attempt_id, cost=None, generation_id='gen-synthetic',
                               outcome='unknown_billing_or_provider')
        self.preflight = {
            'model': MODEL, 'canonical_model': CANONICAL_MODEL,
            'directory_source': BASE_URL + '/models',
            'source': BASE_URL + '/models/' + MODEL + '/endpoints',
            'provider_tag': PROVIDER, 'provider_name': 'Decart',
            'pricing': {'prompt': '0.00000009', 'completion': '0.00000018'},
            'token_upper_bound': 8000, 'output_limit': 1600,
            'billing_input_reservation': 1048576,
        }
        self.metadata = {
            'id': 'gen-synthetic', 'model': CANONICAL_MODEL, 'provider_name': 'Decart',
            'total_cost': 0.00012861, 'native_tokens_prompt': 1267, 'native_tokens_completion': 81,
            'tokens_prompt': 1147, 'tokens_completion': 75, 'native_tokens_reasoning': 0,
            'native_tokens_cached': 0, 'cache_discount': None, 'is_byok': False,
            'cancelled': False, 'finish_reason': 'stop',
        }
        self.report = {
            'evidence_class': 'live_synthetic_questions', 'run_id': 'original-run',
            'model': MODEL, 'mode': 'canary', 'request_policy': POLICY,
            'complete': False, 'stop_reason': 'uncertain_billing_stop',
            'preflight': self.preflight, 'ledger': self.ledger.summary(),
            'cases': [{'case_id': 'ask-01'}],
        }

    def evidence(self):
        return verify_reconciliation(self.report, self.ledger.attempt(self.attempt_id),
                                     self.preflight, self.metadata, Decimal('0.00012861'))

    def test_public_directory_requires_one_exact_pinned_mapping(self):
        endpoint = {'tag': PROVIDER, 'provider_name': 'Decart', 'status': 0,
                    'context_length': 1048576, 'pricing': self.preflight['pricing'],
                    'supported_parameters': ['response_format', 'max_tokens', 'reasoning']}
        correct = {'id': MODEL, 'canonical_slug': CANONICAL_MODEL}
        for models in ([correct], [], [correct, correct],
                       [{'id': MODEL, 'canonical_slug': MODEL + '-20990101'}],
                       [{'id': MODEL + '-other', 'canonical_slug': CANONICAL_MODEL}]):
            with self.subTest(models=models), patch('app.evaluation.ask.urllib.request.urlopen') as transport:
                transport.return_value.__enter__.return_value.read.side_effect = [
                    json.dumps({'data': models}), json.dumps({'data': {'id': MODEL, 'endpoints': [endpoint]}})]
                if models == [correct]:
                    self.assertEqual(official_preflight()['canonical_model'], CANONICAL_MODEL)
                else:
                    with self.assertRaises(BudgetStop):
                        official_preflight()

    def test_alias_and_canonical_are_accepted_only_under_explicit_mapping(self):
        for returned in (MODEL, CANONICAL_MODEL):
            for billed in (MODEL, CANONICAL_MODEL):
                verify_generation_identity(self.preflight, {**self.metadata, 'model': billed},
                                           'gen-synthetic', returned)
        for bad in (MODEL + '-other', CANONICAL_MODEL + '-other', MODEL + '-20260911', 'other/model'):
            with self.subTest(model=bad), self.assertRaises(BudgetStop):
                verify_generation_identity(self.preflight, {**self.metadata, 'model': bad}, 'gen-synthetic')
        with self.assertRaises(BudgetStop):
            verify_generation_identity({**self.preflight, 'canonical_model': MODEL + '-20260911'},
                                       self.metadata, 'gen-synthetic')

    def test_wrong_model_provider_id_and_usage_cost_stop_future_transport(self):
        changes = [({'model': MODEL + '-other'}, CANONICAL_MODEL), ({'provider_name': 'Other'}, CANONICAL_MODEL),
                   ({'id': 'gen-other'}, CANONICAL_MODEL), ({'total_cost': 0.00012862}, CANONICAL_MODEL),
                   ({}, MODEL + '-other'), ({}, None)]
        for index, (change, response_model) in enumerate(changes):
            with self.subTest(change=change, response_model=response_model):
                ledger = BudgetLedger(Path(self.tmp.name) / f'wrong-{index}.sqlite3')
                sdk = MagicMock()
                sdk.get.side_effect = lambda path, **kw: (
                    {'data': {'total_credits': 1, 'total_usage': 0}} if path == '/credits'
                    else httpx.Response(200,json={'data': {**self.metadata, **change}}))
                sdk.chat.completions.create.return_value = SimpleNamespace(
                    id='gen-synthetic', model=response_model,
                    usage=SimpleNamespace(cost=0.00012861, prompt_tokens=1267, completion_tokens=81,
                                          completion_tokens_details=SimpleNamespace(reasoning_tokens=0)))
                with patch('app.evaluation.ask.OpenAI', return_value=sdk):
                    client = PaidClient(ledger=ledger, run_id='test', case_id='ask-01',
                                        preflight=self.preflight, api_key='synthetic')
                request = dict(model=MODEL, extra_body=POLICY, max_tokens=1600,
                               messages=[{'role': 'user', 'content': 'synthetic' * 100}])
                with self.assertRaisesRegex(AskError,'ask_receipt_unverified'):
                    client.create(**request)
                with self.assertRaises(BudgetStop):
                    client.create(**request)
                self.assertTrue(ledger.summary()['uncertain_billing'])
                self.assertEqual(sdk.chat.completions.create.call_count, 1)

    def test_reconciliation_failures_preserve_unknown_and_full_reserve(self):
        before = self.ledger.summary()
        changes = (
            {'model': MODEL + '-other'}, {'id': 'gen-other'}, {'provider_name': 'Other'},
            {'total_cost': None}, {'total_cost': 0.00012862}, {'native_tokens_prompt': 1268},
            {'native_tokens_completion': None}, {'native_tokens_reasoning': 1},
            {'native_tokens_reasoning': False}, {'native_tokens_cached': 1},
            {'cancelled': True}, {'is_byok': True}, {'finish_reason': 'length'},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(BudgetStop):
                verify_reconciliation(self.report, self.ledger.attempt(self.attempt_id),
                                      self.preflight, {**self.metadata, **change}, Decimal('0.00012861'))
            self.assertEqual(self.ledger.summary(), before)
        altered = copy.deepcopy(self.report)
        altered['preflight']['pricing']['prompt'] = '0.00000008'
        with self.assertRaises(BudgetStop):
            verify_reconciliation(altered, self.ledger.attempt(self.attempt_id),
                                  self.preflight, self.metadata, Decimal('0.00012861'))
        with self.assertRaises(BudgetStop):
            verify_reconciliation(self.report, self.ledger.attempt(self.attempt_id),
                                  self.preflight, self.metadata, Decimal('0.00012860'))
        self.assertEqual(self.ledger.summary(), before)

    def test_reconciliation_is_audited_idempotent_and_keeps_review_block(self):
        evidence = self.evidence()
        self.assertTrue(self.ledger.reconcile(self.attempt_id, evidence=evidence))
        once = self.ledger.summary()
        self.assertFalse(BudgetLedger(self.path).reconcile(self.attempt_id, evidence=self.evidence()))
        self.assertEqual(self.ledger.summary(), once)
        self.assertEqual(once['known_cost_usd'], '0.00012861')
        self.assertEqual(len(once['attempts']), 1)
        self.assertEqual(once['attempts'][0]['reserved'], '0.10517760')
        self.assertEqual(once['attempts'][0]['outcome'], 'unknown_billing_or_provider')
        self.assertTrue(once['blocked'])
        self.assertFalse(once['uncertain_billing'])
        self.assertFalse(evidence['strict_json_validated'])
        self.assertFalse(evidence['completion_usage_available'])
        with self.ledger._db() as db:
            audit = dict(db.execute('SELECT * FROM reconciliation').fetchone())
        self.assertEqual(audit['original_state'], 'unknown')
        self.assertEqual(json.loads(audit['evidence_json']), evidence)
        with self.assertRaisesRegex(BudgetStop, 'billing_or_contract_blocked'):
            self.ledger.reserve('no-new-consent', 'ask-01', 8000, 1600)
        with self.assertRaisesRegex(BudgetStop, 'replay_mismatch'):
            self.ledger.reconcile(self.attempt_id, evidence={**evidence, 'cost_usd': '0.00012862'})
        self.assertEqual(self.ledger.summary(), once)

    def test_concurrent_duplicate_reconciliation_settles_once(self):
        evidence = self.evidence()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: BudgetLedger(self.path).reconcile(self.attempt_id, evidence=evidence), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(len(self.ledger.summary()['reconciliations']), 1)
        self.assertEqual(self.ledger.summary()['known_cost_usd'], '0.00012861')

    def test_read_only_reconciliation_uses_real_sdk_and_never_posts(self):
        report_path = Path(self.tmp.name) / 'original.json'
        report_path.write_text(json.dumps(self.report), encoding='utf-8')
        requests = []

        def respond(request):
            requests.append((request.method, request.url.path))
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.path, '/api/v1/generation')
            self.assertEqual(request.url.params['id'], 'gen-synthetic')
            return httpx.Response(200, json={'data': self.metadata})

        def client(**options):
            return OpenAI(**options, http_client=httpx.Client(transport=httpx.MockTransport(respond)))

        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'synthetic'}), \
                patch('app.evaluation.ask.LEDGER', self.path), \
                patch('app.evaluation.ask.official_preflight', return_value=self.preflight), \
                patch('app.evaluation.ask.OpenAI', side_effect=client):
            first = reconcile_canary(report_path, Decimal('0.00012861'))
            second = reconcile_canary(report_path, Decimal('0.00012861'))
        self.assertTrue(first['applied'])
        self.assertFalse(second['applied'])
        self.assertEqual(first['paid_requests_in_run'], 0)
        self.assertEqual(requests, [('GET', '/api/v1/generation')] * 2)

    def test_live_initial_credit_lookup_uses_real_sdk_without_inference(self):
        requests = []

        def respond(request):
            requests.append((request.method, request.url.path))
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.path, '/api/v1/credits')
            return httpx.Response(200, json={'data': {'total_credits': 0, 'total_usage': 0}})

        def client(**options):
            return OpenAI(**options, http_client=httpx.Client(transport=httpx.MockTransport(respond)))

        args = SimpleNamespace(authorization=AUTHORIZATION, budget_usd=Decimal('1'),
                               run_id='synthetic-low-credits', canary_only=True)
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'synthetic'}), \
                patch('app.evaluation.ask.LEDGER', Path(self.tmp.name) / 'low.sqlite3'), \
                patch('app.evaluation.ask.official_preflight', return_value=self.preflight), \
                patch('app.evaluation.ask.OpenAI', side_effect=client), \
                self.assertRaisesRegex(BudgetStop, 'insufficient_existing_credits'):
            live(args)
        self.assertEqual(requests, [('GET', '/api/v1/credits')])


if __name__ == '__main__':
    unittest.main()
