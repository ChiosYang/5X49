from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Generic, Iterable, TypeVar
from uuid import uuid4

from sqlmodel import Session, select

from app.canonical_models import (
    Assertion,
    AssertionProvenance,
    Concept,
    Credit,
    CreditProvenance,
    Film,
    FilmCountry,
    FilmCountryProvenance,
    FilmTitle,
    IdentityReview,
    Person,
    StructuredMetadataReview,
)
from app.contracts.structured_metadata import (
    canonical_json_hash,
    normalize_metadata_text,
    structured_metadata_review_key,
)


PROVENANCE_SELECTION_VERSION = "provenance-selection.v1"
SOURCE_PRECEDENCE = {
    "curated": 0,
    "user": 0,
    "rule": 0,
    "nfo": 1,
    "tmdb": 2,
    "filename": 3,
    "analysis_run": 4,
}

T = TypeVar("T")


@dataclass(frozen=True)
class ResolvedValue(Generic[T]):
    value: T
    source_kind: str | None
    observed_at: str | None
    policy_version: str = PROVENANCE_SELECTION_VERSION
    conflicted: bool = False

    def public_source(self) -> dict[str, str | bool | None]:
        return {
            "source_kind": self.source_kind,
            "observed_at": self.observed_at,
            "policy_version": self.policy_version,
            "conflicted": self.conflicted,
        }


@dataclass(frozen=True)
class ResolvedFilmMetadata:
    canonical_title: ResolvedValue[str | None]
    original_title: ResolvedValue[str | None]
    countries: ResolvedValue[tuple[str, ...]]
    credits: ResolvedValue[tuple[str, ...]]
    genres: ResolvedValue[tuple[str, ...]]
    identity_conflicted: bool

    def public_sources(self) -> dict[str, dict[str, str | bool | None]]:
        sources = {
            "title": self.canonical_title.public_source(),
            "original_title": self.original_title.public_source(),
            "countries": self.countries.public_source(),
            "credits": self.credits.public_source(),
            "genres": self.genres.public_source(),
        }
        sources["identities"] = {
            "source_kind": None,
            "observed_at": None,
            "policy_version": PROVENANCE_SELECTION_VERSION,
            "conflicted": self.identity_conflicted,
        }
        return sources


@dataclass(frozen=True)
class _OwnedValue(Generic[T]):
    value: T
    normalized: str
    source_kind: str
    source_ref: str
    observed_at: str
    stable_id: str
    order: tuple[object, ...] = ()


class ProvenanceResolver:
    """Select current Film metadata without owning source lifecycle."""

    def resolve_film(self, session: Session, film_id: str) -> ResolvedFilmMetadata:
        title, original = self.resolve_titles(session, film_id)
        return ResolvedFilmMetadata(
            canonical_title=title,
            original_title=original,
            countries=self.resolve_countries(session, film_id),
            credits=self.resolve_credits(session, film_id),
            genres=self.resolve_concepts(session, film_id, predicate="HAS_GENRE", kind="genre"),
            identity_conflicted=self.identity_conflicted(session, film_id),
        )

    def materialize_film(self, session: Session, film_id: str) -> ResolvedFilmMetadata:
        resolved = self.resolve_film(session, film_id)
        film = session.get(Film, film_id)
        if film is not None:
            changed = False
            if resolved.canonical_title.value and film.canonical_title != resolved.canonical_title.value:
                film.canonical_title = resolved.canonical_title.value
                changed = True
            if resolved.original_title.value and film.original_title != resolved.original_title.value:
                film.original_title = resolved.original_title.value
                changed = True
            if changed:
                film.updated_at = self._now()
                session.add(film)
        self._reconcile_conflict_review(session, film_id, "title", resolved.canonical_title)
        self._reconcile_conflict_review(session, film_id, "country", resolved.countries)
        self._reconcile_conflict_review(session, film_id, "credit", resolved.credits)
        self._reconcile_conflict_review(session, film_id, "concept", resolved.genres)
        return resolved

    def resolve_titles(
        self,
        session: Session,
        film_id: str,
    ) -> tuple[ResolvedValue[str | None], ResolvedValue[str | None]]:
        rows = session.exec(
            select(FilmTitle)
            .where(FilmTitle.film_id == film_id)
            .where(FilmTitle.superseded_at.is_(None))
        ).all()
        type_rank = {"canonical": 0, "localized": 1, "original": 2, "alternative": 3}
        display = [
            _OwnedValue(
                value=row.title,
                normalized=row.normalized_title,
                source_kind=row.origin_kind,
                source_ref=row.origin_ref,
                observed_at=row.observed_at,
                stable_id=row.id,
                order=(type_rank.get(row.title_type, 99), row.locale),
            )
            for row in rows
        ]
        originals = [item for item, row in zip(display, rows) if row.title_type == "original"]
        return self._select_single(display), self._select_single(originals)

    def resolve_countries(self, session: Session, film_id: str) -> ResolvedValue[tuple[str, ...]]:
        values: list[_OwnedValue[str]] = []
        countries = session.exec(select(FilmCountry).where(FilmCountry.film_id == film_id)).all()
        for country in countries:
            for provenance in session.exec(
                select(FilmCountryProvenance)
                .where(FilmCountryProvenance.film_country_id == country.id)
                .where(FilmCountryProvenance.superseded_at.is_(None))
            ).all():
                values.append(
                    _OwnedValue(
                        value=country.iso_3166_1,
                        normalized=country.iso_3166_1,
                        source_kind=provenance.origin_kind,
                        source_ref=provenance.origin_ref,
                        observed_at=provenance.observed_at,
                        stable_id=provenance.id,
                        order=(country.iso_3166_1,),
                    )
                )
        return self._select_collection(values)

    def resolve_credits(self, session: Session, film_id: str) -> ResolvedValue[tuple[str, ...]]:
        values: list[_OwnedValue[str]] = []
        credits = session.exec(select(Credit).where(Credit.film_id == film_id)).all()
        for credit in credits:
            for provenance in session.exec(
                select(CreditProvenance)
                .where(CreditProvenance.credit_id == credit.id)
                .where(CreditProvenance.superseded_at.is_(None))
            ).all():
                values.append(
                    _OwnedValue(
                        value=credit.id,
                        normalized=credit.semantic_key,
                        source_kind=provenance.origin_kind,
                        source_ref=provenance.origin_ref,
                        observed_at=provenance.observed_at,
                        stable_id=provenance.id,
                        order=(
                            credit.department.casefold(),
                            credit.job.casefold(),
                            credit.billing_order if credit.billing_order is not None else 2**31,
                            credit.semantic_key,
                        ),
                    )
                )
        return self._select_collection(values)

    def selected_credit_names(
        self,
        session: Session,
        film_id: str,
        *,
        department: str | None = None,
        job: str | None = None,
    ) -> tuple[str, ...]:
        resolved = self.resolve_credits(session, film_id)
        names: list[tuple[int, str, str]] = []
        for credit_id in resolved.value:
            credit = session.get(Credit, credit_id)
            if credit is None:
                continue
            if department is not None and credit.department != department:
                continue
            if job is not None and credit.job != job:
                continue
            person = session.get(Person, credit.person_id)
            if person is not None and person.lifecycle_status == "active":
                names.append((credit.billing_order or 0, person.canonical_name, credit.id))
        names.sort(key=lambda item: (item[0], item[1].casefold(), item[2]))
        return tuple(name for _order, name, _id in names)

    def resolve_concepts(
        self,
        session: Session,
        film_id: str,
        *,
        predicate: str,
        kind: str,
    ) -> ResolvedValue[tuple[str, ...]]:
        values: list[_OwnedValue[str]] = []
        assertions = session.exec(
            select(Assertion)
            .where(Assertion.subject_entity_id == film_id)
            .where(Assertion.predicate == predicate)
            .where(Assertion.source_scope == "factual")
            .where(Assertion.review_status == "accepted")
            .where(Assertion.superseded_at.is_(None))
        ).all()
        for assertion in assertions:
            concept = session.get(Concept, assertion.object_entity_id)
            if concept is None or concept.kind != kind or concept.lifecycle_status != "active":
                continue
            provenances = session.exec(
                select(AssertionProvenance)
                .where(AssertionProvenance.assertion_id == assertion.id)
                .where(AssertionProvenance.superseded_at.is_(None))
            ).all()
            for provenance in provenances:
                values.append(
                    _OwnedValue(
                        value=concept.canonical_name,
                        normalized=normalize_metadata_text(concept.canonical_name),
                        source_kind=provenance.origin_kind,
                        source_ref=provenance.origin_ref,
                        observed_at=provenance.last_observed_at,
                        stable_id=provenance.id,
                        order=(normalize_metadata_text(concept.canonical_name), concept.id),
                    )
                )
        return self._select_collection(values)

    @staticmethod
    def identity_conflicted(session: Session, film_id: str) -> bool:
        return session.exec(
            select(IdentityReview.id)
            .where(IdentityReview.film_id == film_id)
            .where(IdentityReview.status == "open")
        ).first() is not None

    @staticmethod
    def source_rank(source_kind: str) -> int:
        return SOURCE_PRECEDENCE.get(source_kind, 100)

    def _select_single(self, values: Iterable[_OwnedValue[str]]) -> ResolvedValue[str | None]:
        values = list(values)
        if not values:
            return ResolvedValue(None, None, None)
        owner_groups = self._owner_groups(values)
        selected_key = min(owner_groups, key=lambda key: self._owner_key(key, owner_groups[key]))
        selected_owner = owner_groups[selected_key]
        selected = min(selected_owner, key=lambda item: (item.order, item.normalized, item.stable_id))
        best_rank = self.source_rank(selected.source_kind)
        competing = [item for item in values if self.source_rank(item.source_kind) == best_rank]
        best_order = min(item.order for item in competing)
        conflict_values = {item.normalized for item in competing if item.order == best_order}
        return ResolvedValue(
            selected.value,
            selected.source_kind,
            selected.observed_at,
            conflicted=len(conflict_values) > 1,
        )

    def _select_collection(self, values: Iterable[_OwnedValue[str]]) -> ResolvedValue[tuple[str, ...]]:
        values = list(values)
        if not values:
            return ResolvedValue((), None, None)
        owner_groups = self._owner_groups(values)
        selected_key = min(owner_groups, key=lambda key: self._owner_key(key, owner_groups[key]))
        selected_owner = owner_groups[selected_key]
        selected_values = tuple(
            item.value
            for item in sorted(
                {item.normalized: item for item in selected_owner}.values(),
                key=lambda item: (item.order, item.normalized, item.stable_id),
            )
        )
        selected_rank = self.source_rank(selected_key[0])
        competing_sets = {
            frozenset(item.normalized for item in items)
            for key, items in owner_groups.items()
            if self.source_rank(key[0]) == selected_rank
        }
        return ResolvedValue(
            selected_values,
            selected_key[0],
            max((item.observed_at for item in selected_owner), default=None),
            conflicted=len(competing_sets) > 1,
        )

    @staticmethod
    def _owner_groups(values: Iterable[_OwnedValue[T]]) -> dict[tuple[str, str], list[_OwnedValue[T]]]:
        groups: dict[tuple[str, str], list[_OwnedValue[T]]] = {}
        for value in values:
            groups.setdefault((value.source_kind, value.source_ref), []).append(value)
        return groups

    def _owner_key(self, owner: tuple[str, str], values: list[_OwnedValue[T]]) -> tuple[object, ...]:
        newest = max((self._timestamp(item.observed_at) for item in values), default=0.0)
        return self.source_rank(owner[0]), -newest, owner[1]

    def _reconcile_conflict_review(
        self,
        session: Session,
        film_id: str,
        field_kind: str,
        resolved: ResolvedValue[object],
    ) -> None:
        existing = session.exec(
            select(StructuredMetadataReview)
            .where(StructuredMetadataReview.film_id == film_id)
            .where(StructuredMetadataReview.field_kind == field_kind)
            .where(StructuredMetadataReview.reason_code == "selection_conflict")
            .where(StructuredMetadataReview.origin_kind == "rule")
            .where(StructuredMetadataReview.origin_ref == PROVENANCE_SELECTION_VERSION)
        ).first()
        now = self._now()
        if not resolved.conflicted:
            if existing is not None and existing.status == "open":
                existing.status = "resolved"
                existing.resolved_at = now
                existing.updated_at = now
                session.add(existing)
            return
        candidate = {
            "candidate_count": len(resolved.value) if isinstance(resolved.value, tuple) else 1,
            "selection_hash": canonical_json_hash(resolved.value),
        }
        review_key, raw_hash = structured_metadata_review_key(
            film_id=film_id,
            field_kind=field_kind,
            reason_code="selection_conflict",
            origin_kind="rule",
            origin_ref=PROVENANCE_SELECTION_VERSION,
            raw_value=candidate,
        )
        if existing is None:
            session.add(
                StructuredMetadataReview(
                    id=f"metadata_review_{uuid4().hex}",
                    film_id=film_id,
                    field_kind=field_kind,
                    reason_code="selection_conflict",
                    raw_value=candidate,
                    raw_value_hash=raw_hash,
                    origin_kind="rule",
                    origin_ref=PROVENANCE_SELECTION_VERSION,
                    review_key=review_key,
                    status="open",
                    created_at=now,
                    updated_at=now,
                )
            )
        elif existing.status == "resolved":
            existing.status = "open"
            existing.resolved_at = None
            existing.updated_at = now
            existing.raw_value = candidate
            existing.raw_value_hash = raw_hash
            existing.review_key = review_key
            session.add(existing)

    @staticmethod
    def _timestamp(value: str) -> float:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


provenance_resolver = ProvenanceResolver()


__all__ = [
    "PROVENANCE_SELECTION_VERSION",
    "SOURCE_PRECEDENCE",
    "ProvenanceResolver",
    "ResolvedFilmMetadata",
    "ResolvedValue",
    "provenance_resolver",
]
