"""One additional approval, using only owned synthetic ledgers and mock transport."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from decimal import Decimal
import hashlib
import io
import json
import sqlite3
import unittest
from unittest.mock import patch

from app.evaluation import ask
from app.evaluation.ask_budget import (
    ADDITIONAL_SCOPE, HARD_LIMIT, STOP_LIMIT, OUTPUT_LIMIT, BudgetLedger, BudgetStop,
    attempt_fingerprint,
)
from app.evaluation.ask_review import ADDITIONAL_AUTHORIZATION, authorize_additional_continuation
import test_ask_conservative_continuation as fixtures


class AskAdditionalContinuationTests(unittest.TestCase):
    def setUp(self):
        self.seed = fixtures.AskConservativeContinuationTests()
        self.seed.setUp()
        self.addCleanup(self.seed.doCleanups)
        self.path, self.root, self.ledger = self.seed.path, self.seed.root, self.seed.ledger
        self.seed.authorize()
        # Include nonempty historical reconciliation/release audits to preserve.
        prior = self.ledger.reserve('synthetic-reviewed', 'case', 100, OUTPUT_LIMIT)
        receipt = {'version': 'ask-reconciliation.v1', 'cost_usd': '0.0004',
                   'generation_id': 'gen-synthetic-reviewed'}
        with self.assertRaises(BudgetStop):
            self.ledger.settle(prior, cost=None, generation_id=receipt['generation_id'], outcome='unknown_billing_or_provider')
        self.ledger.reconcile(prior, evidence=receipt)
        digest = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.ledger.release_review(prior, reconciliation_sha256=digest,
            evidence={'version': 'ask-review-release.v1', 'decision': 'approved', **self.seed.context,
                      'attempt_id': prior, 'reconciliation_sha256': digest})
        self.target = self.ledger.reserve('synthetic-additional-failure', 'case', 100, OUTPUT_LIMIT)
        with self.assertRaises(BudgetStop):
            self.ledger.settle(self.target, cost=None, generation_id=None, outcome='transport_failure')
        self.original = self.ledger.attempt(self.target)
        self.evidence = {'version': 'ask-additional-conservative-continuation.v1', 'decision': 'approved',
            **self.seed.context, 'approval_scope': ADDITIONAL_SCOPE, 'user_confirmed': True,
            'user_approval_ref': 'synthetic-specific-additional-approval', 'user_approved_at': '2000-01-02T00:00:00Z',
            'attempt_id': self.target, 'attempt_sha256': attempt_fingerprint(self.original),
            'ledger_sha256': self.file_hash(), 'approval_sha256': 'd' * 64}
        self.before = self.snapshot()

    def file_hash(self):
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def snapshot(self):
        with closing(sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            return BudgetLedger._history_snapshot(db)

    def extra_rows(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='additional_conservative_continuation'").fetchone():
                return []
            return [dict(row) for row in db.execute('SELECT * FROM additional_conservative_continuation')]

    def authorize(self, evidence=None):
        evidence = self.evidence if evidence is None else evidence
        ledger = BudgetLedger(self.path, existing_only=True)
        return ledger.authorize_additional_continue(evidence['attempt_id'],
            attempt_sha256=evidence['attempt_sha256'], ledger_sha256=evidence['ledger_sha256'], evidence=evidence)

    def rebound(self, target=None):
        target = self.target if target is None else target
        return {**self.evidence, 'attempt_id': target,
                'attempt_sha256': attempt_fingerprint(self.ledger.attempt(target)), 'ledger_sha256': self.file_hash()}

    def test_one_append_preserves_all_history_unknown_cost_and_full_exposure(self):
        before_summary = self.ledger.summary()
        self.assertEqual(self.extra_rows(), [])
        self.assertTrue(self.authorize())
        self.assertEqual(self.snapshot(), self.before)
        summary = self.ledger.summary()
        self.assertEqual(summary['known_cost_usd'], before_summary['known_cost_usd'])
        self.assertEqual(summary['reserved_exposure_usd'], before_summary['reserved_exposure_usd'])
        self.assertTrue(summary['uncertain_billing'])
        self.assertFalse(summary['blocking_uncertainty'])
        self.assertEqual(Decimal(summary['permanent_conservative_hold_usd']), 2 * self.seed.full)
        self.assertEqual(len(summary['conservative_continuations']), 1)
        self.assertEqual(len(summary['additional_conservative_continuations']), 1)
        audit = self.extra_rows()[0]
        self.assertEqual(json.loads(audit['original_snapshot_json']), self.before)
        saved = json.loads(audit['evidence_json'])
        self.assertEqual(saved['original_snapshot_sha256'], hashlib.sha256(audit['original_snapshot_json'].encode()).hexdigest())
        self.assertEqual(saved['user_approval_ref'], self.evidence['user_approval_ref'])
        self.assertEqual(audit['ledger_sha256'], self.evidence['ledger_sha256'])
        self.assertEqual(self.ledger.attempt(self.target), self.original)
        self.assertIsNone(self.ledger.attempt(self.target)['cost'])

    def test_restart_and_exact_replay_do_not_issue_another_permission(self):
        self.authorize()
        once, raw = self.extra_rows(), self.path.read_bytes()
        BudgetLedger(self.path).summary()
        self.assertFalse(self.authorize())
        self.assertEqual(self.extra_rows(), once)
        self.assertEqual(self.snapshot(), self.before)
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertFalse(self.seed.authorize())

    def test_wrong_target_fingerprint_and_invalid_approval_do_not_write(self):
        changes = [{'attempt_sha256': '0' * 64}, {'ledger_sha256': '0' * 64},
                   {'user_confirmed': False}, {'user_approval_ref': ''}, {'approval_sha256': None},
                   {'approval_scope': 'unlimited'}, {'ci_head': 'b' * 40}, {'ci_conclusion': 'failure'}]
        for change in changes:
            with self.subTest(change=change):
                before = self.path.read_bytes()
                with self.assertRaises(BudgetStop):
                    self.authorize({**self.evidence, **change})
                self.assertEqual(self.path.read_bytes(), before)
        for target in (self.seed.target, self.seed.known):
            with self.subTest(target=target), self.assertRaises(BudgetStop):
                self.authorize(self.rebound(target))
        self.assertEqual(self.extra_rows(), [])

    def test_full_file_snapshot_binds_prior_audits_and_target_time(self):
        original_bytes = self.path.read_bytes()
        mutations = [
            ("UPDATE attempt SET created_at='2000-02-01 00:00:00' WHERE id=?", (self.target,)),
            ("UPDATE reconciliation SET evidence_json=evidence_json || ' '", ()),
            ("UPDATE review_release SET evidence_json=evidence_json || ' '", ()),
            ("UPDATE conservative_continuation SET evidence_json=evidence_json || ' '", ()),
        ]
        for sql, args in mutations:
            with self.subTest(sql=sql):
                self.path.write_bytes(original_bytes)
                with self.ledger._db() as db:
                    db.execute(sql, args)
                mutated = self.path.read_bytes()
                with self.assertRaisesRegex(BudgetStop, 'snapshot_mismatch'):
                    self.authorize()
                self.assertEqual(self.path.read_bytes(), mutated)
                self.assertEqual(self.extra_rows(), [])

    def test_reduced_reservation_rejected_even_with_new_matching_snapshot(self):
        with self.ledger._db() as db:
            db.execute('UPDATE attempt SET reserved=? WHERE id=?', ('0', self.target))
        before = self.path.read_bytes()
        with self.assertRaisesRegex(BudgetStop, 'attempt_mismatch'):
            self.authorize(self.rebound())
        self.assertEqual(self.path.read_bytes(), before)

    def test_granted_snapshot_detects_reduced_or_deleted_history(self):
        self.authorize()
        approved = self.path.read_bytes()
        for sql, args in [
            ('UPDATE attempt SET reserved=? WHERE id=?', ('0', self.target)),
            ('UPDATE attempt SET cost=? WHERE id=?', ('0', self.seed.known)),
            ('DELETE FROM review_release', ()),
            ("UPDATE additional_conservative_continuation SET original_snapshot_json='{}'", ()),
        ]:
            with self.subTest(sql=sql):
                self.path.write_bytes(approved)
                with self.ledger._db() as db:
                    db.execute(sql, args)
                with self.assertRaisesRegex(BudgetStop, 'integrity_failed'):
                    self.ledger.reserve('never-continue', 'case', 100, OUTPUT_LIMIT)

    def test_changed_authorization_cannot_replace_consumed_additional_slot(self):
        self.authorize()
        raw = self.path.read_bytes()
        for change in ({'user_approval_ref': 'synthetic-other-approval'}, {'approval_sha256': 'e' * 64},
                       {'ledger_sha256': self.file_hash()}):
            with self.subTest(change=change), self.assertRaisesRegex(BudgetStop, 'already_used'):
                self.authorize({**self.evidence, **change})
        self.assertEqual(self.path.read_bytes(), raw)

    def test_old_user_approval_reference_cannot_authorize_additional_exception(self):
        before = self.path.read_bytes()
        with self.assertRaisesRegex(BudgetStop, 'approval_must_be_distinct'):
            self.authorize({**self.evidence, 'user_approval_ref': self.seed.evidence['user_approval_ref']})
        self.assertEqual(self.path.read_bytes(), before)

    def test_future_unknown_blocks_and_neither_old_nor_new_slot_can_exempt_it(self):
        self.authorize()
        future = self.ledger.reserve('future-unknown', 'case', 100, OUTPUT_LIMIT)
        with self.assertRaises(BudgetStop):
            self.ledger.settle(future, cost=None, generation_id=None, outcome='transport_failure')
        self.assertTrue(self.ledger.summary()['blocking_uncertainty'])
        self.assertFalse(self.authorize())
        with self.assertRaisesRegex(BudgetStop, 'already_used'):
            self.authorize(self.rebound(future))
        with self.assertRaisesRegex(BudgetStop, 'single_conservative_continuation_already_used'):
            self.ledger.authorize_conservative_continue(future,
                attempt_sha256=attempt_fingerprint(self.ledger.attempt(future)),
                evidence={**self.seed.evidence, 'attempt_id': future,
                          'attempt_sha256': attempt_fingerprint(self.ledger.attempt(future))})
        with self.assertRaisesRegex(BudgetStop, 'unsettled_attempt_stop'):
            self.ledger.reserve('no-third-exception', 'case', 100, OUTPUT_LIMIT)

    def test_concurrent_identical_approvals_are_one_append_and_one_replay(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.authorize(), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(len(self.extra_rows()), 1)
        self.assertEqual(self.snapshot(), self.before)

    def test_concurrent_different_approvals_cannot_consume_two_slots(self):
        def authorize(number):
            try:
                return self.authorize({**self.evidence, 'user_approval_ref': 'synthetic-approval-' + str(number)})
            except BudgetStop as error:
                return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(authorize, range(2)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count('additional_conservative_continuation_already_used'), 1)
        self.assertEqual(len(self.extra_rows()), 1)

    def test_concurrent_reservations_still_allow_only_one_unsettled_attempt(self):
        self.authorize()
        def reserve(number):
            try:
                return BudgetLedger(self.path, existing_only=True).reserve('synthetic-next-' + str(number), 'case', 100, OUTPUT_LIMIT)
            except BudgetStop as error:
                return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, range(2)))
        self.assertEqual(results.count('unsettled_attempt_stop'), 1)

    def test_stop_and_hard_limits_do_not_change_or_drop_either_reserve(self):
        self.authorize()
        for index in range(5):
            item = self.ledger.reserve('synthetic-billed-' + str(index), 'case', 100, OUTPUT_LIMIT)
            self.ledger.settle(item, cost='0.1', generation_id='gen-synthetic-billed-' + str(index), outcome='response')
        with self.assertRaisesRegex(BudgetStop, 'cumulative_budget_stop'):
            self.ledger.reserve('over-stop', 'case', 100, OUTPUT_LIMIT)
        # Raise only the stop line in this fixture to exercise the unchanged
        # real 1 USD hard cap, which the production 0.75 stop normally precedes.
        with patch('app.evaluation.ask_budget.STOP_LIMIT', Decimal('2')):
            for index in range(2):
                item = self.ledger.reserve('synthetic-hard-' + str(index), 'case', 100, OUTPUT_LIMIT)
                self.ledger.settle(item, cost='0.1', generation_id='gen-synthetic-hard-' + str(index), outcome='response')
            with self.assertRaisesRegex(BudgetStop, 'cumulative_budget_stop'):
                self.ledger.reserve('over-hard-fixture', 'case', 100, OUTPUT_LIMIT)
        self.assertEqual((STOP_LIMIT, HARD_LIMIT), (Decimal('0.75'), Decimal('1.00')))
        self.assertEqual(Decimal(self.ledger.summary()['permanent_conservative_hold_usd']), 2 * self.seed.full)

    def test_authorization_cannot_be_granted_if_next_full_reserve_exceeds_budget(self):
        before = self.path.read_bytes()
        for limited in ('STOP_LIMIT', 'HARD_LIMIT'):
            with self.subTest(limit=limited), patch('app.evaluation.ask_budget.' + limited, Decimal('0.3')):
                with self.assertRaisesRegex(BudgetStop, 'cumulative_budget_stop'):
                    self.authorize()
        self.assertEqual(self.path.read_bytes(), before)

    def test_schema_is_optional_strict_and_missing_ledger_is_not_created(self):
        self.assertEqual(self.extra_rows(), [])
        BudgetLedger(self.path, existing_only=True).summary()
        self.assertEqual(self.extra_rows(), [])
        self.authorize()
        BudgetLedger(self.path, existing_only=True).summary()
        with self.ledger._db() as db:
            db.execute('CREATE TRIGGER synthetic_hook AFTER INSERT ON attempt BEGIN SELECT 1; END')
        with self.assertRaisesRegex(BudgetStop, 'schema_mismatch'):
            BudgetLedger(self.path, existing_only=True)
        missing = self.root / 'absent' / 'budget.sqlite3'
        with self.assertRaisesRegex(BudgetStop, 'existing_ledger_required'):
            BudgetLedger(missing, existing_only=True)
        self.assertFalse(missing.parent.exists())

    def test_original_slot_must_already_exist_and_empty_optional_table_fails_closed(self):
        with self.ledger._db() as db:
            db.execute('DELETE FROM conservative_continuation')
        before = self.path.read_bytes()
        with self.assertRaisesRegex(BudgetStop, 'attempt_mismatch'):
            self.authorize(self.rebound())
        self.assertEqual(self.path.read_bytes(), before)
        from app.evaluation.ask_budget import _ADDITIONAL_SCHEMA
        with self.ledger._db() as db:
            db.execute(_ADDITIONAL_SCHEMA)
        with self.assertRaisesRegex(BudgetStop, 'integrity_failed'):
            self.ledger.summary()

    def test_explicit_review_and_user_approval_precede_any_optional_schema_write(self):
        approval = {**self.evidence, 'version': 'ask-additional-conservative-approval.v1'}
        path = self.root / 'additional-approval.json'
        path.write_text(json.dumps(approval), encoding='utf-8')
        raw = self.path.read_bytes()
        with patch('app.evaluation.ask_review._verified_review_context', side_effect=AssertionError('must not verify')):
            with self.assertRaisesRegex(BudgetStop, 'explicit_additional_conservative_authorization_required'):
                authorize_additional_continuation(path, authorization=None, ledger_path=self.path, repo_root=self.root)
        with patch('app.evaluation.ask_review._verified_review_context', side_effect=BudgetStop('review_not_approved')):
            with self.assertRaisesRegex(BudgetStop, 'review_not_approved'):
                authorize_additional_continuation(path, authorization=ADDITIONAL_AUTHORIZATION, ledger_path=self.path, repo_root=self.root)
        self.assertEqual(self.path.read_bytes(), raw)
        with patch('app.evaluation.ask_review._verified_review_context', return_value=self.seed.context):
            result = authorize_additional_continuation(path, authorization=ADDITIONAL_AUTHORIZATION,
                                                       ledger_path=self.path, repo_root=self.root)
        self.assertTrue(result['continuation_authorized'])
        self.assertEqual(result['paid_requests_in_run'], 0)
        self.assertEqual(self.snapshot(), self.before)

    def test_cli_cannot_mix_additional_approval_with_live_or_redirect_ledger(self):
        for extra in (['--live'], ['--continue-conservatively', 'old.json'],
                      ['--ledger-path', str(self.path)], ['--attempt-id', self.target]):
            argv = ['ask', '--continue-additionally', 'private.json', *extra,
                    '--output', str(self.root / 'out.json')]
            with self.subTest(extra=extra), patch('sys.argv', argv), patch('sys.stderr', new=io.StringIO()):
                with self.assertRaises(SystemExit) as stopped:
                    ask.main()
                self.assertEqual(stopped.exception.code, 2)
        self.assertEqual(self.extra_rows(), [])

    def test_cli_records_only_approval_and_cannot_construct_provider_client(self):
        approval = {**self.evidence, 'version': 'ask-additional-conservative-approval.v1'}
        path = self.root / 'private-additional.json'
        path.write_text(json.dumps(approval), encoding='utf-8')
        output = self.root / 'result.json'
        argv = ['ask', '--continue-additionally', str(path), '--authorization', ADDITIONAL_AUTHORIZATION,
                '--output', str(output)]
        with patch('sys.argv', argv), patch.object(ask, 'LEDGER', self.path), \
                patch('app.evaluation.ask_review._verified_review_context', return_value=self.seed.context), \
                patch.object(ask, 'OpenAI', side_effect=AssertionError('no provider access')), \
                patch('sys.stdout', new=io.StringIO()):
            self.assertEqual(ask.main(), 0)
        result = json.loads(output.read_text(encoding='utf-8'))
        self.assertTrue(result['continuation_authorized'])
        self.assertEqual(result['paid_requests_in_run'], 0)
        self.assertEqual(self.snapshot(), self.before)

    def test_synthetic_canary_retains_both_unknowns_and_succeeds(self):
        self.authorize()
        self.seed.run_synthetic_canary(fail=False)
        self.assertEqual(self.ledger.attempt(self.target), self.original)

    def test_synthetic_next_transport_failure_stops_after_one_post(self):
        self.authorize()
        self.seed.run_synthetic_canary(fail=True)
        self.assertTrue(self.ledger.summary()['blocking_uncertainty'])
        self.assertEqual(len(self.extra_rows()), 1)


if __name__ == '__main__':
    unittest.main()
