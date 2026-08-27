from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, select

from app.canonical_models import (
    Concept,
    ConceptAlias,
    ExternalIdentity,
    Film,
    FilmTitle,
    GraphEntity,
)
from app.contracts.analysis_persistence import (
    ASSERTION_PREDICATE_REGISTRY,
    AssertionPredicateKey,
    validate_assertion_semantics,
)
from app.contracts.analysis_v2 import AnalysisAssertionCandidate, AnalysisEntityReference, AnalysisV2Output
from app.contracts.structured_metadata import normalize_metadata_text


ANALYSIS_CRITIC_VERSION = "analysis-policy-critic.v1"
MAX_ACCEPTED_ASSERTIONS = 8


@dataclass(frozen=True)
class CriticRejection:
    candidate_key: str
    reason_code: str
    policy_code: str


@dataclass(frozen=True)
class AnalysisCriticResult:
    accepted_keys: tuple[str, ...]
    rejections: tuple[CriticRejection, ...]
    warnings: tuple[str, ...]
    policy_version: str = ANALYSIS_CRITIC_VERSION

    def rejection_for(self, candidate_key: str) -> CriticRejection | None:
        return next((item for item in self.rejections if item.candidate_key == candidate_key), None)


class _CriticFailure(Exception):
    def __init__(self, reason_code: str, policy_code: str):
        super().__init__(policy_code)
        self.reason_code = reason_code
        self.policy_code = policy_code


class AnalysisPolicyCritic:
    """Deterministic, side-effect-free policy gate for model candidates."""

    def evaluate(
        self,
        session: Session,
        *,
        subject_film_id: str,
        output: AnalysisV2Output,
        remote_targets: dict[str, dict[str, Any]] | None = None,
        remote_failures: dict[str, str] | None = None,
    ) -> AnalysisCriticResult:
        remote_targets = remote_targets or {}
        remote_failures = remote_failures or {}
        accepted: list[str] = []
        rejected: list[CriticRejection] = []
        warnings: list[str] = []
        semantic_keys: set[tuple[str, str, str]] = set()

        for index, candidate in enumerate(output.assertions):
            candidate_key = self.candidate_key(index)
            try:
                if len(accepted) >= MAX_ACCEPTED_ASSERTIONS:
                    raise _CriticFailure("invalid_candidate", "assertion_limit_exceeded")
                if candidate.qualifiers and candidate.qualifiers.model_dump(exclude_none=True):
                    raise _CriticFailure("invalid_candidate", "qualifier_not_allowed")
                target_key, target_type, concept_kind = self._inspect_target(
                    session,
                    subject_film_id=subject_film_id,
                    candidate=candidate,
                    remote_details=remote_targets.get(candidate_key),
                    remote_failure=remote_failures.get(candidate_key),
                )
                try:
                    validate_assertion_semantics(
                        predicate=candidate.predicate.value,
                        subject_entity_type="film",
                        object_entity_type=target_type,
                        object_concept_kind=concept_kind,
                    )
                except ValueError as exc:
                    raise _CriticFailure("predicate_type_mismatch", "predicate_type_mismatch") from exc
                if target_key == subject_film_id:
                    raise _CriticFailure("invalid_candidate", "self_reference")
                semantic_key = (candidate.predicate.value, candidate.direction, target_key)
                if semantic_key in semantic_keys:
                    raise _CriticFailure("invalid_candidate", "semantic_duplicate")
                semantic_keys.add(semantic_key)
                accepted.append(candidate_key)

                definition = ASSERTION_PREDICATE_REGISTRY[AssertionPredicateKey(candidate.predicate.value)]
                if definition.evidence_policy == "preferred" and not candidate.evidence_candidates:
                    warnings.append(f"{candidate_key}:preferred_evidence_missing")
            except _CriticFailure as exc:
                rejected.append(
                    CriticRejection(
                        candidate_key=candidate_key,
                        reason_code=exc.reason_code,
                        policy_code=exc.policy_code,
                    )
                )

        return AnalysisCriticResult(tuple(accepted), tuple(rejected), tuple(warnings))

    def _inspect_target(
        self,
        session: Session,
        *,
        subject_film_id: str,
        candidate: AnalysisAssertionCandidate,
        remote_details: dict[str, Any] | None,
        remote_failure: str | None,
    ) -> tuple[str, str, str | None]:
        target = candidate.target
        identities: list[tuple[str, str, str | None]] = []

        if target.entity_id:
            identities.append(self._inspect_entity(session, target, target.entity_id))

        if target.provider and target.external_id:
            existing = session.exec(
                select(ExternalIdentity)
                .where(ExternalIdentity.provider == target.provider)
                .where(ExternalIdentity.external_id == target.external_id)
                .where(ExternalIdentity.identity_status == "active")
            ).first()
            if existing is not None:
                identities.append(self._inspect_entity(session, target, existing.entity_id))
            elif target.provider == "tmdb.movie" and remote_details is not None:
                self._validate_remote_film(target, remote_details)
                identities.append((f"tmdb.movie:{target.external_id}", "film", None))
            elif remote_failure:
                raise _CriticFailure(remote_failure, "remote_identity_unresolved")
            else:
                raise _CriticFailure("identity_conflict", "external_identity_unverified")

        if identities:
            keys = {item[0] for item in identities}
            if len(keys) != 1:
                raise _CriticFailure("identity_conflict", "identity_reference_conflict")
            return identities[0]

        if not target.display_name:
            raise _CriticFailure("unresolved_reference", "target_reference_missing")
        if target.entity_type == "film":
            matches = self._film_name_matches(session, target)
            return self._unique_match(matches)
        if target.entity_type == "concept":
            matches = self._concept_name_matches(session, target, candidate.predicate.value)
            return self._unique_match(matches)
        raise _CriticFailure("predicate_type_mismatch", "person_target_not_supported")

    def _inspect_entity(
        self,
        session: Session,
        target: AnalysisEntityReference,
        entity_id: str,
    ) -> tuple[str, str, str | None]:
        resolved_id = self._follow_merge(session, entity_id)
        entity = session.get(GraphEntity, resolved_id)
        if entity is None or entity.entity_type != target.entity_type:
            raise _CriticFailure("predicate_type_mismatch", "entity_type_mismatch")
        concept_kind = None
        if entity.entity_type == "film":
            self._validate_local_film(session, target, resolved_id)
        elif entity.entity_type == "concept":
            concept = session.get(Concept, resolved_id)
            if concept is None or concept.lifecycle_status != "active":
                raise _CriticFailure("unresolved_reference", "concept_not_active")
            concept_kind = concept.kind
            if target.display_name:
                normalized = normalize_metadata_text(target.display_name)
                known = {normalize_metadata_text(concept.canonical_name)}
                known.update(
                    alias.normalized_alias
                    for alias in session.exec(
                        select(ConceptAlias).where(ConceptAlias.concept_id == resolved_id)
                    ).all()
                )
                if normalized not in known:
                    raise _CriticFailure("identity_conflict", "concept_name_conflict")
        return resolved_id, entity.entity_type, concept_kind

    def _film_name_matches(
        self,
        session: Session,
        target: AnalysisEntityReference,
    ) -> set[tuple[str, str, str | None]]:
        normalized = normalize_metadata_text(target.display_name or "")
        films = session.exec(
            select(Film)
            .where(Film.lifecycle_status == "active")
            .where(Film.release_year == target.release_year)
        ).all()
        matches = {
            film.id
            for film in films
            if normalized
            in {
                normalize_metadata_text(film.canonical_title),
                normalize_metadata_text(film.original_title or ""),
            }
        }
        candidate_ids = {film.id for film in films}
        matches.update(
            title.film_id
            for title in session.exec(
                select(FilmTitle)
                .where(FilmTitle.normalized_title == normalized)
                .where(FilmTitle.superseded_at.is_(None))
            ).all()
            if title.film_id in candidate_ids
        )
        return {(film_id, "film", None) for film_id in matches}

    def _concept_name_matches(
        self,
        session: Session,
        target: AnalysisEntityReference,
        predicate: str,
    ) -> set[tuple[str, str, str | None]]:
        expected_kind = {
            "HAS_THEME": "theme",
            "HAS_MOVEMENT": "movement",
            "HAS_VISUAL_STYLE": "visual_style",
            "HAS_MICRO_GENRE": "micro_genre",
        }.get(predicate)
        if expected_kind is None:
            raise _CriticFailure("predicate_type_mismatch", "concept_predicate_mismatch")
        normalized = normalize_metadata_text(target.display_name or "")
        concepts = session.exec(
            select(Concept)
            .where(Concept.kind == expected_kind)
            .where(Concept.lifecycle_status == "active")
        ).all()
        concept_ids = {concept.id for concept in concepts}
        matches = {
            concept.id
            for concept in concepts
            if normalize_metadata_text(concept.canonical_name) == normalized
        }
        matches.update(
            alias.concept_id
            for alias in session.exec(
                select(ConceptAlias).where(ConceptAlias.normalized_alias == normalized)
            ).all()
            if alias.concept_id in concept_ids
        )
        return {(concept_id, "concept", expected_kind) for concept_id in matches}

    @staticmethod
    def _unique_match(matches: set[tuple[str, str, str | None]]) -> tuple[str, str, str | None]:
        if len(matches) > 1:
            raise _CriticFailure("ambiguous_reference", "ambiguous_name_or_alias")
        if not matches:
            raise _CriticFailure("unresolved_reference", "name_not_resolved")
        return next(iter(matches))

    def _validate_local_film(self, session: Session, target: AnalysisEntityReference, film_id: str) -> None:
        film = session.get(Film, film_id)
        if film is None or film.lifecycle_status != "active":
            raise _CriticFailure("unresolved_reference", "film_not_active")
        if target.release_year is not None and film.release_year != target.release_year:
            raise _CriticFailure("identity_conflict", "film_year_conflict")
        if target.display_name:
            normalized = normalize_metadata_text(target.display_name)
            known = {
                normalize_metadata_text(film.canonical_title),
                normalize_metadata_text(film.original_title or ""),
            }
            known.update(
                title.normalized_title
                for title in session.exec(
                    select(FilmTitle)
                    .where(FilmTitle.film_id == film_id)
                    .where(FilmTitle.superseded_at.is_(None))
                ).all()
            )
            if normalized not in known:
                raise _CriticFailure("identity_conflict", "film_title_conflict")

    @staticmethod
    def _validate_remote_film(target: AnalysisEntityReference, details: dict[str, Any]) -> None:
        try:
            requested_id = int(target.external_id or "")
            returned_id = int(details.get("id"))
        except (TypeError, ValueError) as exc:
            raise _CriticFailure("identity_conflict", "remote_identity_invalid") from exc
        if requested_id <= 0 or requested_id != returned_id:
            raise _CriticFailure("identity_conflict", "remote_id_conflict")
        if target.release_year is not None:
            try:
                year = int(str(details.get("release_date") or "")[:4])
            except ValueError as exc:
                raise _CriticFailure("identity_conflict", "remote_year_conflict") from exc
            if year != target.release_year:
                raise _CriticFailure("identity_conflict", "remote_year_conflict")
        if target.display_name:
            expected = normalize_metadata_text(target.display_name)
            returned = {
                normalize_metadata_text(str(details.get("title") or "")),
                normalize_metadata_text(str(details.get("original_title") or "")),
            }
            if expected not in returned:
                raise _CriticFailure("identity_conflict", "remote_title_conflict")

    @staticmethod
    def _follow_merge(session: Session, entity_id: str) -> str:
        current = entity_id
        seen: set[str] = set()
        for _ in range(8):
            if current in seen:
                raise _CriticFailure("identity_conflict", "merge_cycle")
            seen.add(current)
            entity = session.get(GraphEntity, current)
            if entity is None:
                raise _CriticFailure("unresolved_reference", "entity_missing")
            if entity.lifecycle_status == "active":
                return current
            if entity.lifecycle_status != "merged" or not entity.merged_into_id:
                raise _CriticFailure("unresolved_reference", "entity_not_active")
            current = entity.merged_into_id
        raise _CriticFailure("identity_conflict", "merge_depth_exceeded")

    @staticmethod
    def candidate_key(index: int) -> str:
        return f"a{index:03d}"


analysis_policy_critic = AnalysisPolicyCritic()


__all__ = [
    "ANALYSIS_CRITIC_VERSION",
    "AnalysisCriticResult",
    "AnalysisPolicyCritic",
    "CriticRejection",
    "analysis_policy_critic",
]
