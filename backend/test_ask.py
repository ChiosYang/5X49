import hashlib
import json
import os
import unittest
from threading import BoundedSemaphore
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from openai import APITimeoutError
from sqlmodel import Session, select

import test_explore_query as fixture
import app.services.ask as ask_module
from app.api.ask import router
from app.canonical_models import Person, ProjectionState
from app.contracts.ask import AskInterpretation, AskPlan, AskQuestion, AskQueryRequest, AskResolveRequest
from app.services.ask import AskError, AskInterpreter, AskService
from app.services.projections import ProjectionUnavailable


class AskTests(unittest.TestCase):
    _seed_library = fixture.ExploreQueryTests._seed_library
    _seed_facts = fixture.ExploreQueryTests._seed_facts
    _add_credit = staticmethod(fixture.ExploreQueryTests._add_credit)
    _add_genre = staticmethod(fixture.ExploreQueryTests._add_genre)
    _add_country = staticmethod(fixture.ExploreQueryTests._add_country)

    def setUp(self):
        fixture.ExploreQueryTests.setUp(self)
        self.engine_patch = patch.object(ask_module, "engine", self.engine)
        self.engine_patch.start()
        self.addCleanup(self.engine_patch.stop)
        self.service = AskService()
        app = FastAPI()
        app.include_router(router)
        app.add_exception_handler(ProjectionUnavailable, lambda request, exc: JSONResponse(
            status_code=503, content={"detail": {"code": exc.code}}))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    tearDown = fixture.ExploreQueryTests.tearDown

    def query(self, **values):
        return self.service.query(AskQueryRequest(plan=AskPlan(**values), confirmed=True))

    def test_local_form_combines_country_decade_and_unwatched_strictly(self):
        result = self.query(country="日本", decade=1990, view="unwatched", genre="动作")
        self.assertEqual(result["status"], "ready")
        self.assertEqual([item["film"]["id"] for item in result["results"]["items"]], [self.films["Alpha"]])
        self.assertEqual({item["dimension"] for item in result["results"]["items"][0]["matched_facts"]}, {"genre", "country", "decade"})

    def test_roles_are_enforced_before_counting_and_pagination(self):
        director = self.query(person="Shared Person", person_role="director")
        actor = self.query(person="Shared Person", person_role="actor")
        self.assertEqual(director["results"]["total"], 1)
        self.assertEqual(actor["results"]["total"], 1)
        self.assertEqual(director["results"]["items"][0]["film"]["id"], self.films["Alpha"])
        self.assertEqual(actor["results"]["items"][0]["film"]["id"], self.films["Beta"])
        empty = self.service.query(AskQueryRequest(plan=AskPlan(person="Shared Person", person_role="director"), confirmed=True, offset=1))
        self.assertEqual(empty["results"]["total"], 1)
        self.assertEqual(empty["results"]["items"], [])

    def test_ambiguous_and_fuzzy_names_require_explicit_choice(self):
        fuzzy = self.service.resolve(AskResolveRequest(plan=AskPlan(person="Shared")))
        self.assertEqual(fuzzy["status"], "needs_clarification")
        self.assertEqual(fuzzy["issues"][0]["code"], "choose_person")
        with Session(self.engine) as session:
            other = session.get(Person, self.people["other"])
            other.canonical_name = "Shared Person"
            other.normalized_name = "shared person"
            session.add(other)
            session.commit()
        ambiguous = self.query(person="Shared Person")
        self.assertIsNone(ambiguous["results"])
        self.assertEqual(len(ambiguous["issues"][0]["candidates"]), 2)
        selected = self.service.query(AskQueryRequest(plan=AskPlan(person="Shared Person", person_role="actor"),
                                                    person_id=self.people["shared"], confirmed=True))
        self.assertEqual([row["film"]["id"] for row in selected["results"]["items"]], [self.films["Beta"]])

    def test_unknown_conditions_and_forged_choices_never_broaden_query(self):
        for values in ({"genre": "invented-genre"}, {"country": "Atlantis"}, {"person": "Nobody"}):
            with self.subTest(values=values):
                result = self.query(**values)
                self.assertEqual(result["status"], "needs_clarification")
                self.assertIsNone(result["results"])
        result = self.service.query(AskQueryRequest(plan=AskPlan(person="Shared Person"),
                                                   person_id=self.people["other"], confirmed=True))
        self.assertIsNone(result["results"])
        self.assertEqual(self.query(country="DE")["results"]["total"], 0)

    def test_sort_offset_and_empty_combination_are_exact(self):
        request = AskQueryRequest(plan=AskPlan(country="JP", sort="year", direction="desc"), confirmed=True, offset=1)
        result = self.service.query(request)["results"]
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["items"][0]["film"]["id"], self.films["Alpha"])
        self.assertIsNone(result["next_offset"])
        self.assertEqual(self.query(person="Shared Person", person_role="director", view="watched")["results"]["total"], 0)

    def test_resolving_and_querying_are_read_only_and_do_not_call_model(self):
        before = hashlib.sha256(self.database_path.read_bytes()).hexdigest()
        with patch.object(self.service.interpreter, "interpret", side_effect=AssertionError("unexpected model call")):
            self.service.resolve(AskResolveRequest(plan=AskPlan(person="Shared Person")))
            self.query(person="Shared Person", country="JP")
        self.assertEqual(hashlib.sha256(self.database_path.read_bytes()).hexdigest(), before)
        serialized = json.dumps(self.service.resolve(AskResolveRequest(plan=AskPlan(person="Shared"))))
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("notes", serialized)
        self.assertNotIn("source_ref", serialized)

    def test_no_key_status_and_interpretation_leave_local_form_usable(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            self.assertFalse(self.client.get("/ask/status").json()["configured"])
            response = self.client.post("/ask/interpret", json={"provider_consent": True, "question": "find unwatched films"})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["detail"]["code"], "ask_not_configured")
            self.assertEqual(self.client.post("/ask/resolve", json={"plan": {"country": "JP"}}).status_code, 200)
            result = self.client.post("/ask/query", json={"plan": {"country": "JP"}, "confirmed": True})
            self.assertEqual(result.json()["results"]["total"], 2)

    def test_contract_rejects_unsupported_fields_and_unconfirmed_queries(self):
        for payload in ({"plan": {}, "confirmed": False}, {"plan": {}, "confirmed": 1}, {"plan": {"sql": "DELETE FROM film"}, "confirmed": True},
                        {"plan": {"decade": 1999}, "confirmed": True}, {"plan": {"decade": True}, "confirmed": True},
                        {"plan": {"person_role": "director"}, "confirmed": True},
                        {"plan": {"country": ["JP", "US"]}, "confirmed": True}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post("/ask/query", json=payload).status_code, 422)
        self.assertEqual(self.client.post("/ask/interpret", json={"provider_consent": True, "question": " "}).status_code, 422)
        self.assertEqual(self.client.post("/ask/interpret", json={"provider_consent": True, "question": "x" * 601}).status_code, 422)

    def test_unready_projection_fails_closed(self):
        with Session(self.engine) as session:
            state = session.get(ProjectionState, "explore_facets")
            state.status = "failed"
            session.add(state)
            session.commit()
        response = self.client.post("/ask/query", json={"plan": {}, "confirmed": True})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "projection_unavailable")

    def _interpreter(self, content=None, *, error=None, finish_reason="stop"):
        client = MagicMock()
        client.__enter__.return_value = client
        client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=content), finish_reason=finish_reason)])
        client.chat.completions.create.side_effect = error
        factory = MagicMock(return_value=client)
        return AskInterpreter(client_factory=factory), factory, client

    def test_provider_receives_question_and_static_schema_only_once(self):
        plan = AskPlan(country="JP", decade=1990, view="unwatched")
        interpreter, factory, client = self._interpreter(json.dumps({"status": "ready", "plan": plan.model_dump(), "reason": None}))
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture-credential"}):
            result = interpreter.interpret(AskQuestion(provider_consent=True, question="Find unwatched Japanese films from the 1990s."))
        self.assertEqual(result.plan, plan)
        client.chat.completions.create.assert_called_once()
        args = client.chat.completions.create.call_args.kwargs
        self.assertEqual(args["max_tokens"], 1600)
        self.assertNotIn("tools", args)
        serialized = json.dumps(args)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("fixture-credential", serialized)
        self.assertNotIn("Alpha", serialized)
        self.assertEqual(factory.call_args.kwargs["max_retries"], 0)
        self.assertEqual(factory.call_args.kwargs["timeout"], 20.0)

    def test_invalid_truncated_or_incomplete_provider_output_is_not_executed(self):
        for content in ("not json", '{"status":"ready","plan":{}}',
                        '{"status":"ready","plan":{"sql":"select * from film"}}',
                        '{"status":"unsupported","plan":{}}'):
            interpreter, _, _ = self._interpreter(content)
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture"}), self.assertRaisesRegex(AskError, "ask_invalid_response"):
                interpreter.interpret(AskQuestion(provider_consent=True, question="Find films"))
        interpreter, _, _ = self._interpreter('{"status":"clarify","plan":null}', finish_reason="length")
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture"}), self.assertRaisesRegex(AskError, "ask_invalid_response"):
            interpreter.interpret(AskQuestion(provider_consent=True, question="Find films"))

    def test_provider_errors_timeout_and_busy_state_are_sanitized(self):
        for error, code in [(RuntimeError("SECRET_PRIVATE_PROVIDER_BODY"), "ask_provider_unavailable"),
                            (APITimeoutError(request=httpx.Request("POST", "https://example.com")), "ask_timeout")]:
            interpreter, _, _ = self._interpreter(error=error)
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture"}), self.assertRaises(AskError) as caught:
                interpreter.interpret(AskQuestion(provider_consent=True, question="Find films"))
            self.assertEqual(str(caught.exception), code)
        slots = BoundedSemaphore(1)
        slots.acquire()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture"}), patch.object(ask_module, "_interpretation_slots", slots):
            with self.assertRaisesRegex(AskError, "ask_busy"):
                AskInterpreter().interpret(AskQuestion(provider_consent=True, question="Find films"))

    def test_private_question_is_blocked_before_provider_call(self):
        interpreter, factory, _ = self._interpreter()
        for question in (r"Find films under C:\Movies\private", "find /mnt/private/films", "my api_key=private", "use sk-abcdefgh12345678"):
            with self.subTest(question=question), self.assertRaisesRegex(AskError, "ask_private_input"):
                interpreter.interpret(AskQuestion(provider_consent=True, question=question))
        factory.assert_not_called()

    def test_unsupported_or_vague_intents_never_run_local_queries(self):
        for state in ("unsupported", "clarify"):
            fake = MagicMock()
            fake.interpret.return_value = AskInterpretation(status=state, plan=None)
            service = AskService(interpreter=fake)
            with patch.object(service, "resolve", side_effect=AssertionError("must not resolve partial plan")):
                response = service.interpret(AskQuestion(provider_consent=True, question="Recommend something based on my notes"))
            self.assertEqual(response["status"], state)
            self.assertIsNone(response["plan"])

    def _numeric_fixture(self):
        from app.services.library import library_manager
        from app.services.user_state import film_profile_state_manager
        for title, runtime, seconds in (("Alpha", 90, None), ("Beta", 120, 5401), ("Gamma", None, 0)):
            library_manager.update_film_observation(self.films[title], {"runtime": runtime, "video_duration": seconds})
        for title, rating in (("Alpha", 3), ("Beta", 5)):
            film_profile_state_manager.upsert(self.films[title], rating=rating, fields_set={"rating"})

    def test_duration_boundaries_match_exact_video_seconds_before_counts(self):
        self._numeric_fixture()
        for plan, names in (({"duration_max": 90}, ["Alpha"]),
                            ({"duration_min": 90, "duration_max": 91}, ["Alpha", "Beta"]),
                            ({"duration_min": 90, "duration_min_inclusive": False}, ["Beta"]),
                            ({"duration_max": 90, "duration_max_inclusive": False}, []),
                            ({"duration_min": 120}, [])):
            with self.subTest(plan=plan):
                result = self.query(**plan)["results"]
                self.assertEqual(result["total"], len(names))
                self.assertEqual([item["film"]["id"] for item in result["items"]], [self.films[name] for name in names])
        item = self.query(duration_min=90, duration_min_inclusive=False)["results"]["items"][0]
        self.assertEqual(item["matched_values"], [{"field": "duration", "value": 5401.0, "unit": "seconds", "source": "video"}])
        item = self.query(duration_max=90)["results"]["items"][0]
        self.assertEqual(item["matched_values"][0]["source"], "film_runtime")

    def test_rating_nulls_do_not_use_viewing_or_external_scores_and_intersect_facts(self):
        from app.models import FilmExternalScore
        self._numeric_fixture()
        with Session(self.engine) as session:
            session.add(FilmExternalScore(film_id=self.films["Gamma"], source="tmdb", label="TMDB",
                kind="rating", value=9.9, scale=10.0, fetched_at="2026-10-14T00:00:00Z"))
            session.commit()
        self.assertEqual(self.query(rating_min=1)["results"]["total"], 2)
        self.assertEqual(self.query(rating_min=3, rating_max=3)["results"]["items"][0]["film"]["id"], self.films["Alpha"])
        self.assertEqual(self.query(rating_min=5, duration_max=90)["results"]["total"], 0)
        result = self.query(rating_min=3, duration_max=90, country="JP", person="Shared Person", person_role="director", view="unwatched")
        self.assertEqual(result["results"]["total"], 1)
        self.assertEqual(result["confirmed_plan"]["rating_min"], 3)
        self.assertEqual(result["results"]["items"][0]["matched_values"][1],
            {"field": "rating", "value": 3, "unit": "stars", "source": "film_profile"})
        before = hashlib.sha256(self.database_path.read_bytes()).hexdigest()
        self.query(rating_max=5, duration_min=1)
        self.assertEqual(hashlib.sha256(self.database_path.read_bytes()).hexdigest(), before)

    def test_scalar_contracts_reject_invalid_empty_and_noninteger_ranges(self):
        for plan in ({"duration_min": 0}, {"duration_max": 10001}, {"duration_min": True},
                     {"duration_max": 90.5}, {"duration_min": 100, "duration_max": 90},
                     {"duration_min": 90, "duration_max": 90, "duration_max_inclusive": False},
                     {"duration_max_inclusive": False}, {"rating_min": 0}, {"rating_max": 6},
                     {"rating_min": 4, "rating_max": 3}, {"rating_min": 3.5}, {"rating_min": True}):
            with self.subTest(plan=plan):
                self.assertEqual(self.client.post("/ask/query", json={"plan": plan, "confirmed": True}).status_code, 422)
        self.assertEqual(self.client.post("/ask/interpret", json={"question": "Find films"}).status_code, 422)

    def test_unsupported_explicit_requirements_are_blocked_even_if_provider_would_drop_them(self):
        interpreter, factory, _ = self._interpreter()
        for question, reason in (("Find Japanese films excluding horror", "negation"),
                                 ("找温暖治愈的日本电影", "similarity"), ("Recommend films for my taste", "recommendation"),
                                 ("Find films with IMDb ratings over 8", "unsupported_filter")):
            result = interpreter.interpret(AskQuestion(question=question, provider_consent=True))
            self.assertEqual((result.status, result.plan, result.reason), ("unsupported", None, reason))
        factory.assert_not_called()

    def test_observation_reports_only_real_usage_and_cost_evidence(self):
        plan = AskPlan(duration_max=90, rating_min=4)
        interpreter, _, client = self._interpreter(json.dumps({"status": "ready", "plan": plan.model_dump(), "reason": None}))
        response = client.chat.completions.create.return_value
        response.model = "fixture/model-v1"
        response.usage = SimpleNamespace(prompt_tokens=40, completion_tokens=20, total_tokens=60, cost=0.0001)
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture"}):
            result = interpreter.interpret(AskQuestion(question="Films under 90 minutes with my overall stars >=4", provider_consent=True))
        self.assertEqual(result._observation["total_tokens"], 60)
        self.assertEqual(result._observation["cost_usd"], 0.0001)
        self.assertEqual(result._observation["cost_source"], "provider_usage.cost")
        self.assertGreaterEqual(result._observation["latency_ms"], 0)
        response.usage = None
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture"}):
            result = interpreter.interpret(AskQuestion(question="Find films", provider_consent=True))
        self.assertIsNone(result._observation["total_tokens"])
        self.assertIsNone(result._observation["cost_usd"])

    def test_duplicate_extra_nonfinite_and_partial_json_fail_closed(self):
        full = {"status": "ready", "plan": AskPlan().model_dump(), "reason": None}
        for content in ('{"status":"ready","status":"unsupported","plan":null,"reason":"negation"}',
                        json.dumps({**full, "results": ["invented film"]}),
                        json.dumps({**full, "plan": {**full["plan"], "duration_max": True}}),
                        json.dumps({**full, "plan": {**full["plan"], "rating_min": float("nan")}}),
                        json.dumps({"status":"clarify", "plan":None, "reason":None})):
            interpreter, _, _ = self._interpreter(content)
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture"}), self.assertRaisesRegex(AskError, "ask_invalid_response"):
                interpreter.interpret(AskQuestion(question="Find all films", provider_consent=True))

    def test_query_count_scalar_facts_and_reasons_share_a_read_snapshot(self):
        from sqlalchemy import event
        from app.services.user_state import film_profile_state_manager
        self._numeric_fixture()
        with self.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        changed = False
        def before_read(_connection, _cursor, statement, _parameters, _context, _executemany):
            nonlocal changed
            if not changed and statement.startswith("SELECT library_film_read_model."):
                changed = True
                film_profile_state_manager.upsert(self.films["Alpha"], rating=2, fields_set={"rating"})
        event.listen(self.engine, "before_cursor_execute", before_read)
        try:
            result = self.query(rating_min=3, rating_max=3)["results"]
        finally:
            event.remove(self.engine, "before_cursor_execute", before_read)
        self.assertTrue(changed)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["matched_values"][0]["value"], 3)
        self.assertEqual(result["items"][0]["film"]["profile_state"]["rating"], 3)
        self.assertEqual(self.query(rating_min=3, rating_max=3)["results"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
