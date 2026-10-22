"""No credentials or live network: synthetic transport/billing regressions."""
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import requests

from app.evaluation import openrouter_pilot as pilot
from app.services.openrouter_embeddings import (BudgetLedger, DIMENSIONS, MODEL, PROVIDER,
    ORIGIN, QUERY_PREFIX, NVIDIA_MODEL, NVIDIA_PROVIDER, NvidiaFreeQuote,
    OpenRouterPilotProvider, Quote, fetch_quote, free_quota_preflight)
from app.services.semantic_search import SemanticError


def metadata():
    return {"data": {"id": MODEL, "created": 1761609600, "endpoints": [{
        "provider_name": "DeepInfra", "tag": PROVIDER, "status": 0, "context_length": 32768,
        "pricing": {"prompt": "0.00000001", "completion": "0", "discount": 0}}]}}

def nvidia_metadata():
    return {"data": {"id": NVIDIA_MODEL, "created": 1792591666, "endpoints": [{
        "provider_name": "Nvidia", "tag": NVIDIA_PROVIDER, "status": 0, "context_length": 32768,
        "pricing": {"prompt": "0", "completion": "0", "discount": 0}}]}}


class Response:
    def __init__(self, payload, status=200):
        self.payload, self.status_code, self.closed = payload, status, False

    def iter_content(self, size):
        yield json.dumps(self.payload).encode()

    def close(self):
        self.closed = True


class Transport:
    def __init__(self, *, nvidia=False):
        self.calls, self.modify, self.fail = [], None, False
        self.nvidia = nvidia

    def get(self, url, **kwargs):
        assert kwargs["allow_redirects"] is False
        if url == ORIGIN + "/key":
            return Response({"data": {"free_model_daily_requests": {"remaining": 50}}})
        model = NVIDIA_MODEL if self.nvidia else MODEL
        assert url == f"{ORIGIN}/models/{model}/endpoints"
        return Response(nvidia_metadata() if self.nvidia else metadata())

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.fail:
            raise requests.Timeout("DO_NOT_EXPOSE_PROVIDER_BODY")
        rows = []
        for i, text in enumerate(kwargs["json"]["input"]):
            vector = [0.] * DIMENSIONS
            vector[0 if any(w in text.lower() for w in ("space", "宇宙", "太空")) else 1] = 1.
            rows.append({"index": i, "embedding": vector})
        payload = {"id": "gen-synthetic-123", "model": NVIDIA_MODEL if self.nvidia else MODEL,
                   "provider": "Nvidia" if self.nvidia else "DeepInfra",
                   "data": list(reversed(rows)),
                   "usage": {"prompt_tokens": 10, "total_tokens": 10, "cost": 0 if self.nvidia else 0.0000001}}
        if self.modify:
            self.modify(payload)
        return Response(payload)

    def close(self):
        pass


class OpenRouterPilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "run"
        self.quote = Quote.from_metadata(metadata())
        self.transport = Transport()
        self.ledger = BudgetLedger(self.root, self.quote)
        self.fixture = pilot.approved_fixture()
        self.provider = OpenRouterPilotProvider("synthetic-credential", self.quote, self.ledger,
            pilot.approved_inputs(self.fixture), session=self.transport)

    def test_exact_model_endpoint_and_quote_have_no_unbudgeted_price_component(self):
        self.assertEqual(fetch_quote(self.transport), self.quote)
        for mutate, code in [
            (lambda p: p["data"].update(id="other/model"), "invalid_model_quote"),
            (lambda p: p["data"]["endpoints"][0]["pricing"].update(prompt="0.0001"), "price_exceeds_plan"),
            (lambda p: p["data"]["endpoints"][0]["pricing"].update(request="0.001"), "unsupported_pricing"),
            (lambda p: p["data"]["endpoints"][0].update(context_length=True), "invalid_model_quote"),
        ]:
            with self.subTest(code=code):
                payload = metadata()
                mutate(payload)
                with self.assertRaisesRegex(SemanticError, code):
                    Quote.from_metadata(payload)

    def test_transport_has_only_embedding_fields_and_cached_modes_add_no_calls(self):
        text = self.fixture.cases[0].content_query
        first = self.provider.embed([text], query=True)
        self.assertEqual(self.provider.embed([text], query=True), first)
        self.assertEqual(len(self.transport.calls), 1)
        url, kwargs = self.transport.calls[0]
        self.assertEqual(url, ORIGIN + "/embeddings")
        self.assertFalse(kwargs["allow_redirects"])
        body = kwargs["json"]
        self.assertEqual(set(body), {"model", "input", "encoding_format", "provider"})
        self.assertEqual(body["input"], [QUERY_PREFIX + text])
        self.assertEqual(body["provider"]["only"], [PROVIDER])
        self.assertFalse(body["provider"]["allow_fallbacks"])
        self.assertTrue(body["provider"]["zdr"])
        self.assertEqual(self.ledger.summary()["requests"], 1)
        self.assertEqual(self.ledger.summary()["known_or_estimated_cost_usd"], "1E-7")
        self.assertNotIn("synthetic-credential", self.ledger.path.read_text())
        self.assertNotIn(text, self.ledger.path.read_text())

    def test_unapproved_private_or_tampered_fixture_input_never_dispatches(self):
        for text in ("/private.mkv", "Movies//Private Film.mkv", "Actual user notes", "find another film"):
            with self.subTest(text=text), self.assertRaisesRegex(SemanticError, "pilot_input_not_authorized"):
                self.provider.embed([text], query=True)
        with patch.object(pilot, "FIXTURE_SHA", "0" * 64), self.assertRaisesRegex(SemanticError, "fixture_not_authorized"):
            pilot.approved_fixture()
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.ledger.summary()["requests"], 0)

    def test_timeout_reservation_remains_uncertain_and_blocks_every_subsequent_call(self):
        self.transport.fail = True
        text = self.fixture.cases[0].content_query
        with self.assertRaisesRegex(SemanticError, "^provider_unavailable$"):
            self.provider.embed([text], query=True)
        self.assertEqual(self.ledger.summary()["entries"][0]["status"], "uncertain")
        self.assertFalse(self.ledger.summary()["cost_complete"])
        with self.assertRaisesRegex(SemanticError, "pilot_budget_blocked"):
            self.provider.embed([text], query=True)
        self.assertEqual(len(self.transport.calls), 1)
        with self.assertRaises(FileExistsError):
            BudgetLedger(self.root, self.quote)

    def test_missing_cost_has_explicit_locked_quote_estimate(self):
        self.transport.modify = lambda p: p["usage"].pop("cost")
        self.provider.embed([self.fixture.cases[0].content_query], query=True)
        summary = self.ledger.summary()
        self.assertTrue(summary["cost_complete"])
        self.assertFalse(summary["all_costs_reported"])
        self.assertEqual(summary["entries"][0]["status"], "estimated")
        self.assertIn("pinned endpoint quote", summary["entries"][0]["cost_basis"])
        self.assertEqual(summary["unknown_cost_upper_bound_usd"], "0.01")
        self.assertEqual(summary["total_cost_upper_bound_usd"], "0.01")

    def test_missing_cost_estimate_never_becomes_price_ceiling_upper_bound(self):
        for price in ("0.00000001", "0.00000004"):
            with self.subTest(quoted_price=price), tempfile.TemporaryDirectory() as root:
                data = metadata()
                data["data"]["endpoints"][0]["pricing"]["prompt"] = price
                quote = Quote.from_metadata(data)
                ledger = BudgetLedger(Path(root) / "run", quote)
                transport = Transport()
                transport.modify = lambda p: p["usage"].pop("cost")
                provider = OpenRouterPilotProvider("synthetic", quote, ledger,
                    pilot.approved_inputs(self.fixture), session=transport)
                provider.embed([self.fixture.cases[0].content_query], query=True)
                summary = ledger.summary()
                self.assertEqual(Decimal(summary["estimated_cost_usd"]), Decimal(price) * 10)
                self.assertEqual(summary["reported_cost_usd"], "0")
                self.assertEqual(summary["total_cost_upper_bound_usd"], "0.01")
                # The request can legally reach $.04/M even if preflight saw
                # $.01/M; its unreported cost keeps the full conservative hold.
                self.assertGreaterEqual(Decimal(summary["total_cost_upper_bound_usd"]),
                                        Decimal("0.00000004") * 10)
                self.assertFalse(summary["all_costs_reported"])

    def test_exact_upstream_model_identity_preserves_usage_and_model_receipt(self):
        self.transport.modify = lambda p: p.update(model="Qwen/Qwen3-Embedding-8B", id="embd-synthetic-123")
        self.provider.embed([self.fixture.cases[0].content_query], query=True)
        entry = self.ledger.data["entries"][0]
        self.assertEqual(entry["response_model"], "Qwen/Qwen3-Embedding-8B")
        self.assertEqual(entry["request_id"], "embd-synthetic-123")
        self.assertEqual(entry["status"], "reported")

    def test_dispatch_is_serial_and_an_excess_reported_charge_is_not_hidden(self):
        with ThreadPoolExecutor(2) as pool:
            values = list(pool.map(lambda _: self.provider.embed(
                [self.fixture.cases[0].content_query], query=True), range(2)))
        self.assertEqual(values[0], values[1])
        self.assertEqual(len(self.transport.calls), 1)
        self.transport.modify = lambda p: p["usage"].update(cost=2)
        with self.assertRaisesRegex(SemanticError, "cost_exceeds_reservation"):
            self.provider.embed([self.fixture.cases[1].content_query], query=True)
        self.assertTrue(self.ledger.summary()["halted"])
        self.assertEqual(self.ledger.summary()["known_or_estimated_cost_usd"], "2.0000001")

    def test_bad_response_billing_vectors_or_provider_halt_without_retry(self):
        for mutate in (
            lambda p: p["usage"].update(cost=2),
            lambda p: p["usage"].update(total_tokens=999999),
            lambda p: p["data"][0].update(index=True),
            lambda p: p["data"][0].update(embedding=[float("nan")] * DIMENSIONS),
            lambda p: p.update(provider="Other provider"),
            lambda p: p.update(model="other/model"),
        ):
            with self.subTest(mutate=mutate):
                with tempfile.TemporaryDirectory() as root:
                    transport = Transport()
                    transport.modify = mutate
                    ledger = BudgetLedger(Path(root) / "run", self.quote)
                    provider = OpenRouterPilotProvider("synthetic", self.quote, ledger,
                        pilot.approved_inputs(self.fixture), session=transport)
                    text = self.fixture.cases[0].content_query
                    with self.assertRaises(SemanticError):
                        provider.embed([text], query=True)
                    self.assertTrue(ledger.data["halted"])
                    with self.assertRaisesRegex(SemanticError, "pilot_budget_blocked"):
                        provider.embed([text], query=True)
                    self.assertEqual(len(transport.calls), 1)

    def test_reconciliation_id_is_atomic_before_missing_malformed_or_excess_usage(self):
        for mutate in (
            lambda p: p.pop("usage"),
            lambda p: p.update(usage=None),
            lambda p: p.update(usage=[]),
            lambda p: p.update(usage="malformed"),
            lambda p: p["usage"].update(cost="not-a-cost"),
            lambda p: p["usage"].update(cost=2),
            lambda p: p["usage"].pop("prompt_tokens"),
            lambda p: p["usage"].update(total_tokens=999999),
        ):
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as root:
                transport = Transport()
                transport.modify = mutate
                ledger = BudgetLedger(Path(root) / "run", self.quote)
                provider = OpenRouterPilotProvider("synthetic", self.quote, ledger,
                    pilot.approved_inputs(self.fixture), session=transport)
                settle = ledger.settle
                def check_before_billing(*args):
                    persisted = json.loads(ledger.path.read_text())["entries"][0]
                    self.assertEqual(persisted["status"], "pending")
                    self.assertEqual(persisted["request_id"], "gen-synthetic-123")
                    self.assertEqual(persisted["response_model"], MODEL)
                    self.assertEqual(persisted["response_provider"], "DeepInfra")
                    self.assertIn("response_received_utc", persisted)
                    self.assertIn("usage_shape", persisted)
                    if isinstance(args[1].get("usage"), dict):
                        self.assertIn("usage_evidence", persisted)
                    return settle(*args)
                text = self.fixture.cases[0].content_query
                with patch.object(ledger, "settle", side_effect=check_before_billing), \
                     self.assertRaises(SemanticError):
                    provider.embed([text], query=True)
                persisted = json.loads(ledger.path.read_text())
                self.assertTrue(persisted["halted"])
                self.assertEqual(persisted["entries"][0]["request_id"], "gen-synthetic-123")
                if persisted["entries"][0].get("error") == "cost_exceeds_reservation":
                    self.assertEqual(persisted["entries"][0]["cost_usd"], "2")
                with self.assertRaisesRegex(SemanticError, "pilot_budget_blocked"):
                    provider.embed([text], query=True)
                self.assertEqual(len(transport.calls), 1)

    def test_receipt_does_not_store_secret_like_identifier_or_model(self):
        self.transport.modify = lambda p: p.update(
            id="gen-sk-privatevalue123", model="sk-privatemodel123")
        with self.assertRaisesRegex(SemanticError, "invalid_provider_model"):
            self.provider.embed([self.fixture.cases[0].content_query], query=True)
        persisted = self.ledger.path.read_text()
        self.assertNotIn("sk-private", persisted)
        self.assertEqual(self.ledger.data["entries"][0]["cost_usd"], "1E-7")

    def test_request_count_token_text_and_durable_pending_limits_precede_dispatch(self):
        for _ in range(32):
            entry = self.ledger.reserve(["short"], False)
            self.ledger.settle(entry, {"usage": {"prompt_tokens": 1, "total_tokens": 1, "cost": 0}},
                               self.quote, 0)
        with self.assertRaisesRegex(SemanticError, "pilot_budget_blocked"):
            self.ledger.reserve(["short"], False)
        self.assertLess(Decimal(self.ledger.summary()["reserved_usd"]), Decimal("1"))
        self.assertEqual(self.transport.calls, [])
        with tempfile.TemporaryDirectory() as root:
            ledger = BudgetLedger(Path(root) / "run", self.quote)
            with self.assertRaisesRegex(SemanticError, "pilot_budget_blocked"):
                ledger.reserve(["a" * 20000], True)
            ledger.reserve(["short"], True)
            with self.assertRaisesRegex(SemanticError, "pilot_budget_blocked"):
                ledger.reserve(["short"], True)
        with tempfile.TemporaryDirectory() as root:
            ledger = BudgetLedger(Path(root) / "run", self.quote)
            for _ in range(16):
                entry = ledger.reserve(["a"] * 4, False)
                ledger.settle(entry, {"usage": {"prompt_tokens": 4, "total_tokens": 4, "cost": 0}},
                              self.quote, 0)
            with self.assertRaisesRegex(SemanticError, "pilot_budget_blocked"):
                ledger.reserve(["short"], True)

    def test_fixed_fixture_modes_are_mock_smoke_not_real_quality_or_router_acceptance(self):
        methods = pilot.evaluate_fixture(self.fixture, self.provider)
        self.assertEqual(set(methods), {"lexical", "dense", "hybrid"})
        self.assertLessEqual(len(self.transport.calls), 30)
        for method in methods.values():
            self.assertEqual(method["cases"], 24)
            self.assertEqual(method["hard_condition_violations"], 0)
            self.assertIn("warm local", method["latency_scope"])
        raw = json.dumps([call[1]["json"] for call in self.transport.calls], ensure_ascii=False)
        for title in (film.title for film in self.fixture.films):
            self.assertNotIn(title, raw)
        self.assertNotIn('"watched"', raw)

    def test_default_preflight_does_not_load_any_credentials_or_infer(self):
        with patch.object(pilot, "http_session", return_value=self.transport), \
             patch.object(pilot, "existing_credential") as credential:
            report = pilot.run()
        credential.assert_not_called()
        self.assertEqual(report["status"], "preflight_only_no_inference")
        self.assertFalse(report["real_model"])
        self.assertEqual(self.transport.calls, [])

    def test_existing_secret_source_is_ephemeral_and_no_new_credentials_are_created(self):
        source = Path(self.temp.name) / ".env"
        source.write_text("OPENROUTER_API_KEY=synthetic-existing\n", encoding="utf-8")
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            self.assertEqual(pilot.existing_credential(source), "synthetic-existing")
            self.assertEqual(os.environ["OPENROUTER_API_KEY"], "")
            with self.assertRaisesRegex(SemanticError, "credential_unavailable"):
                pilot.existing_credential(Path(self.temp.name) / "missing.env")

    def test_existing_attempt_blocks_reexecution_before_credentials_or_network(self):
        with patch.object(pilot, "RUN_ROOT", self.root), \
             patch.object(pilot, "http_session", return_value=self.transport), \
             patch.object(pilot, "fetch_quote") as quote, \
             patch.object(pilot, "existing_credential") as credential:
            report = pilot.run(execute=True)
        self.assertEqual(report["error"], "existing_run_requires_reconciliation")
        quote.assert_not_called()
        credential.assert_not_called()
        self.assertEqual(self.transport.calls, [])

    def test_importing_provider_does_not_load_application_database_or_invoke_transport(self):
        result = subprocess.run([sys.executable, "-c",
            "import sys; import app.evaluation.openrouter_pilot; "
            "assert 'app.database' not in sys.modules; assert 'app.services.historian' not in sys.modules"],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


class NvidiaFreePilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.quote = NvidiaFreeQuote.from_metadata(nvidia_metadata())
        self.ledger = BudgetLedger(Path(self.temp.name) / "free", self.quote)
        self.transport = Transport(nvidia=True)
        self.fixture = pilot.approved_fixture()
        self.provider = OpenRouterPilotProvider("synthetic", self.quote, self.ledger,
            pilot.approved_inputs(self.fixture), session=self.transport, accept_nvidia_logging=True)

    def test_exact_zero_price_only_with_no_paid_endpoint_substitution(self):
        self.assertEqual(fetch_quote(self.transport, nvidia_free=True), self.quote)
        for component in ("prompt", "completion", "request"):
            with self.subTest(component=component):
                data = nvidia_metadata()
                data["data"]["endpoints"][0]["pricing"][component] = "0.00000001"
                with self.assertRaises(SemanticError):
                    NvidiaFreeQuote.from_metadata(data)
        wrong = nvidia_metadata()
        wrong["data"]["endpoints"][0]["tag"] = "nvidia/paid"
        with self.assertRaisesRegex(SemanticError, "invalid_model_quote"):
            NvidiaFreeQuote.from_metadata(wrong)

    def test_logging_consent_is_required_and_does_not_change_paid_profile_privacy(self):
        with self.assertRaisesRegex(SemanticError, "nvidia_logging_confirmation_required"):
            OpenRouterPilotProvider("synthetic", self.quote, self.ledger,
                pilot.approved_inputs(self.fixture), session=self.transport)
        with patch.object(pilot, "NVIDIA_RUN_ROOT", Path(self.temp.name) / "absent"), \
             patch.object(pilot, "http_session", return_value=self.transport), \
             patch.object(pilot, "fetch_quote") as quote, \
             patch.object(pilot, "existing_credential") as credential:
            report = pilot.run(execute=True, nvidia_free=True)
        self.assertEqual(report["error"], "nvidia_logging_confirmation_required")
        quote.assert_not_called()
        credential.assert_not_called()
        self.assertEqual(self.transport.calls, [])

    def test_query_passage_modes_no_qwen_prefix_and_zero_price_routing(self):
        # Observed OpenRouter response uses the base slug without :free.
        self.transport.modify = lambda p: p.update(model="nvidia/nemotron-3.5-embed-8b")
        with patch("app.services.openrouter_embeddings.sleep") as pacing:
            self.provider.embed([self.fixture.films[0].overview], query=False)
            self.provider.embed([self.fixture.cases[0].content_query], query=True)
        self.assertTrue(pacing.called)
        for index, expected in enumerate(("passage", "query")):
            body = self.transport.calls[index][1]["json"]
            self.assertEqual(body["input_type"], expected)
            self.assertEqual(body["model"], NVIDIA_MODEL)
            self.assertFalse(body["input"][0].startswith("Instruct:"))
            self.assertEqual(body["provider"]["only"], [NVIDIA_PROVIDER])
            self.assertFalse(body["provider"]["allow_fallbacks"])
            self.assertEqual(body["provider"]["data_collection"], "allow")
            self.assertFalse(body["provider"]["zdr"])
            self.assertEqual(set(body["provider"]["max_price"].values()), {0})
        self.assertEqual(self.ledger.summary()["reported_cost_usd"], "0")
        self.assertEqual(self.ledger.summary()["total_cost_upper_bound_usd"], "0")
        receipt = json.loads(self.ledger.path.read_text())["entries"][0]
        self.assertEqual(receipt["response_model"], "nvidia/nemotron-3.5-embed-8b")
        self.assertEqual(receipt["usage_evidence"]["cost"], 0)

    def test_even_one_nonzero_charge_halts_and_is_retained(self):
        self.transport.modify = lambda p: p["usage"].update(cost=0.0000001)
        with self.assertRaisesRegex(SemanticError, "cost_exceeds_reservation"):
            self.provider.embed([self.fixture.cases[0].content_query], query=True)
        self.assertEqual(self.ledger.summary()["reported_cost_usd"], "1E-7")
        self.assertEqual(self.ledger.data["entries"][0]["request_id"], "gen-synthetic-123")
        with self.assertRaisesRegex(SemanticError, "pilot_budget_blocked"):
            self.provider.embed([self.fixture.cases[1].content_query], query=True)
        self.assertEqual(len(self.transport.calls), 1)

    def test_quota_preflight_is_read_only_and_low_quota_stops(self):
        self.assertEqual(free_quota_preflight(self.transport, "synthetic")["remaining"], 50)
        with patch.object(self.transport, "get", return_value=Response(
                {"data": {"free_model_daily_requests": {"remaining": 1}}})):
            with self.assertRaisesRegex(SemanticError, "insufficient_free_quota"):
                free_quota_preflight(self.transport, "synthetic")
        self.assertEqual(self.transport.calls, [])

    def test_related_qwen_receipt_is_read_only_and_required_for_new_authorization(self):
        parent = Path(self.temp.name) / "old"
        old = BudgetLedger(parent, Quote.from_metadata(metadata()))
        entry = old.reserve(["synthetic"], False)
        old.halt(entry, "invalid_provider_model", 0)
        before = old.path.read_bytes()
        with patch.object(pilot, "RUN_ROOT", parent):
            related = pilot.related_qwen_run()
        self.assertEqual(old.path.read_bytes(), before)
        self.assertEqual(related["reservation_usd"], "0.01")
        self.assertIsNone(related["actual_cost_usd"])
        self.assertFalse(related["retried"])

    def test_new_model_uses_distinct_vector_fingerprint_and_mock_retrieval_only(self):
        paid_quote = Quote.from_metadata(metadata())
        paid_ledger = BudgetLedger(Path(self.temp.name) / "paid", paid_quote)
        paid = OpenRouterPilotProvider("synthetic", paid_quote, paid_ledger,
            pilot.approved_inputs(self.fixture), session=Transport())
        self.assertNotEqual(paid.spec.fingerprint, self.provider.spec.fingerprint)
        with patch("app.services.openrouter_embeddings.sleep"):
            methods = pilot.evaluate_fixture(self.fixture, self.provider)
        self.assertLessEqual(len(self.transport.calls), 30)
        self.assertTrue(all(m["hard_condition_violations"] == 0 for m in methods.values()))
        self.assertEqual(self.ledger.summary()["known_or_estimated_cost_usd"], "0")
        self.assertEqual(self.ledger.data["entries"][0]["response_model"], NVIDIA_MODEL)

    def test_free_ledger_cannot_authorize_a_paid_profile(self):
        with self.assertRaisesRegex(SemanticError, "budget_profile_mismatch"):
            OpenRouterPilotProvider("synthetic", Quote.from_metadata(metadata()), self.ledger,
                pilot.approved_inputs(self.fixture), session=Transport())
        self.assertEqual(self.transport.calls, [])
