import tempfile
import unittest
from pathlib import Path

from sqlmodel import SQLModel, Session, create_engine, select

from app.canonical_models import (
    Assertion,
    AssertionPredicate,
    AssertionProvenance,
    Concept,
    Film,
    GraphEntity,
    LocalProfile,
)
from app.contracts.analysis_persistence import predicate_seed_rows
from app.services.genre_assertion_sync import (
    GenreAssertionSynchronizer,
    ResolvedGenreAssertion,
)


FILM_ID = "film_11111111111111111111111111111111"
DRAMA_ID = "concept_22222222222222222222222222222222"
CRIME_ID = "concept_33333333333333333333333333333333"
T1 = "2026-08-25T00:00:00+00:00"
T2 = "2026-08-26T00:00:00+00:00"


class GenreAssertionSyncTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self._tmp.name) / 'library.db'}")
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add_all([AssertionPredicate(**row) for row in predicate_seed_rows()])
            session.add(LocalProfile(id="profile_local", profile_key="local"))
            session.add(GraphEntity(id=FILM_ID, entity_type="film"))
            session.add(Film(id=FILM_ID, canonical_title="Subject"))
            self._add_genre(session, DRAMA_ID, "tmdb.movie.genre:18", "Drama")
            self._add_genre(session, CRIME_ID, "tmdb.movie.genre:80", "Crime")
            session.commit()
        self.sync = GenreAssertionSynchronizer()

    def tearDown(self):
        self.engine.dispose()
        self._tmp.cleanup()

    @staticmethod
    def _add_genre(session, concept_id, key, name):
        session.add(GraphEntity(id=concept_id, entity_type="concept"))
        session.add(
            Concept(
                id=concept_id,
                kind="genre",
                canonical_key=key,
                canonical_name=name,
            )
        )

    @staticmethod
    def _genre(concept_id=DRAMA_ID, key="tmdb.movie.genre:18", value="Drama", tmdb_id=18):
        return ResolvedGenreAssertion(concept_id, key, value, tmdb_id)

    def test_nfo_and_tmdb_share_one_assertion_with_source_provenance(self):
        with Session(self.engine) as session:
            first = self.sync.sync(
                session,
                film_id=FILM_ID,
                origin_kind="nfo",
                origin_ref="lib_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                observed_at=T1,
                genres=(self._genre(), self._genre()),
            )
            second = self.sync.sync(
                session,
                film_id=FILM_ID,
                origin_kind="tmdb",
                origin_ref="tmdb.movie:42",
                observed_at=T1,
                genres=(self._genre(),),
            )
            session.commit()

        self.assertEqual(first.assertions_created, 1)
        self.assertEqual(second.assertions_created, 0)
        with Session(self.engine) as session:
            assertions = session.exec(select(Assertion)).all()
            provenance = session.exec(select(AssertionProvenance)).all()
        self.assertEqual(len(assertions), 1)
        self.assertEqual(assertions[0].review_status, "accepted")
        self.assertEqual(assertions[0].review_method, "import_policy")
        self.assertEqual({item.origin_kind for item in provenance}, {"nfo", "tmdb"})

    def test_source_refresh_supersedes_only_its_provenance_and_restores(self):
        with Session(self.engine) as session:
            for kind, ref in (("nfo", "lib_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"), ("tmdb", "tmdb.movie:42")):
                self.sync.sync(
                    session,
                    film_id=FILM_ID,
                    origin_kind=kind,
                    origin_ref=ref,
                    observed_at=T1,
                    genres=(self._genre(),),
                )
            self.sync.sync(
                session,
                film_id=FILM_ID,
                origin_kind="nfo",
                origin_ref="lib_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                observed_at=T2,
                genres=(),
            )
            assertion = session.exec(select(Assertion)).one()
            self.assertIsNone(assertion.superseded_at)
            active = session.exec(
                select(AssertionProvenance).where(AssertionProvenance.superseded_at.is_(None))
            ).all()
            self.assertEqual([item.origin_kind for item in active], ["tmdb"])

            self.sync.sync(
                session,
                film_id=FILM_ID,
                origin_kind="tmdb",
                origin_ref="tmdb.movie:42",
                observed_at=T2,
                genres=(),
            )
            self.assertEqual(session.exec(select(Assertion)).one().superseded_at, T2)
            self.sync.sync(
                session,
                film_id=FILM_ID,
                origin_kind="nfo",
                origin_ref="lib_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                observed_at=T2,
                genres=(self._genre(),),
            )
            self.assertIsNone(session.exec(select(Assertion)).one().superseded_at)
            session.commit()

    def test_user_review_decision_is_never_overwritten(self):
        with Session(self.engine) as session:
            self.sync.sync(
                session,
                film_id=FILM_ID,
                origin_kind="nfo",
                origin_ref="lib_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                observed_at=T1,
                genres=(self._genre(),),
            )
            assertion = session.exec(select(Assertion)).one()
            assertion.review_status = "rejected"
            assertion.review_method = "user"
            assertion.review_policy_version = None
            assertion.reviewed_by_profile_id = "profile_local"
            assertion.reviewed_at = T1
            session.add(assertion)
            session.flush()
            self.sync.sync(
                session,
                film_id=FILM_ID,
                origin_kind="nfo",
                origin_ref="lib_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                observed_at=T2,
                genres=(self._genre(),),
            )
            assertion = session.exec(select(Assertion)).one()
        self.assertEqual(assertion.review_status, "rejected")
        self.assertEqual(assertion.review_method, "user")
        self.assertEqual(assertion.reviewed_at, T1)

    def test_unsupported_source_cannot_auto_accept_genre(self):
        with Session(self.engine) as session:
            with self.assertRaisesRegex(ValueError, "does not support"):
                self.sync.sync(
                    session,
                    film_id=FILM_ID,
                    origin_kind="curated",
                    origin_ref="curated:fixture",
                    observed_at=T1,
                    genres=(self._genre(),),
                )


if __name__ == "__main__":
    unittest.main()
