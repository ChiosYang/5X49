import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from app.evaluation.ask import BASE_URL, CANONICAL_MODEL, MODEL, POLICY, PROVIDER, PaidClient, corpus, evaluate_case, transport_error_summary
from app.evaluation.ask_budget import BudgetLedger, BudgetStop
from app.services.ask import AskError, AskInterpreter

SENSITIVE_FIXTURE = 'synthetic-private-error-content'


class AskTransportDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = BudgetLedger(Path(self.tmp.name) / 'budget.sqlite3')
        self.requests = []
        self.errors = []
        self.preflight = {'model': MODEL, 'canonical_model': CANONICAL_MODEL,
                          'directory_source': BASE_URL + '/models',
                          'source': BASE_URL + '/models/' + MODEL + '/endpoints',
                          'provider_tag': PROVIDER, 'provider_name': 'Decart'}

    def interpreter(self, failure):
        def respond(request):
            self.requests.append((request.method, request.url.path))
            if request.url.path == '/api/v1/credits':
                return httpx.Response(200, json={'data': {'total_credits': 1, 'total_usage': 0}})
            self.assertEqual(request.method, 'POST')
            self.assertEqual(request.url.path, '/api/v1/chat/completions')
            return failure(request)

        def client(**options):
            options['api_key'] = 'synthetic'
            return PaidClient(ledger=self.ledger, run_id='synthetic-run', case_id='ask-01',
                              preflight=self.preflight,
                              http_client=httpx.Client(transport=httpx.MockTransport(respond)), **options)

        interpreter = AskInterpreter(client_factory=client, provider_config={
            'model': MODEL, 'base_url': BASE_URL, 'request_options': POLICY})
        original = interpreter.interpret

        def remember(request):
            try:
                return original(request)
            except AskError as error:
                self.errors.append(error)
                raise

        interpreter.interpret = remember
        return interpreter

    def run_case(self, failure):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'synthetic'}):
            return evaluate_case(corpus()[0], self.interpreter(failure))

    def assert_private_report(self, row):
        encoded = json.dumps(row)
        self.assertNotIn(SENSITIVE_FIXTURE, encoded)
        for excluded in ('Authorization', 'Set-Cookie', 'response_body', 'request_body', 'headers'):
            self.assertNotIn(excluded, encoded)
        self.assertEqual(set(row['transport_error']), {
            'exception_type', 'exception_chain_types', 'http_status', 'request_id', 'settlement_exception_type'})

    def test_connection_error_survives_unknown_billing_and_serialization(self):
        def failure(request):
            raise httpx.ConnectError(SENSITIVE_FIXTURE, request=request)

        row = self.run_case(failure)
        diagnostic = row['transport_error']
        self.assertEqual(row['actual_status'], 'ask_provider_unavailable')
        self.assertEqual(diagnostic['exception_type'], 'APIConnectionError')
        self.assertIn('ConnectError', diagnostic['exception_chain_types'])
        self.assertEqual(diagnostic['settlement_exception_type'], 'BudgetStop')
        self.assertIsNone(diagnostic['http_status'])
        self.assertIsNone(diagnostic['request_id'])
        self.assertEqual(type(self.errors[0].__cause__).__name__, 'APIConnectionError')
        self.assertTrue(self.ledger.summary()['uncertain_billing'])
        self.assertEqual(self.ledger.summary()['attempts'][0]['state'], 'unknown')
        self.assertEqual(sum(method == 'POST' for method, path in self.requests), 1)
        self.assert_private_report(row)

    def test_http_status_and_allowlisted_request_id_survive_without_raw_data(self):
        def failure(request):
            return httpx.Response(429, headers={'x-request-id': 'req_SafeCorrelation12345',
                                              'Authorization': SENSITIVE_FIXTURE, 'Set-Cookie': SENSITIVE_FIXTURE},
                                  json={'error': {'message': SENSITIVE_FIXTURE, 'code': 'synthetic_limit'}})

        row = self.run_case(failure)
        diagnostic = row['transport_error']
        self.assertEqual(diagnostic['exception_type'], 'RateLimitError')
        self.assertEqual(diagnostic['http_status'], 429)
        self.assertEqual(diagnostic['request_id'], 'req_SafeCorrelation12345')
        self.assertEqual(diagnostic['settlement_exception_type'], 'BudgetStop')
        self.assertEqual(self.errors[0].__cause__.status_code, 429)
        self.assertTrue(self.ledger.summary()['uncertain_billing'])
        self.assertEqual(sum(method == 'POST' for method, path in self.requests), 1)
        self.assert_private_report(row)

    def test_timeout_is_not_reclassified_as_json_failure(self):
        def failure(request):
            raise httpx.ReadTimeout(SENSITIVE_FIXTURE, request=request)

        row = self.run_case(failure)
        self.assertEqual(row['actual_status'], 'ask_timeout')
        self.assertEqual(row['transport_error']['exception_type'], 'APITimeoutError')
        self.assertIn('ReadTimeout', row['transport_error']['exception_chain_types'])
        self.assert_private_report(row)

    def test_storage_settlement_failure_cannot_replace_original_error(self):
        def failure(request):
            raise httpx.ConnectError(SENSITIVE_FIXTURE, request=request)

        with patch.object(self.ledger, 'settle', side_effect=OSError(SENSITIVE_FIXTURE)):
            row = self.run_case(failure)
        self.assertEqual(row['transport_error']['exception_type'], 'APIConnectionError')
        self.assertEqual(row['transport_error']['settlement_exception_type'], 'OSError')
        self.assertEqual(type(self.errors[0].__cause__).__name__, 'APIConnectionError')
        self.assertEqual(self.ledger.summary()['attempts'][0]['state'], 'reserved')
        with self.assertRaisesRegex(BudgetStop, 'unsettled_attempt_stop'):
            self.ledger.reserve('next', 'case', 100, 100)
        self.assert_private_report(row)

    def test_budget_block_prevents_transport_and_is_not_logged_as_transport(self):
        interpreter = self.interpreter(lambda request: self.fail('No POST allowed'))
        with patch.object(self.ledger, 'reserve', side_effect=BudgetStop('cumulative_budget_stop')), \
                patch.object(self.ledger, 'settle') as settle, \
                patch.dict(os.environ, {'OPENROUTER_API_KEY': 'synthetic'}):
            row = evaluate_case(corpus()[0], interpreter)
        self.assertNotIn('transport_error', row)
        self.assertEqual(sum(method == 'POST' for method, path in self.requests), 0)
        self.assertEqual(self.ledger.summary()['attempts'], [])
        settle.assert_not_called()

    def test_secret_shaped_request_id_is_dropped(self):
        def failure(request):
            return httpx.Response(400, headers={'x-request-id': 'req_sk-or-v1-' + SENSITIVE_FIXTURE},
                                  json={'error': {'message': SENSITIVE_FIXTURE}})

        row = self.run_case(failure)
        self.assertIsNone(row['transport_error']['request_id'])
        self.assertEqual(row['transport_error']['http_status'], 400)
        self.assert_private_report(row)

    def test_summary_does_not_read_exception_text_or_raw_objects(self):
        class OpaqueError(Exception):
            status_code = 503
            request_id = '12345678-1234-1234-1234-123456789abc'

            def __str__(self):
                raise AssertionError('Exception text must not be read')

            @property
            def response(self):
                raise AssertionError('Response must not be read')

            @property
            def request(self):
                raise AssertionError('Request must not be read')

        error = OpaqueError()
        error.__cause__ = error
        result = transport_error_summary(error)
        self.assertEqual(result['exception_chain_types'], ['OpaqueError'])
        self.assertEqual(result['http_status'], 503)
        self.assertEqual(result['request_id'], OpaqueError.request_id)


if __name__ == '__main__':
    unittest.main()
