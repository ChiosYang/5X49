"""Opt-in Explore wiring on isolated SQL fixtures. No real keys or network."""
from copy import deepcopy
from contextlib import closing
from hashlib import sha256
import asyncio
import json
import os
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

import test_explore_query as fixture
from app.api.explore import router, _cancellable_search
from app.canonical_models import Film, ExploreFilmReadModel
from app.contracts.discovery_search import DiscoveryIndexAction, DiscoveryQuery, DiscoveryQuestion
from app.contracts.bound_search_plan import SearchPlan
from app.services.search_index import SearchIndexStore, encode_document
from app.services.search_providers import DECISION, EMBEDDING, RERANK, RouteDecision
from app.services.search_runtime import EvaluationRuntime, configured_evaluation
from app.services.semantic_search import ContentDocument, ContentSource, SemanticError, _hash, corpus_revision


QUESTION = "films about a family reunion"


class RuntimeTests(unittest.TestCase):
    _seed_library = fixture.ExploreQueryTests._seed_library
    _seed_facts = fixture.ExploreQueryTests._seed_facts
    _add_credit = staticmethod(fixture.ExploreQueryTests._add_credit)
    _add_genre = staticmethod(fixture.ExploreQueryTests._add_genre)
    _add_country = staticmethod(fixture.ExploreQueryTests._add_country)
    tearDown = fixture.ExploreQueryTests.tearDown

    def setUp(self):
        fixture.ExploreQueryTests.setUp(self)
        self.factory = Mock(side_effect=AssertionError("Unexpected real provider construction"))
        with Session(self.engine) as session:
            row = session.get(Film, self.films["Alpha"])
            row.overview = "A public fixture about a family reunion."
            session.add(row)
            session.commit()
            title, overview = row.canonical_title, row.overview
        self.document = ContentDocument(self.films["Alpha"], title, (),
            (ContentSource("overview", overview, "rule"),))
        self.manifest = {"version": "search-evaluation-runtime.v1", "internal_evaluation_only": True,
            "scope": "persistent-test-library.v1", "nvidia_public_logging_accepted": True,
            "models": [e.model for e in (DECISION, EMBEDDING, RERANK)],
            "documents": [json.loads(encode_document(self.document))], "revision": corpus_revision((self.document,)),
            "query_hashes": [_hash("a family reunion")],
            "index_path": str(self.root / "content-index.db"), "ledger_path": str(self.root / "receipts.db"),
            "authorization": {"identifier": "synthetic-runtime-grant", "max_posts": 10,
                "limit_usd": "0", "expires": 2000000000},
            "provenance": {"version": "reviewed-public-fields.v1", "reviewed": True,
                "films": {self.document.film_id: {"fields": {
                    key: {"sha256": sha256(value.encode()).hexdigest(),
                          "source": "https://www.themoviedb.org/movie/synthetic-fixture"}
                    for key, value in (("canonical_title", title), ("overview", overview))}}}}}

    def runtime(self, manifest=None):
        return EvaluationRuntime(manifest or self.manifest, self.engine, provider_factory=self.factory)

    def prepare(self, runtime):
        vector = [1.] + [0.] * 4095
        with closing(sqlite3.connect(runtime.index_path)) as connection:
            store = SearchIndexStore(connection)
            store.remember_vector(self.document.chunks[0], vector, runtime.spec, query=False)
            state = store.begin((self.document,), runtime.spec)
            embedding = SimpleNamespace(spec=runtime.spec, embed=Mock(side_effect=AssertionError("No new encoding")))
            self.assertEqual(store.step(state["id"], embedding)["state"], "complete")
        return vector

    def test_disabled_runtime_has_no_key_lookup_or_file_access(self):
        with patch.dict(os.environ, {"SEARCH_INTERNAL_EVALUATION": "0"}), patch(
                "app.services.search_runtime.Path.read_text", side_effect=AssertionError("No config read")):
            self.assertIsNone(configured_evaluation(self.engine))
        self.factory.assert_not_called()

    def test_public_provenance_is_required_before_provider_or_index_creation(self):
        for change in (lambda m: m.pop("provenance"),
                       lambda m: m["provenance"].update(reviewed=False),
                       lambda m: m["provenance"]["films"][self.document.film_id]["fields"].update(notes={}),
                       lambda m: m.update(index_path=str(self.database_path))):
            manifest = deepcopy(self.manifest)
            change(manifest)
            with self.assertRaises(SemanticError):
                self.runtime(manifest)
        self.assertFalse((self.root / "content-index.db").exists())
        self.factory.assert_not_called()

    def test_whitelisted_scalar_change_invalidates_index_without_egress(self):
        runtime = self.runtime()
        self.prepare(runtime)
        with Session(self.engine) as session:
            film = session.get(Film, self.document.film_id)
            film.overview = "A newly edited value not approved for transmission."
            session.add(film)
            session.commit()
        with self.assertRaisesRegex(SemanticError, "search_source_changed"):
            runtime.current_revision()
        self.factory.assert_not_called()

    def test_exact_and_complete_local_filters_never_open_index_or_provider(self):
        runtime = self.runtime()
        self.assertEqual(runtime.interpret(DiscoveryQuestion(question="Alpha", allow_ai=True))["status"], "keyword")
        result = runtime.interpret(DiscoveryQuestion(question="Japanese films", allow_ai=True))
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["results"]["total"], 2)
        self.assertFalse(runtime.index_path.exists())
        self.factory.assert_not_called()

    def test_cached_results_mutation_pagination_and_api_restore_make_zero_calls(self):
        runtime = self.runtime()
        vector = self.prepare(runtime)
        with runtime.search() as search:
            search.decision = SimpleNamespace(decide=lambda _: RouteDecision("hybrid", .99, "exploratory"))
            search.embedding = SimpleNamespace(embed=lambda *_a, **_k: [vector])
            search.reranker = SimpleNamespace(rank=lambda _q, docs: [.95] * len(docs))
            result = search.submit(QUESTION)
        self.assertEqual(result["results"]["total"], 1)
        plan = SearchPlan.model_validate(result["plan"])
        restored = runtime.query(DiscoveryQuery(question=QUESTION, plan=plan, semantic_snapshot=result["snapshot"], offset=40))
        self.assertEqual(restored["results"]["offset"], 0)
        with Session(self.engine) as session:
            row = session.get(ExploreFilmReadModel, self.document.film_id)
            row.watched = True
            session.add(row)
            session.commit()
        plan.view = "unwatched"
        restored = runtime.query(DiscoveryQuery(question=QUESTION, plan=plan, edited=True,
            semantic_snapshot=result["snapshot"], offset=40))
        self.assertEqual(restored["results"]["total"], 0)
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client, patch("app.api.explore._evaluation", return_value=runtime):
            response = client.post("/explore/search/query", json={"question": QUESTION, "plan": plan.model_dump(),
                "edited": True, "semantic_snapshot": result["snapshot"]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["results"]["total"], 0)
        self.factory.assert_not_called()

    def test_index_actions_are_explicit_and_bounded_without_implicit_dispatch(self):
        runtime = self.runtime()
        job = runtime.index(DiscoveryIndexAction(action="begin"))
        self.assertEqual(job["state"], "pending")
        status = runtime.index(DiscoveryIndexAction(action="status", job_id=job["id"]))
        self.assertEqual(status["remaining_chunks"], 1)
        self.assertEqual(runtime.index(DiscoveryIndexAction(action="cancel", job_id=job["id"]))["state"], "cancelled")
        self.assertEqual(runtime.index(DiscoveryIndexAction(action="resume", job_id=job["id"]))["state"], "pending")
        self.factory.assert_not_called()

    def test_explicit_content_removal_uses_bound_snapshot_and_current_strict_sql(self):
        runtime = self.runtime()
        vector = self.prepare(runtime)
        for question in ("Japanese films about a family reunion", "日本电影，关于家庭团聚"):
            with runtime.search() as search:
                search.decision = SimpleNamespace(decide=lambda _: RouteDecision("hybrid", .99, "exploratory"))
                search.embedding = SimpleNamespace(embed=lambda *_a, **_k: [vector])
                search.reranker = SimpleNamespace(rank=lambda _q, docs: [.95] * len(docs))
                result = search.submit(question)
            self.assertEqual(result["status"], "ready", result)
            plan = SearchPlan.model_validate(result["plan"])
            self.assertEqual(plan.countries, ["JP"])
            request = DiscoveryQuery(question=question, plan=plan, edited=True,
                semantic_snapshot=result["snapshot"], semantic_removed=True)
            restored = runtime.query(request)
            self.assertEqual(restored["status"], "ready")
            self.assertNotIn("semantic", restored)
            expected = runtime.local.executor.query(plan)
            self.assertEqual(restored["results"], expected["results"])
            self.assertEqual(restored["results"]["total"], 2)  # More than the one indexed match.
            plan.view = "unwatched"
            plan.sort = "year"
            plan.direction = "desc"
            request.plan = plan
            self.assertEqual(runtime.query(request)["results"], runtime.local.executor.query(plan)["results"])
            self.assertGreater(runtime.query(request)["results"]["total"], 0)
            # Original URL can still restore the semantic result after Back.
            self.assertIn("semantic", runtime.query(request.model_copy(update={"semantic_removed": False})))
            for change in ({"question": "a different question"}, {"semantic_snapshot": "ds_" + "f" * 32}):
                with self.assertRaises(SemanticError):
                    runtime.query(request.model_copy(update=change))
            unknown = plan.model_copy(update={"film_ids": ["film_" + "f" * 32]})
            invalid = runtime.query(request.model_copy(update={"plan": unknown}))
            self.assertEqual(invalid["status"], "needs_clarification")
            self.assertIsNone(invalid["results"])
            for change in ({"semantic_snapshot": None}, {"edited": False}, {"semantic_removed": "true"}):
                with self.assertRaises(ValueError):
                    DiscoveryQuery.model_validate({**request.model_dump(), **change})
            app = FastAPI()
            app.include_router(router)
            with TestClient(app) as client, patch("app.api.explore._evaluation", return_value=runtime):
                response = client.post("/explore/search/query", json=request.model_dump())
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["results"], runtime.local.executor.query(plan)["results"])
        self.factory.assert_not_called()

    def test_disabled_api_never_falls_back_to_chat_for_snapshot_or_evaluation_selection(self):
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client, patch("app.api.explore._evaluation", return_value=None), patch(
                "app.api.explore.discovery_search_service.interpret", side_effect=AssertionError("No legacy chat")):
            response = client.post("/explore/search/interpret", json={"question": QUESTION,
                "allow_ai": True, "evaluation_only": True})
            self.assertEqual(response.json()["reason"], "search_evaluation_disabled")
            response = client.post("/explore/search/query", json={"question": QUESTION,
                "plan": SearchPlan(version="search-plan.v2").model_dump(), "semantic_snapshot": "ds_" + "a" * 32})
            self.assertEqual(response.json()["reason"], "search_evaluation_disabled")
            response = client.post("/explore/search/index", json={"action": "begin"})
            self.assertEqual(response.status_code, 503)


class CancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_signals_worker_and_prevents_followup_work(self):
        observed = []
        def interpret(_request, *, cancelled):
            import time
            for _ in range(100):
                if cancelled():
                    observed.append("cancelled")
                    return {"status": "unavailable", "reason": "search_cancelled"}
                time.sleep(.01)
            raise AssertionError("Cancellation was not delivered")
        async def disconnected():
            return True
        result = await _cancellable_search(SimpleNamespace(is_disconnected=disconnected),
            SimpleNamespace(interpret=interpret), DiscoveryQuestion(question=QUESTION))
        self.assertEqual(result["reason"], "search_cancelled")
        self.assertEqual(observed, ["cancelled"])


if __name__ == "__main__":
    unittest.main()
