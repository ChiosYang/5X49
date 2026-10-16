import json
import os
from pathlib import Path
import tempfile
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI

from app.evaluation.ask import (
    AUTHORIZATION, BASE_URL, CANONICAL_MODEL, MODEL, PROVIDER, ReceiptLookupError,
    corpus, live, read_generation_receipt,
)
GENERATION = 'gen-synthetic-receipt'
PRIVATE_FIXTURE = 'synthetic-private-response-sentinel'


class AskReceiptLookupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.case_number = 0
        self.preflight = {'model': MODEL, 'canonical_model': CANONICAL_MODEL, 'provider_tag': PROVIDER,
                          'provider_name': 'Decart', 'directory_source': BASE_URL + '/models',
                          'source': BASE_URL + '/models/' + MODEL + '/endpoints'}

    @staticmethod
    def metadata():
        return {'id': GENERATION, 'model': CANONICAL_MODEL, 'provider_name': 'Decart',
                'total_cost': 0.0001, 'native_tokens_prompt': 20, 'native_tokens_completion': 10,
                'native_tokens_reasoning': 0, 'account_id': PRIVATE_FIXTURE}

    def run_canary(self, outcomes, *, expect_failure=True):
        self.case_number += 1
        path = self.root / f'synthetic-{self.case_number}.sqlite3'
        requests = []
        remaining = list(outcomes)
        case = corpus()[0]

        def respond(request):
            self.assertEqual(request.url.scheme, 'https')
            self.assertEqual(request.url.host, 'openrouter.ai')
            requests.append((request.method, request.url.path))
            if request.url.path == '/api/v1/credits':
                self.assertEqual(request.method, 'GET')
                return httpx.Response(200, json={'data': {'total_credits': 1, 'total_usage': 0}})
            if request.url.path == '/api/v1/chat/completions':
                self.assertEqual(request.method, 'POST')
                return httpx.Response(200, json={
                    'id': GENERATION, 'model': CANONICAL_MODEL,
                    'choices': [{'message': {'role': 'assistant', 'content': json.dumps({**case['expected'], 'reason': None})}, 'finish_reason': 'stop'}],
                    'usage': {'cost': 0.0001, 'prompt_tokens': 20, 'completion_tokens': 10, 'total_tokens': 30,
                              'completion_tokens_details': {'reasoning_tokens': 0}}})
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.path, '/api/v1/generation')
            self.assertEqual(list(request.url.params.multi_items()), [('id', GENERATION)])
            self.assertTrue(remaining, 'Receipt read count exceeded supplied outcomes')
            outcome = remaining.pop(0)
            if outcome == 'timeout':
                raise httpx.ReadTimeout(PRIVATE_FIXTURE, request=request)
            if isinstance(outcome, int):
                return httpx.Response(outcome, headers={'x-request-id': 'req_SyntheticCorrelation12345',
                                                       'Authorization': PRIVATE_FIXTURE},
                                      json={'error': {'message': PRIVATE_FIXTURE}})
            if isinstance(outcome, str):
                return httpx.Response(200, content=outcome)
            return httpx.Response(200, json=outcome)

        def client(**options):
            return OpenAI(**options, http_client=httpx.Client(transport=httpx.MockTransport(respond)))

        args = SimpleNamespace(authorization=AUTHORIZATION, budget_usd=Decimal('1'),
                               run_id='synthetic-receipt-canary', canary_only=True)
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'synthetic'}), \
                patch('app.evaluation.ask.LEDGER', path), patch('app.evaluation.ask.corpus', return_value=[case]), \
                patch('app.evaluation.ask.official_preflight', return_value=self.preflight), \
                patch('app.evaluation.ask.OpenAI', side_effect=client), \
                patch('app.evaluation.ask.time.sleep') as sleep:
            report = live(args)
            sleeps = [call.args[0] for call in sleep.call_args_list]
            if expect_failure:
                self.assertFalse(report['complete'])
                self.assertEqual(report['cases'][0]['actual_status'], 'ask_receipt_unverified')
                error = report['cases'][0]['receipt_error']
                self.assertTrue(error['completion_response_received'])
                self.assertFalse(error['receipt_verified'])
                self.assertEqual(report['stop_reason'], 'uncertain_billing_stop')
                ledger = report['ledger']
                self.assertTrue(ledger['blocking_uncertainty'])
                self.assertIsNone(ledger['attempts'][0]['cost'])
                self.assertEqual(ledger['attempts'][0]['generation_id'], GENERATION)
                self.assertEqual(ledger['attempts'][0]['state'], 'unknown')
                self.assertEqual(Decimal(ledger['reserved_exposure_usd']), Decimal(ledger['attempts'][0]['reserved']))
                blocked = live(args)
                self.assertFalse(blocked['complete'])
                self.assertEqual(len(blocked['ledger']['attempts']), 1)
        self.assertEqual(sum(method == 'POST' for method, path in requests), 1)
        self.assertNotIn(PRIVATE_FIXTURE, json.dumps(report))
        self.assertNotIn('Authorization', json.dumps(report))
        self.assertNotIn(GENERATION, json.dumps(report['cases'][0]['receipt_check']))
        return report, requests, sleeps

    def test_404_then_success_preserves_attempt_trace_and_one_inference(self):
        report, requests, sleeps = self.run_canary([404, {'data': self.metadata()}], expect_failure=False)
        self.assertTrue(report['complete'])
        self.assertTrue(report['cases'][0]['passed'])
        check = report['cases'][0]['receipt_check']
        self.assertTrue(check['completion_response_received'])
        self.assertTrue(check['receipt_verified'])
        self.assertEqual(check['lookup']['attempt_count'], 2)
        self.assertEqual([row['http_status'] for row in check['lookup']['attempts']], [404, 200])
        self.assertTrue(check['lookup']['attempts'][-1]['id_match'])
        self.assertEqual(sleeps, [0.5])
        self.assertEqual(sum(path == '/api/v1/generation' for method, path in requests), 2)
        self.assertFalse(report['ledger']['blocking_uncertainty'])

    def test_persistent_404_keeps_full_unknown_reserve_and_blocks_next_post(self):
        report, requests, sleeps = self.run_canary([404] * 3)
        lookup = report['cases'][0]['receipt_error']['lookup']
        self.assertEqual(lookup['attempt_count'], 3)
        self.assertEqual([row['http_status'] for row in lookup['attempts']], [404] * 3)
        self.assertTrue(all(row['exception_type'] == 'NotFoundError' for row in lookup['attempts']))
        self.assertTrue(all(row['elapsed_ms'] >= 0 for row in lookup['attempts']))
        self.assertGreaterEqual(lookup['elapsed_ms'], 0)
        self.assertEqual(sleeps, [0.5, 1.0])

    def test_401_and_403_are_receipt_errors_with_unchanged_read_limit(self):
        for status in (401, 403):
            with self.subTest(status=status):
                report, _, _ = self.run_canary([status] * 3)
                lookup = report['cases'][0]['receipt_error']['lookup']
                self.assertEqual(lookup['attempt_count'], 3)
                self.assertEqual([row['http_status'] for row in lookup['attempts']], [status] * 3)

    def test_429_and_5xx_do_not_trigger_sdk_or_inference_retries(self):
        for status in (429, 500, 503):
            with self.subTest(status=status):
                report, _, _ = self.run_canary([status] * 3)
                self.assertEqual([row['http_status'] for row in report['cases'][0]['receipt_error']['lookup']['attempts']], [status] * 3)

    def test_receipt_timeout_retains_completion_received_and_timeout_type(self):
        report, _, _ = self.run_canary(['timeout'] * 3)
        lookup = report['cases'][0]['receipt_error']['lookup']
        self.assertEqual(lookup['attempt_count'], 3)
        self.assertTrue(all(row['exception_type'] == 'APITimeoutError' and row['http_status'] is None for row in lookup['attempts']))

    def test_malformed_200_records_status_without_logging_body(self):
        report, _, _ = self.run_canary([PRIVATE_FIXTURE] * 3)
        attempts = report['cases'][0]['receipt_error']['lookup']['attempts']
        self.assertTrue(all(row['http_status'] == 200 and row['schema_status'] == 'malformed_json' for row in attempts))
        self.assertTrue(all(row['exception_type'] == 'JSONDecodeError' for row in attempts))

    def test_missing_data_is_reported_and_keeps_original_read_limit(self):
        report, _, _ = self.run_canary([{'private': PRIVATE_FIXTURE}] * 3)
        self.assertEqual([row['schema_status'] for row in report['cases'][0]['receipt_error']['lookup']['attempts']], ['missing_data'] * 3)

    def test_wrong_id_is_rejected_without_additional_reads(self):
        report, _, sleeps = self.run_canary([{'data': {**self.metadata(), 'id': 'gen-wrong-synthetic'}}])
        lookup = report['cases'][0]['receipt_error']['lookup']
        self.assertEqual(lookup['attempt_count'], 1)
        self.assertFalse(lookup['attempts'][0]['id_match'])
        self.assertEqual(sleeps, [])

    def test_invalid_data_or_missing_id_fails_closed(self):
        for data in (None, [], {'id': None}):
            with self.subTest(data=data):
                report, _, _ = self.run_canary([{'data': data}])
                self.assertEqual(report['cases'][0]['receipt_error']['lookup']['attempt_count'], 1)

    def test_receipt_verification_failure_is_distinct_from_lookup_failure(self):
        for change in ({'model': 'other/model'}, {'provider_name': 'Other'}, {'total_cost': 0.0002}):
            with self.subTest(change=change):
                report, _, _ = self.run_canary([{'data': {**self.metadata(), **change}}])
                error = report['cases'][0]['receipt_error']
                self.assertEqual(error['stage'], 'generation_receipt_verification')
                self.assertTrue(error['lookup']['attempts'][0]['id_match'])

    def test_shared_reader_single_get_mode_has_no_inference_or_retries(self):
        requests = []

        def respond(request):
            requests.append(request.method)
            self.assertEqual(request.url.host, 'openrouter.ai')
            self.assertEqual(request.url.path, '/api/v1/generation')
            self.assertEqual(list(request.url.params.multi_items()), [('id', GENERATION)])
            return httpx.Response(404, json={'error': {'message': PRIVATE_FIXTURE}})

        with OpenAI(api_key='synthetic', base_url=BASE_URL, max_retries=0,
                    http_client=httpx.Client(transport=httpx.MockTransport(respond))) as client, \
                patch('app.evaluation.ask.time.sleep') as sleep:
            with self.assertRaises(ReceiptLookupError) as caught:
                read_generation_receipt(client, GENERATION)
        self.assertEqual(caught.exception.diagnostic['attempt_count'], 1)
        self.assertEqual(requests, ['GET'])
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
