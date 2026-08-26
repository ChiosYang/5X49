from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from app.canonical_models import (
    Concept,
    ConceptAlias,
    Credit,
    CreditProvenance,
    ExternalIdentity,
    Film,
    FilmCountry,
    FilmCountryProvenance,
    FilmTitle,
    GraphEntity,
    Person,
    StructuredMetadataReview,
)
from app.contracts.structured_metadata import (
    PROVISIONAL_PERSON_PROVIDER,
    CreditObservation,
    ObservationIssue,
    StructuredMetadataObservation,
    credit_semantic_key,
    normalize_metadata_text,
    provisional_person_external_id,
    structured_metadata_review_key,
)
from app.services.genre_assertion_sync import (
    ResolvedGenreAssertion,
    genre_assertion_synchronizer,
)
from app.services.structured_metadata_vocab import (
    GENRE_VOCABULARY_VERSION,
    STRUCTURED_METADATA_VOCABULARY,
)


SOURCE_PRECEDENCE = {
    "curated": 0,
    "nfo": 1,
    "tmdb": 2,
    "filename": 3,
}

_FIELD_TO_GROUP = {
    "title": "titles",
    "country": "countries",
    "person": "credits",
    "credit": "credits",
    "concept": "genres",
}


@dataclass(frozen=True)
class StructuredMetadataSyncResult:
    titles_active: int
    countries_active: int
    credits_active: int
    genre_assertions_active: int
    reviews_open: int


class StructuredMetadataSynchronizer:
    def ensure_genre_vocabulary(self, session: Session) -> None:
        for definition in STRUCTURED_METADATA_VOCABULARY.genres:
            concept = session.exec(
                select(Concept)
                .where(Concept.kind == "genre")
                .where(Concept.canonical_key == definition.canonical_key)
            ).first()
            if concept is None:
                concept_id = self._new_id("concept")
                session.add(GraphEntity(id=concept_id, entity_type="concept"))
                session.flush()
                session.add(
                    Concept(
                        id=concept_id,
                        kind="genre",
                        canonical_key=definition.canonical_key,
                        canonical_name=definition.canonical_name,
                        lifecycle_status="active",
                    )
                )
                session.flush()
                concept = session.get(Concept, concept_id)
            if concept is None:
                raise RuntimeError("genre concept could not be created")
            for locale, alias in definition.aliases:
                normalized_alias = normalize_metadata_text(alias)
                existing = session.exec(
                    select(ConceptAlias)
                    .where(ConceptAlias.concept_id == concept.id)
                    .where(ConceptAlias.locale == locale)
                    .where(ConceptAlias.normalized_alias == normalized_alias)
                ).first()
                if existing is None:
                    session.add(
                        ConceptAlias(
                            id=self._new_id("concept_alias"),
                            concept_id=concept.id,
                            locale=locale,
                            alias=alias,
                            normalized_alias=normalized_alias,
                            provenance_ref=GENRE_VOCABULARY_VERSION,
                        )
                    )
        session.flush()

    def sync(
        self,
        session: Session,
        *,
        film_id: str,
        library_item_id: str | None,
        observation: StructuredMetadataObservation,
        materialize_genre_assertions: bool = True,
    ) -> StructuredMetadataSyncResult:
        if session.get(Film, film_id) is None:
            raise ValueError("structured metadata Film does not exist")
        self.ensure_genre_vocabulary(session)
        current_review_keys: set[str] = set()

        if "titles" in observation.complete_fields:
            self._sync_titles(session, film_id, observation)
        if "countries" in observation.complete_fields:
            self._sync_countries(
                session,
                film_id,
                library_item_id,
                observation,
                current_review_keys,
            )
        if "credits" in observation.complete_fields:
            self._sync_credits(
                session,
                film_id,
                library_item_id,
                observation,
                current_review_keys,
            )
        genre_assertions_active = 0
        if "genres" in observation.complete_fields:
            genre_assertions_active = self._sync_genres(
                session,
                film_id,
                library_item_id,
                observation,
                current_review_keys,
                materialize_genre_assertions=materialize_genre_assertions,
            )
        for issue in observation.issues:
            current_review_keys.add(
                self._upsert_review(
                    session,
                    film_id=film_id,
                    library_item_id=library_item_id,
                    observation=observation,
                    issue=issue,
                )
            )

        self._resolve_obsolete_reviews(
            session,
            film_id=film_id,
            observation=observation,
            current_review_keys=current_review_keys,
        )
        self._materialize_selected_titles(session, film_id)
        session.flush()
        return StructuredMetadataSyncResult(
            titles_active=self._active_title_count(session, film_id),
            countries_active=len(self.selected_country_codes(session, film_id)),
            credits_active=len(self.selected_credit_ids(session, film_id)),
            genre_assertions_active=genre_assertions_active,
            reviews_open=len(
                session.exec(
                    select(StructuredMetadataReview)
                    .where(StructuredMetadataReview.film_id == film_id)
                    .where(StructuredMetadataReview.status == "open")
                ).all()
            ),
        )

    def selected_country_codes(self, session: Session, film_id: str) -> tuple[str, ...]:
        candidates: list[tuple[int, str]] = []
        countries = session.exec(select(FilmCountry).where(FilmCountry.film_id == film_id)).all()
        for country in countries:
            provenance = session.exec(
                select(FilmCountryProvenance)
                .where(FilmCountryProvenance.film_country_id == country.id)
                .where(FilmCountryProvenance.superseded_at.is_(None))
            ).all()
            for item in provenance:
                candidates.append((self.source_rank(item.origin_kind), country.iso_3166_1))
        if not candidates:
            return ()
        best = min(rank for rank, _code in candidates)
        return tuple(sorted({code for rank, code in candidates if rank == best}))

    def selected_credit_ids(self, session: Session, film_id: str) -> tuple[str, ...]:
        candidates: list[tuple[int, str]] = []
        for credit in session.exec(select(Credit).where(Credit.film_id == film_id)).all():
            for provenance in session.exec(
                select(CreditProvenance)
                .where(CreditProvenance.credit_id == credit.id)
                .where(CreditProvenance.superseded_at.is_(None))
            ).all():
                candidates.append((self.source_rank(provenance.origin_kind), credit.id))
        if not candidates:
            return ()
        best = min(rank for rank, _credit_id in candidates)
        return tuple(sorted({credit_id for rank, credit_id in candidates if rank == best}))

    @staticmethod
    def source_rank(origin_kind: str) -> int:
        return SOURCE_PRECEDENCE.get(origin_kind, 100)

    def _sync_titles(
        self,
        session: Session,
        film_id: str,
        observation: StructuredMetadataObservation,
    ) -> None:
        desired: set[tuple[str, str, str]] = set()
        for item in observation.titles:
            title = item.title.strip()
            normalized = normalize_metadata_text(title)
            key = (item.locale, item.title_type, normalized)
            if key in desired:
                continue
            desired.add(key)
            existing = session.exec(
                select(FilmTitle)
                .where(FilmTitle.film_id == film_id)
                .where(FilmTitle.locale == item.locale)
                .where(FilmTitle.title_type == item.title_type)
                .where(FilmTitle.normalized_title == normalized)
                .where(FilmTitle.origin_kind == observation.origin_kind)
                .where(FilmTitle.origin_ref == observation.origin_ref)
            ).first()
            if existing is None:
                session.add(
                    FilmTitle(
                        id=self._new_id("title"),
                        film_id=film_id,
                        locale=item.locale,
                        title_type=item.title_type,
                        title=title,
                        normalized_title=normalized,
                        origin_kind=observation.origin_kind,
                        origin_ref=observation.origin_ref,
                        observed_at=observation.observed_at,
                    )
                )
            elif existing.superseded_at is not None:
                existing.superseded_at = None
                existing.observed_at = observation.observed_at
                existing.title = title
                session.add(existing)

        now = self._now()
        existing_titles = session.exec(
            select(FilmTitle)
            .where(FilmTitle.film_id == film_id)
            .where(FilmTitle.origin_kind == observation.origin_kind)
            .where(FilmTitle.origin_ref == observation.origin_ref)
            .where(FilmTitle.superseded_at.is_(None))
        ).all()
        for existing in existing_titles:
            key = (existing.locale, existing.title_type, existing.normalized_title)
            if key not in desired:
                existing.superseded_at = now
                session.add(existing)

    def _sync_countries(
        self,
        session: Session,
        film_id: str,
        library_item_id: str | None,
        observation: StructuredMetadataObservation,
        current_review_keys: set[str],
    ) -> None:
        desired_codes: set[str] = set()
        for item in observation.countries:
            code = STRUCTURED_METADATA_VOCABULARY.resolve_country(item.value)
            if code is None:
                current_review_keys.add(
                    self._upsert_review(
                        session,
                        film_id=film_id,
                        library_item_id=library_item_id,
                        observation=observation,
                        issue=ObservationIssue("country", "country_unmapped", item.value),
                    )
                )
                continue
            desired_codes.add(code)
            country = session.exec(
                select(FilmCountry)
                .where(FilmCountry.film_id == film_id)
                .where(FilmCountry.iso_3166_1 == code)
            ).first()
            if country is None:
                country = FilmCountry(
                    id=self._new_id("country"),
                    film_id=film_id,
                    iso_3166_1=code,
                )
                session.add(country)
                session.flush()
            provenance = session.exec(
                select(FilmCountryProvenance)
                .where(FilmCountryProvenance.film_country_id == country.id)
                .where(FilmCountryProvenance.origin_kind == observation.origin_kind)
                .where(FilmCountryProvenance.origin_ref == observation.origin_ref)
            ).first()
            if provenance is None:
                session.add(
                    FilmCountryProvenance(
                        id=self._new_id("country_provenance"),
                        film_country_id=country.id,
                        origin_kind=observation.origin_kind,
                        origin_ref=observation.origin_ref,
                        observed_at=observation.observed_at,
                    )
                )
            elif provenance.superseded_at is not None:
                provenance.superseded_at = None
                provenance.observed_at = observation.observed_at
                session.add(provenance)

        now = self._now()
        provenance_rows = session.exec(
            select(FilmCountryProvenance)
            .where(FilmCountryProvenance.origin_kind == observation.origin_kind)
            .where(FilmCountryProvenance.origin_ref == observation.origin_ref)
            .where(FilmCountryProvenance.superseded_at.is_(None))
        ).all()
        for provenance in provenance_rows:
            country = session.get(FilmCountry, provenance.film_country_id)
            if country is not None and country.film_id == film_id and country.iso_3166_1 not in desired_codes:
                provenance.superseded_at = now
                session.add(provenance)

    def _sync_credits(
        self,
        session: Session,
        film_id: str,
        library_item_id: str | None,
        observation: StructuredMetadataObservation,
        current_review_keys: set[str],
    ) -> None:
        desired_keys: set[str] = set()
        for item in observation.credits:
            person = self._resolve_person(
                session,
                film_id=film_id,
                library_item_id=library_item_id,
                observation=observation,
                credit=item,
                current_review_keys=current_review_keys,
            )
            if person is None:
                continue
            semantic_key = credit_semantic_key(
                film_id,
                person.id,
                item.department,
                item.job,
                item.character,
            )
            desired_keys.add(semantic_key)
            credit = session.exec(select(Credit).where(Credit.semantic_key == semantic_key)).first()
            if credit is None:
                credit = Credit(
                    id=self._new_id("credit"),
                    film_id=film_id,
                    person_id=person.id,
                    department=item.department.strip(),
                    job=item.job.strip(),
                    character=item.character.strip(),
                    billing_order=item.billing_order,
                    semantic_key=semantic_key,
                )
                session.add(credit)
                session.flush()
            elif self._observation_owns_credit_order(session, credit, observation.origin_kind):
                if credit.billing_order != item.billing_order:
                    credit.billing_order = item.billing_order
                    credit.updated_at = observation.observed_at
                    session.add(credit)
            provenance = session.exec(
                select(CreditProvenance)
                .where(CreditProvenance.credit_id == credit.id)
                .where(CreditProvenance.origin_kind == observation.origin_kind)
                .where(CreditProvenance.origin_ref == observation.origin_ref)
            ).first()
            if provenance is None:
                session.add(
                    CreditProvenance(
                        id=self._new_id("credit_provenance"),
                        credit_id=credit.id,
                        origin_kind=observation.origin_kind,
                        origin_ref=observation.origin_ref,
                        observed_at=observation.observed_at,
                    )
                )
            elif provenance.superseded_at is not None:
                provenance.superseded_at = None
                provenance.observed_at = observation.observed_at
                session.add(provenance)

        now = self._now()
        provenance_rows = session.exec(
            select(CreditProvenance)
            .where(CreditProvenance.origin_kind == observation.origin_kind)
            .where(CreditProvenance.origin_ref == observation.origin_ref)
            .where(CreditProvenance.superseded_at.is_(None))
        ).all()
        for provenance in provenance_rows:
            credit = session.get(Credit, provenance.credit_id)
            if credit is not None and credit.film_id == film_id and credit.semantic_key not in desired_keys:
                provenance.superseded_at = now
                session.add(provenance)

    def _sync_genres(
        self,
        session: Session,
        film_id: str,
        library_item_id: str | None,
        observation: StructuredMetadataObservation,
        current_review_keys: set[str],
        *,
        materialize_genre_assertions: bool,
    ) -> int:
        resolved_assertions: list[ResolvedGenreAssertion] = []
        for item in observation.genres:
            resolved = STRUCTURED_METADATA_VOCABULARY.resolve_genre(
                item.tmdb_id if item.tmdb_id is not None else item.value
            )
            if resolved is None:
                raw_value: Any = (
                    {"provider": "tmdb", "id": item.tmdb_id, "value": item.value}
                    if item.tmdb_id is not None
                    else item.value
                )
                current_review_keys.add(
                    self._upsert_review(
                        session,
                        film_id=film_id,
                        library_item_id=library_item_id,
                        observation=observation,
                        issue=ObservationIssue("concept", "genre_unmapped", raw_value),
                    )
                )
                continue

            concept = session.exec(
                select(Concept)
                .where(Concept.kind == "genre")
                .where(Concept.canonical_key == resolved.canonical_key)
            ).first()
            graph = session.get(GraphEntity, concept.id) if concept is not None else None
            if (
                concept is None
                or graph is None
                or graph.entity_type != "concept"
                or graph.lifecycle_status != "active"
                or concept.lifecycle_status != "active"
            ):
                current_review_keys.add(
                    self._upsert_review(
                        session,
                        film_id=film_id,
                        library_item_id=library_item_id,
                        observation=observation,
                        issue=ObservationIssue(
                            "concept",
                            "genre_concept_conflict",
                            {"canonical_key": resolved.canonical_key},
                        ),
                    )
                )
                continue

            if not genre_assertion_synchronizer.supports_origin(observation.origin_kind):
                current_review_keys.add(
                    self._upsert_review(
                        session,
                        film_id=film_id,
                        library_item_id=library_item_id,
                        observation=observation,
                        issue=ObservationIssue(
                            "concept",
                            "genre_assertion_requires_user_review",
                            {
                                "canonical_key": resolved.canonical_key,
                                "origin_kind": observation.origin_kind,
                            },
                        ),
                    )
                )
                continue

            resolved_assertions.append(
                ResolvedGenreAssertion(
                    concept_id=concept.id,
                    canonical_key=resolved.canonical_key,
                    observed_value=item.value,
                    provider_id=item.tmdb_id,
                )
            )

        if not materialize_genre_assertions:
            return 0
        if not genre_assertion_synchronizer.supports_origin(observation.origin_kind):
            return genre_assertion_synchronizer.active_count(session, film_id)
        return genre_assertion_synchronizer.sync(
            session,
            film_id=film_id,
            origin_kind=observation.origin_kind,
            origin_ref=observation.origin_ref,
            observed_at=observation.observed_at,
            genres=tuple(resolved_assertions),
        ).active_assertions

    def _resolve_person(
        self,
        session: Session,
        *,
        film_id: str,
        library_item_id: str | None,
        observation: StructuredMetadataObservation,
        credit: CreditObservation,
        current_review_keys: set[str],
    ) -> Person | None:
        provider = credit.provider or PROVISIONAL_PERSON_PROVIDER
        external_id = credit.external_id or provisional_person_external_id(
            observation.source_instance_id,
            credit.name,
        )
        identity = session.exec(
            select(ExternalIdentity)
            .where(ExternalIdentity.provider == provider)
            .where(ExternalIdentity.external_id == external_id)
        ).first()
        if identity is not None:
            graph = session.get(GraphEntity, identity.entity_id)
            person = session.get(Person, identity.entity_id)
            if graph is None or graph.entity_type != "person" or person is None:
                current_review_keys.add(
                    self._upsert_review(
                        session,
                        film_id=film_id,
                        library_item_id=library_item_id,
                        observation=observation,
                        issue=ObservationIssue(
                            "person",
                            "person_identity_conflict",
                            {"provider": provider, "external_id": external_id},
                        ),
                    )
                )
                return None
            if self.source_rank(observation.origin_kind) <= self.source_rank(identity.provenance_kind):
                normalized_name = normalize_metadata_text(credit.name)
                if person.canonical_name != credit.name.strip() or person.normalized_name != normalized_name:
                    person.canonical_name = credit.name.strip()
                    person.normalized_name = normalized_name
                    person.updated_at = observation.observed_at
                    session.add(person)
                    identity.provenance_kind = observation.origin_kind
                    identity.provenance_ref = observation.origin_ref
                    identity.updated_at = observation.observed_at
                    session.add(identity)
            return person

        person_id = self._new_id("person")
        now = observation.observed_at
        session.add(GraphEntity(id=person_id, entity_type="person", created_at=now, updated_at=now))
        session.flush()
        session.add(
            Person(
                id=person_id,
                canonical_name=credit.name.strip(),
                normalized_name=normalize_metadata_text(credit.name),
                resolution_status="verified" if credit.provider and credit.external_id else "provisional",
                lifecycle_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            ExternalIdentity(
                id=self._new_id("identity"),
                entity_id=person_id,
                provider=provider,
                external_id=external_id,
                identity_status="active",
                verified_at=now if credit.provider and credit.external_id else None,
                provenance_kind=observation.origin_kind,
                provenance_ref=observation.origin_ref,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        return session.get(Person, person_id)

    def _upsert_review(
        self,
        session: Session,
        *,
        film_id: str,
        library_item_id: str | None,
        observation: StructuredMetadataObservation,
        issue: ObservationIssue,
    ) -> str:
        review_key, raw_hash = structured_metadata_review_key(
            film_id=film_id,
            field_kind=issue.field_kind,
            reason_code=issue.reason_code,
            origin_kind=observation.origin_kind,
            origin_ref=observation.origin_ref,
            raw_value=issue.raw_value,
        )
        existing = session.exec(
            select(StructuredMetadataReview).where(
                StructuredMetadataReview.review_key == review_key
            )
        ).first()
        if existing is None:
            session.add(
                StructuredMetadataReview(
                    id=self._new_id("metadata_review"),
                    film_id=film_id,
                    library_item_id=library_item_id,
                    field_kind=issue.field_kind,
                    reason_code=issue.reason_code,
                    raw_value=issue.raw_value,
                    raw_value_hash=raw_hash,
                    origin_kind=observation.origin_kind,
                    origin_ref=observation.origin_ref,
                    review_key=review_key,
                    status="open",
                )
            )
        elif existing.status == "resolved":
            existing.status = "open"
            existing.resolved_at = None
            existing.updated_at = observation.observed_at
            session.add(existing)
        return review_key

    def _resolve_obsolete_reviews(
        self,
        session: Session,
        *,
        film_id: str,
        observation: StructuredMetadataObservation,
        current_review_keys: set[str],
    ) -> None:
        now = self._now()
        reviews = session.exec(
            select(StructuredMetadataReview)
            .where(StructuredMetadataReview.film_id == film_id)
            .where(StructuredMetadataReview.origin_kind == observation.origin_kind)
            .where(StructuredMetadataReview.origin_ref == observation.origin_ref)
            .where(StructuredMetadataReview.status == "open")
        ).all()
        for review in reviews:
            group = _FIELD_TO_GROUP[review.field_kind]
            if group in observation.complete_fields and review.review_key not in current_review_keys:
                review.status = "resolved"
                review.resolved_at = now
                review.updated_at = now
                session.add(review)

    def _materialize_selected_titles(self, session: Session, film_id: str) -> None:
        film = session.get(Film, film_id)
        if film is None:
            return
        titles = session.exec(
            select(FilmTitle)
            .where(FilmTitle.film_id == film_id)
            .where(FilmTitle.superseded_at.is_(None))
        ).all()
        if not titles:
            return
        type_rank = {"canonical": 0, "localized": 1, "original": 2, "alternative": 3}
        selected = min(
            titles,
            key=lambda item: (
                self.source_rank(item.origin_kind),
                type_rank[item.title_type],
                item.locale,
                item.normalized_title,
            ),
        )
        originals = [item for item in titles if item.title_type == "original"]
        selected_original = min(
            originals,
            key=lambda item: (
                self.source_rank(item.origin_kind),
                item.locale,
                item.normalized_title,
            ),
        ) if originals else None
        changed = False
        if film.canonical_title != selected.title:
            film.canonical_title = selected.title
            changed = True
        original_value = selected_original.title if selected_original else film.original_title
        if film.original_title != original_value:
            film.original_title = original_value
            changed = True
        if changed:
            film.updated_at = self._now()
            session.add(film)

    def _observation_owns_credit_order(
        self,
        session: Session,
        credit: Credit,
        origin_kind: str,
    ) -> bool:
        active = session.exec(
            select(CreditProvenance)
            .where(CreditProvenance.credit_id == credit.id)
            .where(CreditProvenance.superseded_at.is_(None))
        ).all()
        if not active:
            return True
        best = min(self.source_rank(item.origin_kind) for item in active)
        return self.source_rank(origin_kind) <= best

    @staticmethod
    def _active_title_count(session: Session, film_id: str) -> int:
        return len(
            session.exec(
                select(FilmTitle)
                .where(FilmTitle.film_id == film_id)
                .where(FilmTitle.superseded_at.is_(None))
            ).all()
        )

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


structured_metadata_synchronizer = StructuredMetadataSynchronizer()


__all__ = [
    "SOURCE_PRECEDENCE",
    "StructuredMetadataSyncResult",
    "StructuredMetadataSynchronizer",
    "structured_metadata_synchronizer",
]
