"""Synthetic counterexamples; no real questions, answers or provider requests."""
import re
import unittest

import test_integrated_search as integration
import test_explore_query as fixture
from app.services.search_local import LocalSearch
from app.services.content_request import split_content_request
from app.services.content_clauses import normalize_hard
from app.services.search_literals import hard_plan


class ClauseBoundaryTests(unittest.TestCase):
    def test_soft_preferences_are_kept_in_semantic_text(self):
        for question in (
            "想看人与邻居建立信任的故事，不要求温馨结局。",
            "想看艺术家的故事，不必同演员或同导演。",
            "我找的是一个演员失去声音的故事，不是老师逼他练习的那部。",
            "想看记忆或者感知改变自我的故事。",
            "films about family, not merely people sharing a house",
            "films about ambition, not necessarily a happy ending",
            "Not the film where a teacher demands perfect music. I mean a story of someone losing their voice.",
        ):
            with self.subTest(question=question):
                parsed = split_content_request(question)
                self.assertIsNone(parsed.issue, parsed)
                self.assertTrue(parsed.text)
                self.assertTrue(parsed.is_content)
                self.assertIsNone(parsed.hard.year_min)
        parsed = split_content_request("films about family, not merely people sharing a house")
        self.assertIn("not merely", parsed.text)

    def test_year_clauses_and_local_only_controls_do_not_become_plot(self):
        for question, lower, upper in (
            ("只在本地片库里找，电影年份是 1961—1968：一对陌生人交换秘密的故事。没有匹配就返回空结果。", 1961, 1968),
            ("想看重逢的故事，只要电影年份在1975年及之后的。", 1975, None),
            ("想看家庭照顾的故事，只要上映年份是1952年或更早的。", None, 1952),
            ("films released between 1971 and 1973: a family builds a boat", 1971, 1973),
        ):
            with self.subTest(question=question):
                parsed = split_content_request(question)
                self.assertIsNone(parsed.issue, parsed)
                self.assertEqual((parsed.hard.year_min, parsed.hard.year_max), (lower, upper))
                self.assertNotIn("返回空结果", parsed.text)

    def test_protected_plot_nouns_are_not_genre_facts(self):
        for content in ("a family", "a comedy", "western landscapes"):
            question = "films about " + content + ", after 1987"
            parsed = split_content_request(question)
            self.assertIsNone(parsed.issue, parsed)
            self.assertEqual(parsed.hard.genres, [])
            self.assertEqual(parsed.hard.year_min, 1988)
            self.assertEqual(parsed.text, content)

    def test_languages_are_strict_separate_conditions_when_segmented(self):
        parsed = split_content_request("films in French about a family crossing a border, after 2001")
        self.assertIsNone(parsed.issue, parsed)
        self.assertEqual([(x.kind, x.code, x.exclude) for x in parsed.hard.languages], [("spoken", "fr", False)])
        self.assertEqual(parsed.hard.countries, [])
        self.assertEqual(parsed.hard.year_min, 2002)
        excluded = split_content_request("films about family, not Japanese movies")
        self.assertIsNone(excluded.issue, excluded)
        self.assertEqual(excluded.hard.exclude_countries, ["JP"])
        for question in ("films in Elvish about family", "films about family without violence",
                         "想看家庭的故事，但不要暴力。", "films produced by Unknown Person about family",
                         "films about family, 不要亚特兰蒂斯电影",
                         "想看家庭，不必同演员但必须是2001年以后的电影",
                         "想看家庭故事，但必须不是未知内容", "films about family, must not have unknown material",
                         "films about ambition, not necessarily a comedy and must be in Elvish",
                         "films about ambition, not necessarily a comedy but must not include unknown material",
                         "想看家庭故事，不要求温馨结局而且只能是未知类型"):
            with self.subTest(question=question):
                self.assertIsNotNone(split_content_request(question).issue)

    def test_soft_scope_cannot_consume_a_new_mandatory_clause(self):
        for question in (
            "想看家庭故事，不要求温馨结局但是必须没有暴力",
            "想看家庭故事，不必同演员并且必须由某人主演",
            "想看家庭故事，不要求喜剧且必须非常温柔",
            "films about family, not necessarily scary but must be Japanese films",
            "films about family, not necessarily scary and must be gentle",
        ):
            with self.subTest(question=question):
                parsed = split_content_request(question)
                # Unsupported requirements must not become unconstrained SQL or
                # soft model input; a future supported plan may bind them fully.
                self.assertIsNotNone(parsed.issue, parsed)

    def test_optional_scope_and_residual_hard_check_share_boundaries(self):
        for soft in ("不要求温馨结局", "不必同演员"):
            for conjunction in ("但是", "并且", "而且", "但", "且"):
                for whitespace in ("", " ", "\t", "\n"):
                    for mandatory in ("必须没有暴力", "只要日本电影", "只能是未知类型"):
                        question = "想看家庭故事，"+soft+conjunction+whitespace+mandatory
                        with self.subTest(question=question):
                            self.assertIsNotNone(split_content_request(question).issue)
        for soft in ("not necessarily scary", "not merely scenery"):
            for conjunction in ("and", "but", "also", "however"):
                for whitespace in (" ", "  ", "\t", "\n"):
                    for mandatory in ("must be Japanese films", "only Japanese films", "must not include unknown material"):
                        question = "films about family, "+soft+" "+conjunction+whitespace+mandatory
                        with self.subTest(question=question):
                            self.assertIsNotNone(split_content_request(question).issue)

    def test_narrative_modals_are_not_user_filter_requirements(self):
        for question in (
            "想看一个人必须独自抚养孩子的故事",
            "films about a spy who must be rescued",
            "想看一个只能靠记忆辨认朋友的人",
            "films about a spy who fails and must be rescued",
            "想看一个人失去工作并且必须独自照顾家人的故事",
        ):
            with self.subTest(question=question):
                parsed = split_content_request(question)
                self.assertIsNone(parsed.issue, parsed)
                self.assertEqual(parsed.hard.countries, [])
                self.assertEqual(parsed.hard.people, [])
        for question in (
            "films about a spy, must be Japanese films",
            "films about a spy, but only Japanese films",
            "想看家庭故事，不要求温馨结局但只要日本电影",
            "想看家庭故事，不要求温馨结局但是 必须没有暴力",
        ):
            with self.subTest(question=question):
                self.assertIsNotNone(split_content_request(question).issue)

    def test_story_context_does_not_prove_a_negated_clause_is_plot_contrast(self):
        for question in (
            "想看家庭故事，不是来自亚特兰蒂斯",
            "想看家庭故事，并非日本制作的",
            "想看家庭故事，不是恐怖类型",
            "想看家庭故事，不是来自亚特兰蒂斯的那部",
            '想看家庭故事，不是《Unknown Exact Title》的那部',
            "想看家庭故事，不是由未知人物主演的那部",
        ):
            with self.subTest(question=question):
                parsed = split_content_request(question)
                self.assertIsNotNone(parsed.issue, parsed)

    def test_referential_syntax_requires_local_narrative_not_metadata_evidence(self):
        for negative in (
            "不是日本的那部", "不是科幻的那部", "不是亚特兰蒂斯拍摄的那部",
            "并非某国制作的那部", "不是主演来自亚特兰蒂斯的那部",
        ):
            with self.subTest(negative=negative):
                self.assertIsNotNone(split_content_request("想看家庭故事，"+negative).issue)
        for negative in (
            "the country is Atlantis", "the genre is science fiction",
            "it was filmed in Atlantis", "a man discovers the country is Atlantis",
        ):
            question = "Not the film where "+negative+". I mean a story of a family."
            with self.subTest(question=question):
                self.assertIsNotNone(split_content_request(question).issue)
        for question in (
            "想看一个人失去声音的故事，不是老师逼他练习的那部",
            "想看一个人离家的故事，不是母亲寻找孩子的那部",
            "Not the film where a teacher demands perfect music. I mean a story of a family.",
            "Not the movie in which a mother searches for a child. I mean a story about a reunion.",
        ):
            with self.subTest(question=question):
                parsed = split_content_request(question)
                self.assertIsNone(parsed.issue, parsed)
                self.assertEqual(parsed.hard.exclude_countries, [])
                self.assertEqual(parsed.hard.exclude_genres, [])

    def test_later_topic_does_not_discard_preceding_factual_clauses(self):
        contrast = "Not the movie in which a mother searches for a child. I mean a story about a reunion."
        parsed = split_content_request("Japanese films. "+contrast)
        self.assertIsNone(parsed.issue, parsed)
        self.assertEqual(parsed.hard.countries, ["JP"])
        for unknown in ("Atlantis films", "films produced by Unknown Person", "films in Elvish"):
            with self.subTest(unknown=unknown):
                self.assertIsNotNone(split_content_request(unknown+". "+contrast).issue)

    def test_hard_exclusion_preserves_full_title_punctuation(self):
        names = {"Night!": "film_"+"1"*32, "Night": "film_"+"2"*32}
        lookup = lambda title: [{"key": names[title]}] if title in names else []
        for text in ("excluding Night!", 'excluding "Night!"'):
            plan, issue = hard_plan(text, lookup)
            self.assertIsNone(issue, (text, issue))
            self.assertEqual(plan.exclude_film_ids, [names["Night!"]])
        parsed = split_content_request("films about a reunion, excluding Night!", lookup=lookup)
        self.assertIsNone(parsed.issue, parsed)
        self.assertEqual(parsed.hard.exclude_film_ids, [names["Night!"]])

    def test_normalization_never_trims_characters_from_a_literal_name(self):
        for text in ("但丁导演的电影", "也字演员主演的电影", "starring A Person的", 'excluding "A Film的"', "由某的执导"):
            self.assertEqual(normalize_hard(text), text)

    def test_no_change_person_control_requires_and_preserves_a_named_role(self):
        request = split_content_request("films directed by Named Person about a voyage, 不要换导演凑数")
        self.assertIsNone(request.issue, request)
        self.assertEqual([(p.name, p.role) for p in request.hard.people], [("Named Person", "director")])
        self.assertIsNotNone(split_content_request("films about a voyage, 不要换导演凑数").issue)

    def test_no_relaxation_instructions_need_an_actual_hard_condition(self):
        for question in ("想看重逢故事，年份不能放宽", "想看邻居互助的故事，不要换导演凑数"):
            self.assertIsNotNone(split_content_request(question).issue)
        parsed = split_content_request("找1961—1964 年的电影：一个人学习造船的故事。年份不能放宽。")
        self.assertIsNone(parsed.issue, parsed)
        self.assertEqual((parsed.hard.year_min, parsed.hard.year_max), (1961, 1964))

    def test_story_dates_are_never_invented_as_release_constraints(self):
        parsed = split_content_request("films about a child living in a village after a war")
        self.assertIsNone(parsed.issue, parsed)
        self.assertIsNone(parsed.hard.year_min)
        # An unsegmented numeral is ambiguous; stopping is preferable to treating
        # a story date as a release date or dropping it.
        self.assertIsNotNone(split_content_request("films about a village during 1946").issue)


class QualifiedReferenceTests(unittest.TestCase):
    setUp = integration.IntegratedSearchTests.setUp

    def test_numeric_reference_title_keeps_an_adjacent_identity_year(self):
        request = split_content_request('films like "A Tale 2001" (1971)')
        self.assertIsNone(request.issue, request)
        self.assertEqual(request.reference_year, 1971)
        self.assertIsNone(request.hard.year_min)

    def test_reference_year_is_identity_qualification_not_result_release_filter(self):
        self.engine.reference_candidates = lambda title: [
            {"key": d.film_id, "label": "Shared Title", "year": 1990 + i}
            for i, d in enumerate(self.docs[:2])] if title == "Shared Title" else []
        question = 'films like "Shared Title" (1991), about family'
        parsed = split_content_request(question)
        self.assertIsNone(parsed.issue, parsed)
        self.assertEqual(parsed.reference_year, 1991)
        self.assertIsNone(parsed.hard.year_min)
        result = self.engine.submit(question)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["semantic"]["reference_id"], self.docs[1].film_id)
        self.assertNotIn(self.docs[1].film_id, [x["film"]["id"] for x in result["results"]["items"]])
        missing = self.engine.submit('films like "Shared Title" (1997)')
        self.assertEqual(missing["status"], "needs_clarification", missing)
        self.assertIsNone(missing["results"])

    def test_self_exclusion_and_soft_comparison_preserve_reference(self):
        question = '像《Public Film 1》(1990)那样探讨家庭关系，不必同演员；不要原片。'
        self.engine.reference_candidates = lambda title: [
            {"key": self.docs[0].film_id, "label": title, "year": 1990}] if title == "Public Film 1" else []
        parsed = split_content_request(question)
        self.assertIsNone(parsed.issue, parsed)
        self.assertIn("不必同演员", parsed.text)
        result = self.engine.submit(question)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["semantic"]["reference_id"], self.docs[0].film_id)
        self.assertNotIn(self.docs[0].film_id, [x["film"]["id"] for x in result["results"]["items"]])
        self.decision.decide.assert_not_called()
        self.assertEqual(self.embedding.calls, [])


    def mentions(self, text):
        rows = [{"title": match[0], "start": match.start(), "end": match.end()}
                for doc in self.docs for match in re.finditer(re.escape(doc.title), text)]
        return sorted(rows, key=lambda row: row["start"])

    def test_explicit_alternative_reference_requires_local_identity_choice(self):
        self.engine.title_mentions = self.mentions
        self.engine.reference_candidates = lambda title: [
            {"key": doc.film_id, "label": doc.title, "year": 1990+i}
            for i, doc in enumerate(self.docs) if doc.title == title]
        question = '找几部像《Shared Label》那样的，原片不要；英文名我记不清是 Public Film 1 还是 Public Film 2。'
        first = self.engine.submit(question)
        self.assertEqual(first["status"], "needs_clarification", first)
        self.assertEqual({row["key"] for row in first["issues"][0]["candidates"]},
                         {doc.film_id for doc in self.docs[:2]})
        self.decision.decide.assert_not_called()
        self.reranker.rank.assert_not_called()
        chosen = self.engine.submit(question, reference_id=self.docs[1].film_id)
        self.assertEqual(chosen["status"], "ready", chosen)
        self.assertEqual(chosen["semantic"]["reference_id"], self.docs[1].film_id)
        self.assertNotIn(self.docs[1].film_id, [x["film"]["id"] for x in chosen["results"]["items"]])
        bad = self.engine.submit(question, reference_id=self.docs[2].film_id)
        self.assertEqual(bad["status"], "needs_clarification")

    def test_literal_alternatives_cannot_become_similar_recommendations(self):
        self.engine.title_mentions = self.mentions
        question = '帮我找那部《Shared Label》，英文名我记不清是 Public Film 1 还是 Public Film 2。'
        for selected in (None, self.docs[0].film_id):
            result = self.engine.submit(question, reference_id=selected)
            self.assertEqual(result["status"], "clarify", result)
            self.assertEqual(result["reason"], "ambiguous_film")
            self.assertIsNone(result["results"])
        self.decision.decide.assert_not_called()
        self.reranker.rank.assert_not_called()
        self.assertEqual(self.embedding.calls, [])

    def test_uncertainty_clause_cannot_drop_a_requirement(self):
        self.engine.title_mentions = self.mentions
        for question in (
            'films like "Shared Label", not sure whether Public Film 1 or Public Film 2, in Elvish',
            '像《Shared Label》那样的电影；英文名我记不清是 Public Film 1 还是 Public Film 2 但必须2002年以后',
        ):
            with self.subTest(question=question):
                result = self.engine.submit(question)
                self.assertIn(result["status"], ("clarify", "needs_clarification"), result)
                self.assertIsNone(result["results"])
        self.reranker.rank.assert_not_called()


class StrictSQLBoundaryTests(unittest.TestCase):
    _seed_library = fixture.ExploreQueryTests._seed_library
    _seed_facts = fixture.ExploreQueryTests._seed_facts
    _add_credit = staticmethod(fixture.ExploreQueryTests._add_credit)
    _add_genre = staticmethod(fixture.ExploreQueryTests._add_genre)
    _add_country = staticmethod(fixture.ExploreQueryTests._add_country)
    tearDown = fixture.ExploreQueryTests.tearDown

    def setUp(self):
        fixture.ExploreQueryTests.setUp(self)
        self.local = LocalSearch(self.engine)

    def _add_literal(self, title, year, key):
        from app.services.library import library_manager
        folder = self.root / key
        folder.mkdir()
        video = folder / "synthetic.mkv"
        video.write_bytes(key.encode())
        library_manager.add_observations([{
            "title": title, "original_title": title, "year": year,
            "media_path": str(video.resolve()), "video_file": video.name,
            "folder_path": str(folder.resolve()), "folder_name": folder.name,
            "file_size": video.stat().st_size, "file_mtime": video.stat().st_mtime,
            "library_status": "available", "metadata_source": "filename",
            "scrape_status": "pending", "last_seen_at": fixture.NOW,
            "source_item_key": key,
        }])

    def test_numeric_reference_year_is_not_a_second_real_local_title_mention(self):
        self._add_literal("1984", 1984, "numeric-reference")
        for question in ('films like "1984" (1984), recommend other films',
                         '像《1984》(1984)那样的电影'):
            with self.subTest(question=question):
                self.assertEqual(len(self.local.title_mentions(question)), 2)
                parsed = split_content_request(question, lookup=self.local.reference_candidates,
                    mentions=self.local.title_mentions)
                self.assertIsNone(parsed.issue, parsed)
                self.assertEqual(parsed.reference, "1984")
                self.assertEqual(parsed.reference_year, 1984)
                self.assertIsNone(parsed.hard.year_min)
        ambiguous = split_content_request('films like "1984" or "Beta", recommend other films',
            lookup=self.local.reference_candidates, mentions=self.local.title_mentions)
        self.assertEqual(ambiguous.issue, "ambiguous_reference")

    def test_multiple_real_title_uncertainty_declarations_never_overwrite(self):
        for index, title in enumerate(("Amber", "Birch", "Cedar", "Dune")):
            self._add_literal(title, 1990+index, "choice-"+str(index))
        for question in (
            'films like "Shared Label", not sure whether Amber or Birch, not sure whether Cedar or Dune',
            '像《Shared Label》那样的电影；英文名我记不清是 Amber 还是 Birch；英文名我记不清是 Cedar 还是 Dune',
        ):
            with self.subTest(question=question):
                self.assertEqual(len(self.local.title_mentions(question)), 4)
                parsed = split_content_request(question, lookup=self.local.reference_candidates,
                    mentions=self.local.title_mentions)
                self.assertEqual(parsed.issue, "ambiguous_reference", parsed)
                self.assertEqual(parsed.choice_titles, ())

    def test_unknown_language_cannot_satisfy_positive_or_negative_requirement(self):
        for question in ("films about a family, in French", "films in French about a reunion",
                         "films about a family, not in French"):
            with self.subTest(question=question):
                parsed = split_content_request(question, lookup=self.local.reference_candidates)
                self.assertIsNone(parsed.issue, parsed)
                self.assertEqual(parsed.hard.countries, [])
                result = self.local.executor.query(parsed.hard)
                self.assertEqual(result["status"], "ready", result)
                self.assertEqual(result["results"]["total"], 0)

    def test_year_and_person_hard_filters_run_before_content_and_unknown_names_clarify(self):
        question = "电影年份是1961—1964：一个人学习造船的故事。"
        parsed = split_content_request(question)
        self.assertIsNone(parsed.issue, parsed)
        result = self.local.executor.query(parsed.hard)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["results"]["total"], 0)
        parsed = split_content_request("films directed by Unknown Name about a family")
        self.assertIsNone(parsed.issue, parsed)
        result = self.local.executor.query(parsed.hard)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIsNone(result["results"])


if __name__ == "__main__":
    unittest.main()
