import tempfile
import unittest
from pathlib import Path

from sqlmodel import SQLModel, Session, create_engine, select

import app.models  # noqa: F401
from app.canonical_models import (
    AssertionPredicate,
    Film,
    FilmTitle,
    GraphEntity,
    IdentityReview,
    StructuredMetadataReview,
)
from app.contracts.analysis_persistence import predicate_seed_rows
from app.contracts.structured_metadata import (
    CountryObservation,
    CreditObservation,
    StructuredMetadataObservation,
    TitleObservation,
)
from app.services.provenance_resolver import (
    PROVENANCE_SELECTION_VERSION,
    ProvenanceResolver,
)
from app.services.structured_metadata_sync import StructuredMetadataSynchronizer


FILM_ID = "film_11111111111111111111111111111111"
T1 = "2026-08-25T00:00:00+00:00"
T2 = "2026-08-26T00:00:00+00:00"
T3 = "2026-08-27T00:00:00+00:00"


class ProvenanceResolverTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self._tmp.name) / 'library.db'}")
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add_all([AssertionPredicate(**row) for row in predicate_seed_rows()])
            session.add(GraphEntity(id=FILM_ID, entity_type="film"))
            session.add(Film(id=FILM_ID, canonical_title="Filename title"))
            session.commit()
        self.sync = StructuredMetadataSynchronizer()
        self.resolver = ProvenanceResolver()

    def tearDown(self):
        self.engine.dispose()
        self._tmp.cleanup()

    @staticmethod
    def observation(
        source: str,
        source_ref: str,
        observed_at: str,
        *,
        title: str,
        countries: tuple[str, ...] = (),
        director: str | None = None,
    ) -> StructuredMetadataObservation:
        return StructuredMetadataObservation(
            origin_kind=source,
            origin_ref=source_ref,
            source_instance_id="local",
            observed_at=observed_at,
            complete_fields=frozenset({"titles", "countries", "credits"}),
            titles=(TitleObservation(title, "canonical"),),
            countries=tuple(CountryObservation(code) for code in countries),
            credits=(
                (CreditObservation(director, "Directing", "Director"),)
                if director
                else ()
            ),
        )

    def test_source_precedence_materializes_film_and_keeps_sources_private(self):
        with Session(self.engine) as session:
            self.sync.sync(
                session,
                film_id=FILM_ID,
                library_item_id=None,
                observation=self.observation(
                    "tmdb", "tmdb.movie:42", T2, title="TMDB title", countries=("US",)
                ),
            )
            self.sync.sync(
                session,
                film_id=FILM_ID,
                library_item_id=None,
                observation=self.observation(
                    "nfo", "source:item-a", T1, title="NFO title", countries=("GB",)
                ),
            )
            session.commit()
            resolved = self.resolver.resolve_film(session, FILM_ID)
            film = session.get(Film, FILM_ID)

        self.assertEqual(film.canonical_title, "NFO title")
        self.assertEqual(resolved.canonical_title.value, "NFO title")
        self.assertEqual(resolved.countries.value, ("GB",))
        self.assertEqual(resolved.canonical_title.policy_version, PROVENANCE_SELECTION_VERSION)
        public = resolved.public_sources()
        self.assertEqual(public["title"]["source_kind"], "nfo")
        self.assertNotIn("source_ref", public["title"])

    def test_latest_owner_wins_same_tier_and_conflict_review_is_idempotent(self):
        with Session(self.engine) as session:
            self.sync.sync(
                session,
                film_id=FILM_ID,
                library_item_id=None,
                observation=self.observation(
                    "nfo", "source:item-a", T1, title="Older NFO", countries=("US",)
                ),
            )
            self.sync.sync(
                session,
                film_id=FILM_ID,
                library_item_id=None,
                observation=self.observation(
                    "nfo", "source:item-b", T2, title="Newer NFO", countries=("GB", "FR")
                ),
            )
            self.resolver.materialize_film(session, FILM_ID)
            self.resolver.materialize_film(session, FILM_ID)
            session.commit()
            resolved = self.resolver.resolve_film(session, FILM_ID)
            reviews = session.exec(
                select(StructuredMetadataReview).where(
                    StructuredMetadataReview.reason_code == "selection_conflict"
                )
            ).all()

        self.assertEqual(resolved.canonical_title.value, "Newer NFO")
        self.assertEqual(resolved.countries.value, ("FR", "GB"))
        self.assertTrue(resolved.canonical_title.conflicted)
        self.assertTrue(resolved.countries.conflicted)
        self.assertEqual(len(reviews), 2)
        self.assertTrue(all(review.status == "open" for review in reviews))
        self.assertTrue(all("Newer NFO" not in str(review.raw_value) for review in reviews))

    def test_conflict_review_resolves_when_competing_owner_is_superseded(self):
        with Session(self.engine) as session:
            for ref, when, title in (
                ("source:item-a", T1, "First"),
                ("source:item-b", T2, "Second"),
            ):
                self.sync.sync(
                    session,
                    film_id=FILM_ID,
                    library_item_id=None,
                    observation=self.observation("nfo", ref, when, title=title),
                )
            self.resolver.materialize_film(session, FILM_ID)
            for row in session.exec(
                select(FilmTitle).where(FilmTitle.origin_ref == "source:item-a")
            ).all():
                row.superseded_at = T3
                session.add(row)
            self.resolver.materialize_film(session, FILM_ID)
            session.commit()
            review = session.exec(
                select(StructuredMetadataReview).where(
                    StructuredMetadataReview.reason_code == "selection_conflict"
                )
            ).one()

        self.assertEqual(review.status, "resolved")

    def test_credit_field_uses_one_latest_complete_owner(self):
        with Session(self.engine) as session:
            self.sync.sync(
                session,
                film_id=FILM_ID,
                library_item_id=None,
                observation=self.observation(
                    "nfo", "source:item-a", T1, title="Film", director="Old Director"
                ),
            )
            self.sync.sync(
                session,
                film_id=FILM_ID,
                library_item_id=None,
                observation=self.observation(
                    "nfo", "source:item-b", T2, title="Film", director="New Director"
                ),
            )
            session.commit()
            names = self.resolver.selected_credit_names(
                session,
                FILM_ID,
                department="Directing",
                job="Director",
            )

        self.assertEqual(names, ("New Director",))

    def test_open_identity_review_is_reported_without_exposing_candidate(self):
        with Session(self.engine) as session:
            session.add(
                IdentityReview(
                    film_id=FILM_ID,
                    source_instance_id="local",
                    source_ref="source:item",
                    reason_code="identity_conflict",
                    candidate_hash="a" * 64,
                    review_key="b" * 64,
                )
            )
            session.commit()
            resolved = self.resolver.resolve_film(session, FILM_ID)

        self.assertTrue(resolved.identity_conflicted)
        self.assertEqual(resolved.public_sources()["identities"]["conflicted"], True)


if __name__ == "__main__":
    unittest.main()
