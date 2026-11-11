import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

import test_explore_query as fixture
from app.api import explore
from app.canonical_models import Film
from app.services import ask
from app.services.plot_search import rank_synopses


class SynopsisRankingTests(unittest.TestCase):
    def test_public_synopsis_paraphrases_and_distractors(self):
        corpus = Path(__file__).parent / "fixtures/semantic_search/public-holdout-corpus-v1.json"
        films = json.loads(corpus.read_text(encoding="utf-8"))["films"]
        texts = {film["title_en"]: film["paraphrase"]["zh"] for film in films}
        for question, expected in (
            ("找一部男乐手渐渐听不见、只好重新适应生活的电影", ["Sound of Metal"]),
            ("想看因为送错午饭而成为朋友的两个人的故事", ["The Lunchbox"]),
            ("父亲丢了谋生用的自行车，带儿子找车", ["Bicycle Thieves"]),
            ("想看宇航员在木星海底修复失踪潜艇的故事", []),
        ):
            with self.subTest(question=question):
                ranked = rank_synopses(question, texts.items())
                self.assertEqual([title for title, _ in ranked], expected)
                for title, excerpt in ranked:
                    self.assertIn(excerpt, texts[title])

    def test_extracts_late_passage_and_stable_top_five(self):
        ending = "An obsolete lighthouse shelters a stranded sailor."
        text = "A quiet morning. " * 40 + ending
        rows = [(str(key), text) for key in reversed(range(7))] + [("blank", None)]
        hits = rank_synopses("a stranded sailor in a lighthouse", rows)
        self.assertEqual([key for key, _ in hits], list("01234"))
        for _, excerpt in hits:
            self.assertIn("stranded sailor", excerpt)
            self.assertIn(excerpt, text)
            self.assertLessEqual(len(excerpt), 240)

    def test_two_sentence_quote_starts_at_the_matching_language(self):
        source = "伊拉的午餐被误送给另一名职员。两人交换纸条，建立了友谊。"
        overview = "A lunch delivery takes an unexpected turn. " + source
        self.assertEqual(rank_synopses("想看因为送错午饭而成为朋友的故事", [("film", overview)]),
                         [("film", source)])


class LocalPlotRouteTests(unittest.TestCase):
    _seed_library = fixture.ExploreQueryTests._seed_library
    _seed_facts = fixture.ExploreQueryTests._seed_facts
    _add_credit = staticmethod(fixture.ExploreQueryTests._add_credit)
    _add_genre = staticmethod(fixture.ExploreQueryTests._add_genre)
    _add_country = staticmethod(fixture.ExploreQueryTests._add_country)
    tearDown = fixture.ExploreQueryTests.tearDown

    def setUp(self):
        fixture.ExploreQueryTests.setUp(self)
        self.enterContext(patch.object(ask, "engine", self.engine))
        self.enterContext(patch.object(explore, "_evaluation", return_value=None))
        interpreter = explore.discovery_search_service.ask.interpreter
        self.enterContext(patch.object(interpreter, "configured", return_value=False))
        self.enterContext(patch.object(interpreter, "interpret_search", side_effect=AssertionError("AI called")))
        app = FastAPI()
        app.include_router(explore.router)
        self.client = self.enterContext(TestClient(app))
        for title in ("Alpha", "Gamma"):
            self.overview(title, "暴雨中，一名水手在海岛的灯塔里过夜。")

    def overview(self, title, text):
        with Session(self.engine) as session:
            film = session.get(Film, self.films[title])
            film.overview = text
            session.add(film)
            session.commit()

    def post(self, route, question, **options):
        response = self.client.post("/explore/search/" + route, json={"question": question, "locale": "zh", **options})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_no_key_strict_filters_and_fresh_excerpt(self):
        q = "2000 年以后，关于水手在灯塔躲避暴雨的电影"
        for allow in (True, False):
            self.assertEqual(self.post("interpret", q, allow_ai=allow)["status"], "plot")
        result = self.post("plot", q)
        self.assertEqual(result["status"], "plot")
        self.assertEqual([(item["film"]["title"], item["excerpt"]) for item in result["plot_matches"]],
                         [("Gamma", "暴雨中，一名水手在海岛的灯塔里过夜。")])
        length_question = "少于 110 分钟，关于水手在灯塔躲避暴雨的电影"
        with Session(self.engine) as session:
            for title, minutes in (("Alpha", 99), ("Gamma", 110)):
                film = session.get(Film, self.films[title])
                film.runtime_minutes = minutes
                session.add(film)
            session.commit()
        self.assertEqual([item["film"]["title"] for item in self.post("plot", length_question)["plot_matches"]],
                         ["Alpha"])
        self.overview("Gamma", None)
        self.assertEqual(self.post("plot", q)["plot_matches"], [])
        self.assertEqual(self.post("interpret", "找 2000 年以前的电影")["plan"]["year_max"], 1999)
        self.assertEqual(self.post("interpret", "Alpha")["status"], "keyword")

    def test_invalid_or_unresolved_conditions_do_not_return_plot_hits(self):
        for q in ("films about a lighthouse, under ninety parsecs", "像《Alpha》那样的电影",
                  "films directed by Missing Person about a lighthouse"):
            self.assertNotEqual(self.post("plot", q)["status"], "plot", q)
        response = self.client.post("/explore/search/plot", json={"question": "find C:/private/test.mp4"})
        self.assertEqual(response.status_code, 422)
