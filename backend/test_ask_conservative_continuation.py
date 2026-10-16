import io
import json
import os
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI

from app.evaluation.ask import AUTHORIZATION, BASE_URL, CANONICAL_MODEL, MODEL, PROVIDER, corpus, live, main
from app.evaluation.ask_budget import (
    BILLING_INPUT_RESERVE, COMPLETION_PRICE_CAP, CONSERVATIVE_SCOPE, OUTPUT_LIMIT, PROMPT_PRICE_CAP,
    BudgetLedger, BudgetStop, attempt_fingerprint,
)
from app.evaluation.ask_review import CONSERVATIVE_AUTHORIZATION, authorize_conservative_continuation


class AskConservativeContinuationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'budget.sqlite3'
        self.ledger = BudgetLedger(self.path)
        self.known = self.ledger.reserve('synthetic-known', 'case', 100, OUTPUT_LIMIT)
        self.ledger.settle(self.known, cost='0.0003', generation_id='gen-synthetic-known', outcome='response')
        self.target = self.ledger.reserve('synthetic-failed', 'case', 100, OUTPUT_LIMIT)
        with self.assertRaises(BudgetStop):
            self.ledger.settle(self.target, cost=None, generation_id=None, outcome='transport_failure')
        self.original = self.ledger.attempt(self.target)
        self.fingerprint = attempt_fingerprint(self.original)
        self.full = BILLING_INPUT_RESERVE * PROMPT_PRICE_CAP + OUTPUT_LIMIT * COMPLETION_PRICE_CAP
        self.context = {'reviewed_head': 'a' * 40, 'current_head': 'a' * 40, 'review_ref': 'synthetic-independent-review',
                        'ci_head': 'a' * 40, 'ci_run_id': 42, 'ci_run_attempt': 1, 'ci_conclusion': 'success',
                        'ci_source': 'https://api.github.com/repos/ChiosYang/5X49/actions/runs/42'}
        self.evidence = {'version': 'ask-conservative-continuation.v1', 'decision': 'approved', **self.context,
                         'approval_scope': CONSERVATIVE_SCOPE, 'user_confirmed': True,
                         'user_approval_ref': 'synthetic-single-user-approval', 'user_approved_at': '2000-01-01T00:00:00Z',
                         'attempt_id': self.target, 'attempt_sha256': self.fingerprint}

    def authorize(self, ledger=None):
        return (ledger or self.ledger).authorize_conservative_continue(
            self.target, attempt_sha256=self.fingerprint, evidence=self.evidence)

    def test_original_unknown_and_full_exposure_are_preserved_forever(self):
        before = self.ledger.summary()
        self.assertTrue(self.authorize())
        approved = self.ledger.summary()
        self.assertEqual(self.ledger.attempt(self.target), self.original)
        self.assertEqual(approved['known_cost_usd'], before['known_cost_usd'])
        self.assertEqual(approved['reserved_exposure_usd'], before['reserved_exposure_usd'])
        self.assertTrue(approved['uncertain_billing'])
        self.assertFalse(approved['blocking_uncertainty'])
        self.assertEqual(Decimal(approved['permanent_conservative_hold_usd']), self.full)
        next_attempt = self.ledger.reserve('next', 'case', 100, OUTPUT_LIMIT)
        self.ledger.settle(next_attempt, cost='0.0002', generation_id='gen-synthetic-next', outcome='response')
        restarted = BudgetLedger(self.path)
        summary = restarted.summary()
        self.assertEqual(Decimal(summary['known_cost_usd']), Decimal('0.0005'))
        self.assertEqual(Decimal(summary['reserved_exposure_usd']), self.full + Decimal('0.0005'))
        self.assertEqual(restarted.attempt(self.target), self.original)
        with self.assertRaisesRegex(BudgetStop, 'invalid_settlement'):
            restarted.settle(self.target, cost=0, generation_id='gen-not-a-receipt', outcome='response')
        self.assertFalse(self.authorize(restarted))
        self.assertEqual(len(summary['conservative_continuations']), 1)
        with restarted._db() as db:
            audit = dict(db.execute('SELECT * FROM conservative_continuation').fetchone())
        self.assertEqual(json.loads(audit['original_attempt_json']), self.original)
        self.assertEqual(json.loads(audit['evidence_json']), self.evidence)

    def test_new_unknown_blocks_and_cannot_receive_another_exception(self):
        self.authorize()
        second = self.ledger.reserve('new-failure', 'case', 100, OUTPUT_LIMIT)
        with self.assertRaises(BudgetStop):
            self.ledger.settle(second, cost=None, generation_id=None, outcome='transport_failure')
        row = self.ledger.attempt(second)
        summary = self.ledger.summary()
        self.assertTrue(summary['blocking_uncertainty'])
        self.assertEqual(Decimal(summary['reserved_exposure_usd']), 2 * self.full + Decimal('0.0003'))
        with self.assertRaisesRegex(BudgetStop, 'unsettled_attempt_stop'):
            self.ledger.reserve('no-retry', 'case', 100, OUTPUT_LIMIT)
        with self.assertRaisesRegex(BudgetStop, 'single_conservative_continuation_already_used'):
            self.ledger.authorize_conservative_continue(second, attempt_sha256=attempt_fingerprint(row),
                evidence={**self.evidence, 'attempt_id': second, 'attempt_sha256': attempt_fingerprint(row)})
        self.assertEqual(self.ledger.summary(), summary)

    def test_invalid_approval_or_changed_snapshot_cannot_authorize(self):
        before = self.ledger.summary()
        for change in ({'user_confirmed': False}, {'approval_scope': 'all-unknowns'},
                       {'user_approval_ref': ''}, {'ci_head': 'b' * 40}, {'ci_conclusion': 'failure'}):
            with self.subTest(change=change), self.assertRaises(BudgetStop):
                self.ledger.authorize_conservative_continue(self.target, attempt_sha256=self.fingerprint,
                                                            evidence={**self.evidence, **change})
        with self.assertRaises(BudgetStop):
            self.ledger.authorize_conservative_continue(self.target, attempt_sha256='0' * 64,
                                                        evidence={**self.evidence, 'attempt_sha256': '0' * 64})
        self.assertEqual(self.ledger.summary(), before)

    def test_every_new_reservation_still_obeys_stop_and_hard_limits(self):
        self.authorize()
        # Seed only owned synthetic historical accounting to exercise the cap.
        with self.ledger._db() as db:
            db.execute('UPDATE attempt SET cost=? WHERE id=?', ('0.55', self.known))
        with self.assertRaisesRegex(BudgetStop, 'cumulative_budget_stop'):
            self.ledger.reserve('over-stop', 'case', 100, OUTPUT_LIMIT)
        self.assertEqual(self.ledger.summary()['stop_limit_usd'], '0.75')
        self.assertEqual(self.ledger.summary()['hard_limit_usd'], '1.00')
        self.assertEqual(self.ledger.attempt(self.target), self.original)

    def test_changed_original_cannot_reduce_exposure_and_continue(self):
        self.authorize()
        # Deliberately corrupt only this temporary fixture; production rejects it.
        with self.ledger._db() as db:
            db.execute('UPDATE attempt SET reserved=? WHERE id=?', ('0', self.target))
        with self.assertRaisesRegex(BudgetStop, 'conservative_continuation_integrity_failed'):
            self.ledger.reserve('blocked', 'case', 100, OUTPUT_LIMIT)

    def test_concurrent_duplicate_approval_is_idempotent(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.authorize(BudgetLedger(self.path)), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(len(self.ledger.summary()['conservative_continuations']), 1)

    def test_explicit_user_and_review_approval_precede_ledger_mutation(self):
        approval = {**self.evidence, 'version': 'ask-conservative-approval.v1',
                    'reviewed_head': self.context['reviewed_head'], 'ci_run_id': 42,
                    'review_ref': self.context['review_ref']}
        path = self.root / 'approval.json'
        path.write_text(json.dumps(approval))
        before = self.path.read_bytes()
        with patch('app.evaluation.ask_review._verified_review_context', side_effect=AssertionError('no verification')):
            with self.assertRaisesRegex(BudgetStop, 'explicit_single_conservative_authorization_required'):
                authorize_conservative_continuation(path, authorization=None, ledger_path=self.path, repo_root=self.root)
        with patch('app.evaluation.ask_review._verified_review_context', side_effect=BudgetStop('review_not_approved')):
            with self.assertRaisesRegex(BudgetStop, 'review_not_approved'):
                authorize_conservative_continuation(path, authorization=CONSERVATIVE_AUTHORIZATION,
                                                    ledger_path=self.path, repo_root=self.root)
        self.assertEqual(self.path.read_bytes(), before)
        with patch('app.evaluation.ask_review._verified_review_context', return_value=self.context):
            result = authorize_conservative_continuation(path, authorization=CONSERVATIVE_AUTHORIZATION,
                                                        ledger_path=self.path, repo_root=self.root)
        self.assertTrue(result['continuation_authorized'])
        self.assertTrue(result['actual_cost_still_unknown'])
        self.assertEqual(result['paid_requests_in_run'], 0)

    def test_live_canary_accepts_only_the_explicitly_retained_unknown(self):
        self.run_synthetic_canary(fail=False)

    def test_live_new_transport_failure_stops_after_one_attempt(self):
        self.run_synthetic_canary(fail=True)

    def run_synthetic_canary(self, *, fail):
        self.authorize()
        case = corpus()[0]
        requests = []
        preflight = {'model': MODEL, 'canonical_model': CANONICAL_MODEL, 'directory_source': BASE_URL + '/models',
                     'source': BASE_URL + '/models/' + MODEL + '/endpoints', 'provider_tag': PROVIDER,
                     'provider_name': 'Decart'}

        def respond(request):
            requests.append((request.method, request.url.path))
            if request.url.path == '/api/v1/credits':
                return httpx.Response(200, json={'data': {'total_credits': 1, 'total_usage': 0}})
            if request.url.path == '/api/v1/generation':
                return httpx.Response(200, json={'data': {'id': 'gen-synthetic-new', 'model': CANONICAL_MODEL,
                    'provider_name': 'Decart', 'total_cost': 0.0001, 'native_tokens_prompt': 20,
                    'native_tokens_completion': 10, 'native_tokens_reasoning': 0}})
            self.assertEqual(request.url.path, '/api/v1/chat/completions')
            if fail:
                raise httpx.ConnectError('synthetic connection failure', request=request)
            return httpx.Response(200, json={'id': 'gen-synthetic-new', 'model': CANONICAL_MODEL,
                'choices': [{'message': {'role': 'assistant', 'content': json.dumps({**case['expected'], 'reason': None})},
                             'finish_reason': 'stop'}],
                'usage': {'cost': 0.0001, 'prompt_tokens': 20, 'completion_tokens': 10, 'total_tokens': 30,
                          'completion_tokens_details': {'reasoning_tokens': 0}}})

        def client(**options):
            return OpenAI(**options, http_client=httpx.Client(transport=httpx.MockTransport(respond)))

        args = SimpleNamespace(authorization=AUTHORIZATION, budget_usd=Decimal('1'), run_id='synthetic-canary', canary_only=True)
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'synthetic'}), \
                patch('app.evaluation.ask.LEDGER', self.path), patch('app.evaluation.ask.corpus', return_value=[case]), \
                patch('app.evaluation.ask.official_preflight', return_value=preflight), \
                patch('app.evaluation.ask.OpenAI', side_effect=client):
            report = live(args)
        self.assertEqual(report['complete'], not fail)
        self.assertEqual(report['ledger']['blocking_uncertainty'], fail)
        self.assertTrue(report['ledger']['uncertain_billing'])
        self.assertEqual(self.ledger.attempt(self.target), self.original)
        self.assertEqual(sum(method == 'POST' for method, path in requests), 1)
        if fail:
            self.assertEqual(report['stop_reason'], 'uncertain_billing_stop')
            self.assertEqual(report['cases'][0]['transport_error']['exception_type'], 'APIConnectionError')

    def test_cli_cannot_combine_conservative_approval_and_inference(self):
        args = ['ask', '--live', '--continue-conservatively', 'private.json', '--output', str(self.root / 'out.json')]
        with patch('sys.argv', args), patch('sys.stderr', new=io.StringIO()), self.assertRaises(SystemExit) as stopped:
            main()
        self.assertEqual(stopped.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
