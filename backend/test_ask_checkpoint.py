import contextlib
from copy import deepcopy
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI

from app.evaluation import ask
from app.evaluation.ask_budget import BudgetStop
from app.evaluation.ask_checkpoint import atomic_private_json, digest, encoded

GENERATION = 'gen-synthetic-checkpoint'
SECRET = 'synthetic-header-and-extra-field-never-persist'
PREFLIGHT = {'model': ask.MODEL, 'canonical_model': ask.CANONICAL_MODEL,
    'provider_tag': ask.PROVIDER, 'provider_name': 'Decart',
    'directory_source': ask.BASE_URL + '/models', 'source': ask.BASE_URL + '/models/' + ask.MODEL + '/endpoints',
    'pricing': {'prompt': '0.00000009', 'completion': '0.00000018'},
    'token_upper_bound': 8000, 'output_limit': 1600, 'billing_input_reservation': 1048576}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metadata():
    return {'id': GENERATION, 'model': ask.CANONICAL_MODEL, 'provider_name': 'Decart',
        'total_cost': 0.0000036, 'tokens_prompt': 20, 'tokens_completion': 10,
        'native_tokens_prompt': 20, 'native_tokens_completion': 10, 'native_tokens_reasoning': 0,
        'native_tokens_cached': 0, 'cache_discount': None, 'finish_reason': 'stop',
        'cancelled': False, 'is_byok': False}


def capture(root, *, content=None, missing_usage=False, save_failure=False, write_receipt=True):
    case = ask.corpus()[0]
    response = {'id': GENERATION, 'model': ask.CANONICAL_MODEL, 'sdk_private': SECRET,
        'choices': [{'message': {'role': 'assistant', 'content': content if content is not None else
            json.dumps({**case['expected'], 'reason': None}), 'private': SECRET}, 'finish_reason': 'stop'}],
        'usage': None if missing_usage else {'cost': 0.0000036, 'prompt_tokens': 20,
            'completion_tokens': 10, 'total_tokens': 30, 'completion_tokens_details': {'reasoning_tokens': 0}, 'private': SECRET}}
    requests = []

    def respond(request):
        requests.append((request.method, request.url.path))
        if request.url.path.endswith('/credits'):
            return httpx.Response(200, json={'data': {'total_credits': 1, 'total_usage': 0}})
        if request.url.path.endswith('/chat/completions'):
            return httpx.Response(200, json=response)
        if request.url.path.endswith('/generation'):
            saved = list((root / 'ask-response-checkpoints').glob('*.json'))
            if len(saved) != 1 or json.loads(saved[0].read_text())['response']['id'] != GENERATION:
                raise AssertionError('Complete checkpoint must exist before first GET')
            return httpx.Response(404, headers={'Authorization': SECRET}, json={'error': {'message': SECRET}})
        raise AssertionError('Unexpected synthetic route')

    def client(**options):
        return OpenAI(**options, http_client=httpx.Client(transport=httpx.MockTransport(respond)))

    args = SimpleNamespace(authorization=ask.AUTHORIZATION, budget_usd=Decimal('1'),
                           run_id='synthetic-checkpoint-run', canary_only=True)
    with patch.dict(os.environ, {'OPENROUTER_API_KEY': SECRET}), patch.object(ask, 'LEDGER', root / 'budget.sqlite3'), \
            patch.object(ask, 'OpenAI', side_effect=client), patch.object(ask, 'official_preflight', return_value=PREFLIGHT), \
            patch.object(ask.time, 'sleep'), contextlib.ExitStack() as stack:
        if save_failure:
            stack.enter_context(patch.object(ask, 'save_checkpoint', side_effect=OSError(SECRET)))
        report = ask.live(args)
        later = ask.live(args)
    assert report['complete'] is False and later['ledger']['attempts'] == report['ledger']['attempts']
    assert sum(method == 'POST' for method, _ in requests) == 1
    (root / 'original.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
    (root / 'requests.json').write_text(json.dumps(requests), encoding='utf-8')
    if write_receipt:
        (root / 'receipt.json').write_text(json.dumps({'data': metadata()}), encoding='utf-8')
    return report, requests


def offline_resume(root):
    report = root / 'original.json'
    parsed = json.loads(report.read_text(encoding='utf-8'))
    reference = parsed['cases'][0]['receipt_check'].get('checkpoint', {})
    path = root / 'ask-response-checkpoints' / reference.get('file', 'missing.json')
    with patch.object(ask, 'OpenAI', side_effect=AssertionError('offline network forbidden')), \
            patch.object(ask, 'BudgetLedger', side_effect=AssertionError('offline ledger access forbidden')), \
            patch.object(ask.urllib.request, 'urlopen', side_effect=AssertionError('offline network forbidden')):
        return ask.resume_saved_canary(report, sha(report), path, root / 'receipt.json', sha(root / 'receipt.json'))


class AskCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        for path in self.root.rglob('*'):
            if path.is_file():
                path.chmod(stat.S_IWRITE)
        self.tmp.cleanup()

    def captured(self, **options):
        report, requests = capture(self.root, **options)
        self.report_path = self.root / 'original.json'
        self.receipt_path = self.root / 'receipt.json'
        self.reference = report['cases'][0]['receipt_check'].get('checkpoint')
        self.checkpoint = self.root / 'ask-response-checkpoints' / (self.reference or {}).get('file', 'missing.json')
        return report, requests

    def reseal(self, saved):
        self.checkpoint.chmod(stat.S_IWRITE)
        self.checkpoint.write_bytes(encoded(saved))
        report = json.loads(self.report_path.read_text())
        report['cases'][0]['receipt_check']['checkpoint']['sha256'] = sha(self.checkpoint)
        report['cases'][0]['receipt_check']['checkpoint']['binding_sha256'] = digest(saved['binding'])
        self.report_path.write_text(json.dumps(report), encoding='utf-8')

    def test_atomic_capture_precedes_receipt_get_and_whitelists_private_fields(self):
        report, requests = self.captured()
        self.assertEqual(sum(path.endswith('/generation') for _, path in requests), 3)
        self.assertEqual(sum(method == 'POST' for method, _ in requests), 1)
        self.assertEqual(report['cases'][0]['actual_status'], 'ask_receipt_unverified')
        self.assertEqual(report['ledger']['attempts'][0]['state'], 'unknown')
        self.assertEqual(report['ledger']['attempts'][0]['reserved'], '0.10517760')
        self.assertIsNone(report['ledger']['attempts'][0]['cost'])
        saved = json.loads(self.checkpoint.read_text())
        self.assertEqual(set(saved['response']), {'id', 'model', 'content', 'finish_reason', 'usage'})
        self.assertNotIn(SECRET, self.checkpoint.read_text())
        self.assertNotIn(SECRET, json.dumps(report))
        self.assertEqual(sha(self.checkpoint), self.reference['sha256'])
        self.assertFalse(list(self.checkpoint.parent.glob('*.tmp')))

    def test_readonly_resume_validates_saved_completion_without_ledger_or_network(self):
        self.captured()
        paths = [self.report_path, self.checkpoint, self.receipt_path, self.root / 'budget.sqlite3']
        before = [sha(path) for path in paths]
        result = offline_resume(self.root)
        self.assertTrue(result['saved_response_quality_passed'])
        self.assertTrue(result['strict_json_validated'])
        self.assertTrue(result['review_required'])
        self.assertFalse(result['continuation_authorized'])
        self.assertFalse(result['original_canary_passed'])
        self.assertFalse(result['ledger_written'])
        self.assertEqual(result['paid_requests_in_run'], 0)
        self.assertEqual(before, [sha(path) for path in paths])

    def test_invalid_json_is_retained_and_cannot_become_quality_pass(self):
        self.captured(content='{invalid json')
        result = offline_resume(self.root)
        self.assertTrue(result['receipt_evidence_validated'])
        self.assertFalse(result['saved_response_quality_passed'])
        self.assertFalse(result['strict_json_validated'])
        self.assertEqual(result['case']['actual_status'], 'ask_invalid_response')

    def test_missing_usage_cannot_be_reconstructed_from_receipt(self):
        self.captured(missing_usage=True)
        self.assertIsNone(json.loads(self.checkpoint.read_text())['response']['usage'])
        with self.assertRaisesRegex(BudgetStop, 'usage_missing'):
            offline_resume(self.root)

    def test_checkpoint_failure_stops_before_any_receipt_get_and_keeps_full_reserve(self):
        report, requests = self.captured(save_failure=True)
        self.assertFalse(any(path.endswith('/generation') for _, path in requests))
        self.assertEqual(sum(method == 'POST' for method, _ in requests), 1)
        self.assertEqual(report['cases'][0]['receipt_error']['stage'], 'response_checkpoint')
        self.assertEqual(report['cases'][0]['receipt_error']['checkpoint_error_type'], 'OSError')
        self.assertTrue(report['ledger']['blocking_uncertainty'])
        self.assertEqual(report['ledger']['reserved_exposure_usd'], '0.10517760')

    def test_atomic_publication_does_not_overwrite_or_publish_partial_file(self):
        path = self.root / 'single.json'
        atomic_private_json(path, {'synthetic': 1})
        before = sha(path)
        with self.assertRaises(OSError):
            atomic_private_json(path, {'synthetic': 2})
        self.assertEqual(sha(path), before)
        with patch('app.evaluation.ask_checkpoint.os.fsync', side_effect=OSError('synthetic')):
            with self.assertRaises(OSError):
                atomic_private_json(self.root / 'failed.json', {'synthetic': 3})
        self.assertFalse((self.root / 'failed.json').exists())
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_checkpoint_and_original_report_hash_anchors_reject_tampering(self):
        self.captured()
        report_sha, checkpoint_sha = sha(self.report_path), sha(self.checkpoint)
        original = self.checkpoint.read_bytes()
        self.checkpoint.chmod(stat.S_IWRITE)
        self.checkpoint.write_bytes(original + b' ')
        with self.assertRaisesRegex(BudgetStop, 'input_unverified'):
            offline_resume(self.root)
        self.checkpoint.write_bytes(original)
        report = json.loads(self.report_path.read_text())
        report['run_id'] = 'changed'
        self.report_path.write_text(json.dumps(report))
        with self.assertRaisesRegex(BudgetStop, 'input_unverified'):
            ask.resume_saved_canary(self.report_path, report_sha, self.checkpoint, self.receipt_path, sha(self.receipt_path))
        self.assertEqual(sha(self.checkpoint), checkpoint_sha)

    def test_exact_request_prompt_corpus_case_run_and_code_identity_required(self):
        self.captured()
        original = json.loads(self.checkpoint.read_text())
        for key in ('run_id', 'case_id', 'locale', 'case_sha256', 'request_sha256',
                    'prompt_sha256', 'corpus_sha256', 'preflight_sha256', 'code'):
            with self.subTest(key=key):
                saved = deepcopy(original)
                saved['binding'][key] = 'synthetic-wrong-identity'
                self.reseal(saved)
                with self.assertRaisesRegex(BudgetStop, 'binding_mismatch'):
                    offline_resume(self.root)

    def test_attempt_and_generation_identity_mismatch_rejected(self):
        self.captured()
        original = json.loads(self.checkpoint.read_text())
        for change in ('attempt', 'generation'):
            with self.subTest(change=change):
                saved = deepcopy(original)
                if change == 'attempt':
                    saved['attempt_id'] = '0' * 32
                else:
                    saved['response']['id'] = 'gen-other-synthetic'
                self.reseal(saved)
                with self.assertRaises(BudgetStop):
                    offline_resume(self.root)

    def test_receipt_identity_billing_and_token_contract_errors_rejected(self):
        self.captured()
        for change in ({'id': 'gen-other-synthetic'}, {'model': 'other/model'}, {'provider_name': 'Other'},
                       {'total_cost': 0}, {'native_tokens_reasoning': 1}, {'native_tokens_cached': 1},
                       {'cancelled': True}, {'is_byok': True}, {'finish_reason': 'length'}):
            with self.subTest(change=change):
                self.receipt_path.write_text(json.dumps({'data': {**metadata(), **change}}))
                with self.assertRaises(BudgetStop):
                    offline_resume(self.root)

    def test_usage_mismatch_or_incomplete_fields_fail_closed(self):
        self.captured()
        original = json.loads(self.checkpoint.read_text())
        for key, value in (('cost', None), ('cost', '0'), ('prompt_tokens', 21), ('completion_tokens', None),
                           ('total_tokens', 0), ('reasoning_tokens', None), ('reasoning_tokens', True)):
            with self.subTest(key=key, value=value):
                saved = deepcopy(original)
                saved['response']['usage'][key] = value
                self.reseal(saved)
                with self.assertRaises(BudgetStop):
                    offline_resume(self.root)

    def test_legacy_missing_checkpoint_cannot_recover_lost_completion(self):
        self.captured()
        report = json.loads(self.report_path.read_text())
        del report['cases'][0]['receipt_check']['checkpoint']
        self.report_path.write_text(json.dumps(report))
        with self.assertRaisesRegex(BudgetStop, 'missing_original_response'):
            offline_resume(self.root)

    def test_receipt_expected_digest_is_checked(self):
        self.captured()
        with self.assertRaisesRegex(BudgetStop, 'input_unverified'):
            ask.resume_saved_canary(self.report_path, sha(self.report_path), self.checkpoint, self.receipt_path, '0' * 64)

    def test_cli_cannot_overwrite_input_or_mix_modes(self):
        self.captured()
        original = sha(self.report_path)
        argv = ['ask', '--resume-report', str(self.report_path), '--resume-report-sha256', original,
            '--response-checkpoint', str(self.checkpoint), '--generation-receipt', str(self.receipt_path),
            '--generation-receipt-sha256', sha(self.receipt_path), '--output', str(self.report_path)]
        for extra in ([], ['--live'], ['--ledger-path', str(self.root / 'budget.sqlite3')]):
            with self.subTest(extra=extra), patch.object(sys, 'argv', argv + extra), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                ask.main()
        self.assertEqual(sha(self.report_path), original)

    def test_prior_history_and_cumulative_budget_bytes_remain_unchanged(self):
        ledger = ask.BudgetLedger(self.root / 'budget.sqlite3')
        old = ledger.reserve('synthetic-history', 'old-case', 8000, 1600)
        ledger.settle(old, cost='0.01', generation_id='gen-synthetic-history', outcome='response')
        report, _ = self.captured()
        self.assertEqual(len(report['ledger']['attempts']), 2)
        self.assertEqual(report['ledger']['known_cost_usd'], '0.01')
        original = sha(self.root / 'budget.sqlite3')
        self.assertTrue(offline_resume(self.root)['saved_response_quality_passed'])
        self.assertEqual(sha(self.root / 'budget.sqlite3'), original)
        self.assertEqual(ledger.attempt(old)['cost'], '0.01')

    def test_response_model_none_and_duplicate_json_rejected(self):
        self.captured()
        saved = json.loads(self.checkpoint.read_text())
        saved['response']['model'] = None
        self.reseal(saved)
        with self.assertRaisesRegex(BudgetStop, 'generation_identity'):
            offline_resume(self.root)
        raw = self.checkpoint.read_bytes()
        self.checkpoint.write_bytes(b'{"version":0,' + raw[1:])
        report = json.loads(self.report_path.read_text())
        report['cases'][0]['receipt_check']['checkpoint']['sha256'] = sha(self.checkpoint)
        self.report_path.write_text(json.dumps(report))
        with self.assertRaisesRegex(BudgetStop, 'input_unverified'):
            offline_resume(self.root)

    def test_cli_writes_separate_offline_result_and_preserves_all_inputs(self):
        self.captured()
        paths = [self.report_path, self.checkpoint, self.receipt_path, self.root / 'budget.sqlite3']
        before = [sha(path) for path in paths]
        output = self.root / 'offline-result.json'
        argv = ['ask', '--resume-report', str(self.report_path), '--resume-report-sha256', sha(self.report_path),
            '--response-checkpoint', str(self.checkpoint), '--generation-receipt', str(self.receipt_path),
            '--generation-receipt-sha256', sha(self.receipt_path), '--output', str(output)]
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()), \
                patch.object(ask, 'OpenAI', side_effect=AssertionError('no client')), \
                patch.object(ask, 'BudgetLedger', side_effect=AssertionError('no ledger')):
            self.assertEqual(ask.main(), 0)
        result = json.loads(output.read_text())
        self.assertFalse(result['continuation_authorized'])
        self.assertTrue(result['review_required'])
        self.assertEqual(before, [sha(path) for path in paths])

    def test_relative_output_checks_absolute_ancestor_junctions(self):
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            with patch.object(Path, 'is_junction', autospec=True,
                              side_effect=lambda path: path == self.root):
                with self.assertRaisesRegex(BudgetStop, 'path_invalid'):
                    atomic_private_json(Path('nested/result.json'), {'synthetic': True})
            self.assertFalse((self.root / 'nested').exists())
        finally:
            os.chdir(previous)

    def test_cross_process_404_capture_then_200_receipt_reuses_only_one_post(self):
        env = {**os.environ, 'PYTHON_DOTENV_DISABLED': '1', 'SQLITE_DB_PATH': str(self.root / 'unused.sqlite3'),
               'MEDIA_DIR': str(self.root / 'empty'), 'WATCH_LIBRARY': 'false'}
        first = subprocess.run([sys.executable, '-X', 'utf8', __file__, '--capture-child', str(self.root)],
                               capture_output=True, text=True, env=env, check=True)
        self.assertEqual(json.loads(first.stdout)['post_count'], 1)
        report_hash = sha(self.root / 'original.json')
        ledger_hash = sha(self.root / 'budget.sqlite3')
        second = subprocess.run([sys.executable, '-X', 'utf8', __file__, '--resume-child', str(self.root)],
                                capture_output=True, text=True, env=env, check=True)
        result = json.loads(second.stdout)
        self.assertTrue(result['quality_passed'])
        self.assertEqual(result['receipt_gets'], 1)
        self.assertEqual(result['post_count'], 1)
        self.assertEqual(sha(self.root / 'original.json'), report_hash)
        self.assertEqual(sha(self.root / 'budget.sqlite3'), ledger_hash)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--capture-child':
        report, requests = capture(Path(sys.argv[2]), write_receipt=False)
        print(json.dumps({'post_count': sum(method == 'POST' for method, _ in requests)}))
    elif len(sys.argv) == 3 and sys.argv[1] == '--resume-child':
        root = Path(sys.argv[2])
        reads = []
        def respond(request):
            assert request.method == 'GET' and request.url.path.endswith('/generation')
            assert request.url.params['id'] == GENERATION
            reads.append('GET')
            return httpx.Response(200, json={'data': metadata()})
        with OpenAI(api_key='synthetic', base_url=ask.BASE_URL, max_retries=0,
                    http_client=httpx.Client(transport=httpx.MockTransport(respond))) as client:
            data, _ = ask.read_generation_receipt(client, GENERATION)
        (root / 'receipt.json').write_text(json.dumps({'data': data}))
        result = offline_resume(root)
        requests = json.loads((root / 'requests.json').read_text())
        print(json.dumps({'quality_passed': result['saved_response_quality_passed'], 'receipt_gets': len(reads),
                          'post_count': sum(method == 'POST' for method, _ in requests)}))
    else:
        unittest.main()
