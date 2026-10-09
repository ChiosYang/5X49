import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import event, inspect
from sqlmodel import Session, create_engine, select

import app.services.cinema_dna as dna_module
import app.services.viewings as viewing_module
import test_explore_query as explore_fixture
from app.canonical_models import (
    Assertion, CinemaDnaFilmReadModel, Concept, Film, FilmProfileState,
    GraphEntity, LibraryItem, LocalProfile, Person, ProjectionState, Viewing,
)
from app.database import configure_sqlite_engine
from app.main import app
from app.migrations.backup import create_verified_backup
from app.migrations.restore import restore_verified_backup
from app.migrations.runner import run_migrations
from app.migrations.versions import MIGRATIONS
from app.portability import build_export_payload
from app.services.cinema_dna import cinema_dna_service as dna
from app.services.projections import ProjectionUnavailable, projection_coordinator
from app.services.user_state import film_profile_state_manager
from app.services.viewings import viewing_manager


class CinemaDnaTests(unittest.TestCase):
    # Reuse the factual fixture without inheriting/rerunning its test methods.
    _seed_library = explore_fixture.ExploreQueryTests._seed_library
    _seed_facts = explore_fixture.ExploreQueryTests._seed_facts
    _add_credit = staticmethod(explore_fixture.ExploreQueryTests._add_credit)
    _add_genre = staticmethod(explore_fixture.ExploreQueryTests._add_genre)
    _add_country = staticmethod(explore_fixture.ExploreQueryTests._add_country)

    def setUp(self):
        explore_fixture.ExploreQueryTests.setUp(self)
        self._engines.update({module: module.engine for module in (dna_module, viewing_module)})
        dna_module.engine = viewing_module.engine = self.engine
        with Session(self.engine) as session:
            self.profile_id = session.exec(select(LocalProfile.id).where(LocalProfile.profile_key == "local")).one()

    tearDown = explore_fixture.ExploreQueryTests.tearDown

    def _rate(self, film_id, rating):
        return film_profile_state_manager.upsert(film_id, rating=rating, fields_set={"rating"})

    def _extra_films(self, count, *, start=10, rating=3, year=2012):
        ids = []
        with Session(self.engine) as session:
            for index in range(start, start + count):
                film_id = f"film_{index:032x}"
                ids.append(film_id)
                session.add(GraphEntity(id=film_id, entity_type="film"))
                session.flush()
                session.add(Film(id=film_id, canonical_title=f"Fixture {index:04d}", release_year=year))
                session.flush()
                session.add(Viewing(id=f"view_{index:032x}", profile_id=self.profile_id, film_id=film_id, source="diary", source_record_id=film_id))
                session.add(FilmProfileState(profile_id=self.profile_id, film_id=film_id, rating=rating))
            session.commit()
        return ids

    def test_empty_unrated_and_threshold_boundaries(self):
        # Existing fixture has one unrated confirmed Viewing.
        self.assertEqual(dna.overview()["totals"], {"watched_films": 1, "viewing_records": 1, "rated_films": 0})
        self.assertEqual(dna.facets("decade", metric="preference")["items"], [])
        self._rate(self.films["Beta"], 5)
        viewing_manager.create(self.films["Alpha"], None)
        self._rate(self.films["Alpha"], 1)
        extras = self._extra_films(7)
        self.assertEqual(dna.overview()["needed_global_ratings"], 1)
        self.assertEqual(dna.facets("decade", metric="preference")["total"], 0)
        self._extra_films(1, start=30, year=1991, rating=3)
        rows = {item["key"]: item for item in dna.facets("decade", metric="preference")["items"]}
        self.assertEqual(rows["1990"]["preference"], 3)
        self.assertEqual(rows["1990"]["rated_count"], 3)
        self._rate(extras[0], None)
        self.assertEqual(dna.facets("decade", metric="preference")["items"], [])
        with Session(self.engine) as session:
            for viewing in session.exec(select(Viewing)).all():
                viewing.deleted_at = "2026-09-10"
                session.add(viewing)
            session.commit()
        self.assertEqual(dna.overview()["totals"]["watched_films"], 0)
        self.assertEqual(dna.facets("genre")["items"], [])

    def test_rewatch_dates_and_manual_toggle_do_not_change_film_weight(self):
        film_id = self.films["Beta"]
        self._rate(film_id, 4)
        first = viewing_manager.create(film_id, "2026-09-01")
        second = viewing_manager.create(film_id, "2026-09-01")
        before = dna.facets("decade")["items"]
        viewing_manager.update(first["id"], None)
        self.assertEqual(before, dna.facets("decade")["items"])
        film_profile_state_manager.upsert(film_id, watched=True, fields_set={"watched"})
        self.assertEqual(dna.overview()["totals"]["viewing_records"], 4)
        film_profile_state_manager.upsert(film_id, watched=False, fields_set={"watched"})
        viewing_manager.delete(second["id"])
        viewing_manager.delete(second["id"])
        self.assertEqual(dna.overview()["totals"], {"watched_films": 1, "viewing_records": 2, "rated_films": 1})

    def test_historical_films_survive_media_retirement_and_multiple_editions(self):
        film_id = self.films["Beta"]
        expected = dna.overview()
        with Session(self.engine) as session:
            item = session.exec(select(LibraryItem).where(LibraryItem.film_id == film_id)).one()
            clone = LibraryItem(**{**item.model_dump(), "id": "item_" + "f" * 32, "source_item_key": "second-edition"})
            session.add(clone)
            session.commit()
        self.assertEqual(expected, dna.overview())
        for status in ("ignored", "retired", "available"):
            with Session(self.engine) as session:
                for item in session.exec(select(LibraryItem).where(LibraryItem.film_id == film_id)).all():
                    item.availability_status = status
                    session.add(item)
                session.commit()
            self.assertEqual(expected, dna.overview())
            row = dna.contributors("decade", "1990")["items"][0]
            self.assertEqual(row["in_library"], status == "available")
            self.assertEqual(len(viewing_manager.list_film(film_id)), 1)

    def test_coverage_person_roles_and_fact_decisions_update(self):
        viewing_manager.create(self.films["Alpha"], None)
        viewing_manager.create(self.films["Gamma"], "2025")
        coverage = {d["dimension"]: d["coverage"] for d in dna.overview()["dimensions"]}
        self.assertEqual(coverage["country"], {"total_films": 3, "covered_films": 2, "conflicted_films": 1, "missing_films": 0})
        with Session(self.engine) as session:
            self._add_credit(session, self.films["Alpha"], self.people["shared"], "Acting", "Actor", "d")
            person = session.get(Person, self.people["shared"])
            person.canonical_name = "Renamed Person"
            session.add(person)
            session.commit()
        person = next(row for row in dna.facets("person")["items"] if row["key"] == self.people["shared"])
        self.assertEqual((person["film_count"], person["roles"], person["label"]), (2, ["actor", "director"], "Renamed Person"))
        with Session(self.engine) as session:
            assertion = session.exec(select(Assertion).where(Assertion.subject_entity_id == self.films["Beta"])).one()
            assertion.review_status = "rejected"
            assertion.review_method = "user"
            assertion.reviewed_by_profile_id = self.profile_id
            assertion.review_policy_version = None
            session.add(assertion)
            session.commit()
        self.assertEqual(sum(row["film_count"] for row in dna.facets("genre")["items"]), 2)

    def test_profile_isolation_external_sources_and_inactive_films(self):
        with Session(self.engine) as session:
            session.add(LocalProfile(id="profile_other", profile_key="other", display_name="Other"))
            session.flush()
            session.add(Viewing(id="view_foreign", profile_id="profile_other", film_id=self.films["Alpha"], source="external", source_record_id="foreign"))
            for status in ("confirmed", "needs_review", "rejected"):
                session.add(Viewing(id="view_" + status, profile_id=self.profile_id, film_id=self.films["Beta"], source="external", source_record_id=status, review_status=status))
            session.commit()
        self.assertEqual(dna.overview()["totals"]["viewing_records"], 2)
        with Session(self.engine) as session:
            film = session.get(Film, self.films["Beta"])
            film.lifecycle_status = "tombstoned"
            session.add(film)
            session.commit()
        self.assertEqual(dna.overview()["totals"]["watched_films"], 0)

    def test_atomic_failure_readiness_rebuild_restore_and_export(self):
        before = dna.overview()
        with patch.object(projection_coordinator, "_refresh_cinema_dna", side_effect=RuntimeError("projection failure")):
            with self.assertRaisesRegex(RuntimeError, "projection failure"):
                self._rate(self.films["Beta"], 5)
        self.assertEqual(before, dna.overview())
        with Session(self.engine) as session:
            before_hash = session.get(ProjectionState, "cinema_dna").digest
            projection_coordinator.rebuild_all(session)
            session.commit()
            self.assertEqual(session.get(ProjectionState, "cinema_dna").digest, before_hash)
        payload, version = build_export_payload(self.engine)
        self.assertEqual(version, 6)
        self.assertNotIn("cinema_dna", json.dumps(payload))
        backup = create_verified_backup(self.database_path, self.root / "backup", app_version="test", source_schema_version=6, target_schema_version=6)
        self._rate(self.films["Beta"], 5)
        self.engine.dispose()
        restore_verified_backup(backup.manifest_path, self.database_path,
                                expected_target_sha256=hashlib.sha256(self.database_path.read_bytes()).hexdigest())
        self.assertEqual(before, dna.overview())
        with Session(self.engine) as session:
            state = session.get(ProjectionState, "cinema_dna")
            state.status = "failed"
            session.add(state)
            session.commit()
        with self.assertRaises(ProjectionUnavailable):
            dna.overview()

    def test_api_contract_validation_privacy_pagination_and_unavailable(self):
        self._extra_films(10)
        client = TestClient(app)  # No lifespan: all services use the isolated engine.
        try:
            summary = client.get("/profile/cinema-dna")
            self.assertEqual(summary.status_code, 200)
            page = client.get("/profile/cinema-dna/contributors?dimension=decade&key=2010&limit=3")
            self.assertEqual((page.json()["total"], len(page.json()["items"]), page.json()["next_offset"]), (10, 3, 3))
            self.assertEqual(client.get("/profile/cinema-dna/contributors?dimension=country&key=ZZ").json()["items"], [])
            for query in ("dimension=theme&key=x", "dimension=country&key=../", "dimension=genre&key=person_bad", "dimension=decade&key=2010&limit=101", "dimension=decade&key=2010&offset=-1"):
                self.assertEqual(client.get("/profile/cinema-dna/contributors?" + query).status_code, 422)
            self.assertEqual(client.get("/profile/cinema-dna/facets/genre?metric=invalid").status_code, 422)
            self._rate(self.films["Beta"], 3)
            film_profile_state_manager.upsert(self.films["Beta"], notes="PRIVATE_DNA_CANARY", fields_set={"notes"})
            all_output = json.dumps([dna.overview(), dna.facets("genre"), dna.contributors("decade", "1990")])
            for private in ("PRIVATE_DNA_CANARY", "notes", "origin_ref", "media_path", "token", str(self.root)):
                self.assertNotIn(private, all_output)
            with patch.object(dna, "overview", side_effect=ProjectionUnavailable("cinema_dna projection is unavailable")):
                response = client.get("/profile/cinema-dna")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["detail"]["code"], "projection_unavailable")
        finally:
            client.close()

    def test_200_and_1000_film_queries_have_fixed_reads_and_stable_results(self):
        self._extra_films(199)
        for count in (200, 1000):
            if count == 1000:
                self._extra_films(800, start=209)
            overview = dna.overview()
            self.assertEqual(overview["totals"]["watched_films"], count)
            for dimension in overview["dimensions"]:
                coverage = dimension["coverage"]
                self.assertEqual(sum(coverage[k] for k in ("covered_films", "conflicted_films", "missing_films")), count)
            for query in (dna.overview, lambda: dna.facets("decade"), lambda: dna.contributors("decade", "2010")):
                statements = []
                def record(*args):
                    statements.append(args[2])
                event.listen(self.engine, "before_cursor_execute", record)
                started = time.perf_counter()
                try:
                    result = query()
                    elapsed_ms = (time.perf_counter() - started) * 1000
                finally:
                    event.remove(self.engine, "before_cursor_execute", record)
                self.assertLessEqual(len(statements), 10)
                self.assertEqual(result, query())
                if "items" in result:
                    self.assertLessEqual(len(result["items"]), result["limit"])
                print(f"Cinema DNA fixture={count} sql={len(statements)} ms={elapsed_ms:.1f}")

class CinemaDnaMigrationTests(unittest.TestCase):
    def test_v4_to_v5_upgrade_is_additive_backed_up_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "upgrade.db"
            engine = create_engine(f"sqlite:///{path}")
            configure_sqlite_engine(engine)
            try:
                run_migrations(engine, path, migrations=MIGRATIONS[:4], backup_required=False)
                self.assertNotIn("cinema_dna_film_read_model", inspect(engine).get_table_names())
                result = run_migrations(engine, path, backup_dir=root / "backups")
                self.assertEqual(result.applied_versions, (5, 6))
                self.assertTrue(result.backup.manifest_path.exists())
                projection_coordinator.bootstrap(engine)
                self.assertEqual(run_migrations(engine, path).applied_versions, ())
                self.assertIn("cinema_dna_film_read_model", inspect(engine).get_table_names())
            finally:
                engine.dispose()


class CinemaDnaFormulaTests(unittest.TestCase):
    @staticmethod
    def row(index, rating, countries):
        return {
            "film_id": f"film_{index:032x}", "title": f"Film {index}", "year": 1991,
            "rating": rating, "viewing_count": 1, "in_library": False,
            "coverage": {"genre": "missing", "person": "missing", "country": "covered" if countries else "missing", "decade": "covered"},
            "facts": [{"dimension": "country", "key": key, "label": key, "source": {"source_kind": "nfo"}} for key in countries],
        }

    def test_category_gate_independent_of_global_gate_and_multilabel_denominator(self):
        rows = [self.row(i, 5 if i < 2 else 3, ["JP", "FR"] if i < 2 else ["US"]) for i in range(10)]
        with patch.object(dna, "_load", return_value=rows):
            exposure = {item["key"]: item for item in dna.facets("country")["items"]}
            self.assertEqual(exposure["JP"]["share"], 0.2)
            self.assertAlmostEqual(sum(item["share"] for item in exposure.values()), 1.2)
            self.assertIsNone(exposure["JP"]["preference"])
            self.assertEqual([item["key"] for item in dna.facets("country", metric="preference")["items"]], ["US"])
            rows.append(self.row(11, 2, ["JP", "FR"]))
            ranked = dna.facets("country", metric="preference")["items"]
            self.assertEqual([item["key"] for item in ranked], ["FR", "JP", "US"])
            self.assertEqual(ranked[0]["preference"], 4)
            self.assertEqual(dna.contributors("country", "JP", metric="preference")["total"], 3)
            rows.append(self.row(12, None, ["JP"]))
            self.assertEqual(dna.contributors("country", "JP", metric="preference")["total"], 3)
            self.assertEqual(dna.contributors("country", "JP")["total"], 4)

    def test_preference_orders_unrounded_mean_then_sample_count_then_key(self):
        # Both display as 4.0, but 4 + 1/21 must precede 4 + 1/22.
        rows = [self.row(i, 5 if i == 0 else 4, ["JP"]) for i in range(21)]
        rows += [self.row(i + 100, 5 if i == 0 else 4, ["FR"]) for i in range(22)]
        rows += [self.row(i + 200, 4, ["US", "CA"]) for i in range(3)]
        with patch.object(dna, "_load", return_value=rows):
            page = dna.facets("country", metric="preference", limit=2)
            self.assertEqual([item["key"] for item in page["items"]], ["JP", "FR"])
            self.assertEqual(page["next_offset"], 2)
            self.assertEqual([item["key"] for item in dna.facets("country", metric="preference", offset=2)["items"]], ["CA", "US"])
