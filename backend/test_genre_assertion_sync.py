import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine, select

import app.services.event_store as event_store_module
import app.services.library as library_module
import app.services.user_state as user_state_module
from app.canonical_models import (
    Assertion,
    AssertionProvenance,
    Concept,
    GraphEntity,
    LocalProfile,
    StructuredMetadataReview,
)
from app.contracts.analysis_persistence import (
    AssertionPredicateKey,
    STRUCTURED_GENRE_IMPORT_POLICY_VERSION,
    assertion_qualifier_hash,
    assertion_semantic_key,
)
from app.contracts.structured_metadata import GenreObservation, StructuredMetadataObservation
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.models import EventRecord, Movie
from app.services.event_store import event_store
from app.services.genre_assertion_backfill import backfill_factual_genre_assertions
from app.services.genre_assertion_sync import genre_assertion_synchronizer
from app.services.library import library_manager
from app.services.structured_metadata_sync import structured_metadata_synchronizer


class GenreAssertionSyncTests(unittest.TestCase):
    def setUp(self):
        self._original_library_engine = library_module.engine
        self._original_event_engine = event_store_module.engine
        self._original_user_state_engine = user_state_module.engine
        self._tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self._tmp.name) / "genre-assertions.db"
        self.engine = create_engine(f"sqlite:///{self.database_path}")
        configure_sqlite_engine(self.engine)
        import app.models  # noqa: F401

        SQLModel.metadata.create_all(self.engine)
        run_migrations(
            self.engine,
            self.database_path,
            app_version="test",
            backup_required=False,
        )
        library_module.engine = self.engine
        event_store_module.engine = self.engine
        user_state_module.engine = self.engine

    def tearDown(self):
        library_module.engine = self._original_library_engine
        event_store_module.engine = self._original_event_engine
        user_state_module.engine = self._original_user_state_engine
        self.engine.dispose()
        self._tmp.cleanup()

    def test_sources_share_assertions_and_refresh_only_their_provenance(self):
        library_manager.add_movies([self._movie("shared-sources")])
        film_id, library_item_id = self._owner()

        self._sync(
            film_id,
            library_item_id,
            origin_kind="legacy_movie",
            origin_ref=library_item_id,
            observed_at="2026-08-25T00:00:00+00:00",
            genres=(GenreObservation("Sci-Fi"), GenreObservation("Sci-Fi"), GenreObservation("Drama")),
        )
        self._sync(
            film_id,
            library_item_id,
            origin_kind="nfo",
            origin_ref=library_item_id,
            observed_at="2026-08-25T00:01:00+00:00",
            genres=(GenreObservation("Science Fiction", tmdb_id=878),),
        )
        self._sync(
            film_id,
            library_item_id,
            origin_kind="tmdb",
            origin_ref="tmdb.movie:4242",
            observed_at="2026-08-25T00:02:00+00:00",
            genres=(GenreObservation("Science Fiction", tmdb_id=878),),
        )

        with Session(self.engine) as session:
            assertions = session.exec(select(Assertion)).all()
            provenance = session.exec(select(AssertionProvenance)).all()
            science_fiction = self._assertion_for_concept(session, "tmdb.movie.genre:878")
            science_fiction_id = science_fiction.id
            snapshot = self._rows_snapshot(session)
        self.assertEqual(len(assertions), 2)
        self.assertEqual(len(provenance), 4)
        self.assertEqual({item.origin_kind for item in provenance}, {"migration", "nfo", "tmdb"})
        self.assertTrue(all(item.source_field == "genres" for item in provenance))
        self.assertTrue(all(len(item.source_payload_hash or "") == 64 for item in provenance))

        self._sync(
            film_id,
            library_item_id,
            origin_kind="tmdb",
            origin_ref="tmdb.movie:4242",
            observed_at="2026-08-25T00:02:00+00:00",
            genres=(GenreObservation("Science Fiction", tmdb_id=878),),
        )
        with Session(self.engine) as session:
            self.assertEqual(snapshot, self._rows_snapshot(session))

        self._sync(
            film_id,
            library_item_id,
            origin_kind="nfo",
            origin_ref=library_item_id,
            observed_at="2026-08-25T00:03:00+00:00",
            genres=(),
        )
        self._sync(
            film_id,
            library_item_id,
            origin_kind="legacy_movie",
            origin_ref=library_item_id,
            observed_at="2026-08-25T00:04:00+00:00",
            genres=(GenreObservation("Drama"),),
        )
        self._sync(
            film_id,
            library_item_id,
            origin_kind="tmdb",
            origin_ref="tmdb.movie:4242",
            observed_at="2026-08-25T00:05:00+00:00",
            genres=(),
        )
        with Session(self.engine) as session:
            science_fiction = session.get(Assertion, science_fiction_id)
            self.assertIsNotNone(science_fiction.superseded_at)

        self._sync(
            film_id,
            library_item_id,
            origin_kind="nfo",
            origin_ref=library_item_id,
            observed_at="2026-08-25T00:06:00+00:00",
            genres=(GenreObservation("科幻片"),),
        )
        with Session(self.engine) as session:
            science_fiction = session.get(Assertion, science_fiction_id)
            self.assertIsNone(science_fiction.superseded_at)
            self.assertEqual(len(session.exec(select(Assertion)).all()), 2)

    def test_import_promotes_proposed_but_preserves_user_decisions(self):
        library_manager.add_movies([self._movie("review-preservation")])
        film_id, library_item_id = self._owner()
        with Session(self.engine) as session:
            structured_metadata_synchronizer.ensure_genre_vocabulary(session)
            concept = session.exec(
                select(Concept).where(Concept.canonical_key == "tmdb.movie.genre:878")
            ).one()
            qualifier_hash = assertion_qualifier_hash(None)
            assertion = Assertion(
                subject_entity_id=film_id,
                object_entity_id=concept.id,
                predicate=AssertionPredicateKey.HAS_GENRE.value,
                qualifiers={},
                qualifier_hash=qualifier_hash,
                assertion_key=assertion_semantic_key(
                    subject_entity_id=film_id,
                    predicate=AssertionPredicateKey.HAS_GENRE,
                    object_entity_id=concept.id,
                    qualifier_hash=qualifier_hash,
                ),
                source_scope="inferred",
                review_status="proposed",
                review_method="none",
                first_seen_at="2026-08-24T00:00:00+00:00",
                last_seen_at="2026-08-24T00:00:00+00:00",
            )
            session.add(assertion)
            session.commit()
            assertion_id = assertion.id

        self._sync(
            film_id,
            library_item_id,
            origin_kind="legacy_movie",
            origin_ref=library_item_id,
            observed_at="2026-08-25T00:00:00+00:00",
            genres=(GenreObservation("Sci-Fi"),),
        )
        with Session(self.engine) as session:
            assertion = session.get(Assertion, assertion_id)
            self.assertEqual(assertion.source_scope, "factual")
            self.assertEqual(assertion.review_status, "accepted")
            self.assertEqual(assertion.review_method, "import_policy")
            self.assertEqual(
                assertion.review_policy_version,
                STRUCTURED_GENRE_IMPORT_POLICY_VERSION,
            )
            profile = session.exec(select(LocalProfile)).first()
            self.assertIsNotNone(profile)
            assertion.review_status = "rejected"
            assertion.review_method = "user"
            assertion.review_policy_version = None
            assertion.reviewed_by_profile_id = profile.id
            assertion.reviewed_at = "2026-08-25T00:01:00+00:00"
            session.add(assertion)
            session.commit()
            reviewer_id = profile.id

        self._sync(
            film_id,
            library_item_id,
            origin_kind="tmdb",
            origin_ref="tmdb.movie:4242",
            observed_at="2026-08-25T00:02:00+00:00",
            genres=(GenreObservation("Science Fiction", tmdb_id=878),),
        )
        with Session(self.engine) as session:
            assertion = session.get(Assertion, assertion_id)
            self.assertEqual(assertion.review_status, "rejected")
            self.assertEqual(assertion.review_method, "user")
            self.assertEqual(assertion.reviewed_by_profile_id, reviewer_id)
            self.assertEqual(assertion.reviewed_at, "2026-08-25T00:01:00+00:00")
            self.assertIsNone(assertion.review_policy_version)

        self._sync(
            film_id,
            library_item_id,
            origin_kind="legacy_movie",
            origin_ref=library_item_id,
            observed_at="2026-08-25T00:03:00+00:00",
            genres=(GenreObservation("Sci-Fi"), GenreObservation("Drama")),
        )
        with Session(self.engine) as session:
            drama = self._assertion_for_concept(session, "tmdb.movie.genre:18")
            drama.review_status = "accepted"
            drama.review_method = "user"
            drama.review_policy_version = None
            drama.reviewed_by_profile_id = reviewer_id
            drama.reviewed_at = "2026-08-25T00:04:00+00:00"
            session.add(drama)
            session.commit()
            drama_id = drama.id
        self._sync(
            film_id,
            library_item_id,
            origin_kind="tmdb",
            origin_ref="tmdb.movie:4242",
            observed_at="2026-08-25T00:05:00+00:00",
            genres=(GenreObservation("Drama", tmdb_id=18),),
        )
        with Session(self.engine) as session:
            drama = session.get(Assertion, drama_id)
            self.assertEqual(drama.review_status, "accepted")
            self.assertEqual(drama.review_method, "user")
            self.assertEqual(drama.reviewed_by_profile_id, reviewer_id)
            self.assertEqual(drama.reviewed_at, "2026-08-25T00:04:00+00:00")
            self.assertIsNone(drama.review_policy_version)

    def test_unmapped_unsupported_and_conflicting_genres_only_create_reviews(self):
        library_manager.add_movies([self._movie("genre-reviews")])
        film_id, library_item_id = self._owner()
        self._sync(
            film_id,
            library_item_id,
            origin_kind="tmdb",
            origin_ref="tmdb.movie:9999",
            observed_at="2026-08-25T00:00:00+00:00",
            genres=(GenreObservation("Science Fiction", tmdb_id=999999),),
        )
        self._sync(
            film_id,
            library_item_id,
            origin_kind="curated",
            origin_ref="curated.genre:test",
            observed_at="2026-08-25T00:01:00+00:00",
            genres=(GenreObservation("Drama"),),
        )
        with Session(self.engine) as session:
            concept = session.exec(
                select(Concept).where(Concept.canonical_key == "tmdb.movie.genre:878")
            ).one()
            graph = session.get(GraphEntity, concept.id)
            graph.entity_type = "person"
            session.add(graph)
            session.commit()
        self._sync(
            film_id,
            library_item_id,
            origin_kind="nfo",
            origin_ref=library_item_id,
            observed_at="2026-08-25T00:02:00+00:00",
            genres=(GenreObservation("Sci-Fi"),),
        )
        with Session(self.engine) as session:
            reasons = {item.reason_code for item in session.exec(select(StructuredMetadataReview)).all()}
            count = len(session.exec(select(StructuredMetadataReview)).all())
            self.assertEqual(len(session.exec(select(Assertion)).all()), 0)
        self.assertEqual(
            reasons,
            {
                "genre_unmapped",
                "genre_assertion_requires_user_review",
                "genre_concept_conflict",
            },
        )

        self._sync(
            film_id,
            library_item_id,
            origin_kind="nfo",
            origin_ref=library_item_id,
            observed_at="2026-08-25T00:02:00+00:00",
            genres=(GenreObservation("Sci-Fi"),),
        )
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(StructuredMetadataReview)).all()), count)

    def test_backfill_is_idempotent_and_clear_lifecycle_is_compatible(self):
        movie = {**self._movie("legacy-backfill"), "genres": ["Sci-Fi", "Drama", "Unknown"]}
        library_manager.add_movies([movie])
        with self.engine.begin() as connection:
            first = backfill_factual_genre_assertions(connection)
        with self.engine.connect() as connection:
            before = self._w4_counts(connection)
            run_count = connection.execute(
                text(
                    "SELECT COUNT(*) FROM canonical_backfill_run "
                    "WHERE run_key='factual_genre_assertions.v1'"
                )
            ).scalar_one()
        with self.engine.begin() as connection:
            second = backfill_factual_genre_assertions(connection)
        with self.engine.connect() as connection:
            self.assertEqual(before, self._w4_counts(connection))
            self.assertEqual(
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM canonical_backfill_run "
                        "WHERE run_key='factual_genre_assertions.v1'"
                    )
                ).scalar_one(),
                run_count,
            )
        self.assertEqual(first.counts["assertions_created"], 2)
        self.assertEqual(second.counts["assertions_created"], 0)

        library_manager.clear_library()
        with self.engine.connect() as connection:
            self.assertEqual(before, self._w4_counts(connection))

        result = library_manager.clear_all_data()
        self.assertEqual(set(result), {"user_states", "movies", "jobs", "events"})
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM assertion")).scalar_one(), 0)
            self.assertEqual(
                connection.execute(text("SELECT COUNT(*) FROM assertion_provenance")).scalar_one(),
                0,
            )
            self.assertEqual(
                connection.execute(text("SELECT COUNT(*) FROM assertion_predicate")).scalar_one(),
                9,
            )

    def test_genre_assertion_failure_rolls_back_event_and_legacy_projection(self):
        library_manager.add_movies([self._movie("transaction-rollback")])
        movie_id = library_manager.get_movies()[0]["id"]
        film_id, _library_item_id = self._owner()
        observation = StructuredMetadataObservation(
            origin_kind="tmdb",
            origin_ref="tmdb.movie:4242",
            source_instance_id="tmdb.api",
            observed_at="2026-08-25T00:00:00+00:00",
            complete_fields=frozenset({"genres"}),
            genres=(GenreObservation("Science Fiction", tmdb_id=878),),
        )
        with Session(self.engine) as session:
            events_before = len(session.exec(select(EventRecord)).all())
            title_before = session.get(Movie, movie_id).title

        with patch.object(
            genre_assertion_synchronizer,
            "sync",
            side_effect=RuntimeError("genre assertion sync failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "genre assertion sync failed"):
                event_store.append_and_project(
                    "MetadataMatched",
                    "movie",
                    movie_id,
                    {"current": {"title": "Must Roll Back"}},
                    structured_metadata=observation,
                )

        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(EventRecord)).all()), events_before)
            self.assertEqual(session.get(Movie, movie_id).title, title_before)
            self.assertEqual(
                len(
                    session.exec(
                        select(Assertion).where(Assertion.subject_entity_id == film_id)
                    ).all()
                ),
                0,
            )

    def _sync(
        self,
        film_id: str,
        library_item_id: str,
        *,
        origin_kind: str,
        origin_ref: str,
        observed_at: str,
        genres: tuple[GenreObservation, ...],
    ) -> None:
        observation = StructuredMetadataObservation(
            origin_kind=origin_kind,
            origin_ref=origin_ref,
            source_instance_id="test.source",
            observed_at=observed_at,
            complete_fields=frozenset({"genres"}),
            genres=genres,
        )
        with Session(self.engine) as session:
            structured_metadata_synchronizer.sync(
                session,
                film_id=film_id,
                library_item_id=library_item_id,
                observation=observation,
            )
            session.commit()

    def _movie(self, scanner_id: str) -> dict:
        media_path = str(Path(self._tmp.name) / scanner_id / "movie.mkv")
        return {
            "id": scanner_id,
            "title": "Runtime Film",
            "title_cn": "运行时电影",
            "year": 2026,
            "tmdb_id": "4242",
            "media_path": media_path,
            "folder_path": str(Path(media_path).parent),
            "folder_name": scanner_id,
            "file_size": 123,
            "file_mtime": 456.0,
            "library_status": "available",
            "metadata_source": "nfo",
            "scrape_status": "matched",
        }

    def _owner(self) -> tuple[str, str]:
        with self.engine.connect() as connection:
            row = connection.execute(
                text("SELECT film_id, library_item_id FROM legacy_movie_alias LIMIT 1")
            ).mappings().one()
        return row["film_id"], row["library_item_id"]

    @staticmethod
    def _assertion_for_concept(session: Session, canonical_key: str) -> Assertion:
        concept = session.exec(select(Concept).where(Concept.canonical_key == canonical_key)).one()
        return session.exec(
            select(Assertion).where(Assertion.object_entity_id == concept.id)
        ).one()

    @staticmethod
    def _rows_snapshot(session: Session) -> tuple[list[dict], list[dict]]:
        assertions = sorted(
            (item.model_dump() for item in session.exec(select(Assertion)).all()),
            key=lambda item: item["id"],
        )
        provenance = sorted(
            (item.model_dump() for item in session.exec(select(AssertionProvenance)).all()),
            key=lambda item: item["id"],
        )
        return assertions, provenance

    @staticmethod
    def _w4_counts(connection) -> dict[str, int]:
        return {
            table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            for table in ("assertion", "assertion_provenance", "structured_metadata_review")
        }


if __name__ == "__main__":
    unittest.main()
