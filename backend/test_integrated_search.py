"""Orchestration/restore contracts. Fake vectors/scores are not quality evidence."""
from dataclasses import replace
import json
import sqlite3
import unittest
from unittest.mock import Mock

from app.contracts.bound_search_plan import SearchPlan
from app.services.content_request import split_content_request
from app.services.integrated_search import IntegratedSearch
from app.services.search_index import SearchIndexStore
from app.services.search_providers import RouteDecision
from app.services.semantic_search import (ContentDocument, ContentSource, ProviderSpec,
    SemanticError, corpus_revision)


SPEC = ProviderSpec("synthetic/integration", "fixture.v1", 3)


def doc(i, text):
    return ContentDocument("film_" + f"{i:032x}", "Public Film " + str(i), (),
                           (ContentSource("overview", text, "tmdb"),))


class FakeEmbedding:
    spec = SPEC

    def __init__(self):
        self.calls = []

    def embed(self, texts, *, query):
        self.calls.append((tuple(texts), query))
        return [[1., 0., 0.] if "space" in t.lower() else [0., 1., 0.] for t in texts]


class ContentRequestTests(unittest.TestCase):
    def test_hard_conditions_survive_before_and_after_protected_content(self):
        result = split_content_request("Japanese films about a family reunion, under 90 minutes")
        self.assertIsNone(result.issue)
        self.assertEqual(result.hard.countries, ["JP"])
        self.assertEqual(result.hard.duration_max, 90)
        self.assertTrue(result.hard.duration_max_exclusive)
        self.assertEqual(result.text, "a family reunion")
        suffix = split_content_request("films about family 1999年以后")
        self.assertIsNone(suffix.issue)
        self.assertEqual(suffix.hard.year_min, 2000)

    def test_unsupported_roles_and_content_negation_never_execute_positive_half(self):
        for question in ("films produced by Shared Person about family", "films about family without violence",
                         "关于家庭但不要暴力的电影", "films in Japanese about family"):
            with self.subTest(question=question):
                self.assertIsNotNone(split_content_request(question).issue)

    def test_plot_after_death_is_not_a_release_filter_and_country_inside_plot_is_protected(self):
        request = split_content_request("films about a Japanese family reconnecting after a death")
        self.assertIsNone(request.issue)
        self.assertEqual(request.hard.countries, [])
        self.assertIsNone(request.hard.year_min)
        self.assertIn("after a death", request.text)

    def test_language_conditions_never_become_soft_content_or_country_filters(self):
        for language in ("French", "Japanese", "English", "Korean", "Chinese", "German", "Italian",
                         "Spanish", "Hindi", "Arabic", "Russian", "Portuguese", "Cantonese", "Mandarin"):
            for query in (f"films in {language}", f"{language}-language movies",
                          f"films about a family, in {language}", f"films with {language} audio"):
                with self.subTest(query=query):
                    self.assertEqual(split_content_request(query).issue, "unsupported_filter")
        for query in ("语言学家在山村寻找失踪的兄弟。", "A person hides a letter under a bridge."):
            self.assertIsNone(split_content_request(query).issue)

    def test_semantic_fallback_preserves_all_known_unsupported_metadata_contracts(self):
        for query in ("films by producer Shared Person", "films by writer Shared Person",
                      "movies with a rating of five stars", "favorite films about family without violence",
                      "my favorites", "films matching my notes", "delete all films"):
            with self.subTest(query=query):
                self.assertIsNotNone(split_content_request(query).issue)
        self.assertIsNone(split_content_request("films about a writer hiding a letter").issue)

    def test_cn_prefix_and_explicit_hard_tail(self):
        request = split_content_request("未看的日本电影，关于家庭重聚，少于90分钟")
        self.assertIsNone(request.issue)
        self.assertEqual(request.hard.view, "unwatched")
        self.assertEqual(request.hard.countries, ["JP"])
        self.assertEqual(request.hard.duration_max, 90)

    def test_known_reference_year_is_not_extracted_from_literal_title(self):
        request = split_content_request('films similar to "A Space Odyssey 2001"')
        self.assertIsNone(request.issue)
        self.assertEqual(request.reference, "A Space Odyssey 2001")
        self.assertIsNone(request.hard.year_min)

    def test_cn_quoted_reference_preserves_literal_and_hard_conditions(self):
        for query in ("类似《生之欲》的电影", "找与《生之欲》相似的电影", "像《生之欲》那样的电影"):
            with self.subTest(query=query):
                request = split_content_request(query)
                self.assertIsNone(request.issue)
                self.assertEqual(request.reference, "生之欲")


class IntegratedSearchTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.store = SearchIndexStore(self.db)
        self.docs = (doc(1, "A family reunion and unresolved tensions."),
                     doc(2, "A family reconnects at a gathering."), doc(3, "A space voyage."))
        self.embedding = FakeEmbedding()
        state = self.store.begin(self.docs, SPEC)
        self.store.step(state["id"], self.embedding)
        self.embedding.calls.clear()
        self.allowed = [d.film_id for d in self.docs]
        self.local = Mock(return_value={"version": "discovery.v1", "status": "keyword", "plan": None, "source": "local"})
        self.decision = Mock()
        self.decision.decide.return_value = RouteDecision("hybrid", .95, "exploratory")
        self.reranker = Mock()
        self.reranker.rank.side_effect = lambda query, documents: [.9 if "family" in t else .001 for t in documents]
        self.summary_rows = {d.film_id: {"id": d.film_id, "title": d.title, "year": 1990 + i}
                             for i, d in enumerate(self.docs)}
        self.hard_calls = []

        def resolved(plan, people_ids):
            return {"version": "discovery.v2", "plan": plan.model_dump(), "status": "ready", "source": "local",
                    "constraints": [], "issues": [], "people_ids": people_ids, "reason": None}

        def eligible(plan, people_ids):
            self.hard_calls.append(plan)
            return {"eligible_ids": [i for i in self.allowed if not plan.countries or i == self.docs[0].film_id]}

        self.engine = IntegratedSearch(self.store, SPEC, local_interpret=self.local,
            known_literal=lambda q: q == "Public Film 1", resolve_hard=resolved, eligible=eligible,
            summaries=lambda ids: {key: self.summary_rows[key] for key in ids if key in self.summary_rows},
            corpus_revision=lambda: corpus_revision(self.docs),
            reference_candidates=lambda title: [{"key": self.docs[0].film_id, "label": self.docs[0].title}]
                if title == "Public Film 1" else [], decision=self.decision, embedding=self.embedding, reranker=self.reranker)

    def test_exact_identity_and_complete_local_plan_have_zero_new_model_calls(self):
        self.assertEqual(self.engine.submit("Public Film 1")["status"], "keyword")
        self.local.return_value = {"status": "ready", "plan": SearchPlan(version="search-plan.v2", countries=["JP"]).model_dump()}
        self.assertEqual(self.engine.submit("Japanese films")["status"], "ready")
        self.decision.decide.assert_not_called()
        self.assertEqual(self.embedding.calls, [])
        self.reranker.rank.assert_not_called()

    def test_hard_plan_precedes_bounded_rerank_and_summaries(self):
        result = self.engine.submit("Japanese films about a family reunion, under 90 minutes")
        self.assertEqual(result["status"], "ready")
        self.assertEqual([r["film"]["id"] for r in result["results"]["items"]], [self.docs[0].film_id])
        self.assertEqual(len(self.reranker.rank.call_args.args[1]), 1)
        self.assertEqual(self.hard_calls[-1].countries, ["JP"])
        self.assertEqual(self.hard_calls[-1].duration_max, 90)
        self.assertEqual(self.decision.decide.call_args.args, ("a family reunion",))

    def test_restore_filter_edit_mutation_and_shrinking_offset_never_call_models(self):
        result = self.engine.submit("Japanese films about a family reunion")
        token = result["snapshot"]
        calls = (self.decision.decide.call_count, len(self.embedding.calls), self.reranker.rank.call_count)
        expanded = self.engine.resume("Japanese films about a family reunion", token,
            plan=SearchPlan(version="search-plan.v2"), offset=40, edited=True)
        self.assertEqual(expanded["results"]["offset"], 0)
        self.assertEqual(expanded["results"]["total"], 2)
        self.assertEqual(expanded["semantic"]["fallback"], "search_cached_local_ranking")
        self.allowed.remove(self.docs[0].film_id)
        restored = self.engine.resume("Japanese films about a family reunion", token)
        self.assertEqual(restored["results"]["total"], 0)
        self.assertEqual(calls, (self.decision.decide.call_count, len(self.embedding.calls), self.reranker.rank.call_count))

    def test_empty_hard_eligibility_can_recover_after_mutation_without_new_models(self):
        self.allowed = []
        result = self.engine.submit("films about a family reunion")
        self.assertEqual(result["results"]["total"], 0)
        self.reranker.rank.assert_not_called()
        self.allowed = [self.docs[0].film_id]
        restored = self.engine.resume("films about a family reunion", result["snapshot"])
        self.assertEqual(restored["results"]["total"], 1)
        self.assertEqual(len(self.embedding.calls), 1)
        self.reranker.rank.assert_not_called()

    def test_rerank_timeout_is_disclosed_and_keeps_local_hybrid(self):
        self.reranker.rank.side_effect = SemanticError("provider_http_429")
        result = self.engine.submit("films about a family reunion")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["semantic"]["fallback"], "provider_http_429")
        self.assertGreater(result["results"]["total"], 0)

    def test_reference_uses_content_vector_not_title_query_and_skips_decision_embedding(self):
        result = self.engine.submit('films similar to "Public Film 1"')
        self.assertEqual(result["status"], "ready")
        self.assertNotIn(self.docs[0].film_id, [r["film"]["id"] for r in result["results"]["items"]])
        self.decision.decide.assert_not_called()
        self.assertEqual(self.embedding.calls, [])
        self.assertEqual(self.reranker.rank.call_args.args[0], self.docs[0].chunks[0])

    def test_missing_reference_does_not_fuzzily_select_or_drop_identity(self):
        result = self.engine.submit('films similar to "Unknown Public Title"')
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIsNone(result["results"])
        self.decision.decide.assert_not_called()

    def test_known_missing_alias_or_unsupported_requirements_stop_before_models(self):
        for query in ("films produced by Shared Person about family", "films about family without violence"):
            self.assertEqual(self.engine.submit(query)["status"], "clarify")
        self.decision.decide.assert_not_called()
        self.assertEqual(self.embedding.calls, [])

    def test_route_model_cannot_discard_hard_conditions_by_selecting_keyword(self):
        self.decision.decide.return_value = RouteDecision("keyword", .99)
        result = self.engine.submit("Japanese films about a family reunion")
        self.assertEqual(result["status"], "clarify")
        self.assertIsNone(result["plan"])
        self.assertEqual(self.embedding.calls, [])

    def test_private_input_is_rejected_before_any_callback(self):
        with self.assertRaisesRegex(SemanticError, "private_input"):
            self.engine.submit("films about Movies//My Private Film.mkv")
        self.local.assert_not_called()
        self.decision.decide.assert_not_called()

    def test_modified_metadata_requires_explicit_resubmit_and_never_reembeds(self):
        result = self.engine.submit("films about a family reunion")
        self.docs = (*self.docs[:2], doc(3, "A changed space story."))
        with self.assertRaisesRegex(SemanticError, "search_index_stale"):
            self.engine.resume("films about a family reunion", result["snapshot"])
        self.assertEqual(len(self.embedding.calls), 1)

    def test_snapshot_cannot_introduce_an_outside_film(self):
        result = self.engine.submit("films about a family reunion")
        payload = self.store.snapshot(result["snapshot"], "films about a family reunion")
        payload["scores"]["film_" + "f" * 32] = 1
        bad_token = self.store.save_snapshot("films about a family reunion", payload)
        with self.assertRaisesRegex(SemanticError, "search_snapshot_invalid"):
            self.engine.resume("films about a family reunion", bad_token)

    def test_reference_clarification_survives_refresh_without_inference(self):
        question = 'films similar to "Unknown Public Title"'
        result = self.engine.submit(question)
        restored = self.engine.resume(question, result["snapshot"])
        self.assertEqual(restored["status"], "needs_clarification")
        self.assertEqual(restored["issues"][0]["field"], "reference")
        self.assertTrue(restored["semantic"]["requires_submit"])
        self.decision.decide.assert_not_called()
        self.reranker.rank.assert_not_called()

    def test_person_choice_snapshot_does_not_infer_when_last_choice_is_in_url(self):
        original = self.engine.resolve_hard
        def unresolved(plan, ids):
            result = original(plan, ids)
            if not ids:
                result.update(status="needs_clarification", issues=[
                    {"field": "people", "index": 0, "code": "choose_person", "candidates": []}])
            return result
        self.engine.resolve_hard = unresolved
        question = "films about a family reunion"
        result = self.engine.submit(question)
        self.assertEqual(result["status"], "needs_clarification")
        restored = self.engine.resume(question, result["snapshot"], people_ids={"0": "person_" + "a" * 32})
        self.assertEqual(restored["reason"], "search_snapshot_requires_submit")
        self.assertIsNone(restored["results"])
        self.decision.decide.assert_not_called()
        self.assertEqual(self.embedding.calls, [])

    def test_cancellation_between_stages_stops_all_later_models(self):
        for phase in ("before", "decision", "embedding", "rerank"):
            with self.subTest(phase=phase):
                cancelled = {"value": phase == "before"}
                self.decision.reset_mock(side_effect=True)
                self.reranker.reset_mock(side_effect=True)
                self.embedding.calls.clear()
                def decide(_q):
                    cancelled["value"] = phase == "decision"
                    return RouteDecision("hybrid", .99, "exploratory")
                def rank(_q, docs):
                    cancelled["value"] = phase == "rerank"
                    return [.95] * len(docs)
                old_embed = self.embedding.embed
                def embed(*args, **kwargs):
                    values = old_embed(*args, **kwargs)
                    cancelled["value"] = phase == "embedding"
                    return values
                self.decision.decide.side_effect = decide
                self.reranker.rank.side_effect = rank
                self.embedding.embed = embed
                try:
                    result = self.engine.submit("films about a family reunion", cancelled=lambda: cancelled["value"])
                finally:
                    self.embedding.embed = old_embed
                self.assertEqual(result["reason"], "search_cancelled")
                if phase == "before": self.decision.decide.assert_not_called()
                if phase in {"before", "decision"}: self.assertEqual(self.embedding.calls, [])
                if phase != "rerank": self.reranker.rank.assert_not_called()


if __name__ == "__main__":
    unittest.main()
