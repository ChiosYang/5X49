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
            response = self.client.post("/ask/interpret", json={"question": "find unwatched films"})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["detail"]["code"], "ask_not_configured")
            self.assertEqual(self.client.post("/ask/resolve", json={"plan": {"country": "JP"}}).status_code, 200)
            result = self.client.post("/ask/query", json={"plan": {"country": "JP"}, "confirmed": True})
            self.assertEqual(result.json()["results"]["total"], 2)

    def test_contract_rejects_unsupported_fields_and_unconfirmed_queries(self):
        for payload in ({"plan": {}, "confirmed": False}, {"plan": {"sql": "DELETE FROM film"}, "confirmed": True},
                        {"plan": {"decade": 1999}, "confirmed": True}, {"plan": {"decade": True}, "confirmed": True},
                        {"plan": {"person_role": "director"}, "confirmed": True},
                        {"plan": {"country": ["JP", "US"]}, "confirmed": True}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post("/ask/query", json=payload).status_code, 422)
        self.assertEqual(self.client.post("/ask/interpret", json={"question": " "}).status_code, 422)
        self.assertEqual(self.client.post("/ask/interpret", json={"question": "x" * 601}).status_code, 422)

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
        interpreter, factory, client = self._interpreter(json.dumps({"status": "ready", "plan": plan.model_dump()}))
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture-credential"}):
            result = interpreter.interpret(AskQuestion(question="Find unwatched Japanese films from the 1990s."))
        self.assertEqual(result.plan, plan)
        client.chat.completions.create.assert_called_once()
        args = client.chat.completions.create.call_args.kwargs
        self.assertEqual(args["max_tokens"], 1200)
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
                interpreter.interpret(AskQuestion(question="Find films"))
        interpreter, _, _ = self._interpreter('{"status":"clarify","plan":null}', finish_reason="length")
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture"}), self.assertRaisesRegex(AskError, "ask_invalid_response"):
            interpreter.interpret(AskQuestion(question="Find films"))

    def test_provider_errors_timeout_and_busy_state_are_sanitized(self):
        for error, code in [(RuntimeError("SECRET_PRIVATE_PROVIDER_BODY"), "ask_provider_unavailable"),
                            (APITimeoutError(request=httpx.Request("POST", "https://example.com")), "ask_timeout")]:
            interpreter, _, _ = self._interpreter(error=error)
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture"}), self.assertRaises(AskError) as caught:
                interpreter.interpret(AskQuestion(question="Find films"))
            self.assertEqual(str(caught.exception), code)
        slots = BoundedSemaphore(1)
        slots.acquire()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture"}), patch.object(ask_module, "_interpretation_slots", slots):
            with self.assertRaisesRegex(AskError, "ask_busy"):
                AskInterpreter().interpret(AskQuestion(question="Find films"))

    def test_private_question_is_blocked_before_provider_call(self):
        interpreter, factory, _ = self._interpreter()
        for question in (r"Find films under C:\Movies\private", "find /mnt/private/films", "my api_key=private", "use sk-abcdefgh12345678"):
            with self.subTest(question=question), self.assertRaisesRegex(AskError, "ask_private_input"):
                interpreter.interpret(AskQuestion(question=question))
        factory.assert_not_called()

    def test_unsupported_or_vague_intents_never_run_local_queries(self):
        for state in ("unsupported", "clarify"):
            fake = MagicMock()
            fake.interpret.return_value = AskInterpretation(status=state, plan=None)
            service = AskService(interpreter=fake)
            with patch.object(service, "resolve", side_effect=AssertionError("must not resolve partial plan")):
                response = service.interpret(AskQuestion(question="Recommend something based on my notes"))
            self.assertEqual(response["status"], state)
            self.assertIsNone(response["plan"])


if __name__ == "__main__":
    unittest.main()
