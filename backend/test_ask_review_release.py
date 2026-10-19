import io
import json
from pathlib import Path
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from app.evaluation.ask import main
from app.evaluation.ask_budget import BudgetLedger, BudgetStop
from app.evaluation.ask_review import RELEASE_AUTHORIZATION, release_review_hold, verify_review_approval


class AskReviewReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Synthetic Test')
        self.git('config', 'user.email', 'test@example.invalid')
        (self.repo / 'app.py').write_text('synthetic = 1\n')
        (self.repo / 'docs').mkdir()
        (self.repo / 'docs' / 'readme.md').write_text('Synthetic documentation.\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'synthetic reviewed code')
        self.reviewed = self.git('rev-parse', 'HEAD')
        self.ledger_path = self.root / 'budget.sqlite3'
        self.ledger = BudgetLedger(self.ledger_path)
        self.attempt = self.ledger.reserve('synthetic-run', 'synthetic-case', 100, 100)
        with self.assertRaises(BudgetStop):
            self.ledger.settle(self.attempt, cost=None, generation_id='gen-synthetic-review',
                               outcome='unknown_billing_or_provider')
        self.receipt = {'version': 'ask-reconciliation.v1', 'generation_id': 'gen-synthetic-review',
                        'cost_usd': '0.0002'}
        self.ledger.reconcile(self.attempt, evidence=self.receipt)
        self.reconciliation = self.ledger.summary()['reconciliations'][0]['evidence_sha256']
        self.approval = {'version': 'ask-review-approval.v1', 'decision': 'approved',
                         'reviewed_head': self.reviewed, 'ci_run_id': 42,
                         'review_ref': 'synthetic-independent-parent-review',
                         'attempt_id': self.attempt, 'reconciliation_sha256': self.reconciliation}
        self.ci = {'id': 42, 'run_attempt': 1, 'head_sha': self.reviewed, 'status': 'completed', 'conclusion': 'success',
                   'path': '.github/workflows/ci.yml', 'event': 'pull_request',
                   'repository': {'full_name': 'ChiosYang/5X49'}, 'pull_requests': [{'number': 28}]}
        self.approval_path = self.root / 'approval.json'
        self.approval_path.write_text(json.dumps(self.approval))

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True).strip()

    def mock_ci(self, ci=None):
        transport = patch('app.evaluation.ask_review.urllib.request.urlopen')
        fake = transport.start()
        self.addCleanup(transport.stop)
        fake.return_value.__enter__.return_value.read.return_value = json.dumps(ci if ci is not None else self.ci)
        return fake

    def evidence(self):
        self.mock_ci()
        return verify_review_approval(self.approval, repo_root=self.repo)

    def release(self, authorization=RELEASE_AUTHORIZATION):
        return release_review_hold(self.approval_path, authorization=authorization,
                                   ledger_path=self.ledger_path, repo_root=self.repo)

    def test_release_is_audited_idempotent_and_keeps_original_accounting(self):
        fake = self.mock_ci()
        before = self.ledger.attempt(self.attempt)
        totals = self.ledger.summary()
        first = self.release()
        second = self.release()
        self.assertTrue(first['applied'])
        self.assertFalse(second['applied'])
        self.assertEqual(first['paid_requests_in_run'], 0)
        self.assertFalse(first['strict_json_validated'])
        after = self.ledger.attempt(self.attempt)
        self.assertEqual(after, {**before, 'state': 'settled'})
        result = self.ledger.summary()
        self.assertEqual(result['known_cost_usd'], totals['known_cost_usd'])
        self.assertEqual(result['reserved_exposure_usd'], totals['reserved_exposure_usd'])
        self.assertEqual(len(result['review_releases']), 1)
        with self.ledger._db() as db:
            audit = dict(db.execute('SELECT * FROM review_release').fetchone())
        stored = json.loads(audit['evidence_json'])
        self.assertEqual(stored['reviewed_head'], self.reviewed)
        self.assertEqual(stored['ci_run_id'], 42)
        self.assertEqual(stored['ci_run_attempt'], 1)
        self.assertEqual(stored['review_ref'], self.approval['review_ref'])
        self.assertEqual(audit['previous_state'], 'blocked')
        self.assertFalse(self.ledger.reconcile(self.attempt, evidence=self.receipt))
        self.assertEqual(self.ledger.attempt(self.attempt)['state'], 'settled')
        for call in fake.call_args_list:
            request = call.args[0]
            self.assertEqual(request.get_method(), 'GET')
            self.assertEqual(request.full_url, 'https://api.github.com/repos/ChiosYang/5X49/actions/runs/42')

    def test_uncommitted_and_unreviewed_code_reject_before_ci(self):
        fake = self.mock_ci()
        before = self.ledger_path.read_bytes()
        (self.repo / 'app.py').write_text('synthetic = 2\n')
        with self.assertRaisesRegex(BudgetStop, 'unreviewed_worktree_changes'):
            self.release()
        self.git('add', '.')
        self.git('commit', '-qm', 'synthetic unreviewed code')
        with self.assertRaisesRegex(BudgetStop, 'unreviewed_code_changes'):
            self.release()
        self.assertEqual(self.ledger_path.read_bytes(), before)
        fake.assert_not_called()

    def test_only_committed_documentation_may_follow_reviewed_head(self):
        self.mock_ci()
        (self.repo / 'docs' / 'readme.md').write_text('Updated synthetic documentation.\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'synthetic documentation followup')
        result = self.release()
        self.assertEqual(result['review_evidence']['reviewed_head'], self.reviewed)
        self.assertEqual(result['review_evidence']['current_head'], self.git('rev-parse', 'HEAD'))

    def test_worktree_changes_during_ci_lookup_cannot_release(self):
        before = self.ledger_path.read_bytes()
        with patch('app.evaluation.ask_review.urllib.request.urlopen') as fake:
            def response():
                (self.repo / 'app.py').write_text('synthetic = 3\n')
                return json.dumps(self.ci)
            fake.return_value.__enter__.return_value.read.side_effect = response
            with self.assertRaisesRegex(BudgetStop, 'worktree_changed_during_review_verification'):
                self.release()
        self.assertEqual(self.ledger_path.read_bytes(), before)

    def test_missing_or_mismatched_ci_cannot_change_ledger(self):
        variants = ({'id': 43}, {'run_attempt': None}, {'head_sha': 'a' * 40}, {'conclusion': 'failure'},
                    {'status': 'in_progress'}, {'path': '.github/workflows/unrelated.yml'},
                    {'repository': {'full_name': 'other/repo'}}, {'event': 'push'}, {'pull_requests': []})
        before = self.ledger_path.read_bytes()
        for change in variants:
            with self.subTest(change=change), patch('app.evaluation.ask_review.urllib.request.urlopen') as fake:
                fake.return_value.__enter__.return_value.read.return_value = json.dumps({**self.ci, **change})
                with self.assertRaisesRegex(BudgetStop, 'review_ci_evidence_mismatch'):
                    self.release()
                self.assertEqual(self.ledger_path.read_bytes(), before)
        with patch('app.evaluation.ask_review.urllib.request.urlopen', side_effect=RuntimeError('synthetic offline')):
            with self.assertRaisesRegex(BudgetStop, 'review_ci_evidence_unavailable'):
                self.release()
        self.assertEqual(self.ledger_path.read_bytes(), before)

    def test_release_leaves_other_unknowns_and_global_stop_intact(self):
        # Historical damaged/imported fixtures may contain another unknown;
        # seed only this owned temporary database, never the task ledger.
        with self.ledger._db() as db:
            db.execute("INSERT INTO attempt(id,run_id,case_id,reserved,state,outcome) VALUES ('other','old','old','0.1','unknown','transport_failure')")
        before = self.ledger.attempt('other')
        totals = self.ledger.summary()
        self.mock_ci()
        self.release()
        self.assertEqual(self.ledger.attempt('other'), before)
        self.assertEqual(self.ledger.summary()['known_cost_usd'], totals['known_cost_usd'])
        self.assertEqual(self.ledger.summary()['reserved_exposure_usd'], totals['reserved_exposure_usd'])
        with self.assertRaisesRegex(BudgetStop, 'unsettled_attempt_stop'):
            self.ledger.reserve('still-blocked', 'case', 100, 100)
        evidence = {**self.evidence(), 'attempt_id': 'other'}
        with self.assertRaisesRegex(BudgetStop, 'review_hold_not_reconciled'):
            self.ledger.release_review('other', reconciliation_sha256=self.reconciliation, evidence=evidence)

    def test_wrong_reconciliation_and_replay_or_new_failure_remain_blocked(self):
        evidence = self.evidence()
        before = self.ledger.summary()
        wrong = {**evidence, 'reconciliation_sha256': '0' * 64}
        with self.assertRaises(BudgetStop):
            self.ledger.release_review(self.attempt, reconciliation_sha256='0' * 64, evidence=wrong)
        self.assertEqual(self.ledger.summary(), before)
        self.ledger.release_review(self.attempt, reconciliation_sha256=self.reconciliation, evidence=evidence)
        with self.assertRaisesRegex(BudgetStop, 'replay_mismatch'):
            self.ledger.release_review(self.attempt, reconciliation_sha256=self.reconciliation,
                                       evidence={**evidence, 'review_ref': 'different-review'})
        self.ledger.block(self.attempt, 'new-token-contract-failure')
        with self.assertRaises(BudgetStop):
            self.ledger.release_review(self.attempt, reconciliation_sha256=self.reconciliation, evidence=evidence)
        self.assertTrue(self.ledger.summary()['blocked'])

    def test_concurrent_release_creates_one_audit(self):
        evidence = self.evidence()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: BudgetLedger(self.ledger_path).release_review(
                self.attempt, reconciliation_sha256=self.reconciliation, evidence=evidence), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(len(self.ledger.summary()['review_releases']), 1)

    def test_explicit_release_authorization_and_approval_are_required(self):
        before = self.ledger_path.read_bytes()
        with patch('app.evaluation.ask_review.verify_review_approval', side_effect=AssertionError('no verification')):
            with self.assertRaisesRegex(BudgetStop, 'explicit_review_release_authorization_required'):
                self.release(authorization=None)
        for change in ({'decision': 'pending'}, {'reviewed_head': 'short'}, {'review_ref': ''},
                       {'reconciliation_sha256': 'short'}, {'ci_run_id': True}):
            with self.subTest(change=change), self.assertRaises(BudgetStop):
                verify_review_approval({**self.approval, **change}, repo_root=self.repo)
        self.assertEqual(self.ledger_path.read_bytes(), before)

    def test_cli_release_is_exclusive_with_inference(self):
        args = ['ask', '--live', '--release-review', str(self.approval_path), '--output', str(self.root / 'out.json')]
        with patch('sys.argv', args), patch('sys.stderr', new=io.StringIO()), \
                patch('app.evaluation.ask.OpenAI', side_effect=AssertionError('no provider')), \
                self.assertRaises(SystemExit) as stopped:
            main()
        self.assertEqual(stopped.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
