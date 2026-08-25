import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine, select

import app.services.event_store as event_store_module
import app.services.library as library_module
import app.services.user_state as user_state_module
from app.canonical_models import (
    CreditProvenance,
    Film,
    FilmTitle,
    StructuredMetadataReview,
)
from app.contracts.structured_metadata import (
    CountryObservation,
    CreditObservation,
    StructuredMetadataObservation,
    TitleObservation,
)
from app.database import configure_sqlite_engine
from app.migrations.runner import run_migrations
from app.models import EventRecord, Movie
from app.services.event_store import event_store
from app.services.library import library_manager
from app.services.metadata.nfo_writer import NFOWriter
from app.services.scanner import NFOScanner
from app.services.structured_metadata_backfill import (
    backfill_legacy_structured_metadata,
    split_legacy_directors,
)
from app.services.structured_metadata_observations import (
    tmdb_structured_metadata_observation,
)
from app.services.structured_metadata_sync import structured_metadata_synchronizer
from app.services.structured_metadata_vocab import STRUCTURED_METADATA_VOCABULARY


class StructuredMetadataRuntimeTests(unittest.TestCase):
    def setUp(self):
        self._original_library_engine = library_module.engine
        self._original_event_engine = event_store_module.engine
        self._original_user_state_engine = user_state_module.engine
        self._tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self._tmp.name) / "runtime.db"
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

    def test_vocabulary_and_legacy_backfill_are_deterministic(self):
        self.assertEqual(
            STRUCTURED_METADATA_VOCABULARY.resolve_genre("科幻片").tmdb_id,
            878,
        )
        self.assertEqual(STRUCTURED_METADATA_VOCABULARY.resolve_country("USA"), "US")
        self.assertEqual(STRUCTURED_METADATA_VOCABULARY.resolve_country("中国大陆"), "CN")
        self.assertEqual(
            split_legacy_directors("Last, First & Partner ; Second Director"),
            ("Last, First & Partner", "Second Director"),
        )

        library_manager.add_movies(
            [
                {
                    **self._movie("legacy-structured"),
                    "director": "Last, First & Partner ; Second Director",
                    "actors": [
                        {"name": "Shared Person", "role": "Lead"},
                        {"name": "Shared Person", "role": "Cameo"},
                    ],
                    "countries": ["USA", "Atlantis"],
                    "genres": ["Sci-Fi", "Unmapped Genre"],
                }
            ]
        )

        with self.engine.begin() as connection:
            first = backfill_legacy_structured_metadata(connection)
            counts_after_first = self._structured_counts(connection)
        with self.engine.begin() as connection:
            second = backfill_legacy_structured_metadata(connection)
            counts_after_second = self._structured_counts(connection)

        self.assertEqual(first.counts["movies_scanned"], 1)
        self.assertEqual(second.counts["movies_scanned"], 1)
        self.assertEqual(counts_after_first, counts_after_second)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    text("SELECT COUNT(*) FROM person WHERE canonical_name='Shared Person'")
                ).scalar_one(),
                1,
            )
            self.assertEqual(
                connection.execute(
                    text("SELECT iso_3166_1 FROM film_country")
                ).scalars().all(),
                ["US"],
            )
            reason_codes = set(
                connection.execute(
                    text(
                        "SELECT reason_code FROM structured_metadata_review "
                        "WHERE status='open'"
                    )
                ).scalars()
            )
        self.assertEqual(reason_codes, {"country_unmapped", "genre_unmapped"})

    def test_source_refresh_is_idempotent_and_preserves_other_provenance(self):
        library_manager.add_movies([self._movie("source-refresh")])
        film_id, library_item_id = self._owner()
        tmdb = StructuredMetadataObservation(
            origin_kind="tmdb",
            origin_ref="tmdb.movie:4242",
            source_instance_id="tmdb",
            observed_at="2026-08-25T00:00:00+00:00",
            titles=(
                TitleObservation("TMDB Title", "canonical", "en"),
                TitleObservation("Original TMDB", "original", "en"),
            ),
            countries=(CountryObservation("US"),),
            credits=(
                CreditObservation(
                    "TMDB Director",
                    "Directing",
                    "Director",
                    provider="tmdb.person",
                    external_id="100",
                ),
            ),
        )
        nfo = StructuredMetadataObservation(
            origin_kind="nfo",
            origin_ref=library_item_id,
            source_instance_id="legacy.local",
            observed_at="2026-08-25T00:01:00+00:00",
            titles=(TitleObservation("NFO Title", "canonical", "en"),),
            countries=(CountryObservation("GB"),),
            credits=(
                CreditObservation(
                    "NFO Director",
                    "Directing",
                    "Director",
                ),
            ),
        )
        with Session(self.engine) as session:
            structured_metadata_synchronizer.sync(
                session,
                film_id=film_id,
                library_item_id=library_item_id,
                observation=tmdb,
            )
            structured_metadata_synchronizer.sync(
                session,
                film_id=film_id,
                library_item_id=library_item_id,
                observation=nfo,
            )
            session.commit()
        counts = self._session_counts()
        with Session(self.engine) as session:
            structured_metadata_synchronizer.sync(
                session,
                film_id=film_id,
                library_item_id=library_item_id,
                observation=nfo,
            )
            session.commit()
        self.assertEqual(counts, self._session_counts())

        with Session(self.engine) as session:
            film = session.get(Film, film_id)
            self.assertEqual(film.canonical_title, "NFO Title")
            self.assertEqual(
                structured_metadata_synchronizer.selected_country_codes(session, film_id),
                ("GB",),
            )
            provenance = session.exec(select(CreditProvenance)).all()
            self.assertEqual({item.origin_kind for item in provenance}, {"nfo", "tmdb"})

        refreshed_nfo = StructuredMetadataObservation(
            origin_kind="nfo",
            origin_ref=library_item_id,
            source_instance_id="legacy.local",
            observed_at="2026-08-25T00:02:00+00:00",
            titles=(TitleObservation("NFO Title 2", "canonical", "en"),),
            countries=(),
            credits=(),
        )
        with Session(self.engine) as session:
            structured_metadata_synchronizer.sync(
                session,
                film_id=film_id,
                library_item_id=library_item_id,
                observation=refreshed_nfo,
            )
            session.commit()
        with Session(self.engine) as session:
            self.assertEqual(session.get(Film, film_id).canonical_title, "NFO Title 2")
            self.assertEqual(
                structured_metadata_synchronizer.selected_country_codes(session, film_id),
                ("US",),
            )
            active_origins = {
                row.origin_kind
                for row in session.exec(select(CreditProvenance)).all()
                if row.superseded_at is None
            }
            self.assertEqual(active_origins, {"tmdb"})

    def test_review_resolves_reopens_and_respects_dismissal(self):
        library_manager.add_movies([self._movie("review-lifecycle")])
        film_id, library_item_id = self._owner()

        def sync_country(value: str | None) -> None:
            observation = StructuredMetadataObservation(
                origin_kind="nfo",
                origin_ref=library_item_id,
                source_instance_id="legacy.local",
                observed_at="2026-08-25T00:00:00+00:00",
                complete_fields=frozenset({"countries"}),
                countries=(CountryObservation(value),) if value else (),
            )
            with Session(self.engine) as session:
                structured_metadata_synchronizer.sync(
                    session,
                    film_id=film_id,
                    library_item_id=library_item_id,
                    observation=observation,
                )
                session.commit()

        sync_country("Atlantis")
        self.assertEqual(self._review_status(), "open")
        sync_country(None)
        self.assertEqual(self._review_status(), "resolved")
        sync_country("Atlantis")
        self.assertEqual(self._review_status(), "open")
        with self.engine.begin() as connection:
            connection.execute(
                text("UPDATE structured_metadata_review SET status='dismissed'")
            )
        sync_country(None)
        sync_country("Atlantis")
        self.assertEqual(self._review_status(), "dismissed")

    def test_scanner_and_nfo_writer_keep_legacy_shape_and_full_observation(self):
        folder = Path(self._tmp.name) / "media" / "Observed Film"
        folder.mkdir(parents=True)
        (folder / "movie.mkv").write_bytes(b"not-a-real-video")
        actors = "".join(
            f"<actor tmdbid='{1000 + index}'><name>Actor {index}</name>"
            f"<role>Role {index}</role><order>{index}</order></actor>"
            for index in range(12)
        )
        (folder / "movie.nfo").write_text(
            "<movie><title>Localized</title><originaltitle>Original</originaltitle>"
            "<year>2026</year><language>zh-CN</language><originallanguage>en</originallanguage>"
            "<country>USA</country><genre tmdbid='878'>Science Fiction</genre>"
            "<director tmdbid='1'>Director One</director>"
            "<director><name>Director Two</name><tmdbid>2</tmdbid></director>"
            f"{actors}</movie>",
            encoding="utf-8",
        )
        observed = NFOScanner(folder.parent).scan_folder_observed(folder)
        self.assertIsNotNone(observed)
        self.assertEqual(observed.movie["director"], "Director One")
        self.assertEqual(len(observed.movie["actors"]), 5)
        self.assertEqual(len(observed.structured_metadata.credits), 12)
        directors = [
            credit
            for credit in observed.structured_metadata.credits
            if credit.department == "Directing"
        ]
        actors_observed = [
            credit
            for credit in observed.structured_metadata.credits
            if credit.department == "Acting"
        ]
        self.assertEqual([item.name for item in directors], ["Director One", "Director Two"])
        self.assertEqual(len(actors_observed), 10)
        self.assertEqual(actors_observed[-1].billing_order, 9)

        output = Path(self._tmp.name) / "written"
        output.mkdir()
        path = NFOWriter().write_movie_nfo(
            output,
            {
                "id": 42,
                "title": "Localized",
                "original_title": "Original",
                "original_language": "en",
                "genres": [{"id": 878, "name": "Science Fiction"}],
                "credits": {
                    "crew": [{"id": 1, "name": "Director", "job": "Director"}],
                    "cast": [{"id": 2, "name": "Actor", "character": "Lead", "order": 7}],
                },
            },
            None,
            None,
        )
        root = ET.parse(path).getroot()
        self.assertEqual(root.findtext("originallanguage"), "en")
        self.assertEqual(root.find("genre").get("tmdbid"), "878")
        self.assertEqual(root.find("director").get("tmdbid"), "1")
        self.assertEqual(root.find("actor").get("tmdbid"), "2")
        self.assertEqual(root.findtext("actor/order"), "7")

    def test_tmdb_fixture_is_reduced_to_safe_observation(self):
        fixture = {
            "original_title": "Original",
            "original_language": "en",
            "title": "Localized",
            "production_countries": [{"iso_3166_1": "US", "name": "United States"}],
            "genres": [{"id": 878, "name": "Science Fiction"}],
            "credits": {
                "crew": [
                    {"id": 1, "name": "Director A", "job": "Director", "department": "Directing"}
                ],
                "cast": [
                    {"id": index + 10, "name": f"Actor {index}", "character": "Role", "order": index}
                    for index in range(12)
                ],
            },
            "api_key": "must-not-be-copied",
            "private_path": "C:\\Private\\movie.mkv",
        }
        observation = tmdb_structured_metadata_observation(
            fixture,
            tmdb_id=42,
            language="zh-CN",
            observed_at="2026-08-25T00:00:00+00:00",
        )
        serialized = repr(observation)
        self.assertEqual(observation.origin_ref, "tmdb.movie:42")
        self.assertEqual(len([item for item in observation.credits if item.job == "Actor"]), 10)
        self.assertTrue(all(item.provider == "tmdb.person" for item in observation.credits))
        self.assertNotIn("must-not-be-copied", serialized)
        self.assertNotIn("Private", serialized)

    def test_structured_sync_failure_rolls_back_event_and_legacy_projection(self):
        library_manager.add_movies([self._movie("transaction-rollback")])
        movie_id = library_manager.get_movies()[0]["id"]
        film_id, _library_item_id = self._owner()
        observation = StructuredMetadataObservation(
            origin_kind="tmdb",
            origin_ref="tmdb.movie:4242",
            source_instance_id="tmdb.api",
            observed_at="2026-08-25T00:00:00+00:00",
            complete_fields=frozenset({"titles"}),
            titles=(TitleObservation("Must Roll Back", "canonical", "en"),),
        )
        with Session(self.engine) as session:
            events_before = len(session.exec(select(EventRecord)).all())
            title_before = session.get(Movie, movie_id).title

        from unittest.mock import patch

        with patch.object(
            structured_metadata_synchronizer,
            "sync",
            side_effect=RuntimeError("structured sync failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "structured sync failed"):
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
                        select(FilmTitle)
                        .where(FilmTitle.film_id == film_id)
                        .where(FilmTitle.origin_kind == "tmdb")
                    ).all()
                ),
                0,
            )

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

    def _review_status(self) -> str:
        with Session(self.engine) as session:
            return session.exec(select(StructuredMetadataReview)).one().status

    def _session_counts(self) -> dict[str, int]:
        with self.engine.connect() as connection:
            return self._structured_counts(connection)

    @staticmethod
    def _structured_counts(connection) -> dict[str, int]:
        return {
            table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            for table in (
                "person",
                "credit",
                "credit_provenance",
                "concept",
                "concept_alias",
                "film_title",
                "film_country",
                "film_country_provenance",
                "structured_metadata_review",
            )
        }


if __name__ == "__main__":
    unittest.main()
