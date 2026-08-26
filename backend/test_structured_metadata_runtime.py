import tempfile
import unittest
from pathlib import Path

from sqlmodel import SQLModel, Session, create_engine, select

from app.canonical_models import (
    Assertion,
    AssertionPredicate,
    Credit,
    CreditProvenance,
    Film,
    FilmCountryProvenance,
    FilmTitle,
    GraphEntity,
    LibraryItem,
    LocalProfile,
    StructuredMetadataReview,
)
from app.contracts.analysis_persistence import predicate_seed_rows
from app.contracts.structured_metadata import (
    CountryObservation,
    CreditObservation,
    GenreObservation,
    StructuredMetadataObservation,
    TitleObservation,
)
from app.services.structured_metadata_sync import StructuredMetadataSynchronizer


FILM_ID = "film_11111111111111111111111111111111"
ITEM_ID = "lib_22222222222222222222222222222222"
T1 = "2026-08-25T00:00:00+00:00"
T2 = "2026-08-26T00:00:00+00:00"


class StructuredMetadataRuntimeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self._tmp.name) / 'library.db'}")
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add_all([AssertionPredicate(**row) for row in predicate_seed_rows()])
            session.add(LocalProfile(id="profile_local", profile_key="local"))
            session.add(GraphEntity(id=FILM_ID, entity_type="film"))
            session.add(Film(id=FILM_ID, canonical_title="Filename title"))
            session.add(
                LibraryItem(
                    id=ITEM_ID,
                    profile_id="profile_local",
                    film_id=FILM_ID,
                    source_type="local",
                    source_instance_id="local",
                    source_item_key="item:fixture",
                )
            )
            session.commit()
        self.sync = StructuredMetadataSynchronizer()

    def tearDown(self):
        self.engine.dispose()
        self._tmp.cleanup()

    @staticmethod
    def _observation(
        origin_kind,
        origin_ref,
        *,
        titles=(),
        countries=(),
        credits=(),
        genres=(),
        complete_fields=frozenset({"titles", "countries", "credits", "genres"}),
        observed_at=T1,
    ):
        return StructuredMetadataObservation(
            origin_kind=origin_kind,
            origin_ref=origin_ref,
            source_instance_id="local",
            observed_at=observed_at,
            complete_fields=complete_fields,
            titles=tuple(titles),
            countries=tuple(countries),
            credits=tuple(credits),
            genres=tuple(genres),
        )

    def test_nfo_metadata_beats_tmdb_without_deleting_tmdb_provenance(self):
        with Session(self.engine) as session:
            self.sync.sync(
                session,
                film_id=FILM_ID,
                library_item_id=ITEM_ID,
                observation=self._observation(
                    "tmdb",
                    "tmdb.movie:42",
                    titles=(TitleObservation("TMDB title", "canonical", "en-US"),),
                    countries=(CountryObservation("US"),),
                    credits=(CreditObservation("TMDB Director", "Directing", "Director", provider="tmdb.person", external_id="7"),),
                    genres=(GenreObservation("Drama", 18, "en"),),
                ),
            )
            result = self.sync.sync(
                session,
                film_id=FILM_ID,
                library_item_id=ITEM_ID,
                observation=self._observation(
                    "nfo",
                    ITEM_ID,
                    titles=(TitleObservation("NFO title", "canonical", "und"),),
                    countries=(CountryObservation("中国大陆"),),
                    credits=(CreditObservation("NFO Director", "Directing", "Director"),),
                    genres=(GenreObservation("Crime", 80, "en"),),
                ),
            )
            session.commit()

            film = session.get(Film, FILM_ID)
            active_titles = session.exec(
                select(FilmTitle).where(FilmTitle.superseded_at.is_(None))
            ).all()
            country_provenance = session.exec(select(FilmCountryProvenance)).all()
            credit_provenance = session.exec(select(CreditProvenance)).all()
            assertions = session.exec(select(Assertion)).all()
        self.assertEqual(film.canonical_title, "NFO title")
        self.assertEqual({row.origin_kind for row in active_titles}, {"nfo", "tmdb"})
        self.assertEqual({row.origin_kind for row in country_provenance}, {"nfo", "tmdb"})
        self.assertEqual({row.origin_kind for row in credit_provenance}, {"nfo", "tmdb"})
        self.assertEqual(result.countries_active, 1)
        self.assertEqual(result.credits_active, 1)
        self.assertEqual(len(assertions), 2)

    def test_identical_replay_is_idempotent_and_source_refresh_is_scoped(self):
        first = self._observation(
            "nfo",
            ITEM_ID,
            titles=(TitleObservation("Stable title", "canonical"),),
            countries=(CountryObservation("GB"),),
            credits=(CreditObservation("Director", "Directing", "Director"),),
            genres=(GenreObservation("Drama", 18),),
        )
        with Session(self.engine) as session:
            self.sync.sync(session, film_id=FILM_ID, library_item_id=ITEM_ID, observation=first)
            session.commit()
            counts_before = self._counts(session)
            self.sync.sync(session, film_id=FILM_ID, library_item_id=ITEM_ID, observation=first)
            session.commit()
            self.assertEqual(self._counts(session), counts_before)

            self.sync.sync(
                session,
                film_id=FILM_ID,
                library_item_id=ITEM_ID,
                observation=self._observation(
                    "nfo",
                    ITEM_ID,
                    titles=(),
                    countries=(),
                    credits=(),
                    genres=(),
                    observed_at=T2,
                ),
            )
            session.commit()
            self.assertTrue(all(row.superseded_at for row in session.exec(select(FilmTitle)).all()))
            self.assertTrue(all(row.superseded_at for row in session.exec(select(CreditProvenance)).all()))
            self.assertTrue(all(row.superseded_at for row in session.exec(select(FilmCountryProvenance)).all()))
            self.assertTrue(all(row.superseded_at for row in session.exec(select(Assertion)).all()))

    def test_unmapped_values_create_one_review_then_resolve_and_reopen(self):
        bad = self._observation(
            "nfo",
            ITEM_ID,
            countries=(CountryObservation("Atlantis"),),
            genres=(GenreObservation("Impossible genre"),),
            complete_fields=frozenset({"countries", "genres"}),
        )
        good = self._observation(
            "nfo",
            ITEM_ID,
            countries=(CountryObservation("US"),),
            genres=(GenreObservation("Drama", 18),),
            complete_fields=frozenset({"countries", "genres"}),
            observed_at=T2,
        )
        with Session(self.engine) as session:
            self.sync.sync(session, film_id=FILM_ID, library_item_id=ITEM_ID, observation=bad)
            self.sync.sync(session, film_id=FILM_ID, library_item_id=ITEM_ID, observation=bad)
            session.commit()
            reviews = session.exec(select(StructuredMetadataReview)).all()
            self.assertEqual(len(reviews), 2)
            self.assertTrue(all(row.status == "open" for row in reviews))

            self.sync.sync(session, film_id=FILM_ID, library_item_id=ITEM_ID, observation=good)
            session.commit()
            self.assertTrue(
                all(row.status == "resolved" for row in session.exec(select(StructuredMetadataReview)).all())
            )

            self.sync.sync(session, film_id=FILM_ID, library_item_id=ITEM_ID, observation=bad)
            session.commit()
            self.assertTrue(
                all(row.status == "open" for row in session.exec(select(StructuredMetadataReview)).all())
            )

    @staticmethod
    def _counts(session):
        return (
            len(session.exec(select(FilmTitle)).all()),
            len(session.exec(select(Credit)).all()),
            len(session.exec(select(CreditProvenance)).all()),
            len(session.exec(select(FilmCountryProvenance)).all()),
            len(session.exec(select(Assertion)).all()),
        )


if __name__ == "__main__":
    unittest.main()
