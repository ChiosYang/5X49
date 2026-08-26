from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.canonical_models import Assertion, AssertionProvenance
from app.contracts.analysis_persistence import (
    AssertionPredicateKey,
    STRUCTURED_GENRE_IMPORT_POLICY_VERSION,
    assertion_provenance_id,
    assertion_qualifier_hash,
    assertion_semantic_key,
    preserve_review_status,
    validate_automatic_assertion_decision,
)
from app.contracts.structured_metadata import canonical_json_hash, normalize_metadata_text
from app.services.structured_metadata_vocab import GENRE_VOCABULARY_VERSION


GENRE_ASSERTION_SOURCE_FIELD = "genres"

_PROVENANCE_ORIGIN_KIND = {
    "nfo": "nfo",
    "tmdb": "tmdb",
}


@dataclass(frozen=True)
class ResolvedGenreAssertion:
    concept_id: str
    canonical_key: str
    observed_value: str
    provider_id: int | None = None


@dataclass(frozen=True)
class GenreAssertionSyncResult:
    active_assertions: int
    assertions_created: int
    provenance_created: int
    provenance_superseded: int


class GenreAssertionSynchronizer:
    def supports_origin(self, origin_kind: str) -> bool:
        return origin_kind in _PROVENANCE_ORIGIN_KIND

    def sync(
        self,
        session: Session,
        *,
        film_id: str,
        origin_kind: str,
        origin_ref: str,
        observed_at: str,
        genres: tuple[ResolvedGenreAssertion, ...],
    ) -> GenreAssertionSyncResult:
        provenance_origin_kind = _PROVENANCE_ORIGIN_KIND.get(origin_kind)
        if provenance_origin_kind is None:
            raise ValueError("Genre assertion origin does not support automatic acceptance")
        self._validate_timestamp(observed_at)
        validate_automatic_assertion_decision(
            predicate=AssertionPredicateKey.HAS_GENRE,
            source_scope="factual",
            review_status="accepted",
            review_method="import_policy",
            origin_kind=origin_kind,
            review_policy_version=STRUCTURED_GENRE_IMPORT_POLICY_VERSION,
        )

        qualifier_hash = assertion_qualifier_hash(None)
        desired_assertion_ids: set[str] = set()
        touched_assertion_ids: set[str] = set()
        seen_concepts: set[str] = set()
        assertions_created = 0
        provenance_created = 0

        for genre in genres:
            if genre.concept_id in seen_concepts:
                continue
            seen_concepts.add(genre.concept_id)
            assertion_key = assertion_semantic_key(
                subject_entity_id=film_id,
                predicate=AssertionPredicateKey.HAS_GENRE,
                object_entity_id=genre.concept_id,
                qualifier_hash=qualifier_hash,
            )
            assertion = session.exec(
                select(Assertion).where(Assertion.assertion_key == assertion_key)
            ).first()
            if assertion is None:
                assertion = Assertion(
                    subject_entity_id=film_id,
                    object_entity_id=genre.concept_id,
                    predicate=AssertionPredicateKey.HAS_GENRE.value,
                    qualifiers={},
                    qualifier_hash=qualifier_hash,
                    assertion_key=assertion_key,
                    source_scope="factual",
                    review_status="accepted",
                    review_method="import_policy",
                    review_policy_version=STRUCTURED_GENRE_IMPORT_POLICY_VERSION,
                    reviewed_at=observed_at,
                    first_seen_at=observed_at,
                    last_seen_at=observed_at,
                    created_at=observed_at,
                    updated_at=observed_at,
                )
                session.add(assertion)
                session.flush()
                assertions_created += 1
            else:
                self._apply_automatic_acceptance(assertion, observed_at)
                session.add(assertion)

            desired_assertion_ids.add(assertion.id)
            touched_assertion_ids.add(assertion.id)
            payload_hash = canonical_json_hash(
                {
                    "canonical_key": genre.canonical_key,
                    "genre_vocabulary_version": GENRE_VOCABULARY_VERSION,
                    "observed_value": normalize_metadata_text(genre.observed_value),
                    "provider_id": genre.provider_id,
                }
            )
            provenance = session.exec(
                select(AssertionProvenance)
                .where(AssertionProvenance.assertion_id == assertion.id)
                .where(AssertionProvenance.origin_kind == provenance_origin_kind)
                .where(AssertionProvenance.origin_ref == origin_ref)
            ).first()
            if provenance is None:
                session.add(
                    AssertionProvenance(
                        id=assertion_provenance_id(),
                        assertion_id=assertion.id,
                        origin_kind=provenance_origin_kind,
                        origin_scope="factual",
                        origin_ref=origin_ref,
                        source_field=GENRE_ASSERTION_SOURCE_FIELD,
                        source_payload_hash=payload_hash,
                        first_observed_at=observed_at,
                        last_observed_at=observed_at,
                    )
                )
                provenance_created += 1
            else:
                changed = False
                if provenance.superseded_at is not None:
                    provenance.superseded_at = None
                    changed = True
                if provenance.last_observed_at != observed_at:
                    provenance.last_observed_at = observed_at
                    changed = True
                if provenance.source_payload_hash != payload_hash:
                    provenance.source_payload_hash = payload_hash
                    changed = True
                if changed:
                    session.add(provenance)

        session.flush()
        provenance_superseded = 0
        active_for_source = session.exec(
            select(AssertionProvenance)
            .where(AssertionProvenance.origin_kind == provenance_origin_kind)
            .where(AssertionProvenance.origin_ref == origin_ref)
            .where(AssertionProvenance.source_field == GENRE_ASSERTION_SOURCE_FIELD)
            .where(AssertionProvenance.superseded_at.is_(None))
        ).all()
        for provenance in active_for_source:
            assertion = session.get(Assertion, provenance.assertion_id)
            if (
                assertion is not None
                and assertion.subject_entity_id == film_id
                and assertion.predicate == AssertionPredicateKey.HAS_GENRE.value
                and assertion.id not in desired_assertion_ids
            ):
                provenance.superseded_at = observed_at
                session.add(provenance)
                touched_assertion_ids.add(assertion.id)
                provenance_superseded += 1

        session.flush()
        for assertion_id_value in touched_assertion_ids:
            self._refresh_assertion_lifecycle(session, assertion_id_value, observed_at)
        session.flush()
        return GenreAssertionSyncResult(
            active_assertions=self.active_count(session, film_id),
            assertions_created=assertions_created,
            provenance_created=provenance_created,
            provenance_superseded=provenance_superseded,
        )

    @staticmethod
    def active_count(session: Session, film_id: str) -> int:
        assertions = session.exec(
            select(Assertion)
            .where(Assertion.subject_entity_id == film_id)
            .where(Assertion.predicate == AssertionPredicateKey.HAS_GENRE.value)
            .where(Assertion.superseded_at.is_(None))
        ).all()
        return len(assertions)

    @staticmethod
    def _apply_automatic_acceptance(assertion: Assertion, observed_at: str) -> None:
        requested_status = preserve_review_status(assertion.review_status, "accepted")
        changed = False
        if assertion.source_scope != "factual":
            assertion.source_scope = "factual"
            changed = True
        if requested_status == "accepted" and assertion.review_status == "proposed":
            assertion.review_status = "accepted"
            assertion.review_method = "import_policy"
            assertion.review_policy_version = STRUCTURED_GENRE_IMPORT_POLICY_VERSION
            assertion.reviewed_by_profile_id = None
            assertion.reviewed_at = observed_at
            changed = True
        if assertion.superseded_at is not None:
            assertion.superseded_at = None
            changed = True
        if assertion.last_seen_at != observed_at:
            assertion.last_seen_at = observed_at
            changed = True
        if changed:
            assertion.updated_at = observed_at

    @staticmethod
    def _refresh_assertion_lifecycle(
        session: Session,
        assertion_id_value: str,
        observed_at: str,
    ) -> None:
        assertion = session.get(Assertion, assertion_id_value)
        if assertion is None:
            return
        active = session.exec(
            select(AssertionProvenance)
            .where(AssertionProvenance.assertion_id == assertion_id_value)
            .where(AssertionProvenance.superseded_at.is_(None))
        ).all()
        if active:
            latest = max(
                (item.last_observed_at for item in active),
                key=GenreAssertionSynchronizer._timestamp_key,
            )
            changed = False
            if assertion.superseded_at is not None:
                assertion.superseded_at = None
                changed = True
            if assertion.last_seen_at != latest:
                assertion.last_seen_at = latest
                changed = True
            if changed:
                assertion.updated_at = observed_at
                session.add(assertion)
        elif assertion.superseded_at is None:
            assertion.superseded_at = observed_at
            assertion.updated_at = observed_at
            session.add(assertion)

    @staticmethod
    def _validate_timestamp(value: str) -> None:
        GenreAssertionSynchronizer._timestamp_key(value)

    @staticmethod
    def _timestamp_key(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Genre assertion observed_at must be ISO-8601") from exc
        if parsed.tzinfo is None:
            raise ValueError("Genre assertion observed_at must include a timezone")
        return parsed.astimezone(timezone.utc)


genre_assertion_synchronizer = GenreAssertionSynchronizer()


__all__ = [
    "GENRE_ASSERTION_SOURCE_FIELD",
    "GenreAssertionSyncResult",
    "GenreAssertionSynchronizer",
    "ResolvedGenreAssertion",
    "genre_assertion_synchronizer",
]
