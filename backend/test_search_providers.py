"""Native search APIs and authorization accounting, using synthetic transport only."""
from copy import deepcopy
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock

import requests

from app.services.search_budget import SearchAuthorization, SearchBudget
from app.services.search_providers import (DECISION, EMBEDDING, RERANK, ENDPOINTS,
    DecisionProvider, EgressScope, EndpointQuote, RerankProvider, SearchEmbeddingProvider, SearchProviderClient)
from app.services.semantic_search import SemanticError, _hash


QUERY = "Films about reconnecting with a distant family"
DOCUMENTS = ("A daughter returns home and reconnects with her family.",
             "A crew repairs a remote spacecraft.")


def metadata(endpoint):
    return {"data": {"id": endpoint.model, "created": 1792021417, "endpoints": [{
        "provider_name": endpoint.provider_name, "tag": endpoint.provider, "status": 0,
        "context_length": endpoint.context, "pricing": {"prompt": endpoint.price_ceiling,
            "completion": "0", "discount": 0}}]}}


def zdr():
    return {"data": [{"model_id": e.model, "tag": e.provider} for e in ENDPOINTS]}


class Response:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def iter_content(self, _size):
        yield json.dumps(self.payload).encode()

    def close(self):
        pass


class Transport:
    def __init__(self):
        self.posts, self.gets, self.modify = [], [], None
        self.failure = None

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        assert "headers" not in kwargs and kwargs["allow_redirects"] is False
        if url.endswith("/endpoints/zdr"):
            return Response(zdr())
        return Response(metadata(next(e for e in ENDPOINTS if e.model in url)))

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if self.failure:
            raise self.failure
        endpoint = next(e for e in ENDPOINTS if url.endswith(e.api_path))
        body = kwargs["json"]
        data = {"id": "gen-safe-request-123", "model": endpoint.model, "provider": endpoint.provider_name,
                "usage": {"total_tokens": 100, "cost": 0}}
        if endpoint == DECISION:
            data["answers"] = {"route": {"type": "choice", "choice": "semantic", "confidence": .95,
                "probabilities": {"keyword": .01, "semantic": .95, "hybrid": .03, "clarify": .01}},
                "intent": {"type": "choice", "choice": "exploratory", "confidence": .9,
                           "probabilities": {"factual": .1, "exploratory": .9}}}
        elif endpoint == EMBEDDING:
            data["data"] = [{"index": i, "embedding": [1.] + [0.] * 4095} for i in range(len(body["input"]))]
        else:
            data["results"] = [{"index": i, "relevance_score": .9 - i * .1} for i in reversed(range(len(body["documents"])))]
        if self.modify:
            self.modify(data)
        return Response(data)

    def close(self):
        pass


class SearchProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "shared-budget.sqlite3"
        self.authorization = SearchAuthorization("test-approval-v1", 20, "0", 2000000000)
        self.ledger = SearchBudget(self.path, self.authorization, clock=lambda: 1800000000)
        self.addCleanup(self.ledger.close)
        self.scope = EgressScope("public-evaluation.v2", frozenset(_hash(d) for d in DOCUMENTS),
                                frozenset({_hash(QUERY)}), accept_logged_public=True)
        self.transport = Transport()
        self.key = Mock(return_value="synthetic-not-a-real-key")
        self.client = SearchProviderClient(self.ledger, self.scope, self.key, session=self.transport)
        self.client.preflight()

    def test_three_native_apis_have_pinned_routes_no_chat_or_fallback(self):
        self.assertEqual(DecisionProvider(self.client).decide(QUERY).route, "semantic")
        self.assertEqual(len(SearchEmbeddingProvider(self.client).embed(DOCUMENTS, query=False)), 2)
        self.assertEqual(RerankProvider(self.client).rank(QUERY, DOCUMENTS), [.9, .8])
        self.assertEqual(self.ledger.summary()["requests"], 3)
        for (url, options), endpoint in zip(self.transport.posts, ENDPOINTS):
            self.assertTrue(url.endswith(endpoint.api_path))
            self.assertFalse(options["allow_redirects"])
            self.assertEqual(options["json"]["model"], endpoint.model)
            self.assertEqual(options["json"]["provider"]["only"], [endpoint.provider])
            self.assertEqual(options["json"]["provider"]["data_collection"], "allow" if endpoint.logs_public_input else "deny")
            self.assertEqual(options["json"]["provider"]["zdr"], not endpoint.logs_public_input)
            self.assertIs(options["json"]["provider"]["allow_fallbacks"], False)
        self.assertNotIn("state", self.transport.posts[1][1]["json"])
        self.assertNotIn("messages", json.dumps([p[1]["json"] for p in self.transport.posts]))
        receipt_text = json.dumps(self.ledger.summary())
        self.assertNotIn(QUERY, receipt_text)
        self.assertNotIn(DOCUMENTS[0], receipt_text)
        self.assertNotIn("synthetic-not-a-real-key", receipt_text)

    def test_scope_and_paths_stop_before_credentials_reservation_and_transport(self):
        for text in ("Unapproved public text", "Movies//My Private Film.mkv", "~/private.mkv",
                     "`/private.mkv`", "Movies\\\\Private.mkv"):
            with self.subTest(text=text), self.assertRaises(SemanticError):
                SearchEmbeddingProvider(self.client).embed((text,), query=False)
        self.assertEqual(self.ledger.summary()["requests"], 0)
        self.assertEqual(self.transport.posts, [])
        self.key.assert_not_called()

    def test_metadata_preflight_has_no_key_lookup_and_rejects_inactive_price_or_missing_zdr(self):
        self.key.assert_not_called()
        for mutate, policies, code in (
            (lambda p: p["data"]["endpoints"][0].update(status=-2), zdr(), "search_endpoint_unavailable"),
            (lambda p: p["data"]["endpoints"][0]["pricing"].update(prompt="0.000000001"), zdr(), "search_price_changed"),
            (lambda p: p["data"]["endpoints"][0]["pricing"].update(prompt="1"), zdr(), "search_price_changed"),
            (lambda p: p["data"]["endpoints"][0]["pricing"].update(request="0.001"), zdr(), "search_pricing_unsupported"),
            (lambda p: None, {"data": []}, "search_privacy_unverified"),
        ):
            payload = metadata(DECISION)
            mutate(payload)
            with self.subTest(code=code), self.assertRaisesRegex(SemanticError, code):
                EndpointQuote.validate(DECISION, payload, policies)

    def test_missing_or_stale_preflight_prevents_dispatch(self):
        self.client.quotes.clear()
        with self.assertRaisesRegex(SemanticError, "search_preflight_required"):
            DecisionProvider(self.client).decide(QUERY)
        self.assertEqual(self.ledger.summary()["requests"], 0)

    def test_invalid_usage_preserves_reconciliation_id_and_halts_all_endpoints(self):
        self.transport.modify = lambda p: p.pop("usage")
        with self.assertRaisesRegex(SemanticError, "search_billing_uncertain"):
            DecisionProvider(self.client).decide(QUERY)
        first = self.ledger.summary()["receipts"][0]
        self.assertEqual(json.loads(first["evidence"])["id"], "gen-safe-request-123")
        self.assertEqual(first["state"], "uncertain")
        with self.assertRaisesRegex(SemanticError, "search_budget_blocked"):
            SearchEmbeddingProvider(self.client).embed(DOCUMENTS, query=False)
        self.assertEqual(len(self.transport.posts), 1)

    def test_observed_overcharge_survives_halt_with_conservative_upper_bound(self):
        self.transport.modify = lambda p: p["usage"].update(cost="2")
        with self.assertRaisesRegex(SemanticError, "search_cost_exceeds_reservation"):
            DecisionProvider(self.client).decide(QUERY)
        report = self.ledger.summary()
        self.assertEqual(report["total_cost_upper_bound_usd"], "2")
        self.assertEqual(json.loads(report["receipts"][0]["evidence"])["usage"]["cost"], "2")

    def test_unreported_cost_keeps_full_reservation_not_sample_quote_estimate(self):
        self.transport.modify = lambda p: p["usage"].pop("cost")
        with self.assertRaisesRegex(SemanticError, "search_billing_uncertain"):
            DecisionProvider(self.client).decide(QUERY)
        report = self.ledger.summary()
        self.assertEqual(report["unreported_upper_bound_usd"], report["receipts"][0]["reservation"])

    def test_timeout_is_not_retried_and_restart_preserves_pending_hold(self):
        self.transport.failure = requests.Timeout("NEVER_PRINT_BODY")
        with self.assertRaisesRegex(SemanticError, "search_provider_unavailable"):
            DecisionProvider(self.client).decide(QUERY)
        other = SearchBudget(self.path, self.authorization)
        self.addCleanup(other.close)
        with self.assertRaisesRegex(SemanticError, "search_budget_blocked"):
            other.reserve("query", "public-evaluation.v2", input_hash=_hash(QUERY), tokens=100, reservation="0")
        self.assertEqual(len(self.transport.posts), 1)
        self.assertNotIn("NEVER_PRINT_BODY", json.dumps(other.summary()))

    def test_reservation_is_shared_across_scopes_and_endpoints(self):
        self.ledger.reserve("query", "library-validation.v1", input_hash=_hash(QUERY), tokens=100, reservation="0")
        with self.assertRaisesRegex(SemanticError, "search_budget_blocked"):
            DecisionProvider(self.client).decide(QUERY)
        self.key.assert_not_called()
        self.assertEqual(self.transport.posts, [])

    def test_authorization_cannot_be_replaced_to_reset_spending(self):
        changed = SearchAuthorization("different-approval", 20, "1", 2000000000)
        with self.assertRaisesRegex(SemanticError, "search_authorization_changed"):
            SearchBudget(self.path, changed)

    def test_actual_database_cannot_be_opened_as_budget(self):
        path = Path(self.temp.name) / "canonical.db"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE film (id TEXT)")
        db.close()
        with self.assertRaisesRegex(SemanticError, "search_budget_not_owned"):
            SearchBudget(path, self.authorization)

    def test_native_rerank_rejects_duplicate_or_outside_candidates_and_nonfinite(self):
        base = {"results": [{"index": 0, "relevance_score": .8}, {"index": 1, "relevance_score": .2}]}
        for value in (True, -1, 2, 0):
            payload = deepcopy(base)
            payload["results"][1]["index"] = value
            with self.subTest(value=value), self.assertRaisesRegex(SemanticError, "search_rerank_invalid"):
                RerankProvider._parse(payload, 2)
        for value in (float("nan"), float("inf"), True, -1, 2):
            payload = deepcopy(base)
            payload["results"][0]["relevance_score"] = value
            with self.subTest(score=value), self.assertRaisesRegex(SemanticError, "search_rerank_invalid"):
                RerankProvider._parse(payload, 2)

    def test_invalid_provider_output_stops_next_request_even_with_valid_usage(self):
        self.transport.modify = lambda p: p["answers"]["route"].update(choice="run_sql")
        with self.assertRaisesRegex(SemanticError, "search_decision_invalid"):
            DecisionProvider(self.client).decide(QUERY)
        with self.assertRaisesRegex(SemanticError, "search_budget_blocked"):
            RerankProvider(self.client).rank(QUERY, DOCUMENTS)
        self.assertEqual(len(self.transport.posts), 1)

    def test_routing_mismatch_records_charge_then_stops(self):
        self.transport.modify = lambda p: p.update(provider="UnapprovedProvider")
        with self.assertRaisesRegex(SemanticError, "search_route_mismatch"):
            DecisionProvider(self.client).decide(QUERY)
        report = self.ledger.summary()
        self.assertIsNotNone(report["halted"])
        self.assertEqual(json.loads(report["receipts"][0]["evidence"])["provider"], "UnapprovedProvider")

    def test_native_decision_low_confidence_is_clarification_not_forced_route(self):
        self.transport.modify = lambda p: p["answers"]["route"].update(confidence=.59)
        self.assertEqual(DecisionProvider(self.client).decide(QUERY).route, "clarify")

    def test_uncertain_content_mode_uses_stricter_factual_admission(self):
        self.transport.modify = lambda p: p["answers"]["intent"].update(confidence=.2)
        result = DecisionProvider(self.client).decide(QUERY)
        self.assertEqual(result.route, "semantic")
        self.assertEqual(result.mode, "factual")

    def test_missing_key_is_known_not_sent_and_does_not_create_unknown_charge(self):
        self.key.return_value = None
        with self.assertRaisesRegex(SemanticError, "search_not_configured"):
            DecisionProvider(self.client).decide(QUERY)
        summary = self.ledger.summary()
        self.assertEqual(summary["requests"], 0)
        self.assertEqual(summary["attempts"], 1)
        self.assertIsNone(summary["halted"])
        self.assertEqual(summary["receipts"][0]["state"], "not_sent")
        self.assertEqual(self.transport.posts, [])

    def test_cancelled_owner_stops_before_key_reservation_and_transport(self):
        self.client.cancelled = lambda: True
        with self.assertRaisesRegex(SemanticError, "search_cancelled"):
            DecisionProvider(self.client).decide(QUERY)
        self.key.assert_not_called()
        self.assertEqual(self.ledger.summary()["attempts"], 0)

    def test_free_models_cannot_be_used_for_library_or_without_public_logging_consent(self):
        library = EgressScope("library-validation.v1", self.scope.document_hashes)
        denied = SearchProviderClient(self.ledger, library, self.key, session=self.transport)
        with self.assertRaisesRegex(SemanticError, "search_provider_evaluation_only"):
            denied.preflight()
        no_consent = EgressScope("public-evaluation.v2", self.scope.document_hashes, self.scope.query_hashes)
        denied = SearchProviderClient(self.ledger, no_consent, self.key, session=self.transport)
        with self.assertRaisesRegex(SemanticError, "search_public_logging_consent_required"):
            denied.preflight()
        self.assertEqual(self.transport.posts, [])
        self.key.assert_not_called()

    def test_any_nonzero_free_endpoint_charge_is_recorded_and_stops(self):
        self.transport.modify = lambda p: p["usage"].update(cost=.000000001)
        with self.assertRaisesRegex(SemanticError, "search_cost_exceeds_reservation"):
            DecisionProvider(self.client).decide(QUERY)
        self.assertEqual(self.ledger.summary()["total_cost_upper_bound_usd"], "1E-9")

    def test_published_dated_mammoth_alias_is_accepted_but_unknown_revision_is_not(self):
        self.transport.modify = lambda p: p.update(model="baseten/mammoth-1-20261021")
        self.assertEqual(DecisionProvider(self.client).decide(QUERY).route, "semantic")
        self.transport.modify = lambda p: p.update(model="baseten/mammoth-1-99999999")
        with self.assertRaisesRegex(SemanticError, "search_route_mismatch"):
            DecisionProvider(self.client).decide(QUERY)
        with self.assertRaisesRegex(SemanticError, "search_alias_acknowledgment_invalid"):
            self.ledger.acknowledge_published_alias()

    def test_alias_acknowledgment_retains_settled_receipts_and_cannot_clear_unknown_cost(self):
        number = self.ledger.reserve("decision", "public-evaluation.v2", input_hash=_hash(QUERY), tokens=100, reservation="0")
        payload = {"id": "gen-observed", "model": "baseten/mammoth-1-20261021", "provider": "BaseTen",
                   "usage": {"cost": 0, "total_tokens": 50}}
        self.ledger.capture(number, payload)
        self.ledger.fail(number, "search_route_mismatch", 1)
        with self.assertRaisesRegex(SemanticError, "search_alias_acknowledgment_invalid"):
            self.ledger.acknowledge_published_alias()
        with self.ledger.db:
            self.ledger.db.execute("UPDATE search_budget_receipts SET state='reported',cost='0' WHERE number=?", (number,))
        self.ledger.acknowledge_published_alias()
        self.assertEqual(self.ledger.summary()["requests"], 1)
        self.assertIsNone(self.ledger.summary()["halted"])


if __name__ == "__main__":
    unittest.main()
