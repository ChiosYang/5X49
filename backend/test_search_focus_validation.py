"""Synthetic-only authorization, body binding and restart/stop regressions."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import requests

from app.evaluation import search_focus_validation as runner
from app.evaluation.search_focus_budget import FocusBudget, PREFIX
from app.services.search_budget import SearchAuthorization, SearchBudget
from app.services.search_providers import DECISION, EMBEDDING, RERANK, EgressScope, RerankProvider
from app.services.semantic_search import SemanticError, _hash
from test_search_providers import Transport
import test_integrated_search as integration


class FocusBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.path = self.root / "shared-budget.sqlite3"
        self.auth = SearchAuthorization("synthetic-focus-original", 320, "0", 10)
        self.budget = FocusBudget(self.path, self.auth, clock=lambda: 100)
        self.addCleanup(self.budget.close)
        self.bodies = [{"query": f"family obligations aspect {i}",
                        "documents": ["A family reunites.", "An isolated traveller returns home."], "top_n": 2}
                       for i in range(5)]
        with self.budget.db:
            for n in range(1, 9):
                self.budget.db.execute("INSERT INTO search_budget_receipts VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (n, "rerank", "public-evaluation.v2", _hash(str(n)), 100, "0",
                     "uncertain" if n in {2, 4, 8} else "reported", "{}", None if n in {2, 4, 8} else "0", 1.))
            self.budget.db.executemany("INSERT INTO search_budget_meta VALUES (?,?)", [
                ("halted", "old_interrupted_request"), ("bounded_validation_v1_grant", '{"max_attempts":20}'),
                ("bounded_validation_v1_halt", '{"number":8,"code":"provider_http_429"}')])
        self.old_rows = self.budget.rows(); self.old_meta = self.budget.historical_meta()
        self.grant = {"version": "focus-validation-grant.v1", "authorization": self.auth.fingerprint,
            "baseline": 8, "max_attempts": 13, "issued": 99, "expires": 200,
            "rows_sha256": _hash(self.old_rows), "meta_sha256": _hash(self.old_meta),
            "plan_sha256": _hash("synthetic plan"), "requests": [runner.request_record(b) for b in self.bodies]}
        for target in ("socket.socket.connect", "requests.sessions.Session.request"):
            guard = patch(target, side_effect=AssertionError("Offline test: network forbidden"))
            guard.start(); self.addCleanup(guard.stop)

    def reserve(self, i=0, **overrides):
        args = dict(input_hash=self.grant["requests"][i]["input_hash"],
                    tokens=self.grant["requests"][i]["tokens"], reservation="0")
        args.update(overrides)
        return self.budget.reserve("rerank", "public-evaluation.v2", **args)

    def settle(self, n):
        value = {"id": "gen-synthetic", "model": RERANK.model, "provider": RERANK.provider_name,
                 "usage": {"total_tokens": 10, "cost": 0}}
        self.budget.capture(n, value); self.budget.settle(n, value, .1)

    def unchanged(self):
        self.assertEqual(self.budget.rows()[:8], self.old_rows)
        self.assertEqual(self.budget.historical_meta(), self.old_meta)

    def test_default_original_and_previous_budget_cannot_dispatch(self):
        with self.assertRaises(SemanticError): self.reserve()
        self.budget.activate(self.grant)
        from app.evaluation.search_validation_budget import ValidationBudget
        for cls in (SearchBudget, ValidationBudget):
            with self.subTest(cls=cls), context_close(cls(self.path, self.auth, clock=lambda: 100)) as original:
                with self.assertRaises(SemanticError):
                    original.reserve("rerank", "public-evaluation.v2", **self.grant["requests"][0], reservation="0")
        self.unchanged(); self.assertEqual(len(self.budget.rows()), 8)

    def test_exact_sequence_five_once_shared_count_and_restart(self):
        self.budget.activate(self.grant)
        for i in range(5):
            n = self.reserve(i); self.settle(n)
            self.assertEqual(n, 9 + i)
            self.budget.activate(self.grant)  # Idempotent activation cannot reset consumed inputs.
            with self.assertRaises(SemanticError): self.reserve(i)
        with self.assertRaises(SemanticError): self.reserve()
        self.assertEqual(len(self.budget.rows()), 13)
        self.assertEqual([r["number"] for r in self.budget.rows() if r["state"] == "uncertain"], [2, 4, 8])
        self.assertFalse(self.budget.summary()["total_cost_finalized"]); self.unchanged()

    def test_scope_stage_order_tokens_and_nonzero_reservation_rejected(self):
        self.budget.activate(self.grant)
        for purpose, scope in (("decision", "public-evaluation.v2"), ("query", "public-evaluation.v2"),
                               ("document", "public-evaluation.v2"), ("rerank", "persistent-test-library.v1")):
            with self.assertRaises(SemanticError):
                self.budget.reserve(purpose, scope, **self.grant["requests"][0], reservation="0")
        for overrides in ({"input_hash": self.old_rows[-1]["input_hash"]}, {"tokens": 1}, {"reservation": ".01"}):
            with self.assertRaises(SemanticError): self.reserve(**overrides)
        with self.assertRaises(SemanticError): self.reserve(1)
        self.assertEqual(len(self.budget.rows()), 8); self.unchanged()

    def test_grant_mutations_and_old_receipt_or_meta_changes_fail_closed(self):
        mutations = ({"max_attempts": 14}, {"expires": 99}, {"issued": True}, {"plan_sha256": "x"},
                     {"requests": self.grant["requests"][:4]},
                     {"requests": [self.grant["requests"][0]] * 5})
        for change in mutations:
            with self.assertRaises(SemanticError): self.budget.activate({**self.grant, **change})
        self.budget.activate(self.grant)
        with self.assertRaises(SemanticError): self.budget.activate({**self.grant, "plan_sha256": _hash("new")})
        with self.budget.db:
            self.budget.db.execute("UPDATE search_budget_meta SET value='changed' WHERE key='halted'")
        with self.assertRaises(SemanticError): self.reserve()
        with self.budget.db:
            self.budget.db.execute("UPDATE search_budget_meta SET value=? WHERE key='halted'", (self.old_meta["halted"],))
            self.budget.db.execute("UPDATE search_budget_receipts SET cost='0' WHERE number=2")
        with self.assertRaises(SemanticError): self.reserve()

    def test_pending_uncertain_not_sent_or_expired_never_retry(self):
        self.budget.activate(self.grant); n = self.reserve()
        with self.assertRaises(SemanticError): self.reserve(1)
        self.budget.fail(n, "provider_http_429", .3)
        for i in (0, 1):
            with self.assertRaises(SemanticError): self.reserve(i)
        self.budget.clock = lambda: 300
        with self.assertRaises(SemanticError): self.reserve(1)
        self.assertEqual(self.budget.summary()["focus_halted"], "provider_http_429"); self.unchanged()

    def test_evidence_after_expiry_and_historical_write_protection(self):
        self.budget.activate(self.grant); n = self.reserve(); self.budget.clock = lambda: 300
        self.settle(n)  # Save the already-dispatched response even after expiry.
        for operation in (lambda: self.budget.capture(8, {}), lambda: self.budget.settle(8, {}, .1),
                          lambda: self.budget.fail(8, "x", .1), lambda: self.budget.not_sent(8, "search_cancelled")):
            with self.assertRaises(SemanticError): operation()
        self.unchanged()

    def test_body_guard_rejects_other_endpoints_changes_and_candidate_order_before_key(self):
        self.budget.activate(self.grant)
        transport = Transport(); key = Mock(return_value="synthetic-test-key")
        scope = EgressScope("public-evaluation.v2", frozenset(_hash(t) for b in self.bodies for t in b["documents"]),
                            frozenset(_hash(b["query"]) for b in self.bodies), True)
        client = runner.FocusClient(self.budget, scope, key, cases=[{"body": b} for b in self.bodies], session=transport)
        self.addCleanup(client.close); client.preflight((RERANK,))
        options = dict(purpose="rerank", texts=self.bodies[0]["documents"],
                       query_texts=(self.bodies[0]["query"],), timeout=10, validate=lambda value: value)
        for endpoint, body in ((DECISION, self.bodies[0]), (EMBEDDING, self.bodies[0]),
                               (RERANK, {**self.bodies[0], "documents": list(reversed(self.bodies[0]["documents"]))}),
                               (RERANK, {**self.bodies[0], "query": "new focus"}),
                               (RERANK, {**self.bodies[0], "top_n": 1})):
            with self.assertRaises(SemanticError): client.request(endpoint, body, **options)
        key.assert_not_called(); self.assertEqual(transport.posts, []); self.assertEqual(len(self.budget.rows()), 8)
        self.assertEqual(RerankProvider(client).rank(self.bodies[0]["query"], self.bodies[0]["documents"]), [.9, .8])
        self.assertEqual(len(transport.posts), 1); self.unchanged()

    def test_cost_invalid_usage_invalid_scores_and_timeout_all_stop_once(self):
        # Each scenario gets its own synthetic ledger; no live source is opened.
        for failure in ("cost", "usage", "scores", "timeout", "429", "key"):
            with self.subTest(failure=failure):
                path = self.root / (failure + ".db")
                target = FocusBudget(path, self.auth, clock=lambda: 100)
                self.budget.db.backup(target.db)
                try:
                    target.activate(self.grant)
                    transport = Transport(); key = Mock(return_value="" if failure == "key" else "synthetic")
                    if failure == "timeout": transport.failure = requests.Timeout()
                    elif failure == "429":
                        from test_search_providers import Response
                        transport.post = Mock(return_value=Response({}, 429))
                    elif failure == "cost": transport.modify = lambda data: data["usage"].update(cost=1)
                    elif failure == "usage": transport.modify = lambda data: data.pop("usage")
                    elif failure == "scores": transport.modify = lambda data: data["results"][0].update(index=100)
                    scope = EgressScope("public-evaluation.v2", frozenset(_hash(t) for t in self.bodies[0]["documents"]),
                                        frozenset({_hash(self.bodies[0]["query"])}), True)
                    client = runner.FocusClient(target, scope, key, cases=[{"body": b} for b in self.bodies], session=transport)
                    client.preflight((RERANK,))
                    with self.assertRaises(SemanticError): RerankProvider(client).rank(self.bodies[0]["query"], self.bodies[0]["documents"])
                    self.assertIsNotNone(target.summary()["focus_halted"])
                    with self.assertRaises(SemanticError):
                        target.reserve("rerank", "public-evaluation.v2", **self.grant["requests"][1], reservation="0")
                    self.assertEqual(len(target.rows()), 9); self.assertEqual(target.rows()[:8], self.old_rows)
                    if failure in {"cost", "usage", "scores"}:
                        self.assertIn("gen-safe-request", target.rows()[-1]["evidence"])
                    client.close()
                finally:
                    target.close()

    def runner_fixture(self):
        fixture = integration.IntegratedSearchTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        rows = [{"id": f"SYN{i}", "question": f'films like "Public Film 1" about family obligations aspect {i}'} for i in range(5)]
        cases = runner.capture_cases(fixture.engine, fixture.store, rows)
        self.grant["requests"] = [{k: c[k] for k in ("input_hash", "tokens")} for c in cases]
        plan = {"configuration": {"cases": cases}, "grant": self.grant}
        (self.root / runner.DIRECTORY).mkdir()
        (self.root / "authorization.json").write_text(json.dumps(asdict(self.auth)), encoding="utf8")
        @contextmanager
        def context(_root):
            yield fixture.engine, fixture.store, fixture.embedding.spec, fixture.docs
        budget_factory = lambda path, auth: FocusBudget(path, auth, clock=lambda: 100)
        class SafeTransport(Transport):
            def post(self, *args, **kwargs):
                response = super().post(*args, **kwargs); response.headers = {}
                return response
        transport = SafeTransport(); key = Mock(return_value="synthetic-key")
        guards = [patch.object(runner, "verify_plan", return_value=rows),
                  patch.object(runner, "context", side_effect=context),
                  patch.object(runner, "FocusBudget", side_effect=budget_factory),
                  patch("app.services.openrouter_embeddings.http_session", return_value=transport),
                  patch("app.evaluation.openrouter_pilot.existing_credential", key),
                  patch("app.services.search_providers.SearchEmbeddingProvider",
                        return_value=SimpleNamespace(spec=fixture.embedding.spec))]
        for guard in guards:
            guard.start(); self.addCleanup(guard.stop)
        return plan, fixture, transport, key

    def test_runner_full_synthetic_transport_and_restart_never_repeats_completed_posts(self):
        plan, fixture, transport, key = self.runner_fixture()
        result = runner.execute(self.root, plan, None)
        self.assertEqual((result["new_posts"], result["total_attempts"]), (5, 13))
        self.assertEqual(len(transport.posts), 5); self.assertEqual(key.call_count, 5)
        self.assertTrue(all(url.endswith("/v1/rerank") for url, _ in transport.posts))
        self.assertTrue(all("systemone" not in url for url, _ in transport.gets))
        self.assertTrue(runner.execute(self.root, plan, None)["already_complete"])
        self.assertEqual(len(transport.posts), 5)
        fixture.decision.decide.assert_not_called(); self.assertEqual(fixture.embedding.calls, [])
        for i in range(1, 6):
            saved = json.loads((self.root / runner.DIRECTORY / f"case-{i}.json").read_text(encoding="utf8"))
            self.assertFalse(saved["independent_acceptance"])
            self.assertTrue((self.root / runner.DIRECTORY / f"response-{i+8}.json").is_file())
        self.unchanged()

    def test_runner_partial_stop_and_restart_do_not_construct_provider_or_read_key(self):
        plan, _, transport, key = self.runner_fixture()
        transport.failure = requests.Timeout()
        with self.assertRaises(SemanticError): runner.execute(self.root, plan, None)
        self.assertEqual(len(transport.posts), 1); self.assertEqual(key.call_count, 1)
        with patch.object(runner, "FocusClient") as provider:
            with self.assertRaises(SemanticError): runner.execute(self.root, plan, None)
            provider.assert_not_called()
        self.assertEqual(len(transport.posts), 1); self.assertEqual(key.call_count, 1); self.unchanged()

    def test_runner_missing_durable_output_cannot_resend_reported_response(self):
        plan, _, transport, key = self.runner_fixture()
        self.budget.activate(self.grant); n = self.reserve(); self.settle(n)
        with self.assertRaises(SemanticError): runner.execute(self.root, plan, None)
        self.assertEqual(transport.posts, []); key.assert_not_called(); self.unchanged()

    def test_runner_no_dispatch_does_not_misattribute_a_historical_receipt(self):
        plan, fixture, transport, key = self.runner_fixture()
        fixture.allowed.clear()
        with self.assertRaises(SemanticError): runner.execute(self.root, plan, None)
        saved = json.loads((self.root / runner.DIRECTORY / "case-1.json").read_text(encoding="utf8"))
        self.assertIsNone(saved["receipt"])
        self.assertEqual(transport.posts, []); key.assert_not_called(); self.unchanged()

    def offline_plan_fixture(self):
        fixture = integration.IntegratedSearchTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        rows = [{"id": f"SYN{i}", "question": f'films like "Public Film 1" about family obligations aspect {i}'} for i in range(5)]
        cases = runner.capture_cases(fixture.engine, fixture.store, rows)
        for name in runner.FILES:
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic public source", encoding="utf8")
        (self.root / "authorization.json").write_text(json.dumps(asdict(self.auth)), encoding="utf8")
        report = {"configuration": runner.source_configuration(), "new_requests": 0,
            "seen_regression_only": True, "independent_acceptance": False,
            "read_only_sources": {n: runner.digest(self.root / n) for n in runner.FILES[1:]},
            "results": [{"id": c["id"], "unverified": True, "events": [{"purpose": "rerank",
                "wire_body_sha256": c["input_hash"], "verified_recording": False, "new_requests": 0}]} for c in cases]}
        report["read_only_sources"]["shared-budget.sqlite3"] = runner.digest(self.path)
        source = self.root / "offline-report.json"
        source.write_text(json.dumps(report), encoding="utf8")
        @contextmanager
        def context(_root):
            yield fixture.engine, fixture.store, fixture.embedding.spec, fixture.docs
        for guard in (patch.object(runner, "context", side_effect=context),
                      patch.object(runner, "execution_questions", return_value=rows)):
            guard.start(); self.addCleanup(guard.stop)
        return source

    def test_offline_prepare_recomputes_exact_inputs_without_activating_or_changing_sources(self):
        source = self.offline_plan_fixture(); before = runner.digest(self.path)
        plan = runner.prepare(self.root, source)
        self.assertEqual(len(plan["configuration"]["cases"]), 5)
        self.assertEqual(plan["grant"]["max_attempts"], 13)
        self.assertEqual(runner.prepare(self.root, source), plan)
        self.assertEqual(runner.digest(self.path), before)
        self.assertIsNone(self.budget._value(PREFIX + "grant")); self.unchanged()

    def test_windows_report_keys_prepare_without_rewriting_sealed_report_or_ledger(self):
        source = self.offline_plan_fixture()
        report = json.loads(source.read_text(encoding="utf8"))
        report["read_only_sources"] = {k.replace("/", "\\"): v for k, v in report["read_only_sources"].items()}
        source.write_text(json.dumps(report), encoding="utf8")
        original_report, original_ledger = runner.digest(source), runner.digest(self.path)
        plan = runner.prepare(self.root, source)
        self.assertEqual([c["id"] for c in plan["configuration"]["cases"]], [f"SYN{i}" for i in range(5)])
        self.assertEqual(runner.verify_plan(self.root, plan)[-1]["id"], "SYN4")
        self.assertEqual(runner.digest(source), original_report)
        self.assertEqual(runner.digest(self.path), original_ledger)
        self.assertIsNone(self.budget._value(PREFIX + "grant")); self.unchanged()

    def test_source_key_normalization_is_comparison_only_and_rejects_unsafe_aliases(self):
        original = {"one/two.db": "a", "three\\four.db": "b", "five\\six/seven.db": "c"}
        expected = {"one/two.db": "a", "three/four.db": "b", "five/six/seven.db": "c"}
        saved = deepcopy(original)
        self.assertEqual(runner.source_hashes(original), expected)
        self.assertEqual(original, saved)
        invalid = ("", "/absolute.db", "\\absolute.db", "C:/file.db", "C:\\file.db", "C:file.db",
                   "//server/share/file.db", "\\\\server\\share\\file.db", "\\\\?\\C:\\file.db",
                   "../file.db", "..\\file.db", "one/../file.db", "one\\..\\file.db", "one/..\\file.db",
                   "./file.db", "one/./file.db", "one//file.db", "one\\\\file.db", "one/file.db:stream", "one/\0file.db")
        for key in invalid:
            with self.subTest(key=key), self.assertRaises(SemanticError): runner.source_hashes({key: "a"})
        with self.assertRaises(SemanticError): runner.source_hashes({"one/two.db": "a", "one\\two.db": "a"})
        for invalid_value in (None, [], {1: "a"}):
            with self.assertRaises(SemanticError): runner.source_hashes(invalid_value)

    def test_unsafe_or_colliding_report_keys_stop_before_cache_and_no_plan_is_written(self):
        source = self.offline_plan_fixture()
        original = json.loads(source.read_text(encoding="utf8"))
        for key in ("/absolute.db", "C:relative.db", "../file.db", "holdout\\public-library.sqlite3"):
            report = deepcopy(original); report["read_only_sources"][key] = "same"
            source.write_text(json.dumps(report), encoding="utf8")
            before = runner.digest(self.path)
            with patch.object(runner, "context") as cache:
                with self.assertRaises(SemanticError): runner.prepare(self.root, source)
                cache.assert_not_called()
            self.assertFalse((self.root / runner.DIRECTORY / "plan.json").exists())
            self.assertEqual(runner.digest(self.path), before)

    def test_plan_rejects_changed_scope_sources_code_and_new_input_even_if_rehashed(self):
        source = self.offline_plan_fixture(); plan = runner.prepare(self.root, source)
        changed = deepcopy(plan); changed["configuration"]["cases"][0]["body"]["query"] = "a different focus"
        changed["configuration"]["cases"][0].update(runner.request_record(changed["configuration"]["cases"][0]["body"]))
        changed["grant"]["plan_sha256"] = _hash(changed["configuration"])
        with self.assertRaises(SemanticError): runner.verify_plan(self.root, changed)
        changed = deepcopy(plan); changed["configuration"]["cases"].reverse()
        changed["grant"]["plan_sha256"] = _hash(changed["configuration"])
        with self.assertRaises(SemanticError): runner.verify_plan(self.root, changed)
        with patch.object(runner, "code_revision", return_value="changed"):
            with self.assertRaises(SemanticError): runner.verify_plan(self.root, plan)
        (self.root / runner.FILES[1]).write_text("changed", encoding="utf8")
        with self.assertRaises(SemanticError): runner.verify_plan(self.root, plan)
        self.unchanged()


@contextmanager
def context_close(value):
    try: yield value
    finally: value.close()


class FocusCaptureTests(unittest.TestCase):
    setUp = integration.IntegratedSearchTests.setUp

    def test_collect_five_reference_requests_without_decision_embedding_or_network(self):
        rows = [{"id": f"SYN{i}", "question": f'films like "Public Film 1" about family obligations aspect {i}'} for i in range(5)]
        with patch("socket.socket.connect", side_effect=AssertionError("No network")), \
             patch("requests.sessions.Session.request", side_effect=AssertionError("No HTTP")):
            cases = runner.capture_cases(self.engine, self.store, rows)
        self.assertEqual(len(cases), 5); self.assertEqual(len({c["input_hash"] for c in cases}), 5)
        self.assertTrue(all(self.docs[0].chunks[0] not in c["body"]["documents"] for c in cases))
        self.assertTrue(all(c["reference_id"] == self.docs[0].film_id for c in cases))
        self.decision.decide.assert_not_called(); self.assertEqual(self.embedding.calls, [])

    def test_wrong_extent_plain_reference_private_input_and_nonreference_are_rejected(self):
        for question in ('films like "Public Film 1"', 'films about family obligations',
                         'films like "Public Film 1", use Movies//private.mkv'):
            with self.subTest(question=question), self.assertRaises(SemanticError):
                runner.capture_cases(self.engine, self.store, [{"id": "SYN", "question": question}])
        for body in ({"query": "/private.mkv", "documents": ["safe"], "top_n": 1},
                     {"query": "focus", "documents": ["Movies//private.mkv"], "top_n": 1},
                     {"query": "focus", "documents": ["safe"], "top_n": True}):
            with self.assertRaises(SemanticError): runner.request_record(body)


if __name__ == "__main__":
    unittest.main()
