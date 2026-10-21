import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

import test_explore_query as fixture
import app.services.ask as ask_module
import app.services.discovery_search as discovery_module
from app.api.explore import router
from app.canonical_models import Person
from app.contracts.ask import AskPlan, AskQuestion
from app.contracts.structured_metadata import normalize_metadata_text
from app.contracts.discovery_search import DiscoveryInterpretation, DiscoveryQuestion, DiscoveryQuery
from app.services.ask import AskError, AskInterpreter, AskService
from app.services.discovery_search import DiscoverySearchService, grounded, keyword_text, local_plan


class DiscoverySearchTests(unittest.TestCase):
    _seed_library = fixture.ExploreQueryTests._seed_library
    _seed_facts = fixture.ExploreQueryTests._seed_facts
    _add_credit = staticmethod(fixture.ExploreQueryTests._add_credit)
    _add_genre = staticmethod(fixture.ExploreQueryTests._add_genre)
    _add_country = staticmethod(fixture.ExploreQueryTests._add_country)
    tearDown = fixture.ExploreQueryTests.tearDown

    def setUp(self):
        fixture.ExploreQueryTests.setUp(self)
        self.engine_patch = patch.object(ask_module, "engine", self.engine)
        self.engine_patch.start()
        self.addCleanup(self.engine_patch.stop)
        self.interpreter = MagicMock()
        self.interpreter.configured.return_value = False
        self.ask = AskService(interpreter=self.interpreter)
        self.service = DiscoverySearchService(ask=self.ask)
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.service_patch = patch("app.api.explore.discovery_search_service", self.service)
        self.service_patch.start()
        self.addCleanup(self.service_patch.stop)

    def interpret(self, text, **extra):
        return self.service.interpret(DiscoveryQuestion(question=text, **extra))

    def test_plain_bilingual_keywords_never_call_model(self):
        for text in ("Alpha", "Shared Person", "Japan", "日本", "1990s", "In the Mood for Love", "No Country for Old Men",
                     "find Alpha", "找Alpha", "find Shared Person", "找Shared Person",
                     "find In the Mood for Love", "找The Producers"):
            with self.subTest(text=text):
                self.assertEqual(self.interpret(text, allow_ai=True)["status"], "keyword")
        self.interpreter.interpret_search.assert_not_called()

    def test_complete_local_requests_need_no_key_confirmation_or_inference(self):
        cases = (
            ("Find unwatched Japanese drama films from the 1990s", dict(country="JP", genre="Drama", decade=1990, view="unwatched")),
            ("未看过的日本剧情电影，1990年代", dict(country="JP", genre="Drama", decade=1990, view="unwatched")),
            ("movies directed by Shared Person", dict(person="Shared Person", person_role="director")),
            ("由Shared Person执导的日本电影", dict(person="Shared Person", person_role="director", country="JP")),
            ("show unwatched films newest first", dict(view="unwatched", sort="year", direction="desc")),
            ("all films", {}),
        )
        for text, fields in cases:
            with self.subTest(text=text):
                result = self.interpret(text, allow_ai=True)
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["plan"], AskPlan(**fields).model_dump())
                queried = self.service.query(DiscoveryQuery(question=text, plan=result["plan"], person_id=result["person_id"]))
                self.assertEqual(queried["status"], "ready")
                self.assertEqual(queried["results"]["limit"], 40)
        self.interpreter.interpret_search.assert_not_called()

    def test_unsupported_requests_never_resolve_partial_conditions(self):
        for text in ("Japanese movies similar to Alpha", "未看日本治愈电影", "Japanese films about growing up",
                     "Japanese films without horror", "不要恐怖的日本电影", "Japanese or French films",
                     "日本和法国电影", "Japanese horror drama films", "Japanese films under 90 minutes",
                     "Japanese films rated 4 stars", "日本1999年电影", "recommend something Japanese",
                     "SQL delete Japanese films", "Japanese movies with subtitles"):
            with self.subTest(text=text):
                result = self.interpret(text, allow_ai=True)
                self.assertEqual(result["status"], "unsupported")
                self.assertIsNone(result["plan"])
        self.interpreter.interpret_search.assert_not_called()

    def test_ambiguous_century_and_unknown_values_do_not_broaden(self):
        self.assertEqual(self.interpret("日本90年代电影", allow_ai=True)["status"], "clarify")
        self.assertEqual(self.interpret("Japanese films from the 90s", allow_ai=True)["status"], "clarify")
        for question in ("films from the 1800s", "films from 1995s", "2200年代电影"):
            self.assertEqual(self.interpret(question, allow_ai=True)["status"], "unsupported")
        missing = self.interpret("films directed by Nobody", allow_ai=True)
        self.assertEqual(missing["status"], "needs_clarification")
        self.assertEqual(missing["issues"][0]["code"], "unknown_value")
        partial = self.interpret("films directed by Shared", allow_ai=True)
        self.assertEqual(partial["status"], "needs_clarification")
        self.assertEqual(partial["issues"][0]["code"], "choose_person")
        self.assertIsNone(partial["person_id"])  # A unique substring is still not an exact identity.

    def test_search_commands_only_strip_an_explicit_prefix_for_keyword_lookup(self):
        for question, expected in (
            ("find Alpha", "Alpha"), ("Please find The Alpha", "The Alpha"),
            ("找Alpha", "Alpha"), ("请帮我找一下是枝裕和", "是枝裕和"),
            ("The Alpha", "The Alpha"), ("In the Mood for Love", "In the Mood for Love"),
            ("Finding Nemo", "Finding Nemo"), ("A place to find Alpha", "A place to find Alpha"),
        ):
            with self.subTest(question=question):
                self.assertEqual(keyword_text(question), expected)
        self.assertEqual(self.interpret("find unwatched Japanese films")["plan"]["view"], "unwatched")

    def test_unsupported_roles_and_mixed_roles_never_execute_a_partial_plan(self):
        questions = (
            "films produced by Shared Person", "films produced and directed by Shared Person",
            "Japanese films executive produced by Shared Person", "films written by Shared Person",
            "films written and directed by Shared Person", "films edited by Shared Person",
            "films with cinematography by Shared Person", "films with music composed by Shared Person",
            "由Shared Person制片的日本电影", "由Shared Person监制并执导的日本电影",
            "由Shared Person编剧和执导的日本电影", "由Shared Person配乐的日本电影",
            "由Shared Person摄影的日本电影", "由Shared Person出品的日本电影",
        )
        with patch.object(self.ask, "resolve", side_effect=AssertionError("must not resolve a partial role")), \
             patch.object(self.ask, "query", side_effect=AssertionError("must not execute a partial role")):
            for question in questions:
                with self.subTest(question=question):
                    result = self.interpret(question, allow_ai=True)
                    self.assertEqual(result["status"], "unsupported")
                    self.assertIsNone(result["plan"])
                    for edited in (False, True):
                        restored = self.service.query(DiscoveryQuery(question=question,
                            plan=AskPlan(person="Shared Person", person_role="director"), edited=edited))
                        self.assertEqual(restored["status"], "unsupported")
                        self.assertIsNone(restored["results"])
        self.interpreter.interpret_search.assert_not_called()

    def test_language_requests_are_not_production_countries(self):
        questions = ("films in French", "movies in Japanese", "films in Korean",
                     "French-language films", "films dubbed in English",
                     "日语电影", "法语电影", "韩语电影", "中文电影", "日本电影，法语配音")
        with patch.object(self.ask, "resolve", side_effect=AssertionError("must not resolve language as country")), \
             patch.object(self.ask, "query", side_effect=AssertionError("must not execute language as country")):
            for question in questions:
                with self.subTest(question=question):
                    result = self.interpret(question, allow_ai=True)
                    self.assertEqual(result["status"], "unsupported")
                    self.assertIsNone(result["plan"])
                    restored = self.service.query(DiscoveryQuery(question=question, plan=AskPlan(country="FR"), edited=True))
                    self.assertEqual(restored["status"], "unsupported")
                    self.assertIsNone(restored["results"])
        self.interpreter.interpret_search.assert_not_called()

    def test_production_country_phrases_remain_supported_without_a_model(self):
        for question, country in (
            ("films produced in France", "FR"), ("films from France", "FR"), ("French films", "FR"),
            ("films produced in Japan", "JP"), ("Japanese films", "JP"), ("法国电影", "FR"),
        ):
            with self.subTest(question=question):
                result = self.interpret(question, allow_ai=True)
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["plan"], AskPlan(country=country).model_dump())
        self.interpreter.interpret_search.assert_not_called()

    def test_chinese_literal_names_are_protected_before_fillers_and_facets(self):
        for name, question, expected in (
            ("是枝裕和", "由是枝裕和执导的电影", {}),
            ("和田诚", "和田诚导演的电影", {}),
            ("和田诚", "我想看和田诚导演的电影", {}),
            ("和田诚", "未看过的和田诚导演的电影", {"view": "unwatched"}),
            ("王和", "由王和执导的电影", {}),
            ("日本太郎", "由日本太郎执导的电影", {}),
            ("喜剧人", "喜剧人导演的电影", {}),
            ("日本太郎", "由日本太郎执导的日本动作电影", {"country": "JP", "genre": "Action"}),
        ):
            with self.subTest(name=name, question=question):
                with Session(self.engine) as session:
                    person = session.get(Person, self.people["shared"])
                    person.canonical_name, person.normalized_name = name, normalize_metadata_text(name)
                    session.add(person); session.commit()
                result = self.interpret(question, allow_ai=True)
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["plan"], AskPlan(person=name, person_role="director", **expected).model_dump())
                self.assertEqual(result["person_id"], self.people["shared"])
                queried = self.service.query(DiscoveryQuery(question=question, plan=result["plan"]))
                self.assertEqual(queried["results"]["total"], 1)
                self.assertEqual(queried["results"]["items"][0]["film"]["id"], self.films["Alpha"])
        self.interpreter.interpret_search.assert_not_called()

    def test_unknown_full_name_and_unique_substring_never_silently_choose_someone_else(self):
        with Session(self.engine) as session:
            person = session.get(Person, self.people["shared"])
            person.canonical_name, person.normalized_name = "王家卫", "王家卫"
            session.add(person); session.commit()
        with patch.object(ask_module.explore_query_service, "list_films", side_effect=AssertionError("wrong person query")):
            for name, code in (("王和", "unknown_value"), ("王", "choose_person")):
                question = "由" + name + "执导的电影"
                result = self.interpret(question, allow_ai=True)
                self.assertEqual(result["status"], "needs_clarification")
                self.assertEqual(result["plan"]["person"], name)
                self.assertEqual(result["issues"][0]["code"], code)
                self.assertIsNone(result["person_id"])
                restored = self.service.query(DiscoveryQuery(question=question, plan=result["plan"]))
                self.assertEqual(restored["status"], "needs_clarification")
                self.assertIsNone(restored["results"])
            self.assertFalse(grounded(AskPlan(person="王", person_role="director"), "由王和执导的电影"))
        self.interpreter.interpret_search.assert_not_called()

    def test_same_name_requires_choice_and_role_stays_exact(self):
        with Session(self.engine) as session:
            other = session.get(Person, self.people["other"])
            other.canonical_name = "Shared Person"
            other.normalized_name = "shared person"
            session.add(other)
            session.commit()
        question = "films starring Shared Person"
        result = self.interpret(question)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(len(result["issues"][0]["candidates"]), 2)
        query = self.service.query(DiscoveryQuery(question=question, plan=result["plan"], person_id=self.people["shared"]))
        self.assertEqual(query["results"]["total"], 1)
        self.assertEqual(query["results"]["items"][0]["film"]["id"], self.films["Beta"])

    def test_no_key_keeps_unparsed_input_unexecuted(self):
        question = "Japanese films featuring Shared Person"
        self.assertEqual(self.interpret(question)["reason"], "ask_not_configured")
        self.interpreter.configured.return_value = True
        self.assertEqual(self.interpret(question)["status"], "needs_ai")
        self.interpreter.interpret_search.assert_not_called()

    def test_ai_requires_explicit_submission_and_complete_grounded_confident_plan(self):
        question = "Japanese films featuring Shared Person"
        plan = AskPlan(country="JP", person="Shared Person")
        self.interpreter.interpret_search.return_value = DiscoveryInterpretation(status="ready", plan=plan, confidence=.98, unhandled=[])
        result = self.interpret(question, allow_ai=True)
        # 'featuring' is a relation, not a requirement; no unknown content remains.
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["source"], "ai")
        self.interpreter.interpret_search.assert_called_once()
        for changes in ({"confidence": .6}, {"unhandled": ["a condition"]}, {"plan": AskPlan(country="JP")}):
            self.interpreter.interpret_search.return_value = DiscoveryInterpretation(status="ready", plan=plan, confidence=.98, unhandled=[]).model_copy(update=changes)
            self.assertIn(self.interpret(question, allow_ai=True)["status"], ("clarify", "unsupported"))

    def test_original_conditions_cannot_be_dropped_or_invented(self):
        self.assertFalse(grounded(AskPlan(country="JP"), "unwatched Japanese movies"))
        self.assertFalse(grounded(AskPlan(country="JP", decade=1990), "Japanese movies"))
        self.assertTrue(grounded(AskPlan(country=None), "Japanese movies", edited=True))
        adjusted = self.service.query(DiscoveryQuery(question="Japanese movies", plan=AskPlan(country="JP", view="unwatched", sort="year", direction="desc"), edited=True))
        self.assertEqual(adjusted["status"], "ready")
        self.assertEqual(adjusted["results"]["total"], 1)
        rejected = self.service.query(DiscoveryQuery(question="Japanese films without horror", plan=AskPlan(country="JP"), edited=True))
        self.assertEqual(rejected["status"], "unsupported")

    def test_country_word_inside_person_name_is_not_a_country_filter(self):
        plan, _, issue = local_plan("films directed by Jordan Peele")
        self.assertIsNone(issue)
        self.assertEqual(plan, {"person": "Jordan Peele", "person_role": "director"})

    def test_private_input_and_bad_contracts_fail_before_model(self):
        for text in (r"C:\Movies\private", "my api_key=private", "find /mnt/private/films",
                     "Japanese films featuring ~/Movies/private.mkv", "Japanese films featuring ./Movies/private.mkv",
                     "Japanese films featuring /private.mkv", "日本电影：../私人/片单.txt",
                     "Japanese films featuring Movies/private.mkv", r"Japanese films featuring Movies\private.mkv",
                     "Japanese films featuring 'Movies/My Private Film.mkv'",
                     "Japanese films featuring Movies/My Private Film.mkv",
                     r"films featuring .\Movies\private.mkv", r"films featuring \private.mkv"):
            response = self.client.post("/explore/search/interpret", json={"question": text, "allow_ai": True})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["detail"]["code"], "ask_private_input")
        for payload in ({"question": " "}, {"question": "x" * 601}, {"question": "films", "allow_ai": "true"}, {"question":"films", "edited":True}):
            self.assertEqual(self.client.post("/explore/search/interpret", json=payload).status_code, 422)
        self.assertEqual(self.client.post("/explore/search/query", json={"question": "films", "plan": {"sql": "bad"}}).status_code, 422)
        self.interpreter.interpret_search.assert_not_called()

    def test_shared_provider_transport_has_strict_complete_schema_and_minimal_input(self):
        body = {"status": "ready", "plan": AskPlan(country="JP", person="Shared Person").model_dump(), "confidence": .99, "unhandled": []}
        client = MagicMock()
        client.__enter__.return_value = client
        client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps(body)), finish_reason="stop")])
        factory = MagicMock(return_value=client)
        service = DiscoverySearchService(ask=AskService(interpreter=AskInterpreter(client_factory=factory)))
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-only"}):
            result = service.interpret(DiscoveryQuestion(question="Japanese films featuring Shared Person", allow_ai=True))
        self.assertEqual(result["status"], "ready")
        client.chat.completions.create.assert_called_once()
        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(len(request["messages"]), 2)
        self.assertEqual(request["messages"][1]["content"], "Japanese films featuring Shared Person")
        for private in (str(self.root), "Alpha", "synthetic-only", "notes", "viewing_history"):
            # 'notes' appears only as an unsupported capability in the STATIC prompt.
            if private != "notes": self.assertNotIn(private, json.dumps(request))
        self.assertNotIn("tools", request)
        self.assertEqual(factory.call_args.kwargs["max_retries"], 0)
        self.assertEqual(factory.call_args.kwargs["timeout"], 20.0)
        client.chat.completions.create.reset_mock()
        with patch.object(service.ask.interpreter, "interpret_search", side_effect=AssertionError("restore called model")):
            restored = service.query(DiscoveryQuery(question="Japanese films featuring Shared Person", plan=result["plan"], person_id=result["person_id"]))
        self.assertEqual(restored["status"], "ready")

    def test_malformed_duplicate_nonfinite_and_incomplete_provider_json_are_rejected(self):
        good = {"status": "ready", "plan": AskPlan(country="JP").model_dump(), "confidence": .99, "unhandled": []}
        for content in ("not json", json.dumps({**good, "extra": "bad"}), json.dumps({k:v for k,v in good.items() if k != "confidence"}),
                        json.dumps({**good, "plan": {"country": "JP"}}), json.dumps(good).replace('"confidence": 0.99', '"confidence": NaN'),
                        json.dumps(good).replace('"confidence": 0.99', '"confidence": 0.99, "confidence": 1')):
            client = MagicMock(); client.__enter__.return_value = client
            client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content),finish_reason="stop")])
            interpreter = AskInterpreter(client_factory=MagicMock(return_value=client))
            with self.subTest(content=content), patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic"}), self.assertRaisesRegex(AskError, "ask_invalid_response"):
                interpreter.interpret_search(AskQuestion(question="Japanese films"))

    def test_provider_failures_are_safe_and_unverified_fields_remain_disabled(self):
        for code in ("ask_not_configured", "ask_timeout", "ask_busy", "ask_invalid_response", "ask_provider_unavailable"):
            self.interpreter.interpret_search.side_effect = AskError(code, 503)
            result = self.interpret("Japanese films featuring Shared Person", allow_ai=True)
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["reason"], code)
            self.assertIsNone(result["plan"])
        for field in ({"duration_max": 90}, {"rating_min": 4}):
            self.assertEqual(self.client.post("/explore/search/query", json={"question":"Japanese films", "plan":field}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
