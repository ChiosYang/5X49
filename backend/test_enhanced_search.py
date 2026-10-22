import unittest
import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import ValidationError
from sqlmodel import Session, select
from sqlalchemy import event

import test_explore_query as fixture
from app.canonical_models import Film, FilmTitle, FilmMetadataOverride, PersonAlias, ExternalIdentity, ExploreFacetReadModel, GraphEntity, LibraryFilmReadModel, ExploreFilmReadModel
from app.contracts.discovery_search import DiscoveryQuestion, DiscoveryQuery
from app.contracts.search_plan import SearchPlan, SearchInterpretation
from app.services import ask as ask_module
from app.services.ask import AskService, AskInterpreter, AskError
from app.services.discovery_search import DiscoverySearchService
from app.services.projections import projection_reader, PROJECTION_VERSIONS, _hash
from app.services.search_execution import search_plan_executor
from app.services.search_rules import parse_extended, accepted_interpretation
from app.evaluation.enhanced_search import SearchCase, evaluate


class EnhancedSearchTests(unittest.TestCase):
    _seed_library = fixture.ExploreQueryTests._seed_library
    _seed_facts = fixture.ExploreQueryTests._seed_facts
    _add_credit = staticmethod(fixture.ExploreQueryTests._add_credit)
    _add_genre = staticmethod(fixture.ExploreQueryTests._add_genre)
    _add_country = staticmethod(fixture.ExploreQueryTests._add_country)
    tearDown = fixture.ExploreQueryTests.tearDown

    def setUp(self):
        fixture.ExploreQueryTests.setUp(self)
        engine_patch = patch.object(ask_module, "engine", self.engine)
        engine_patch.start()
        self.addCleanup(engine_patch.stop)
        self.interpreter = MagicMock()
        self.interpreter.configured.return_value = False
        self.service = DiscoverySearchService(ask=AskService(interpreter=self.interpreter))
        with Session(self.engine) as session:
            for name, minutes in (("Alpha", 89), ("Beta", 90)):
                film = session.get(Film, self.films[name])
                film.runtime_minutes = minutes
                session.add(film)
            self._add_credit(session, self.films["Alpha"], self.people["other"], "Acting", "Actor", "d")
            session.commit()

    def search(self, question, **extra):
        resolution = self.service.interpret(DiscoveryQuestion(question=question, allow_ai=True))
        if resolution["status"] == "ready":
            return self.service.query(DiscoveryQuery(question=question, plan=resolution["plan"],
                people_ids=resolution.get("people_ids", {}), person_id=resolution.get("person_id"), **extra))
        return resolution

    def ids(self, result):
        return [item["film"]["id"] for item in result["results"]["items"]]

    def run_evaluation(self):
        examples = (
            ("Japanese or French films", ("Alpha", "Beta")),
            ("日本或法国电影", ("Alpha", "Beta")),
            ("films under 90 minutes", ("Alpha",)),
            ("少于90分钟的电影", ("Alpha",)),
            ("films after 1999", ("Gamma",)),
            ("1999年之后的电影", ("Gamma",)),
            ("films excluding Japan", ()),
            ("排除日本的电影", ()),
            ("films directed by Shared Person and starring Other Person", ("Alpha",)),
            ("由Shared Person执导，由Other Person主演的电影", ("Alpha",)),
            ("unwatched films between 1994 and 1999", ("Alpha",)),
            ("未看1994到1999年电影", ("Alpha",)),
        )
        cases = [SearchCase(f"factual-{i + 1}", question, tuple(self.films[title] for title in titles))
                 for i, (question, titles) in enumerate(examples)]
        return evaluate(cases, lambda question: self.ids(self.search(question)))

    def test_offline_expected_id_quality_metrics_are_separate_from_live_model_claims(self):
        report = self.run_evaluation()
        self.assertEqual(report["cases"], 12)
        self.assertEqual(report["recall_at_40"], 1)
        self.assertEqual(report["top1_accuracy"], 1)
        self.assertEqual(report["hard_condition_violations"], 0)
        self.assertFalse(report["real_model"])
        self.interpreter.interpret_search.assert_not_called()

    def test_bilingual_expected_ids_for_complete_hard_conditions(self):
        cases = (
            ("Japanese or French films", ["Alpha", "Beta"]),
            ("日本或法国电影", ["Alpha", "Beta"]),
            ("Japanese or French films excluding horror or drama", ["Alpha", "Beta"]),
            ("films not horror", ["Alpha", "Beta", "Gamma"]),
            ("action or drama films", ["Alpha", "Beta", "Gamma"]),
            ("动作或剧情电影", ["Alpha", "Beta", "Gamma"]),
            ("Japanese films excluding horror", ["Alpha", "Beta"]),
            ("日本电影，不要恐怖", ["Alpha", "Beta"]),
            ("films excluding France", ["Alpha", "Beta"]),
            ("电影，排除法国", ["Alpha", "Beta"]),
            ("films between 1994 and 1999", ["Alpha", "Beta"]),
            ("1994到1999年电影", ["Alpha", "Beta"]),
            ("films after 1999", ["Gamma"]),
            ("1999年之后的电影", ["Gamma"]),
            ("films in 1994", ["Alpha"]),
            ("films in 2100", []),
            ("1994年电影", ["Alpha"]),
            ("films under 90 minutes", ["Alpha"]),
            ("films under 90 minutes sorted by title", ["Alpha"]),
            ("少于90分钟的电影", ["Alpha"]),
            ("films at most 90 minutes", ["Alpha", "Beta"]),
            ("不超过90分钟的电影", ["Alpha", "Beta"]),
            ("90分钟以内的电影", ["Alpha", "Beta"]),
            ("films between 89 and 90 minutes", ["Alpha", "Beta"]),
            ("89到90分钟电影", ["Alpha", "Beta"]),
            ("unwatched films between 1994 and 1999", ["Alpha"]),
            ("未看1994到1999年电影", ["Alpha"]),
            ("films directed by Shared Person and starring Other Person", ["Alpha"]),
            ("由Shared Person执导，由Other Person主演的电影", ["Alpha"]),
            ("films starring Shared Person and Other Person", []),
        )
        for question, titles in cases:
            with self.subTest(question=question):
                result = self.search(question)
                self.assertEqual(result["status"], "ready", result)
                self.assertEqual(self.ids(result), [self.films[title] for title in titles])
        self.interpreter.interpret_search.assert_not_called()
        self.interpreter.interpret_extended_search.assert_not_called()

    def test_unknown_conflicted_and_missing_values_do_not_match_exclusions(self):
        # Gamma's country conflict cannot prove 'not France' or 'not Japan'.
        self.assertEqual(self.ids(self.search("films excluding Japan")), [])
        # Missing runtime is not a short Film; exact cutoff stays exclusive.
        self.assertEqual(self.ids(self.search("films over 89 minutes")), [self.films["Beta"]])
        with Session(self.engine) as session:
            for row in session.exec(select(ExploreFacetReadModel).where(
                    ExploreFacetReadModel.film_id == self.films["Beta"], ExploreFacetReadModel.dimension == "genre")).all():
                row.eligible = False
                session.add(row)
            session.info["skip_projection_hook"] = True
            session.commit()
        self.assertEqual(self.ids(self.search("films excluding horror")), [self.films["Alpha"], self.films["Gamma"]])
        unknown = self.search("films excluding Atlantis")
        self.assertEqual(unknown["status"], "unsupported")
        self.assertIsNone(unknown["results"])

    def test_no_partial_execution_for_unsupported_or_mixed_requirements(self):
        for question in ("Japanese or under 90 minutes films", "Japanese films under 90 minutes about growing up",
                "films produced and directed by Shared Person between 1990 and 2000",
                "films in French under 90 minutes", "films under 90 minutes rated 4 stars",
                "1994 or 1999 films", "films starring Shared Person or Other Person",
                "Japanese or French action and drama films", "films excluding Japanese horror",
                "未看日本治愈电影，少于90分钟", "1994到1999年法语电影", "日本或法国电影，不要某个主题"):
            with self.subTest(question=question):
                result = self.search(question)
                self.assertIn(result["status"], ("unsupported", "clarify"))
                self.assertIsNone(result["results"])
        self.interpreter.interpret_search.assert_not_called()

    def test_role_conjunction_is_per_clause_even_for_same_identity(self):
        plan = SearchPlan(version="search-plan.v2", people=[{"name": "Shared Person", "role": "director"},
                                  {"name": "Shared Person", "role": "actor"}])
        self.assertEqual(search_plan_executor.query(plan)["results"]["total"], 0)
        negative = SearchPlan(version="search-plan.v2", people=[{"name": "Shared Person", "role": "actor", "exclude": True}])
        self.assertEqual(self.ids(search_plan_executor.query(negative)), [self.films["Alpha"], self.films["Gamma"]])

    def test_normalized_punctuation_and_role_words_inside_names_keep_literal_spans(self):
        question = "未看日本或法国动作或剧情电影，2098年，由本地导演甲执导，少于90分钟"
        plan, leftover, issue = parse_extended(question)
        self.assertFalse(issue or leftover)
        self.assertEqual(plan.people[0].name, "本地导演甲")
        self.assertEqual(plan.people[0].role, "director")
        self.assertEqual((plan.countries, plan.year_min, plan.year_max, plan.view), (["FR", "JP"], 2098, 2098, "unwatched"))
        self.assertEqual(parse_extended("日本电影由是枝裕和执导，少于90分钟")[0].people[0].name, "是枝裕和")

    def test_year_clauses_intersect_in_every_order_without_overwriting_bounds(self):
        for question, lower, upper in (
            ("films from the 1990s before 1995", 1990, 1994),
            ("films before 1995 from the 1990s", 1990, 1994),
            ("films from the 1990s through 1995", 1990, 1995),
            ("films through 1995 from the 1990s", 1990, 1995),
            ("1990年代1995年以前的电影", 1990, 1994),
            ("1995年以前的1990年代电影", 1990, 1994),
            ("films from the 1990s after 1995", 1996, 1999),
            ("films after 1995 from the 1990s", 1996, 1999),
            ("1995年以后1990年代电影", 1996, 1999),
            ("films between 1990 and 2000 through 1995", 1990, 1995),
            ("films through 1995 between 1990 and 2000", 1990, 1995),
            ("films before 2000 in 1994", 1994, 1994),
            ("films in 1994 before 2000", 1994, 1994),
        ):
            with self.subTest(question=question):
                plan, leftover, issue = parse_extended(question)
                self.assertFalse(issue or leftover)
                self.assertEqual((plan.year_min, plan.year_max), (lower, upper))
                result = self.search(question)
                self.assertEqual(result["status"], "ready")
                self.assertTrue(all(lower <= item["film"]["year"] <= upper for item in result["results"]["items"]))
        for question in ("films in the 1990s before 1980", "films before 1980 in the 1990s",
                "films before 1990 released in 2000", "films released in 2000 before 1990",
                "1990年代1980年以前的电影", "1980年以前的1990年代电影", "1990年以前2000年上映的电影"):
            with self.subTest(question=question):
                result = self.search(question)
                self.assertNotEqual(result["status"], "ready")
                self.assertIsNone(result["results"])
        self.interpreter.interpret_search.assert_not_called()

    def test_person_boundaries_preserve_supported_year_duration_and_negative_role_clauses(self):
        for suffix, expected in (("after 1999", []), ("before 1999", ["Alpha"]),
                ("since 1994", ["Alpha"]), ("through 1994", ["Alpha"]),
                ("less than 90 minutes", ["Alpha"]), ("more than 90 minutes", []),
                ("less than90minutes", ["Alpha"]), ("more than90minutes", []),
                ("and not starring Other Person", []), ("and not directed by Other Person", ["Alpha"])):
            question = "films directed by Shared Person " + suffix
            with self.subTest(question=question):
                result = self.search(question)
                self.assertEqual(result["status"], "ready", result)
                self.assertEqual(result["plan"]["people"][0]["name"], "Shared Person")
                self.assertEqual(self.ids(result), [self.films[title] for title in expected])
        self.interpreter.interpret_search.assert_not_called()

    def test_alias_identity_dedup_normalization_exact_priority_and_supersession(self):
        with Session(self.engine) as session:
            session.add(ExternalIdentity(id="identity_alias", entity_id=self.people["shared"], provider="tmdb.person",
                external_id="7", identity_status="active", provenance_kind="tmdb"))
            session.flush()
            for index, value in enumerate(("千と千尋", "千与千寻", "ＡＬＰＨＡ", "Shared Person")):
                session.add(FilmTitle(id=f"title_alias_{index}", film_id=self.films["Beta"], title=value,
                    normalized_title=value.casefold(), title_type="alternative", locale="und",
                    origin_kind="tmdb", origin_ref="tmdb.movie:7", observed_at=fixture.NOW))
            session.add(PersonAlias(id="alias_name", person_id=self.people["shared"], film_id=self.films["Alpha"],
                identity_id="identity_alias", name="共有者", normalized_name="共有者", origin_kind="tmdb",
                origin_ref="tmdb.movie:1", observed_at=fixture.NOW))
            session.commit()
        for query in ("千と千尋", "千与千寻"):
            page = projection_reader.film_page(self.engine, query=query, rank_exact=True)
            self.assertEqual([row["id"] for row in page["items"]], [self.films["Beta"]])
        page = projection_reader.film_page(self.engine, query="ａｌｐｈａ", rank_exact=True)
        self.assertEqual({row["id"] for row in page["items"]}, {self.films["Alpha"], self.films["Beta"]})
        page = projection_reader.film_page(self.engine, query="Shared Person", rank_exact=True)
        self.assertEqual([row["id"] for row in page["items"]], [self.films["Beta"], self.films["Alpha"]])
        with Session(self.engine) as session:
            candidates, exact = AskService._people(session, "共有者")
            self.assertTrue(exact)
            self.assertEqual([p["key"] for p in candidates], [self.people["shared"]])
            title = session.get(FilmTitle, "title_alias_0")
            title.superseded_at = fixture.NOW
            session.add(title)
            session.commit()
        self.assertEqual(projection_reader.film_page(self.engine, query="千と千尋")["total"], 0)
        self.assertEqual(self.search("find 千与千寻")["status"], "keyword")
        with Session(self.engine) as session:
            identity = session.get(ExternalIdentity, "identity_alias")
            identity.identity_status = "disputed"
            session.add(identity)
            session.commit()
            self.assertEqual(AskService._people(session, "共有者"), ([], False))
        self.assertEqual(projection_reader.film_page(self.engine, query="共有者")["total"], 0)

    def test_sql_query_count_and_page_materialization_do_not_grow_with_library_size(self):
        with Session(self.engine) as session:
            session.info["skip_projection_hook"] = True
            session.add_all([GraphEntity(id=f"film_{index + 1000:032x}", entity_type="film") for index in range(200)])
            session.flush()
            session.add_all([Film(id=f"film_{index + 1000:032x}", canonical_title=f"Scale {index:03}", release_year=2098)
                for index in range(200)])
            session.flush()
            for index in range(200):
                film_id = f"film_{index + 1000:032x}"
                title = f"Scale {index:03}"
                payload = {"id": film_id, "title": title, "year": 2098, "runtime_minutes": 89,
                    "primary_item": None, "profile_state": {"watched": False}}
                session.add(LibraryFilmReadModel(film_id=film_id, sort_title=title, release_year=2098,
                    visible=True, payload=payload, source_hash=_hash(payload), projection_version=PROJECTION_VERSIONS["library"]))
                session.add(ExploreFilmReadModel(film_id=film_id, sort_title=title, release_year=2098,
                    watched=False, source_hash=_hash({"sort_title": title, "release_year": 2098, "watched": False}),
                    projection_version=PROJECTION_VERSIONS["explore_films"]))
            session.commit()
        statements = []
        def record(_connection, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)
        event.listen(self.engine, "before_cursor_execute", record)
        try:
            result = search_plan_executor.query(SearchPlan(version="search-plan.v2", year_min=2098, year_max=2098), offset=100000)
        finally:
            event.remove(self.engine, "before_cursor_execute", record)
        self.assertEqual(result["results"]["total"], 200)
        self.assertEqual(result["results"]["offset"], 160)
        self.assertEqual(len(result["results"]["items"]), 40)
        self.assertLessEqual(len(statements), 12)

    def test_mock_extended_transport_is_minimal_and_never_enabled_by_routing(self):
        question = "films under 90 minutes"
        plan, leftover, issue = parse_extended(question)
        self.assertFalse(leftover or issue)
        body = {"status": "ready", "plan": plan.model_dump(), "confidence": .99, "unhandled": []}
        client = MagicMock()
        client.__enter__.return_value = client
        client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content=json.dumps(body)))])
        interpreter = AskInterpreter(client_factory=MagicMock(return_value=client))
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-only"}):
            result = interpreter.interpret_extended_search(DiscoveryQuestion(question=question))
        self.assertTrue(accepted_interpretation(result, question))
        args = client.chat.completions.create.call_args.kwargs
        self.assertEqual(args["messages"][1], {"role": "user", "content": question})
        self.assertNotIn("Alpha", json.dumps(args))
        self.assertNotIn(str(self.root), json.dumps(args))
        self.assertNotIn("tools", args)
        client.chat.completions.create.assert_called_once()
        for changed in ({"confidence": .3}, {"unhandled": ["a missing condition"]},
                {"plan": plan.model_copy(update={"countries": ["JP"]})},
                {"plan": plan.model_copy(update={"duration_max": None, "duration_max_exclusive": False})}):
            candidate = SearchInterpretation(**{**body, **changed})
            self.assertFalse(accepted_interpretation(candidate, question))
        self.search(question)
        self.interpreter.interpret_extended_search.assert_not_called()

    def test_invalid_contracts_and_no_inference_on_restore(self):
        for data in ({"year_min": 2000, "year_max": 1990}, {"duration_min": True},
                {"duration_max": 0}, {"year_max": 2101}, {"people": [{"name": "A", "role": "producer"}]},
                {"sql": "SELECT *"}, {"duration_min_exclusive": True}, {"countries": ["JP", "JP"]}):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                SearchPlan(version="search-plan.v2", **data)
        result = self.search("films under 90 minutes")
        self.service.query(DiscoveryQuery(question="films under 90 minutes", plan=result["plan"], offset=40))
        self.interpreter.interpret_search.assert_not_called()

    def test_effective_manual_year_and_nulls_are_applied_without_writes(self):
        with Session(self.engine) as session:
            session.add(FilmMetadataOverride(film_id=self.films["Alpha"], values={"year": None}, revision=1))
            session.commit()
        self.assertEqual(self.ids(self.search("films in 1994")), [])
        with Session(self.engine) as session:
            override = session.get(FilmMetadataOverride, self.films["Alpha"])
            self.assertEqual(override.values, {"year": None})
            self.assertEqual(session.get(Film, self.films["Alpha"]).release_year, 1994)


if __name__ == "__main__":
    unittest.main()
