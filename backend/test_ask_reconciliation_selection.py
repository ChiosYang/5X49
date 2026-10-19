"""Synthetic cumulative-report reconciliation; never reads private receipts."""
import copy
from contextlib import closing
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI

from app.evaluation import ask
from app.evaluation.ask_budget import BudgetLedger, BudgetStop, attempt_fingerprint
import test_ask_reconciliation as fixtures


class AskReconciliationSelectionTests(unittest.TestCase):
    def setUp(self):
        seed = fixtures.AskReconciliationTests()
        seed.setUp()
        self.addCleanup(seed.doCleanups)
        self.root, self.path = Path(seed.tmp.name), seed.path
        self.ledger, self.target = seed.ledger, seed.attempt_id
        self.preflight = copy.deepcopy(seed.preflight)
        self.metadata = {**seed.metadata, 'id': 'gen-selection-fixture',
                         'total_cost': '0.00001080', 'native_tokens_prompt': 100,
                         'native_tokens_completion': 10, 'tokens_prompt': 90, 'tokens_completion': 8}
        self.cost = Decimal('0.00001080')
        self.prior, self.held = 'a' * 32, 'b' * 32
        digest = lambda value: hashlib.sha256(value.encode()).hexdigest()
        with self.ledger._db() as db:
            db.execute('UPDATE attempt SET generation_id=? WHERE id=?', (self.metadata['id'], self.target))
            db.execute('INSERT INTO attempt(id,run_id,case_id,reserved,cost,generation_id,state,outcome) VALUES (?,?,?,?,?,?,?,?)',
                       (self.prior, 'prior-fixture', 'ask-01', '0.10517760', '0.00000100',
                        'gen-prior-fixture', 'settled', 'unknown_billing_or_provider'))
            db.execute('INSERT INTO attempt(id,run_id,case_id,reserved,state,outcome) VALUES (?,?,?,?,?,?)',
                       (self.held, 'held-fixture', 'ask-01', '0.10517760', 'unknown', 'transport_failure'))
            # Preserve the real cumulative ordering: settled, permanent unknown,
            # then the newest unknown targeted by the saved canary report.
            db.execute('UPDATE attempt SET rowid=4 WHERE id=?', (self.target,))
            old_evidence = json.dumps({'synthetic': 'prior-reconciliation'}, sort_keys=True)
            db.execute('INSERT INTO reconciliation(attempt_id,generation_id,cost,original_state,original_outcome,original_reserved,evidence_json,evidence_sha256) VALUES (?,?,?,?,?,?,?,?)',
                       (self.prior, 'gen-prior-fixture', '0.00000100', 'unknown',
                        'unknown_billing_or_provider', '0.10517760', old_evidence, digest(old_evidence)))
            release = json.dumps({'synthetic': 'prior-review-release'}, sort_keys=True)
            db.execute('INSERT INTO review_release(attempt_id,reconciliation_sha256,previous_state,evidence_json,evidence_sha256) VALUES (?,?,?,?,?)',
                       (self.prior, digest(old_evidence), 'blocked', release, digest(release)))
            held = dict(db.execute('SELECT * FROM attempt WHERE id=?', (self.held,)).fetchone())
            original = json.dumps(held, sort_keys=True, separators=(',', ':'))
            approval = json.dumps({'synthetic': 'consumed-permanent-hold'}, sort_keys=True)
            db.execute('INSERT INTO conservative_continuation(singleton,attempt_id,attempt_sha256,reserved,original_attempt_json,evidence_json,evidence_sha256) VALUES (1,?,?,?,?,?,?)',
                       (self.held, attempt_fingerprint(held), held['reserved'], original, approval, digest(approval)))
        self.report = {**copy.deepcopy(seed.report), 'ledger': self.ledger.summary()}
        self.report_path = self.root / 'original-cumulative.json'
        self.save_report(self.report)
        self.requests = []

    def save_report(self, report):
        self.report_path.write_text(json.dumps(report), encoding='utf-8')

    def snapshot(self, path=None):
        with closing(sqlite3.connect((path or self.path).resolve().as_uri() + '?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            return {table: [dict(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY rowid')]
                    for table in ('attempt', 'reconciliation', 'review_release', 'conservative_continuation')}

    def call(self, *, attempt_id=None, path=None, default=False, metadata=None):
        def respond(request):
            self.requests.append((request.method, request.url.path, dict(request.url.params)))
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.path, '/api/v1/generation')
            self.assertEqual(request.url.params['id'], self.metadata['id'])
            return httpx.Response(200, json={'data': self.metadata if metadata is None else metadata})

        def client(**options):
            return OpenAI(**options, http_client=httpx.Client(transport=httpx.MockTransport(respond)))

        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'synthetic'}), \
                patch.object(ask, 'LEDGER', self.path), \
                patch.object(ask, 'official_preflight', return_value=self.preflight) as directory, \
                patch.object(ask, 'OpenAI', side_effect=client) as sdk:
            try:
                return ask.reconcile_canary(self.report_path, self.cost, attempt_id=attempt_id,
                                            ledger_path=None if default else path or self.path)
            finally:
                self.directory_calls, self.sdk_calls = directory.call_count, sdk.call_count

    def test_three_attempt_report_preserves_full_hash_other_rows_and_review_hold(self):
        before, original_bytes = self.snapshot(), self.report_path.read_bytes()
        with patch.object(ask, 'verify_reconciliation', wraps=ask.verify_reconciliation) as verify:
            result = self.call(attempt_id=self.target)
        self.assertEqual(verify.call_args.args[0], self.report)
        self.assertEqual(len(verify.call_args.args[0]['ledger']['attempts']), 3)
        self.assertEqual(result['evidence']['original_report_sha256'],
                         hashlib.sha256(json.dumps(self.report, sort_keys=True).encode()).hexdigest())
        self.assertEqual(self.report_path.read_bytes(), original_bytes)
        self.assertTrue(result['applied'])
        self.assertTrue(result['review_required'])
        self.assertFalse(result['strict_json_validated'])
        after = self.snapshot()
        self.assertEqual(after['attempt'][:2], before['attempt'][:2])
        for table in ('review_release', 'conservative_continuation'):
            self.assertEqual(after[table], before[table])
        self.assertEqual(after['reconciliation'][:1], before['reconciliation'])
        changed = after['attempt'][-1]
        self.assertEqual(changed, {**before['attempt'][-1], 'state': 'blocked', 'cost': str(self.cost)})
        audit = after['reconciliation'][-1]
        self.assertEqual(audit['attempt_id'], self.target)
        self.assertEqual(audit['original_reserved'], before['attempt'][-1]['reserved'])
        self.assertEqual(audit['original_state'], 'unknown')
        self.assertEqual(audit['original_outcome'], before['attempt'][-1]['outcome'])
        self.assertEqual(self.requests, [('GET', '/api/v1/generation', {'id': self.metadata['id']})])
        summary = result['ledger']
        self.assertTrue(summary['uncertain_billing'])
        self.assertFalse(summary['blocking_uncertainty'])
        self.assertTrue(summary['blocked'])
        self.assertEqual(len(summary['conservative_continuations']), 1)
        with self.assertRaisesRegex(BudgetStop, 'billing_or_contract_blocked'):
            self.ledger.reserve('never-release', 'ask-01', 8000, 1600)

    def test_idempotent_replay_keeps_existing_audits_and_original_reserve(self):
        self.assertTrue(self.call(attempt_id=self.target)['applied'])
        once, bytes_once = self.snapshot(), self.path.read_bytes()
        self.assertFalse(self.call(attempt_id=self.target)['applied'])
        self.assertEqual(self.snapshot(), once)
        self.assertEqual(self.path.read_bytes(), bytes_once)
        self.assertEqual(len(self.requests), 2)

    def test_missing_wrong_old_and_duplicate_selectors_fail_before_transport(self):
        for selected in (None, 'not-in-report', self.prior):
            with self.subTest(selected=selected):
                before = self.path.read_bytes()
                with self.assertRaises(BudgetStop):
                    self.call(attempt_id=selected)
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual((self.directory_calls, self.sdk_calls), (0, 0))
        duplicate = copy.deepcopy(self.report)
        duplicate['ledger']['attempts'].append(copy.deepcopy(duplicate['ledger']['attempts'][-1]))
        self.save_report(duplicate)
        with self.assertRaisesRegex(BudgetStop, 'selector_mismatch'):
            self.call(attempt_id=self.target)
        self.assertEqual((self.directory_calls, self.sdk_calls), (0, 0))

    def test_single_attempt_report_retains_implicit_selector_and_default_ledger(self):
        single_path = self.root / 'standalone-single.db'
        ledger = BudgetLedger(single_path)
        target = ledger.reserve('original-run', 'ask-01', 8000, 1600)
        with self.assertRaises(BudgetStop):
            ledger.settle(target, cost=None, generation_id=self.metadata['id'],
                          outcome='unknown_billing_or_provider')
        # This is a separately created one-attempt original, never a cropped
        # cumulative report supplied to the reconciliation implementation.
        single = {**copy.deepcopy(self.report), 'ledger': ledger.summary()}
        self.save_report(single)
        with patch.object(self, 'path', single_path):
            self.assertTrue(self.call(default=True)['applied'])

    def test_missing_ledger_and_parent_are_never_created(self):
        missing = self.root / 'not-created' / 'budget.sqlite3'
        with self.assertRaisesRegex(BudgetStop, 'existing_ledger_required'):
            self.call(attempt_id=self.target, path=missing)
        self.assertFalse(missing.parent.exists())
        self.assertEqual((self.directory_calls, self.sdk_calls), (0, 0))

    def test_invalid_empty_old_schema_and_write_hook_ledgers_are_not_initialized(self):
        invalid, empty = self.root / 'invalid.db', self.root / 'empty.db'
        invalid.write_bytes(b'not sqlite')
        empty.write_bytes(b'')
        old, hook, version = (self.root / name for name in ('old.db', 'hook.db', 'version.db'))
        for path in (old, hook, version):
            shutil.copyfile(self.path, path)
        with closing(sqlite3.connect(old)) as db, db:
            db.execute('DROP TABLE conservative_continuation')
        with closing(sqlite3.connect(hook)) as db, db:
            db.execute("CREATE TRIGGER unexpected AFTER UPDATE ON attempt BEGIN UPDATE attempt SET outcome='changed'; END")
        with closing(sqlite3.connect(version)) as db, db:
            db.execute('PRAGMA user_version=99')
        for path in (invalid, empty, old, hook, version):
            with self.subTest(path=path.name):
                before = path.read_bytes()
                with self.assertRaises(BudgetStop):
                    self.call(attempt_id=self.target, path=path)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual((self.directory_calls, self.sdk_calls), (0, 0))

    def test_existing_schema_wrong_ledger_or_changed_identity_never_reads_provider(self):
        other = self.root / 'other.db'
        BudgetLedger(other)
        with self.assertRaisesRegex(BudgetStop, 'historical_attempt_missing'):
            self.call(attempt_id=self.target, path=other)
        self.assertEqual((self.directory_calls, self.sdk_calls), (0, 0))
        shutil.copyfile(self.path, other)
        with closing(sqlite3.connect(other)) as db, db:
            db.execute('UPDATE attempt SET run_id=? WHERE id=?', ('different-fixture', self.target))
        before = other.read_bytes()
        with self.assertRaisesRegex(BudgetStop, 'historical_attempt_evidence_mismatch'):
            self.call(attempt_id=self.target, path=other)
        self.assertEqual(other.read_bytes(), before)
        self.assertEqual((self.directory_calls, self.sdk_calls), (0, 0))

    def test_rw_connections_refuse_recreation_after_validation(self):
        ledger = BudgetLedger(self.path, existing_only=True)
        archived = self.path.with_suffix('.archived')
        self.path.rename(archived)
        with self.assertRaisesRegex(BudgetStop, 'existing_ledger_required'):
            ledger.attempt(self.target)
        self.assertFalse(self.path.exists())
        self.assertTrue(archived.is_file())

    def test_rw_uri_refuses_file_removed_between_check_and_connect(self):
        ledger = BudgetLedger(self.path, existing_only=True)
        archived = self.path.with_suffix('.race-archived')
        original_connect = sqlite3.connect
        calls = []

        def connect(database_path, *args, **options):
            calls.append((database_path, options))
            self.assertTrue(database_path.endswith('?mode=rw'))
            self.assertTrue(options.get('uri'))
            self.path.rename(archived)
            return original_connect(database_path, *args, **options)

        with patch('app.evaluation.ask_budget.sqlite3.connect', side_effect=connect):
            with self.assertRaisesRegex(BudgetStop, 'existing_ledger_invalid'):
                ledger.attempt(self.target)
        self.assertEqual(len(calls), 1)
        self.assertFalse(self.path.exists())
        self.assertTrue(archived.is_file())

    def test_receipt_mismatch_leaves_all_rows_and_audits_unchanged(self):
        before = self.snapshot()
        with self.assertRaisesRegex(BudgetStop, 'historical_cost_evidence_mismatch'):
            self.call(attempt_id=self.target, metadata={**self.metadata, 'total_cost': '0.00002'})
        self.assertEqual(self.snapshot(), before)
        self.assertEqual([method for method, *_ in self.requests], ['GET'])

    def test_cli_parameters_cannot_redirect_other_modes_or_repeat(self):
        out = self.root / 'must-not-write.json'
        modes = ([], ['--live'], ['--release-review', 'synthetic.json'],
                 ['--continue-conservatively', 'synthetic.json'])
        for mode in modes:
            for extra in (['--attempt-id', self.target], ['--ledger-path', str(self.path)]):
                with self.subTest(mode=mode, extra=extra), \
                        patch('sys.argv', ['ask', *mode, *extra, '--output', str(out)]), \
                        patch('sys.stderr', new=io.StringIO()), \
                        patch.object(ask, 'live') as live, patch.object(ask, 'offline') as offline, \
                        patch.object(ask, 'release_review_hold') as release, \
                        patch.object(ask, 'authorize_conservative_continuation') as continuation:
                    with self.assertRaises(SystemExit) as caught:
                        ask.main()
                    self.assertEqual(caught.exception.code, 2)
                    for action in (live, offline, release, continuation):
                        action.assert_not_called()
        for extra in (['--attempt-id', self.target, '--attempt-id', self.target],
                      ['--ledger-path', str(self.path), '--ledger-path', str(self.path)]):
            with self.subTest(duplicate=extra), \
                    patch('sys.argv', ['ask', '--reconcile-report', str(self.report_path), *extra, '--output', str(out)]), \
                    patch('sys.stderr', new=io.StringIO()), patch.object(ask, 'reconcile_canary') as action:
                with self.assertRaises(SystemExit) as caught:
                    ask.main()
                self.assertEqual(caught.exception.code, 2)
                action.assert_not_called()
        self.assertFalse(out.exists())

    def test_cli_dispatches_exact_selector_and_explicit_existing_path(self):
        out = self.root / 'dispatch.json'
        with patch('sys.argv', ['ask', '--reconcile-report', str(self.report_path),
                               '--attempt-id', self.target, '--ledger-path', str(self.path),
                               '--expected-cost-usd', str(self.cost), '--output', str(out)]), \
                patch('sys.stdout', new=io.StringIO()), \
                patch.object(ask, 'reconcile_canary', return_value={'review_required': True, 'evidence': {}}) as action:
            self.assertEqual(ask.main(), 0)
        action.assert_called_once_with(self.report_path, self.cost, attempt_id=self.target, ledger_path=self.path)


if __name__ == '__main__':
    unittest.main()
