"""New wording/counterexamples for the post-failure revision, without a model."""
import re
import unittest
from unittest.mock import patch

from sqlmodel import Session

import test_explore_query as fixture
import test_integrated_search as integration
from app.canonical_models import GraphEntity, Person
from app.contracts.bound_search_plan import SearchPlan
from app.services import ask as ask_module
from app.services.content_request import split_content_request
from app.services.search_literals import bind_literal, hard_plan
from app.services.search_local import LocalSearch
from app.services.structured_metadata_vocab import normalize_metadata_text


class LiteralSyntaxTests(unittest.TestCase):
    def setUp(self):
        self.first, self.second = "film_" + "1" * 32, "film_" + "2" * 32
        self.names = {"silver road": self.first, "旧日之光": self.first, "mother!": self.second,
            "no country for old men": self.second, "face/off": self.second, "9/11": self.second,
            "v/h/s": self.second, "a film about rain": self.first}

    def lookup(self, text):
        identifier = self.names.get(normalize_metadata_text(text))
        return [{"key": identifier, "label": text}] if identifier else []

    def bind(self, text):
        return bind_literal(text, self.lookup, lambda name: normalize_metadata_text(name) == "shared person")

    def test_local_bindings_preserve_the_original_factual_payload_without_ids(self):
        from app.contracts.search_plan import SearchPlan as FactualSearchPlan
        legacy = FactualSearchPlan(version="search-plan.v2", countries=["JP"], year_min=2000)
        current = SearchPlan.model_validate(legacy.model_dump())
        self.assertEqual(current.model_dump(), legacy.model_dump())
        bound = current.model_copy(update={"film_ids": [self.first], "exclude_film_ids": [self.second]})
        self.assertEqual(SearchPlan.model_validate(bound.model_dump()), bound)
        self.assertEqual(bound.model_dump()["film_ids"], [self.first])
        with self.assertRaises(ValueError):
            SearchPlan(version="search-plan.v2", film_ids=[self.first, self.first])

    def test_complete_wrappers_and_one_sentence_period_preserve_raw_input_separately(self):
        for text in ("Find the film Silver Road.", "Please find Silver Road.", "show me Silver Road",
                     "I want to watch Silver Road.", "请帮我寻找《旧日之光》。", "我想找《旧日之光》这部电影。",
                     "有没有《旧日之光》？", "Silver Road.", "find Shared Person."):
            with self.subTest(text=text):
                bound = self.bind(text)
                self.assertIsNotNone(bound)
                self.assertIsNotNone(bound.keyword, bound)
                self.assertTrue(self.lookup(bound.keyword) or bound.keyword == "Shared Person")
                self.assertIsNone(bound.plan)

    def test_real_title_punctuation_request_words_and_short_names_take_precedence(self):
        for title in ("Mother!", "No Country for Old Men", "Face/Off", "V/H/S", "9/11", "A Film About Rain"):
            with self.subTest(title=title):
                self.assertEqual(self.bind(title).keyword, title)
                self.assertEqual(self.bind("Find the film " + title).keyword, title)
        self.names["mother"] = self.first
        self.assertEqual(self.bind("Mother!").keyword, "Mother!")
        self.assertNotEqual(self.lookup(self.bind("Mother!").keyword), self.lookup("Mother"))

    def test_unknown_quoted_identity_remains_literal_not_a_nearby_recommendation(self):
        for text in ("Find 'An Unlisted Film'.", "帮我找《不存在的电影》。"):
            binding = self.bind(text)
            self.assertIsNotNone(binding.keyword)
            self.assertEqual(self.lookup(binding.keyword), [])

    def test_explicit_exact_only_uses_identity_not_contains_and_missing_or_ambiguous_stops(self):
        for text in ("Silver Road, exact film only, no substitutes.", "只找《旧日之光》，不要相似推荐。",
                     'Find "Silver Road", no similar films.', "只要旧日之光"):
            with self.subTest(text=text):
                binding = self.bind(text)
                self.assertEqual(binding.plan.film_ids, [self.first])
                self.assertIsNone(binding.keyword)
        # A prefix-only lookup would return the sequel. Exact-only must not.
        self.names["unlisted film 2"] = self.second
        for text in ("Unlisted Film, exact film only, no substitutes.", "只找《不存在的电影》，不要相似推荐。"):
            with self.subTest(text=text):
                self.assertEqual(self.bind(text).issue, "unknown_film")
        lookup = lambda name: [{"key": self.first}, {"key": self.second}] if name == "Same Title" else []
        self.assertEqual(bind_literal('Find "Same Title", no substitutes.', lookup).issue, "ambiguous_film")

    def test_narrative_sentences_and_unconsumed_qualifiers_never_truncate_to_a_known_title(self):
        for text in ("A lonely person walks along Silver Road while remembering a friend.",
                     "Silver Road saves someone in a story I cannot remember.",
                     "Find the film Silver Road but make it comforting",
                     "I want a film about the people who live on Silver Road."):
            with self.subTest(text=text):
                self.assertIsNone(self.bind(text))
        self.assertIsNotNone(self.bind("Silver Road, produced by Unknown Person").issue)

    def test_known_identity_qualifiers_bind_both_positive_and_negative_ids(self):
        binding = self.bind('Silver Road, not the original "Mother!"')
        self.assertEqual(binding.plan.film_ids, [self.first])
        self.assertEqual(binding.plan.exclude_film_ids, [self.second])
        binding = self.bind("Silver Road, before 1998")
        self.assertEqual(binding.plan.year_max, 1997)
        self.assertEqual(binding.plan.film_ids, [self.first])

    def test_unknown_or_ambiguous_exclusions_never_become_absence(self):
        plan, issue = hard_plan('excluding "Unlisted Film"', self.lookup)
        self.assertIsNone(plan)
        self.assertEqual(issue, "unknown_film")
        lookup = lambda title: [{"key": self.first}, {"key": self.second}]
        self.assertEqual(hard_plan('excluding "Same Title"', lookup)[1], "ambiguous_film")

    def test_supported_year_negation_is_a_strict_positive_bound(self):
        for text in ("not anything released before 1998", "not from before 1998", "不要1998年以前的电影"):
            plan, issue = hard_plan(text, self.lookup)
            self.assertIsNone(issue, (text, issue))
            self.assertEqual(plan.year_min, 1998)
        plan, issue = hard_plan("not released after 1998", self.lookup)
        self.assertIsNone(issue)
        self.assertEqual(plan.year_max, 1998)


class LiteralSQLTests(unittest.TestCase):
    _seed_library = fixture.ExploreQueryTests._seed_library
    _seed_facts = fixture.ExploreQueryTests._seed_facts
    _add_credit = staticmethod(fixture.ExploreQueryTests._add_credit)
    _add_genre = staticmethod(fixture.ExploreQueryTests._add_genre)
    _add_country = staticmethod(fixture.ExploreQueryTests._add_country)
    tearDown = fixture.ExploreQueryTests.tearDown

    def setUp(self):
        fixture.ExploreQueryTests.setUp(self)
        self.local = LocalSearch(self.engine)

    def test_identity_year_and_role_constraints_are_executed_together_in_sql(self):
        for question, total in (("Alpha, in 1994", 1), ("Alpha, before 1990", 0),
                                ("Alpha, not Beta", 1), ("Alpha, not Alpha", 0),
                                ("Alpha, starring Shared Person", 0)):
            with self.subTest(question=question):
                result = self.local.interpret(question)
                self.assertEqual(result["status"], "ready", result)
                self.assertEqual(result["results"]["total"], total)
                self.assertEqual(result["plan"]["film_ids"], [self.films["Alpha"]])

    def test_explicit_exact_only_keeps_partial_title_neighbors_out_of_results(self):
        with Session(self.engine) as session:
            from app.canonical_models import FilmSearchReadModel
            neighbor = session.get(FilmSearchReadModel, self.films["Beta"])
            neighbor.exact_titles = "\nalpha sequel\n"
            session.add(neighbor)
            session.commit()
        for question in ("Alpha, exact film only, no substitutes.", "只找《Alpha》，不要相似推荐。"):
            result = self.local.interpret(question)
            self.assertEqual(result["status"], "ready", result)
            self.assertEqual([row["film"]["id"] for row in result["results"]["items"]], [self.films["Alpha"]])

    def test_missing_id_cannot_run_a_partial_inclusion_or_exclusion(self):
        missing = "film_" + "f" * 32
        for field in ("film_ids", "exclude_film_ids"):
            result = self.local.executor.query(SearchPlan(version="search-plan.v2", countries=["JP"], **{field: [missing]}))
            self.assertEqual(result["status"], "needs_clarification")
            self.assertIsNone(result["results"])

    def test_supported_compound_boundaries_use_v2_and_keep_people_and_years(self):
        cases = (
            ("Shared Person directed it in the 1990s: a family reconnects during a storm.", "Shared Person", 1990, 1999),
            ("films by Shared Person after 1992 about a child crossing an ocean", "Shared Person", 1993, None),
            ("由Shared Person执导、1992年以后的电影，一个孩子开始远行。", "Shared Person", 1993, None),
        )
        for question, name, lower, upper in cases:
            with self.subTest(question=question):
                request = split_content_request(question, lookup=self.local.reference_candidates, mentions=self.local.title_mentions)
                self.assertIsNone(request.issue, request)
                self.assertTrue(request.is_content)
                self.assertEqual((request.hard.year_min, request.hard.year_max), (lower, upper))
                self.assertEqual([(p.name, p.role) for p in request.hard.people], [(name, "director")])
                self.assertEqual(self.local.executor.query(request.hard)["status"], "ready")

    def test_same_name_different_ids_are_not_merged_or_selected_by_name(self):
        identifier = "person_" + "d" * 32
        with Session(self.engine) as session:
            session.add(GraphEntity(id=identifier, entity_type="person"))
            session.add(Person(id=identifier, canonical_name="Shared Person", normalized_name="shared person", resolution_status="verified"))
            session.flush()
            self._add_credit(session, self.films["Gamma"], identifier, "Directing", "Director", "duplicate-name")
            session.commit()
        result = self.local.interpret("films directed by Shared Person after 1990")
        self.assertEqual(result["status"], "needs_clarification")
        choices = result["issues"][0]["candidates"]
        self.assertEqual({c["key"] for c in choices}, {self.people["shared"], identifier})
        self.assertIsNone(result["results"])

    def test_old_v2_url_meaning_and_bound_title_restore_stay_local(self):
        from app.contracts.discovery_search import DiscoveryQuery
        from app.services.discovery_search import DiscoverySearchService
        with patch.object(ask_module, "engine", self.engine):
            service = DiscoverySearchService()
            question = "Alpha, before 1999"
            resolved = self.local.interpret(question)
            restored = service.query(DiscoveryQuery(question=question, plan=resolved["plan"]))
            self.assertEqual(restored["results"]["total"], 1)
            old = SearchPlan(version="search-plan.v2", year_min=1994, year_max=1994)
            self.assertEqual(service.query(DiscoveryQuery(question="films in 1994", plan=old))["results"]["total"], 1)
            changed = old.model_copy(update={"film_ids": [self.films["Beta"]]})
            self.assertEqual(service.query(DiscoveryQuery(question="films in 1994", plan=changed))["status"], "unsupported")

    def test_bound_title_edits_keep_results_and_revalidate_the_complete_original(self):
        from app.contracts.discovery_search import DiscoveryQuery
        from app.services.discovery_search import DiscoverySearchService
        with patch.object(ask_module, "engine", self.engine):
            service = DiscoverySearchService()
            for question in ("Alpha, before 1999", "Alpha, exact film only, no substitutes.", "只找《Alpha》，不要相似推荐。"):
                original = SearchPlan.model_validate(self.local.interpret(question)["plan"])
                for changes in ({"sort": "year", "direction": "desc"}, {"year_max": None}, {"view": "all"}):
                    plan = original.model_copy(update=changes)
                    result = service.query(DiscoveryQuery(question=question, plan=plan, edited=True))
                    self.assertEqual(result["status"], "ready", result)
                    self.assertEqual([row["film"]["id"] for row in result["results"]["items"]], [self.films["Alpha"]])
                removed = original.model_copy(update={"film_ids": [], "year_max": None})
                self.assertEqual(service.query(DiscoveryQuery(question=question, plan=removed, edited=True))["results"]["total"], 3)
            for question in ("Alpha, produced by Shared Person", "Alpha, in French", "Alpha, before 1999 without violence",
                             "Japanese films about a family reunion", "只找《Unknown》，不要相似推荐。"):
                result = service.query(DiscoveryQuery(question=question, plan=original, edited=True))
                self.assertEqual(result["status"], "unsupported", (question, result))
                self.assertIsNone(result["results"])
            unedited = original.model_copy(update={"film_ids": [self.films["Beta"]]})
            self.assertEqual(service.query(DiscoveryQuery(question="Alpha, exact film only, no substitutes.",
                plan=unedited))["status"], "unsupported")
            unknown = original.model_copy(update={"film_ids": ["film_" + "f" * 32]})
            result = service.query(DiscoveryQuery(question="Alpha, before 1999", plan=unknown, edited=True))
            self.assertEqual(result["status"], "needs_clarification")
            self.assertIsNone(result["results"])


class NaturalReferenceTests(unittest.TestCase):
    setUp = integration.IntegratedSearchTests.setUp

    def mentions(self, text):
        return [{"title": m.group(), "start": m.start(), "end": m.end()}
                for d in self.docs for m in re.finditer(re.escape(d.title), text, re.I)]

    def test_natural_reference_is_bound_and_excluded_before_rerank_and_after_restore(self):
        self.engine.title_mentions = self.mentions
        for question in ("我喜欢《Public Film 1》的家庭主题，找其他电影。",
                         "《Public Film 1》那种家庭关系的感觉，还能看什么？",
                         "I enjoyed the family tension in Public Film 1. What else can I watch?",
                         "Something like Public Film 1 in exploring family obligations."):
            with self.subTest(question=question):
                result = self.engine.submit(question)
                self.assertEqual(result["status"], "ready", result)
                self.assertEqual(result["semantic"]["reference_id"], self.docs[0].film_id)
                self.assertNotIn(self.docs[0].film_id, [x["film"]["id"] for x in result["results"]["items"]])
                self.assertIn(self.docs[0].film_id, self.hard_calls[-1].exclude_film_ids)
                self.assertNotIn(self.docs[0].chunks[0], self.reranker.rank.call_args.args[1])
                calls = self.reranker.rank.call_count
                restored = self.engine.resume(question, result["snapshot"])
                self.assertNotIn(self.docs[0].film_id, [x["film"]["id"] for x in restored["results"]["items"]])
                self.assertEqual(self.reranker.rank.call_count, calls)
        self.decision.decide.assert_not_called()
        self.assertEqual(self.embedding.calls, [])

    def test_unknown_multiple_or_unhandled_reference_does_not_run_positive_half(self):
        self.engine.title_mentions = self.mentions
        for question in ("I liked 'Unknown Public Film'. What else can I watch?",
                         "Something like Public Film 1 and Public Film 2.",
                         'films like "Public Film 1", but without violence'):
            with self.subTest(question=question):
                result = self.engine.submit(question)
                self.assertIn(result["status"], ("clarify", "needs_clarification"))
                self.assertIsNone(result["results"])
        self.decision.decide.assert_not_called()
        self.reranker.rank.assert_not_called()
        self.assertEqual(self.embedding.calls, [])

    def test_two_reference_identities_require_selection_without_fuzzy_merging(self):
        self.engine.reference_candidates = lambda title: [
            {"key": d.film_id, "label": "Shared Title"} for d in self.docs[:2]]
        result = self.engine.submit('films like "Shared Title"')
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(len(result["issues"][0]["candidates"]), 2)
        self.reranker.rank.assert_not_called()

    def test_reference_prefix_cannot_discard_a_hard_condition_or_unknown_constraint(self):
        self.engine.title_mentions = self.mentions
        for question in ('under 90 minutes like "Public Film 1"',
                         '90分钟以内类似《Public Film 1》',
                         'under 90 minutes I liked "Public Film 1". What else?'):
            with self.subTest(question=question):
                parsed = split_content_request(question, mentions=self.mentions)
                self.assertIsNone(parsed.issue, parsed)
                self.assertEqual(parsed.hard.duration_max, 90)
        for question in ('rated five stars like "Public Film 1"',
                         '必须适合孩子观看，类似《Public Film 1》'):
            with self.subTest(question=question):
                result = self.engine.submit(question)
                self.assertIn(result["status"], ("clarify", "needs_clarification"))
                self.assertIsNone(result["results"])
        self.decision.decide.assert_not_called()
        self.reranker.rank.assert_not_called()


if __name__ == "__main__":
    unittest.main()
