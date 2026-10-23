"""Two real worker threads sharing one synthetic authorization ledger."""
from pathlib import Path
import tempfile
from threading import Event, Thread
import unittest

from app.services.search_budget import SearchAuthorization, SearchBudget
from app.services.search_providers import DecisionProvider, EgressScope, SearchProviderClient
from app.services.semantic_search import SemanticError, _hash
from test_search_providers import Transport, QUERY, DOCUMENTS


class SharedDispatchTests(unittest.TestCase):
    def run_pair(self, cancel_new):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipts.db"
            grant = SearchAuthorization("synthetic-concurrency", 10, "0", 2000000000)
            initial = SearchBudget(path, grant)
            initial.close()
            scope = EgressScope("public-evaluation.v2", frozenset(_hash(t) for t in DOCUMENTS),
                frozenset({_hash(QUERY)}), accept_logged_public=True)
            entered, release, second_ready, second_sent, cancelled = (Event() for _ in range(5))
            results = {}

            class Controlled(Transport):
                def __init__(self, old):
                    super().__init__()
                    self.old = old
                def post(self, *args, **kwargs):
                    if self.old:
                        entered.set()
                        if not release.wait(5): raise RuntimeError("Synthetic timeout")
                    else:
                        second_sent.set()
                    return super().post(*args, **kwargs)

            def worker(old):
                ledger = SearchBudget(path, grant)
                client = SearchProviderClient(ledger, scope, lambda: "synthetic-key", session=Controlled(old),
                    cancelled=(lambda: False) if old else cancelled.is_set)
                try:
                    client.preflight()
                    if not old: second_ready.set()
                    results[old] = DecisionProvider(client).decide(QUERY).route
                except Exception as error:
                    results[old] = error.code if isinstance(error, SemanticError) else type(error).__name__
                finally:
                    client.close()
                    ledger.close()
            first = Thread(target=worker, args=(True,))
            second = Thread(target=worker, args=(False,))
            first.start()
            try:
                self.assertTrue(entered.wait(3))
                second.start()
                self.assertTrue(second_ready.wait(3))
                self.assertFalse(second_sent.wait(.05))
                if cancel_new: cancelled.set()
            finally:
                release.set()
                first.join(5)
                if second.ident is not None: second.join(5)
            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            ledger = SearchBudget(path, grant)
            try:
                summary = ledger.summary()
            finally:
                ledger.close()
            self.assertEqual(results[True], "semantic")
            self.assertEqual(results[False], "search_cancelled" if cancel_new else "semantic")
            self.assertEqual(summary["requests"], 1 if cancel_new else 2)
            self.assertIsNone(summary["halted"])
            self.assertTrue(all(r["state"] == "reported" for r in summary["receipts"]))

    def test_new_submit_waits_for_known_inflight_receipt_without_false_budget_halt(self):
        self.run_pair(False)

    def test_cancelled_queued_submit_has_no_key_reservation_or_second_transport(self):
        self.run_pair(True)


if __name__ == "__main__":
    unittest.main()
