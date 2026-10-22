"""Synthetic contract tests. The hand-written vector map is NOT a language model."""
import json
from contextlib import closing
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session, select

import test_explore_query as fixture
from app.canonical_models import (Assertion, AssertionProvenance, Concept, Film,
    FilmMetadataOverride, GraphEntity, ExploreFacetReadModel)
from app.contracts.analysis_persistence import assertion_qualifier_hash, assertion_semantic_key
from app.contracts.search_plan import SearchPlan
from app.services import ask as ask_module
from app.services.ask import AskError
from app.services.search_execution import search_plan_executor
from app.services.semantic_content import collect_content
from app.services.semantic_search import (ContentDocument, ContentSource, ProviderSpec,
    SemanticCache, SemanticError, SemanticSearch, corpus_revision)
from app.evaluation.semantic_search import SemanticCase, evaluate, load_fixture


SPEC = ProviderSpec("synthetic/three-axes", "fixture-v1", 3)


class SyntheticProvider:
    """Explicit labels exercise transport/cache/ranking, never model accuracy."""
    spec = SPEC

    def __init__(self):
        self.calls = []

    def embed(self, texts, *, query):
        self.calls.append((tuple(texts), query))
        return [[1., 0., 0.] if any(word in text.lower() for word in ("space", "宇宙", "太空"))
                else [0., 1., 0.] if any(word in text.lower() for word in ("dream", "梦境"))
                else [0., 0., 1.] for text in texts]


def film_id(number):
    return "film_" + f"{number:032x}"


def document(number, text, title=None):
    return ContentDocument(film_id(number), title or f"Film {number}", (),
                           (ContentSource("overview", text, "library"),))


class SemanticCoreTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.cache = SemanticCache(self.db)
        self.provider = SyntheticProvider()
        self.docs = (document(1, "A space journey with a lost crew."),
                     document(2, "宇宙旅行中寻找失散的船员。"),
                     document(3, "A dream within another dream."))
        self.revision = self.cache.replace(self.docs, self.provider)
        self.engine = SemanticSearch(self.cache, SPEC, provider=self.provider)
        self.ids = [d.film_id for d in self.docs]

    def submit(self, question="space journey", **extra):
        return self.engine.submit(question, eligible_ids=self.ids,
                                  expected_revision=self.revision, **extra)

    def test_cross_language_fixture_retrieval_is_explicitly_not_real_quality(self):
        for question, first in (("space journey", 1), ("宇宙旅行", 2)):
            with self.subTest(question=question):
                page = self.submit(question)
                self.assertEqual({i["film_id"] for i in page["items"]}, set(self.ids[:2]))
                self.assertEqual(page["items"][0]["film_id"], film_id(first))
                self.assertFalse(page["real_model_quality_verified"])
                self.assertEqual(page["mode"], "offline-contract")
                self.assertEqual(page["items"][0]["sources"], ["overview:library"])

    def test_unchanged_documents_do_not_reembed_and_model_changes_invalidate(self):
        count = len(self.provider.calls)
        self.assertEqual(self.cache.replace(self.docs, self.provider), self.revision)
        self.assertEqual(len(self.provider.calls), count)
        changed = ProviderSpec(SPEC.name, "fixture-v2", 3)
        with self.assertRaisesRegex(SemanticError, "index_stale"):
            self.cache.documents(changed)

    def test_privacy_is_screened_before_excerpt_truncation_and_query_calls(self):
        count = len(self.provider.calls)
        for path in ("/private.mkv", "~/Movies/private.mkv", "Movies/My Private Film.mkv",
                     r"Movies\My Private Film.mkv", "/private.mkv"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(SemanticError, "private_input"):
                    document(7, "space " * 500 + path)
                with self.assertRaisesRegex(SemanticError, "private_input"):
                    self.submit(f"space journey featuring '{path}'")
        self.assertEqual(len(self.provider.calls), count)
        for title in ("Face/Off", "V/H/S", "9/11"):
            self.assertTrue(ContentDocument(film_id(8), title, (), self.docs[0].sources))

    def test_provider_shape_nan_zero_boolean_and_failure_preserve_old_index(self):
        for vector in ([1, 0], [float("nan"), 0, 1], [float("inf"), 0, 1],
                       [0, 0, 0], [True, 0, 1]):
            bad = SyntheticProvider()
            bad.embed = lambda texts, query=False, v=vector: [v] * len(texts)
            with self.subTest(vector=vector):
                with self.assertRaisesRegex(SemanticError, "invalid_vector"):
                    self.cache.replace((document(4, "changed space content"),), bad)
                self.assertEqual(self.cache.value("revision"), self.revision)
                self.assertEqual(set(self.cache.documents(SPEC)), set(self.ids))
        bad.embed = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private provider detail"))
        with self.assertRaisesRegex(SemanticError, "^provider_unavailable$"):
            self.cache.replace((document(4, "changed space content"),), bad)

    def test_missing_provider_and_empty_hard_selection_never_call_model(self):
        engine = SemanticSearch(self.cache, SPEC)
        with self.assertRaisesRegex(SemanticError, "not_configured"):
            engine.submit("space", eligible_ids=self.ids, expected_revision=self.revision)
        page = engine.submit("space", eligible_ids=[], expected_revision=self.revision)
        self.assertEqual(page["total"], 0)

    def test_similarity_uses_reference_content_and_exact_identity_not_title_vectors(self):
        candidates = self.engine.reference_candidates("ＦＩＬＭ １",
            {self.ids[0]: ("Film 1",), self.ids[1]: ("Film 1", "别名")})
        self.assertEqual(candidates, self.ids[:2])
        count = len(self.provider.calls)
        page = self.submit("Film 1", reference_id=self.ids[0])
        self.assertEqual([i["film_id"] for i in page["items"]], [self.ids[1]])
        self.assertEqual(len(self.provider.calls), count)
        with self.assertRaisesRegex(SemanticError, "reference_missing_content"):
            self.submit("A known title with no plot", reference_id=film_id(99))
        with self.assertRaisesRegex(SemanticError, "missing_content"):
            ContentDocument(film_id(99), "Title alone", (), ())

    def test_snapshots_restore_repage_and_survive_provider_outage_without_calls(self):
        page = self.submit()
        count = len(self.provider.calls)
        offline = SemanticSearch(self.cache, SPEC)
        restored = offline.resume(page["snapshot_id"], "space journey",
            eligible_ids=[self.ids[1]], expected_revision=self.revision, offset=40)
        self.assertEqual(restored["offset"], 0)
        self.assertEqual([i["film_id"] for i in restored["items"]], [self.ids[1]])
        self.assertEqual(len(self.provider.calls), count)
        for question in ("dream", "SPACE JOURNEY"):
            with self.assertRaisesRegex(SemanticError, "snapshot_mismatch"):
                offline.resume(page["snapshot_id"], question, eligible_ids=self.ids, expected_revision=self.revision)
        with self.assertRaisesRegex(SemanticError, "snapshot_expired"):
            SemanticSearch(self.cache, SPEC, clock=lambda: 10 ** 12).resume(
                page["snapshot_id"], "space journey", eligible_ids=self.ids, expected_revision=self.revision)

    def test_content_change_or_query_in_flight_cannot_relabel_old_ranking_as_current(self):
        page = self.submit()
        new = self.cache.replace((document(1, "A dream with no space crew"),), self.provider)
        with self.assertRaisesRegex(SemanticError, "snapshot_stale"):
            self.engine.resume(page["snapshot_id"], "space journey",
                eligible_ids=self.ids, expected_revision=new)
        count = len(self.provider.calls)
        with self.assertRaisesRegex(SemanticError, "index_stale"):
            self.submit()
        self.assertEqual(len(self.provider.calls), count)
        self.revision = new
        original = self.provider.embed
        def delayed(texts, *, query):
            if query:
                self.cache.replace((document(2, "Another dream"),), SyntheticProvider())
            return original(texts, query=query)
        self.provider.embed = delayed
        with self.assertRaisesRegex(SemanticError, "index_stale"):
            self.submit()

    def test_only_hard_eligible_candidates_reach_optional_bounded_reranker(self):
        class Rank:
            seen = []
            def rank(self, question, documents):
                self.seen = documents
                return [.9] * len(documents)
        ranker = Rank()
        engine = SemanticSearch(self.cache, SPEC, provider=self.provider, reranker=ranker)
        result = engine.submit("space journey", eligible_ids=[self.ids[1]], expected_revision=self.revision)
        self.assertEqual([i["film_id"] for i in result["items"]], [self.ids[1]])
        self.assertEqual(len(ranker.seen), 1)
        self.assertNotIn("lost crew", ranker.seen[0])
        ranker.rank = lambda *args: [float("nan")]
        with self.assertRaisesRegex(SemanticError, "invalid_rerank"):
            engine.submit("space journey", eligible_ids=[self.ids[1]], expected_revision=self.revision)

    def test_41_to_40_last_page_shrink_reuses_snapshot_without_provider_calls(self):
        docs = tuple(document(i, "space crew") for i in range(1, 42))
        revision = self.cache.replace(docs, self.provider)
        ids = [d.film_id for d in docs]
        page = self.engine.submit("space", eligible_ids=ids, expected_revision=revision)
        second = self.engine.resume(page["snapshot_id"], "space", eligible_ids=ids, expected_revision=revision, offset=40)
        count = len(self.provider.calls)
        self.assertEqual(len(second["items"]), 1)
        shrunk = self.engine.resume(page["snapshot_id"], "space", eligible_ids=ids[:40],
                                   expected_revision=revision, offset=40)
        self.assertEqual((shrunk["total"], shrunk["offset"], len(shrunk["items"])), (40, 0, 40))
        self.assertEqual(len(self.provider.calls), count)

    def test_dedicated_cache_persists_but_refuses_canonical_connection_and_corrupt_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "owned-semantic.sqlite"
            with closing(sqlite3.connect(path)) as connection:
                cache = SemanticCache(connection)
                revision = cache.replace(self.docs, self.provider)
                engine = SemanticSearch(cache, SPEC, provider=self.provider)
                page = engine.submit("space", eligible_ids=self.ids, expected_revision=revision)
            with closing(sqlite3.connect(path)) as connection:
                engine = SemanticSearch(SemanticCache(connection), SPEC)
                self.assertEqual(engine.resume(page["snapshot_id"], "space",
                    eligible_ids=self.ids, expected_revision=revision)["total"], 2)
        with closing(sqlite3.connect(":memory:")) as canonical:
            canonical.execute("CREATE TABLE film(id TEXT)")
            with self.assertRaisesRegex(SemanticError, "cache_not_owned"):
                SemanticCache(canonical)
            self.assertEqual(canonical.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'semantic_%'").fetchone()[0], 0)
        page = self.submit()
        self.db.execute("UPDATE semantic_snapshots SET ranked=?", (json.dumps([self.ids[0], self.ids[0]]),))
        with self.assertRaisesRegex(SemanticError, "snapshot_invalid"):
            self.engine.resume(page["snapshot_id"], "space journey", eligible_ids=self.ids, expected_revision=self.revision)

    def test_limits_and_corrupt_cached_text_fail_before_provider_calls(self):
        count = len(self.provider.calls)
        with self.assertRaisesRegex(SemanticError, "corpus_limit"):
            self.cache.replace([self.docs[0]] * 5001, self.provider)
        with self.assertRaisesRegex(SemanticError, "duplicate_identity"):
            self.cache.replace([self.docs[0]] * 2, self.provider)
        for dimensions in (True, 0, 4097, "3"):
            with self.assertRaisesRegex(SemanticError, "invalid_provider_spec"):
                ProviderSpec("synthetic", "v1", dimensions)
        with self.assertRaisesRegex(SemanticError, "invalid_eligible_ids"):
            self.engine.submit("space", eligible_ids=["../private"], expected_revision=self.revision)
        row = json.loads(self.db.execute("SELECT document FROM semantic_documents LIMIT 1").fetchone()[0])
        row["chunks"] = ["space featuring Movies/private.mkv"]
        self.db.execute("UPDATE semantic_documents SET document=? WHERE film_id=?", (json.dumps(row), self.ids[0]))
        with self.assertRaisesRegex(SemanticError, "private_input"):
            self.submit()
        self.assertEqual(len(self.provider.calls), count)

    def test_snapshots_are_bounded_and_metrics_expose_hard_violations_without_quality_claims(self):
        for _ in range(101):
            self.submit()
        self.assertEqual(self.db.execute("SELECT count(*) FROM semantic_snapshots").fetchone()[0], 100)
        cases = [SemanticCase("english-space", "space journey", tuple(self.ids[:2]), tuple(self.ids)),
                 SemanticCase("chinese-space", "宇宙旅行", tuple(self.ids[:2]), tuple(self.ids)),
                 SemanticCase("hard-country", "space", (self.ids[1],), (self.ids[1],))]
        report = evaluate(cases, {"hybrid-fixture": lambda case: [
            i["film_id"] for i in self.engine.submit(case.question, eligible_ids=case.hard_allowed_ids,
                expected_revision=self.revision)["items"]]})
        self.assertFalse(report["real_model"] or report["human_quality_verified"])
        self.assertEqual(report["methods"]["hybrid-fixture"]["recall_at_40"], 1)
        self.assertEqual(report["methods"]["hybrid-fixture"]["hard_condition_violations"], 0)
        bad = evaluate([cases[-1]], {"broken": lambda case: [self.ids[0]]})
        self.assertEqual(bad["methods"]["broken"]["hard_condition_violations"], 1)
        self.assertEqual(bad["methods"]["broken"]["precision_at_10"], 0)

    def test_reviewable_bilingual_pilot_manifest_has_independent_hard_truth_and_no_user_data(self):
        manifest = load_fixture(Path(__file__).parent / "fixtures" / "semantic_search" / "quality-v1.json")
        self.assertEqual(len(manifest.films), 8)
        self.assertEqual(len(manifest.cases), 24)
        self.assertEqual(sum(c.locale == "zh" for c in manifest.cases), 12)
        self.assertEqual(sum(c.locale == "en" for c in manifest.cases), 12)
        self.assertEqual(sum(c.reference is not None for c in manifest.cases), 2)
        self.assertTrue(all(len(f.document().chunks) == 1 for f in manifest.films))
        self.assertIn("not evidence of natural-language parsing", manifest.notice)
        broken = manifest.model_dump()
        broken["cases"][0]["expected"] = [999]
        with self.assertRaises(ValueError):
            type(manifest).model_validate(broken)
        broken = manifest.model_dump()
        broken["cases"][20]["allowed"] = [1,3,6,8]  # Film 1 is not watched.
        with self.assertRaises(ValueError):
            type(manifest).model_validate(broken)

    def test_standalone_model_core_does_not_load_application_database_or_chat_client(self):
        result = subprocess.run([sys.executable, "-c",
            "import sys; from app.services.semantic_search import SemanticSearch; "
            "assert 'app.database' not in sys.modules; assert 'openai' not in sys.modules"],
            cwd=Path(__file__).parent, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


class SemanticLibraryBridgeTests(unittest.TestCase):
    _seed_library = fixture.ExploreQueryTests._seed_library
    _seed_facts = fixture.ExploreQueryTests._seed_facts
    _add_credit = staticmethod(fixture.ExploreQueryTests._add_credit)
    _add_genre = staticmethod(fixture.ExploreQueryTests._add_genre)
    _add_country = staticmethod(fixture.ExploreQueryTests._add_country)
    tearDown = fixture.ExploreQueryTests.tearDown

    def setUp(self):
        fixture.ExploreQueryTests.setUp(self)
        target = patch.object(ask_module, "engine", self.engine)
        target.start()
        self.addCleanup(target.stop)
        with Session(self.engine) as session:
            for title in ("Alpha", "Beta"):
                film = session.get(Film, self.films[title])
                film.overview = "space crew" if title == "Alpha" else "宇宙旅行"
                session.add(film)
            session.commit()

    def test_factual_bridge_matches_sql_executor_and_never_ignores_unknown_values(self):
        for values in ({}, {"countries": ["JP", "FR"]}, {"exclude_countries": ["JP"]},
                       {"year_min": 1990, "year_max": 1995}, {"view": "unwatched"},
                       {"people": [{"name": "Shared Person", "role": "director"}]},
                       {"people": [{"name": "Shared Person", "role": "director"},
                                   {"name": "Shared Person", "role": "actor"}]}):
            plan = SearchPlan(version="search-plan.v2", **values)
            ids = search_plan_executor.eligible_ids(plan)
            result = search_plan_executor.query(plan)
            self.assertEqual(ids["status"], result["status"])
            if ids["status"] == "ready":
                self.assertEqual(set(ids["eligible_ids"]), {i["film"]["id"] for i in result["results"]["items"]})
        unknown = search_plan_executor.eligible_ids(SearchPlan(version="search-plan.v2", countries=["Atlantis"]))
        self.assertEqual(unknown["status"], "needs_clarification")
        self.assertNotIn("eligible_ids", unknown)
        with self.assertRaisesRegex(AskError, "search_candidate_limit"):
            search_plan_executor.eligible_ids(SearchPlan(version="search-plan.v2"), maximum=1)

    def test_corpus_labels_actual_overview_source_manual_overrides_and_missing_content(self):
        corpus = collect_content(self.engine)
        docs = {d.film_id: d for d in corpus.documents}
        self.assertEqual(docs[self.films["Alpha"]].source_labels, ["overview:library"])
        self.assertEqual(corpus.excluded[self.films["Gamma"]], "missing_content")
        self.assertIn(self.films["Gamma"], corpus.identities)
        with Session(self.engine) as session:
            session.add(FilmMetadataOverride(film_id=self.films["Alpha"], values={"overview": "A dream"}))
            session.commit()
        changed = collect_content(self.engine)
        self.assertNotEqual(corpus.revision, changed.revision)
        self.assertEqual(next(d for d in changed.documents if d.film_id == self.films["Alpha"]).source_labels,
                         ["overview:user"])
        with Session(self.engine) as session:
            film = session.get(Film, self.films["Beta"])
            film.overview = "space featuring Movies/private.mkv"
            session.add(film)
            session.commit()
        self.assertEqual(collect_content(self.engine).excluded[self.films["Beta"]], "private_input")

    def test_reviewed_themes_keep_interpretive_label_and_withdrawn_or_proposed_are_excluded(self):
        with Session(self.engine) as session:
            for index, status in ((80, "accepted"), (81, "proposed")):
                concept_id = "con_" + f"{index:032x}"
                session.add(GraphEntity(id=concept_id, entity_type="concept"))
                session.flush()
                session.add(Concept(id=concept_id, kind="theme", canonical_key=f"synthetic-theme-{index}",
                                    canonical_name=f"Dream theme {index}"))
                session.flush()
                qualifier = assertion_qualifier_hash({})
                key = assertion_semantic_key(subject_entity_id=self.films["Gamma"], predicate="HAS_THEME",
                    object_entity_id=concept_id, qualifier_hash=qualifier)
                assertion_id = "assert_" + f"{index:032x}"
                session.add(Assertion(id=assertion_id, subject_entity_id=self.films["Gamma"],
                    object_entity_id=concept_id, predicate="HAS_THEME", qualifiers={}, qualifier_hash=qualifier,
                    assertion_key=key, source_scope="inferred", review_status=status,
                    review_method="import_policy" if status == "accepted" else "none",
                    review_policy_version="synthetic.v1" if status == "accepted" else None,
                    reviewed_at=fixture.NOW if status == "accepted" else None,
                    first_seen_at=fixture.NOW, last_seen_at=fixture.NOW))
                session.flush()
                session.add(AssertionProvenance(id="aprov_" + f"{index:032x}", assertion_id=assertion_id,
                    origin_kind="user", origin_scope="inferred", origin_ref="synthetic",
                    first_observed_at=fixture.NOW, last_observed_at=fixture.NOW))
            session.commit()
        corpus = collect_content(self.engine)
        theme = next(d for d in corpus.documents if d.film_id == self.films["Gamma"])
        self.assertEqual(theme.source_labels, ["reviewed_theme:user"])
        self.assertEqual([s.text for s in theme.sources], ["Dream theme 80"])
        with Session(self.engine) as session:
            provenance = session.get(AssertionProvenance, "aprov_" + f"{80:032x}")
            provenance.superseded_at = fixture.NOW
            session.add(provenance)
            session.commit()
        self.assertEqual(collect_content(self.engine).excluded[self.films["Gamma"]], "missing_content")


if __name__ == "__main__":
    unittest.main()
