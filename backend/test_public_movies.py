"""Public source/qrels validation and transport mocks; never live model calls."""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.evaluation import public_movie_pilot as pilot
from app.evaluation.public_movies import PublicFixture, hard_ids, load_fixture, score
from app.services.openrouter_embeddings import BudgetLedger, NvidiaFreeQuote, Quote, free_quota_preflight
from app.services.semantic_search import SemanticError
from test_openrouter_embeddings import Transport, metadata, nvidia_metadata


class PublicMovieTests(unittest.TestCase):
    def setUp(self):
        self.fixture = load_fixture(pilot.FIXTURE)
        self.raw = json.loads(pilot.FIXTURE.read_text(encoding="utf-8"))

    def test_real_identities_source_revisions_and_exact_local_aliases(self):
        f = self.fixture
        self.assertEqual(len({film.qid for film in f.films}), 24)
        still = next(film for film in f.films if film.key == "still-walking")
        self.assertEqual(still.qid, "Q874074")
        self.assertEqual(still.directors.value, ["Q740758"])
        for source in f.sources:
            if source.kind == "structured_metadata":
                self.assertTrue(source.revision.isdigit())
                self.assertEqual(source.license, "CC0-1.0")
        for case in f.cases:
            if case.kind == "identity":
                self.assertIsNone(case.embedding_query)
                self.assertEqual(len(case.expected_ids), 1)

    def test_public_scope_counts_shared_text_and_no_private_input(self):
        f = self.fixture
        self.assertEqual(len(f.inputs()), 38)
        self.assertEqual(sum(query for _, query in f.inputs()), 14)
        self.assertEqual(sum(c.reference_id is not None for c in f.cases), 2)
        self.assertLessEqual(sum(len(text.encode()) + 256 for text, _ in f.inputs()), 20000)
        for film in f.films:
            self.assertEqual(film.document().chunks, (film.document_text,))
        self.assertEqual(f.configuration["maximum_requests"], 42)
        self.assertFalse(f.configuration["production_enabled"])

    def test_work_year_never_uses_later_us_theatrical_label(self):
        films = {f.key: f for f in self.fixture.films}
        self.assertEqual(films["minari"].year.value, 2020)
        self.assertEqual(films["after-yang"].year.value, 2021)
        self.assertEqual(films["living"].year.value, 2022)

    def test_runtime_disagreement_is_retained_and_fails_hard_predicate(self):
        by_key = {f.key: f for f in self.fixture.films}
        self.assertEqual(by_key["past-lives"].minutes.status, "conflicted")
        self.assertIsNone(by_key["past-lives"].minutes.value)
        self.assertEqual({o.value for o in by_key["past-lives"].runtime_observations}, {105, 106})
        case = next(c for c in self.fixture.cases if c.id == "hard-zh-duration")
        self.assertEqual(case.expected_ids, [by_key["living"].id])
        self.assertNotIn(by_key["aftersun"].id, case.allowed_ids)

    def test_unsupported_truth_is_never_invented_for_watch_or_actor_role(self):
        from app.contracts.search_plan import SearchPlan
        for plan in (SearchPlan(version="search-plan.v2", view="unwatched"),
                     SearchPlan(version="search-plan.v2", people=[{"name":"王家卫","role":"actor"}])):
            with self.assertRaisesRegex(ValueError, "no watch history or actor truth"):
                hard_ids(self.fixture.films, self.fixture.people, plan)

    def test_qrels_are_graded_provisional_and_reference_itself_is_excluded(self):
        for c in self.fixture.cases:
            self.assertEqual(set(c.expected_ids), {q.film_id for q in c.qrels if q.grade >= 2})
            for q in c.qrels:
                self.assertTrue(q.reason)
                self.assertTrue(q.sources)
            if c.kind == "theme":
                self.assertEqual(c.qrels_status, "provisional-curated-not-human-gold")
            if c.reference_id:
                self.assertNotIn(c.reference_id, c.allowed_ids)
                self.assertNotIn(c.reference_id, [q.film_id for q in c.qrels])

    def test_schema_rejects_private_unproven_identity_grade_and_partial_hard_truth(self):
        mutations = [
            lambda d: d["films"][0].update(id=d["films"][1]["id"]),
            lambda d: d["films"][0].update(document_text="Movies//My Private Film.mkv"),
            lambda d: d["cases"][4].update(question="Japanese films featuring ~/Movies/private.mkv"),
            lambda d: d["cases"][10]["qrels"][0].update(grade=True),
            lambda d: d["cases"][20].update(expected_ids=[]),
            lambda d: d["configuration"].update(fallbacks=True),
            lambda d: d["configuration"].update(provider="other"),
        ]
        for mutation in mutations:
            data = deepcopy(self.raw)
            mutation(data)
            with self.subTest(mutation=mutation), self.assertRaises((ValidationError, ValueError)):
                PublicFixture.model_validate(data)

    def test_metrics_use_grades_and_report_abstention_instead_of_fake_hit(self):
        theme = next(c for c in self.fixture.cases if c.id == "theme-en-gathering")
        best = max(theme.qrels, key=lambda q: q.grade)
        weak = next(q for q in theme.qrels if q.grade == 1)
        self.assertGreater(score(theme, [best.film_id])["ndcg_at_10"], score(theme, [weak.film_id])["ndcg_at_10"])
        self.assertFalse(score(theme, [weak.film_id])["top1_hit"])
        empty = next(c for c in self.fixture.cases if c.kind == "no_answer")
        self.assertTrue(score(empty, [best.film_id])["no_answer_false_positive"])
        self.assertTrue(score(empty, [])["top1_hit"])
        with self.assertRaises(ValueError):
            score(theme, [best.film_id, best.film_id])

    def test_frozen_manifest_and_default_preparation_need_no_credentials_network_or_db(self):
        with patch.object(pilot, "http_session", side_effect=AssertionError("no HTTP")), \
                patch.object(pilot, "existing_credential", side_effect=AssertionError("no key")), \
                patch.object(sqlite3, "connect", side_effect=AssertionError("no DB")):
            report = pilot.run()
        self.assertEqual(report["status"], "frozen_preparation_no_inference")
        self.assertEqual(report["expected_requests"], 38)
        self.assertFalse(report["real_model"])

    def test_changed_fixture_fails_before_network_and_existing_run_cannot_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            changed = Path(folder) / "fixture.json"
            changed.write_text(json.dumps(self.raw) + " ", encoding="utf-8")
            with patch.object(pilot, "FIXTURE", changed), patch.object(pilot, "http_session") as network:
                with self.assertRaisesRegex(SemanticError, "public_fixture_not_frozen"):
                    pilot.run(execute=True, accept_nvidia_logging=True)
                network.assert_not_called()
            with patch.object(pilot, "RUN_ROOT", Path(folder)), patch.object(pilot, "http_session") as network:
                with self.assertRaisesRegex(SemanticError, "existing_run_requires_reconciliation"):
                    pilot.run(execute=True, accept_nvidia_logging=True)
                network.assert_not_called()

    def test_zero_price_public_ledger_accepts_42_but_never_43_and_does_not_expand_paid_scope(self):
        quote = NvidiaFreeQuote.from_metadata(nvidia_metadata())
        with tempfile.TemporaryDirectory() as folder:
            ledger = BudgetLedger(Path(folder) / "public", quote, scope="public-movies.v1")
            for _ in range(42):
                e = ledger.reserve(["public short fact"], False)
                ledger.settle(e, {"usage":{"prompt_tokens":1,"total_tokens":1,"cost":0}}, quote, .01)
            with self.assertRaisesRegex(SemanticError, "pilot_budget_blocked"):
                ledger.reserve(["one too many"], True)
            self.assertEqual(len(ledger.data["entries"]), 42)
            self.assertEqual(ledger.summary()["reported_cost_usd"], "0")
            with self.assertRaisesRegex(SemanticError, "public_trial_requires_free_model"):
                BudgetLedger(Path(folder)/"paid", Quote.from_metadata(metadata()), scope="public-movies.v1")
            self.assertFalse((Path(folder)/"paid").exists())

    def test_public_quota_uses_38_not_old_smoke_30(self):
        transport = Transport(nvidia=True)
        self.assertEqual(free_quota_preflight(transport,"mock",minimum_posts=38)["remaining"],50)
        from test_openrouter_embeddings import Response
        with patch.object(transport,"get",return_value=Response({"data":{"free_model_daily_requests":{"remaining":37}}})):
            with self.assertRaisesRegex(SemanticError,"insufficient_free_quota"):
                free_quota_preflight(transport,"mock",minimum_posts=38)

    def test_mock_run_saves_38_vectors_replays_without_http_and_preserves_unknown_prior(self):
        transport = Transport(nvidia=True)
        prior = {"receipt_sha256":"a"*64,"requests":1,"actual_cost_usd":None,"reservation_usd":"0.01","status":"halted_unreconciled"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "public"
            with patch.object(pilot,"RUN_ROOT",root), patch.object(pilot,"http_session",return_value=transport), \
                    patch.object(pilot,"existing_credential",return_value="synthetic-credential"), \
                    patch.object(pilot,"related_qwen_run",return_value=deepcopy(prior)), \
                    patch("app.services.openrouter_embeddings.sleep"):
                report = pilot.run(execute=True,accept_nvidia_logging=True)
            self.assertEqual(report["status"],"completed_public_movie_pilot")
            self.assertEqual(len(transport.calls),38)
            self.assertEqual(report["billing"]["requests"],38)
            self.assertEqual(report["related_prior_run"],prior)
            saved=json.loads((root/"vectors.json").read_text(encoding="utf-8"))
            self.assertEqual(len(saved["entries"]),38)
            frozen_before=(root/"vectors.json").read_bytes()
            with patch.object(pilot,"RUN_ROOT",root), patch.object(pilot,"http_session",side_effect=AssertionError("no replay HTTP")):
                replay=pilot.replay()
            self.assertEqual(replay["new_model_calls"],0)
            self.assertEqual((root/"vectors.json").read_bytes(),frozen_before)
            for method in report["methods"]:
                original=[r["actual_ids"] for r in report["methods"][method]["results"]]
                replayed=[r["actual_ids"] for r in replay["methods"][method]["results"]]
                self.assertEqual(original,replayed)
                self.assertEqual(report["methods"][method]["semantic_cases"]["cases"],16)
                self.assertEqual(report["methods"][method]["all_cases"]["hard_condition_violations"],0)
            self.assertNotIn(b"synthetic-credential",(root/"report.json").read_bytes())

    def test_changed_revision_or_missing_consent_makes_zero_embedding_posts(self):
        transport=Transport(nvidia=True)
        with tempfile.TemporaryDirectory() as folder, patch.object(pilot,"RUN_ROOT",Path(folder)/"public"), \
                patch.object(pilot,"http_session",return_value=transport), \
                patch.object(pilot,"related_qwen_run",return_value={}):
            with self.assertRaisesRegex(SemanticError,"nvidia_logging_confirmation_required"):
                pilot.run(execute=True)
            quote=NvidiaFreeQuote(Decimal(0),1792591667)
            with patch.object(pilot,"fetch_quote",return_value=quote):
                result=pilot.run(execute=True,accept_nvidia_logging=True)
            self.assertEqual(result["error"],"public_model_revision_changed")
            self.assertEqual(transport.calls,[])

    def test_failed_dispatch_stops_once_and_preserves_partial_vectors_and_receipt(self):
        transport=Transport(nvidia=True)
        transport.fail=True
        with tempfile.TemporaryDirectory() as folder, patch.object(pilot,"RUN_ROOT",Path(folder)/"public"), \
                patch.object(pilot,"http_session",return_value=transport), \
                patch.object(pilot,"related_qwen_run",return_value={"reservation_usd":"0.01"}), \
                patch.object(pilot,"existing_credential",return_value="synthetic-credential"):
            report=pilot.run(execute=True,accept_nvidia_logging=True)
            self.assertEqual(report["status"],"stopped")
            self.assertEqual(len(transport.calls),1)
            self.assertTrue(report["billing"]["halted"])
            with self.assertRaisesRegex(SemanticError,"existing_run_requires_reconciliation"):
                pilot.run(execute=True,accept_nvidia_logging=True)
            self.assertEqual(len(transport.calls),1)


class PublicHardExecutorTests(unittest.TestCase):
    """Real SQL executor over reviewed public projections, never a user DB."""
    @classmethod
    def setUpClass(cls):
        from sqlmodel import SQLModel, create_engine
        from app.canonical_models import (Concept, ExploreFacetReadModel, ExploreFilmReadModel,
            ExternalIdentity, Film, GraphEntity, LibraryFilmReadModel, Person, PersonAlias, ProjectionState)
        from app.services.projections import PROJECTION_VERSIONS
        from app.services.structured_metadata_vocab import STRUCTURED_METADATA_VOCABULARY as vocabulary
        from app.contracts.structured_metadata import normalize_metadata_text as norm
        cls.fixture=load_fixture(pilot.FIXTURE)
        cls.engine=create_engine("sqlite://")
        SQLModel.metadata.create_all(cls.engine)
        cls.people_ids={p.qid:"person_"+sha256(p.qid.encode()).hexdigest()[:32] for p in cls.fixture.people}
        with cls.engine.begin() as conn:
            def add(model,**fields):
                row=model(**fields)
                conn.execute(model.__table__.insert().values(**row.model_dump()))
            for name in ("library","explore_films","explore_facets"):
                add(ProjectionState,name=name,projection_version=PROJECTION_VERSIONS[name],status="ready",row_count=24)
            genres={}
            for label in {g for f in cls.fixture.films for g in f.genres.value}:
                entry=vocabulary.resolve_genre(label)
                cid="concept_"+sha256(entry.canonical_key.encode()).hexdigest()[:32]
                genres[label]=cid
                add(GraphEntity,id=cid,entity_type="concept")
                add(Concept,id=cid,kind="genre",canonical_name=entry.canonical_name,canonical_key=entry.canonical_key)
            for person in cls.fixture.people:
                pid=cls.people_ids[person.qid]
                add(GraphEntity,id=pid,entity_type="person")
                add(Person,id=pid,canonical_name=person.name,normalized_name=norm(person.name),resolution_status="verified")
                add(ExternalIdentity,id="external_"+person.qid,entity_id=pid,provider="wikidata",
                    external_id=person.qid,provenance_kind="public-fixture",provenance_ref=person.source)
            for film in cls.fixture.films:
                add(GraphEntity,id=film.id,entity_type="film")
                add(Film,id=film.id,canonical_title=film.title_en,release_year=film.year.value,runtime_minutes=film.minutes.value)
                add(LibraryFilmReadModel,film_id=film.id,sort_title=norm(film.title_en),release_year=film.year.value,
                    payload={"title":film.title_en,"runtime_minutes":film.minutes.value,"primary_item":None},
                    source_hash="0"*64,projection_version=PROJECTION_VERSIONS["library"])
                add(ExploreFilmReadModel,film_id=film.id,sort_title=norm(film.title_en),release_year=film.year.value,
                    source_hash="0"*64,projection_version=PROJECTION_VERSIONS["explore_films"])
                for dimension,keys in (("country",film.countries.value),
                        ("genre",[genres[g] for g in film.genres.value]),
                        ("person",[cls.people_ids[p] for p in film.directors.value if p in cls.people_ids])):
                    for key in keys:
                        add(ExploreFacetReadModel,dimension=dimension,facet_key=key,film_id=film.id,
                            display_label=key,normalized_label=norm(key),payload={"roles":["director"]} if dimension=="person" else {},
                            source_hash="0"*64,projection_version=PROJECTION_VERSIONS["explore_facets"])
            for person in cls.fixture.people:
                fid=next(f.id for f in cls.fixture.films if person.qid in f.directors.value)
                names={norm(n):n for n in person.aliases}
                for index,(normalized,name) in enumerate(names.items()):
                    add(PersonAlias,id=f"alias_{person.qid}_{index}",person_id=cls.people_ids[person.qid],film_id=fid,
                        identity_id="external_"+person.qid,name=name,normalized_name=normalized,
                        origin_kind="public-fixture",origin_ref=person.source,observed_at="2026-10-22T08:32:00Z")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_actual_sql_executor_matches_all_frozen_hard_truth(self):
        from app.services import ask as ask_module
        from app.services.search_execution import search_plan_executor
        with patch.object(ask_module,"engine",self.engine):
            for case in self.fixture.cases:
                if case.kind!="hard_conditions":continue
                with self.subTest(case=case.id):
                    result=search_plan_executor.eligible_ids(case.hard)
                    self.assertEqual(result["status"],"ready")
                    self.assertEqual(set(result["eligible_ids"]),set(case.expected_ids))

    def test_conflicted_duration_never_matches_even_if_both_values_meet_bound(self):
        from app.contracts.search_plan import SearchPlan
        from app.services import ask as ask_module
        from app.services.search_execution import search_plan_executor
        conflicted={f.id for f in self.fixture.films if f.minutes.status=="conflicted"}
        with patch.object(ask_module,"engine",self.engine):
            result=search_plan_executor.eligible_ids(SearchPlan(version="search-plan.v2",duration_max=10000))
        self.assertFalse(set(result["eligible_ids"]) & conflicted)


if __name__=="__main__":
    unittest.main()
