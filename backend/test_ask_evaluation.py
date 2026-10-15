import json
import os
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.evaluation.ask import AUTHORIZATION, corpus, live, live_gate, offline, official_preflight, MODEL, PROVIDER, PaidClient, POLICY
from app.evaluation.ask_budget import BudgetLedger, BudgetStop, input_upper_bound
from app.services.ask import AskInterpreter


class AskEvaluationTests(unittest.TestCase):
    def test_supported_accuracy_never_excuses_dropped_unsupported_requirements(self):
        self.assertFalse(live_gate(True,False,1.0,1))
        self.assertFalse(live_gate(True,True,1.0,0))
        self.assertFalse(live_gate(False,False,1.0,0))
        self.assertFalse(live_gate(True,False,0.94,0))
        self.assertTrue(live_gate(True,False,0.95,0))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'budget.sqlite3'

    def test_bilingual_fixtures_are_contract_evidence_not_model_quality(self):
        report = offline()
        self.assertEqual((report['fixture_cases'], report['fixture_passed']), (58, 58))
        self.assertIsNone(report['live_supported_accuracy'])
        self.assertIsNone(report['cost_usd'])
        self.assertEqual({case['locale'] for case in corpus()}, {'en', 'zh'})
        self.assertTrue({'person_ambiguity', 'negation', 'no_results', 'interface_failure', 'malicious_format', 'privacy'} <= {case['category'] for case in corpus()})

    def test_every_complete_prompt_is_bounded_by_bytes_including_schema_and_framing(self):
        for case in corpus():
            self.assertLessEqual(input_upper_bound([{'content': AskInterpreter.prompt()}, {'content':case['question']}]), 8000)
        with self.assertRaisesRegex(BudgetStop, 'input_token_upper_bound_exceeded'):
            input_upper_bound([{'content':'中'*3000}])

    def test_no_live_transport_without_explicit_auth_budget_and_existing_key(self):
        args = SimpleNamespace(authorization=None, budget_usd=Decimal('1'), run_id='test', canary_only=False)
        with patch('app.evaluation.ask.official_preflight', side_effect=AssertionError('no network')):
            with self.assertRaisesRegex(BudgetStop, 'authorization'):
                live(args)
            args.authorization=AUTHORIZATION
            args.budget_usd=Decimal('5')
            with self.assertRaisesRegex(BudgetStop, 'authorization'):
                live(args)
            args.budget_usd=Decimal('1')
            with patch.dict(os.environ, {'OPENROUTER_API_KEY':''}), self.assertRaisesRegex(BudgetStop, 'credential_missing'):
                live(args)

    def test_unknown_billing_and_process_interruption_block_later_runners(self):
        ledger = BudgetLedger(self.path)
        attempt = ledger.reserve('first-run', 'first', 8000, 1600)
        with self.assertRaisesRegex(BudgetStop, 'unsettled_attempt'):
            BudgetLedger(self.path).reserve('second-run', 'second', 8000, 1600)
        with self.assertRaisesRegex(BudgetStop, 'unknown_billing'):
            ledger.settle(attempt, cost=None, generation_id=None, outcome='timeout')
        with self.assertRaisesRegex(BudgetStop, 'unsettled_attempt'):
            ledger.reserve('second-run', 'second', 8000, 1600)
        self.assertTrue(ledger.summary()['uncertain_billing'])

    def test_budget_is_cumulative_across_runs_and_uses_pre_request_reservation(self):
        ledger = BudgetLedger(self.path)
        # Seed historical, explicitly settled evidence rather than 670 requests.
        with ledger._db() as db:
            db.execute("INSERT INTO attempt(id,run_id,case_id,reserved,cost,generation_id,state) VALUES ('old','old','old','0.749','0.749','generation-old','settled')")
        with self.assertRaisesRegex(BudgetStop, 'cumulative_budget_stop'):
            BudgetLedger(self.path).reserve('new-run','new',8000,1600)
        self.assertEqual(ledger.summary()['known_cost_usd'], '0.749')

    def test_atomic_reservation_blocks_concurrent_paid_requests(self):
        ledger = BudgetLedger(self.path)
        def reserve(index):
            try:
                return ledger.reserve('same-run',str(index),8000,1600)
            except BudgetStop:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            attempts=list(pool.map(reserve,range(4)))
        self.assertEqual(sum(value is not None for value in attempts),1)

    def test_actual_cost_and_generation_ids_persist_without_questions_or_secrets(self):
        ledger=BudgetLedger(self.path)
        attempt=ledger.reserve('run','case-1',8000,1600)
        ledger.settle(attempt,cost=0.0003,generation_id='gen-public',outcome='response')
        next_attempt=BudgetLedger(self.path).reserve('run2','case-2',8000,1600)
        ledger.settle(next_attempt,cost=0,generation_id='gen-free',outcome='response')
        summary=ledger.summary()
        self.assertEqual(summary['known_cost_usd'],'0.0003')
        self.assertFalse(summary['uncertain_billing'])
        self.assertEqual(summary['attempts'][0]['generation_id'],'gen-public')
        self.assertNotIn('question',json.dumps(summary))
        self.assertNotIn('api_key',json.dumps(summary))

    def test_price_model_provider_and_parameter_changes_fail_closed(self):
        endpoint={'tag':PROVIDER,'pricing':{'prompt':'0.00000009','completion':'0.00000018'},
                  'provider_name':'Decart','status':0,'context_length':1048576,'supported_parameters':['response_format','max_tokens','reasoning']}
        for changes in ({'pricing':{'prompt':'0.00001','completion':'0.00000018'}},
                        {'supported_parameters':[]},{'status':1},{'tag':'other'}):
            payload={'data':{'id':MODEL,'endpoints':[{**endpoint,**changes}]}}
            with patch('app.evaluation.ask.urllib.request.urlopen') as response:
                response.return_value.__enter__.return_value.read.return_value=json.dumps(payload)
                with self.assertRaises(BudgetStop): official_preflight()

    def _paid_client(self, sdk, ledger):
        with patch('app.evaluation.ask.OpenAI', return_value=sdk):
            return PaidClient(ledger=ledger,run_id='test',case_id='canary',preflight={'provider_name':'Decart'},api_key='synthetic')

    def test_paid_transport_reserves_absolute_context_cost_and_records_verified_generation(self):
        from unittest.mock import MagicMock
        sdk=MagicMock()
        sdk.chat.completions.create.return_value=SimpleNamespace(id='gen-synthetic',model=MODEL,
            usage=SimpleNamespace(cost=0.0001,prompt_tokens=20,completion_tokens=10,
                completion_tokens_details=SimpleNamespace(reasoning_tokens=0)))
        sdk.get.side_effect=lambda path, **kwargs: {'data':{'total_credits':1,'total_usage':0}} if path=='/credits' else {'data':{'provider_name':'Decart','model':MODEL,'total_cost':0.0001}}
        ledger=BudgetLedger(self.path)
        client=self._paid_client(sdk,ledger)
        client.create(model=MODEL,extra_body=POLICY,max_tokens=1600,messages=[{'content':'synthetic'}])
        receipt=ledger.summary()['attempts'][0]
        self.assertEqual(Decimal(receipt['reserved']),Decimal('0.1051776'))
        self.assertEqual(receipt['cost'],'0.0001')
        self.assertEqual(receipt['generation_id'],'gen-synthetic')
        sdk.chat.completions.create.assert_called_once()

    def test_low_balance_and_changed_policy_stop_before_paid_transport(self):
        from unittest.mock import MagicMock
        sdk=MagicMock()
        sdk.get.return_value={'data':{'total_credits':0.01,'total_usage':0}}
        ledger=BudgetLedger(self.path)
        client=self._paid_client(sdk,ledger)
        with self.assertRaisesRegex(BudgetStop,'insufficient_existing_credits'):
            client.create(model=MODEL,extra_body=POLICY,max_tokens=1600,messages=[{'content':'synthetic'}])
        with self.assertRaisesRegex(BudgetStop,'request_policy_changed'):
            client.create(model='expensive/other',extra_body=POLICY,max_tokens=1600,messages=[{'content':'synthetic'}])
        sdk.chat.completions.create.assert_not_called()
        self.assertEqual(ledger.summary()['attempts'],[])

    def test_nonzero_reasoning_keeps_actual_cost_and_blocks_later_runs(self):
        from unittest.mock import MagicMock
        sdk=MagicMock()
        sdk.chat.completions.create.return_value=SimpleNamespace(id='gen-synthetic',model=MODEL,
            usage=SimpleNamespace(cost=0.0001,prompt_tokens=20,completion_tokens=10,
                completion_tokens_details=SimpleNamespace(reasoning_tokens=1)))
        sdk.get.side_effect=lambda path, **kwargs: {'data':{'total_credits':1,'total_usage':0}} if path=='/credits' else {'data':{'provider_name':'Decart','model':MODEL,'total_cost':0.0001}}
        ledger=BudgetLedger(self.path)
        with self.assertRaisesRegex(BudgetStop,'token_or_reasoning_contract_failed'):
            self._paid_client(sdk,ledger).create(model=MODEL,extra_body=POLICY,max_tokens=1600,messages=[{'content':'synthetic'}])
        self.assertEqual(ledger.summary()['known_cost_usd'],'0.0001')
        with self.assertRaisesRegex(BudgetStop,'billing_or_contract_blocked'):
            BudgetLedger(self.path).reserve('later','new',8000,1600)


if __name__=='__main__': unittest.main()
