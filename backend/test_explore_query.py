import hashlib
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import event as sqlalchemy_event
from sqlmodel import Session, create_engine, delete, select

import app.database as database
import app.services.event_store as event_store_module
import app.services.explore_query as explore_query_module
import app.services.library as library_module
import app.services.operation_snapshots as snapshots_module
import app.services.user_state as user_state_module
from app.canonical_models import (
    Assertion,
    AssertionProvenance,
    Concept,
    Credit,
    CreditProvenance,
    ExploreFacetReadModel,
    ExploreFilmReadModel,
    Film,
    FilmCountry,
    FilmCountryProvenance,
    GraphEntity,
    LocalProfile,
    Person,
    ProjectionState,
    Viewing,
)
from app.contracts.analysis_persistence import assertion_qualifier_hash, assertion_semantic_key
from app.contracts.structured_metadata import credit_semantic_key, normalize_metadata_text
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.services.explore_query import explore_query_service
from app.services.library import library_manager
from app.services.projections import ProjectionUnavailable, projection_coordinator


NOW = "2026-09-01T00:00:00+00:00"


class ExploreQueryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.database_path = self.root / "library.db"
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        configure_sqlite_engine(self.engine)
        run_migrations(self.engine, self.database_path, app_version="test", backup_required=False)
        projection_coordinator.bootstrap(self.engine)
        self._engines = {
            module: module.engine
            for module in (
                database,
                event_store_module,
                explore_query_module,
                library_module,
                snapshots_module,
                user_state_module,
            )
        }
        for module in self._engines:
            module.engine = self.engine
        self.films = self._seed_library()
        self.people = self._seed_facts()

    def tearDown(self):
        for module, original in self._engines.items():
            module.engine = original
        self.engine.dispose()
        self._tmp.cleanup()

    def test_overview_reports_fact_coverage_conflicts_and_people_roles(self):
        overview = explore_query_service.overview()
        self.assertEqual(overview["total_films"], 3)
        dimensions = {item["dimension"]: item for item in overview["dimensions"]}
        self.assertEqual(dimensions["genre"]["coverage"]["covered_films"], 3)
        self.assertEqual(dimensions["person"]["coverage"]["covered_films"], 3)
        self.assertEqual(dimensions["country"]["coverage"], {
            "total_films": 3,
            "covered_films": 2,
            "conflicted_films": 1,
            "missing_films": 0,
        })
        self.assertEqual(dimensions["decade"]["coverage"]["covered_films"], 3)
        people = explore_query_service.list_facets("person", query="shared", limit=30, offset=0)
        self.assertEqual(people["total"], 1)
        self.assertEqual(people["items"][0]["key"], self.people["shared"])
        self.assertEqual(people["items"][0]["roles"], ["actor", "director"])
        self.assertEqual(people["items"][0]["owned_count"], 2)
        self.assertEqual(people["items"][0]["watched_count"], 1)

    def test_strict_filters_use_or_within_dimensions_and_and_across_dimensions(self):
        with Session(self.engine) as session:
            action = session.exec(select(Concept).where(Concept.canonical_name == "Action")).one()
            drama = session.exec(select(Concept).where(Concept.canonical_name == "Drama")).one()
        all_genres = explore_query_service.list_films(
            filters={"genre": [action.id, drama.id], "person": [], "country": [], "decade": []},
            view="all",
            sort="title",
            direction="asc",
            limit=40,
            offset=0,
        )
        self.assertEqual(all_genres["total"], 3)
        strict = explore_query_service.list_films(
            filters={
                "genre": [action.id],
                "person": [self.people["shared"]],
                "country": ["JP"],
                "decade": ["1990"],
            },
            view="unwatched",
            sort="year",
            direction="desc",
            limit=40,
            offset=0,
        )
        self.assertEqual(strict["total"], 1)
        self.assertEqual(strict["items"][0]["film"]["id"], self.films["Alpha"])
        self.assertEqual(
            {fact["dimension"] for fact in strict["items"][0]["matched_facts"]},
            {"genre", "person", "country", "decade"},
        )

    def test_context_counts_and_preview_follow_strict_and_or_semantics(self):
        with Session(self.engine) as session:
            action = session.exec(select(Concept).where(Concept.canonical_name == "Action")).one()
            drama = session.exec(select(Concept).where(Concept.canonical_name == "Drama")).one()
        empty_filters = {dimension: [] for dimension in ("genre", "person", "country", "decade")}
        landing = explore_query_service.context(filters=empty_filters, view="all", limit=6)
        dimensions = {item["dimension"]: item for item in landing["dimensions"]}
        self.assertEqual(landing["current_total"], 3)
        self.assertEqual(dimensions["country"]["operator"], "and")
        japan = next(item for item in dimensions["country"]["items"] if item["key"] == "JP")
        self.assertEqual(japan["result_count"], 2)
        self.assertEqual(japan["additional_count"], 0)
        self.assertEqual(japan["preview_film"]["id"], self.films["Alpha"])

        action_context = explore_query_service.context(
            filters={**empty_filters, "genre": [action.id]},
            view="all",
            limit=6,
        )
        genre = next(
            item for item in action_context["dimensions"] if item["dimension"] == "genre"
        )
        self.assertEqual(genre["operator"], "or")
        drama_item = next(item for item in genre["items"] if item["key"] == drama.id)
        self.assertEqual(drama_item["result_count"], 3)
        self.assertEqual(drama_item["additional_count"], 1)
        self.assertEqual(drama_item["preview_film"]["id"], self.films["Gamma"])
        self.assertEqual(
            action_context,
            explore_query_service.context(
                filters={**empty_filters, "genre": [action.id]},
                view="all",
                limit=6,
            ),
        )

    def test_context_respects_view_and_can_recover_an_unresolved_dimension_with_or(self):
        empty_filters = {dimension: [] for dimension in ("genre", "person", "country", "decade")}
        unwatched = explore_query_service.context(filters=empty_filters, view="unwatched", limit=6)
        self.assertEqual(unwatched["current_total"], 2)
        country = next(
            item for item in unwatched["dimensions"] if item["dimension"] == "country"
        )
        japan = next(item for item in country["items"] if item["key"] == "JP")
        self.assertEqual(japan["result_count"], 1)

        unresolved = explore_query_service.context(
            filters={**empty_filters, "country": ["US"]},
            view="all",
            limit=6,
        )
        self.assertEqual(unresolved["current_total"], 0)
        country = next(
            item for item in unresolved["dimensions"] if item["dimension"] == "country"
        )
        self.assertEqual(country["operator"], "or")
        japan = next(item for item in country["items"] if item["key"] == "JP")
        self.assertEqual(japan["result_count"], 2)
        self.assertEqual(japan["additional_count"], 2)

    def test_context_current_total_matches_strict_films_for_every_dimension_and_view(self):
        with Session(self.engine) as session:
            action = session.exec(
                select(Concept).where(Concept.canonical_name == "Action")
            ).one()
        empty = {dimension: [] for dimension in ("genre", "person", "country", "decade")}
        cases = [
            ({**empty, "genre": [action.id]}, "all"),
            ({**empty, "person": [self.people["shared"]]}, "all"),
            ({**empty, "country": ["JP"]}, "all"),
            ({**empty, "decade": ["1990"]}, "all"),
            (empty, "watched"),
            (empty, "unwatched"),
            (
                {
                    "genre": [action.id],
                    "person": [self.people["shared"]],
                    "country": ["JP"],
                    "decade": ["1990"],
                },
                "unwatched",
            ),
        ]
        for filters, view in cases:
            with self.subTest(filters=filters, view=view):
                context = explore_query_service.context(filters=filters, view=view, limit=6)
                films = explore_query_service.list_films(
                    filters=filters,
                    view=view,
                    sort="title",
                    direction="asc",
                    limit=40,
                    offset=0,
                )
                self.assertEqual(context["current_total"], films["total"])

    def test_conflicted_or_unknown_facets_remain_unresolved_and_never_relax(self):
        with Session(self.engine) as session:
            conflicted = session.exec(
                select(ExploreFacetReadModel)
                .where(ExploreFacetReadModel.dimension == "country")
                .where(ExploreFacetReadModel.conflicted.is_(True))
            ).one()
        result = explore_query_service.list_films(
            filters={
                "genre": [],
                "person": [],
                "country": [conflicted.facet_key],
                "decade": [],
            },
            view="all",
            sort="title",
            direction="asc",
            limit=40,
            offset=0,
        )
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["unresolved_filters"][0]["key"], conflicted.facet_key)
        self.assertTrue(result["strict"])

    def test_missing_projection_fails_closed(self):
        with Session(self.engine) as session:
            session.exec(delete(ProjectionState).where(ProjectionState.name == "explore_facets"))
            session.commit()
        with self.assertRaises(ProjectionUnavailable):
            explore_query_service.overview()
        with self.assertRaises(ProjectionUnavailable):
            explore_query_service.context(
                filters={dimension: [] for dimension in ("genre", "person", "country", "decade")},
                view="all",
                limit=6,
            )

    def test_viewing_create_and_delete_refresh_watched_projection_and_counts(self):
        with Session(self.engine) as session:
            beta = session.get(ExploreFilmReadModel, self.films["Beta"])
            self.assertTrue(beta.watched)
            existing = session.exec(
                select(Viewing).where(Viewing.film_id == self.films["Beta"])
            ).one()
            existing.deleted_at = NOW
            existing.updated_at = NOW
            session.add(existing)
            session.commit()
        with Session(self.engine) as session:
            self.assertFalse(session.get(ExploreFilmReadModel, self.films["Beta"]).watched)
            profile_id = session.exec(select(LocalProfile.id)).one()
            session.add(Viewing(
                id="view_" + "f" * 32,
                profile_id=profile_id,
                film_id=self.films["Alpha"],
                watched_at="2026-09-02",
                watched_at_precision="date",
                source="diary",
                source_record_id="explore-watched-alpha",
                review_status="confirmed",
            ))
            session.commit()
        with Session(self.engine) as session:
            self.assertTrue(session.get(ExploreFilmReadModel, self.films["Alpha"]).watched)
        people = explore_query_service.list_facets("person", query="shared", limit=30, offset=0)
        self.assertEqual(people["items"][0]["watched_count"], 1)

    def test_decade_projection_handles_boundaries_and_missing_year(self):
        with Session(self.engine) as session:
            for title, year in (("Alpha", 1888), ("Beta", 1999), ("Gamma", 2000)):
                film = session.get(Film, self.films[title])
                film.release_year = year
                film.updated_at = NOW
                session.add(film)
            session.commit()
        facets = explore_query_service.list_facets("decade", query=None, limit=30, offset=0)
        self.assertEqual({item["key"] for item in facets["items"]}, {"1880", "1990", "2000"})
        with Session(self.engine) as session:
            film = session.get(Film, self.films["Alpha"])
            film.release_year = None
            film.updated_at = NOW
            session.add(film)
            session.commit()
        facets = explore_query_service.list_facets("decade", query=None, limit=30, offset=0)
        self.assertEqual({item["key"] for item in facets["items"]}, {"1990", "2000"})
        self.assertEqual(facets["coverage"]["missing_films"], 1)

    def test_person_search_paginates_high_cardinality_facets(self):
        with Session(self.engine) as session:
            for index in range(1000, 1105):
                suffix = f"{index:032x}"
                person_id = f"person_{suffix}"
                session.add(GraphEntity(id=person_id, entity_type="person", lifecycle_status="active"))
            session.flush()
            for index in range(1000, 1105):
                suffix = f"{index:032x}"
                person_id = f"person_{suffix}"
                name = f"Bulk Person {index}"
                session.add(Person(
                    id=person_id,
                    canonical_name=name,
                    normalized_name=normalize_metadata_text(name),
                    resolution_status="verified",
                    lifecycle_status="active",
                ))
            session.flush()
            for index in range(1000, 1105):
                suffix = f"{index:032x}"
                person_id = f"person_{suffix}"
                credit_id = f"credit_{suffix}"
                session.add(Credit(
                    id=credit_id,
                    film_id=self.films["Gamma"],
                    person_id=person_id,
                    department="Acting",
                    job="Actor",
                    semantic_key=credit_semantic_key(
                        self.films["Gamma"], person_id, "Acting", "Actor"
                    ),
                ))
                session.add(CreditProvenance(
                    id=f"cprov_{suffix}",
                    credit_id=credit_id,
                    origin_kind="curated",
                    origin_ref="bulk-person-fixture",
                    observed_at=NOW,
                ))
            session.commit()
        page = explore_query_service.list_facets(
            "person", query="bulk person", limit=30, offset=90
        )
        self.assertEqual(page["total"], 105)
        self.assertEqual(len(page["items"]), 15)
        self.assertIsNone(page["next_offset"])
        self.assertTrue(all(item["roles"] == ["actor"] for item in page["items"]))
        context = explore_query_service.context(
            filters={dimension: [] for dimension in ("genre", "person", "country", "decade")},
            view="all",
            limit=6,
        )
        people = next(item for item in context["dimensions"] if item["dimension"] == "person")
        self.assertEqual(len(people["items"]), 6)
        self.assertTrue(people["has_more"])

    def test_public_payload_contains_no_private_source_material(self):
        result = explore_query_service.list_films(
            filters={"genre": [], "person": [self.people["shared"]], "country": [], "decade": []},
            view="all",
            sort="title",
            direction="asc",
            limit=40,
            offset=0,
        )
        serialized = str(result).casefold()
        self.assertNotIn(str(self.root).casefold(), serialized)
        for forbidden in ("origin_ref", "source_ref", "absolute_path", "media_path", "token"):
            self.assertNotIn(forbidden, serialized)

        statements = []
        def count_statement(*_args):
            statements.append(1)
        sqlalchemy_event.listen(self.engine, "before_cursor_execute", count_statement)
        try:
            context = explore_query_service.context(
                filters={dimension: [] for dimension in ("genre", "person", "country", "decade")},
                view="all",
                limit=6,
            )
        finally:
            sqlalchemy_event.remove(self.engine, "before_cursor_execute", count_statement)
        self.assertLessEqual(len(statements), 10)
        serialized = str(context).casefold()
        self.assertNotIn(str(self.root).casefold(), serialized)
        for forbidden in ("origin_ref", "source_ref", "absolute_path", "media_path", "token"):
            self.assertNotIn(forbidden, serialized)

    def _seed_library(self) -> dict[str, str]:
        for index, (title, year) in enumerate((("Alpha", 1994), ("Beta", 1999), ("Gamma", 2005))):
            folder = self.root / title
            folder.mkdir()
            video = folder / f"{title}.mkv"
            video.write_bytes(title.encode("utf-8"))
            library_manager.add_observations([
                {
                    "title": title,
                    "original_title": title,
                    "year": year,
                    "media_path": str(video.resolve()),
                    "video_file": video.name,
                    "folder_path": str(folder.resolve()),
                    "folder_name": folder.name,
                    "file_size": video.stat().st_size,
                    "file_mtime": video.stat().st_mtime,
                    "library_status": "available",
                    "metadata_source": "filename",
                    "scrape_status": "pending",
                    "last_seen_at": NOW,
                    "source_item_key": f"explore-{index}",
                }
            ])
        with Session(self.engine) as session:
            rows = session.exec(select(Film)).all()
            return {row.canonical_title: row.id for row in rows}

    def _seed_facts(self) -> dict[str, str]:
        shared_id = "person_" + "a" * 32
        other_id = "person_" + "b" * 32
        with Session(self.engine) as session:
            for person_id, name in ((shared_id, "Shared Person"), (other_id, "Other Person")):
                session.add(GraphEntity(id=person_id, entity_type="person", lifecycle_status="active"))
                session.add(Person(
                    id=person_id,
                    canonical_name=name,
                    normalized_name=normalize_metadata_text(name),
                    resolution_status="verified",
                    lifecycle_status="active",
                ))
            session.flush()
            self._add_credit(session, self.films["Alpha"], shared_id, "Directing", "Director", "a")
            self._add_credit(session, self.films["Beta"], shared_id, "Acting", "Actor", "b")
            self._add_credit(session, self.films["Gamma"], other_id, "Acting", "Actor", "c")
            action = session.exec(select(Concept).where(Concept.canonical_name == "Action")).one()
            drama = session.exec(select(Concept).where(Concept.canonical_name == "Drama")).one()
            self._add_genre(session, self.films["Alpha"], action, "a")
            self._add_genre(session, self.films["Beta"], action, "b")
            self._add_genre(session, self.films["Gamma"], drama, "c")
            self._add_country(session, self.films["Alpha"], "JP", "alpha", "a")
            self._add_country(session, self.films["Beta"], "JP", "beta", "b")
            self._add_country(session, self.films["Gamma"], "US", "gamma-a", "c")
            self._add_country(session, self.films["Gamma"], "FR", "gamma-b", "d")
            profile_id = session.exec(select(LocalProfile.id)).one()
            session.add(Viewing(
                id="view_" + "e" * 32,
                profile_id=profile_id,
                film_id=self.films["Beta"],
                watched_at="2026-09-01",
                watched_at_precision="date",
                source="diary",
                source_record_id="explore-watched",
                review_status="confirmed",
            ))
            session.commit()
        return {"shared": shared_id, "other": other_id}

    @staticmethod
    def _add_credit(session: Session, film_id: str, person_id: str, department: str, job: str, suffix: str):
        credit_id = "credit_" + suffix * 32
        session.add(Credit(
            id=credit_id,
            film_id=film_id,
            person_id=person_id,
            department=department,
            job=job,
            semantic_key=credit_semantic_key(film_id, person_id, department, job),
        ))
        session.add(CreditProvenance(
            id="cprov_" + suffix * 32,
            credit_id=credit_id,
            origin_kind="nfo",
            origin_ref=f"film:{film_id}",
            observed_at=NOW,
        ))

    @staticmethod
    def _add_genre(session: Session, film_id: str, concept: Concept, suffix: str):
        qualifier_hash = assertion_qualifier_hash({})
        key = assertion_semantic_key(
            subject_entity_id=film_id,
            predicate="HAS_GENRE",
            object_entity_id=concept.id,
            qualifier_hash=qualifier_hash,
        )
        assertion_id = "assert_" + hashlib.sha256(key.encode()).hexdigest()[:32]
        session.add(Assertion(
            id=assertion_id,
            subject_entity_id=film_id,
            object_entity_id=concept.id,
            predicate="HAS_GENRE",
            qualifiers={},
            qualifier_hash=qualifier_hash,
            assertion_key=key,
            source_scope="factual",
            review_status="accepted",
            review_method="import_policy",
            review_policy_version="test.v1",
            reviewed_at=NOW,
            first_seen_at=NOW,
            last_seen_at=NOW,
        ))
        session.add(AssertionProvenance(
            id="aprov_" + suffix * 32,
            assertion_id=assertion_id,
            origin_kind="nfo",
            origin_scope="factual",
            origin_ref=f"film:{film_id}",
            source_field="genres",
            first_observed_at=NOW,
            last_observed_at=NOW,
        ))

    @staticmethod
    def _add_country(session: Session, film_id: str, code: str, origin_ref: str, suffix: str):
        country_id = "fcountry_" + suffix * 32
        session.add(FilmCountry(id=country_id, film_id=film_id, iso_3166_1=code))
        session.add(FilmCountryProvenance(
            id="fcprov_" + suffix * 32,
            film_country_id=country_id,
            origin_kind="nfo",
            origin_ref=origin_ref,
            observed_at=NOW,
        ))


if __name__ == "__main__":
    unittest.main()
