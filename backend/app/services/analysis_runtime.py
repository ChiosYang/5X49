from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from app.canonical_models import (
    AnalysisResolutionReview,
    AnalysisRun,
    Assertion,
    AssertionEvidence,
    AssertionProvenance,
    Concept,
    ConceptAlias,
    Evidence,
    ExternalIdentity,
    Film,
    FilmCountry,
    FilmTitle,
    GraphEntity,
)
from app.contracts.analysis_persistence import (
    AssertionPredicateKey,
    analysis_review_key,
    analysis_run_idempotency_key,
    assertion_evidence_id,
    assertion_qualifier_hash,
    assertion_semantic_key,
    evidence_semantic_key,
    preserve_review_status,
    validate_analysis_review_candidate,
    validate_assertion_semantics,
    validate_automatic_assertion_decision,
)
from app.contracts.analysis_v2 import (
    AnalysisAssertionCandidate,
    AnalysisConceptOption,
    AnalysisEntityReference,
    AnalysisV2Input,
    AnalysisV2Output,
)
from app.contracts.structured_metadata import StructuredMetadataObservation, canonical_json_hash, normalize_metadata_text
from app.models import Job
from app.services.analysis_evidence import EvidenceBatchResult, EVIDENCE_VERIFICATION_POLICY_VERSION
from app.services.analysis_critic import ANALYSIS_CRITIC_VERSION, AnalysisCriticResult
from app.services.event_store import event_store
from app.services.structured_metadata_observations import tmdb_structured_metadata_observation
from app.services.structured_metadata_sync import structured_metadata_synchronizer


ANALYSIS_KIND = "genealogy_v2"
ANALYSIS_SCHEMA_VERSION = "analysis-output.v2"
ANALYSIS_RESOLVER_VERSION = "analysis-resolver.v3"
ANALYSIS_POLICY_VERSION = ANALYSIS_CRITIC_VERSION
ANALYSIS_APP_VERSION = "0.1.0"
ACTIVE_JOB_STATUSES = frozenset({"queued", "running", "cancelling"})


class AnalysisRuntimeError(RuntimeError):
    error_category = "runtime"
    error_code = "analysis_runtime_error"


class AnalysisAlreadyRunning(AnalysisRuntimeError):
    error_code = "analysis_already_running"


class AnalysisSubjectMismatch(AnalysisRuntimeError):
    error_category = "validation"
    error_code = "analysis_subject_mismatch"


class ResolutionFailure(AnalysisRuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class AnalysisStart:
    run_id: str
    film_id: str
    analysis_input: AnalysisV2Input
    input_hash: str
    provider: str
    model: str
    cached: bool


@dataclass(frozen=True)
class AnalysisCompletion:
    run_id: str
    assertions: int
    evidence: int
    reviews: int
    view: dict[str, Any]


class AnalysisRuntimePersistence:
    def start(
        self,
        session: Session,
        *,
        film_id: str,
        job_id: str,
        provider: str,
        model: str,
        prompt_version: str,
    ) -> AnalysisStart:
        if session.get(Film, film_id) is None:
            raise AnalysisRuntimeError("Film does not exist")
        analysis_input = self.build_input(session, film_id)
        input_hash = canonical_json_hash(analysis_input.model_dump(mode="json"))
        idempotency_key = analysis_run_idempotency_key(
            film_id=film_id,
            analysis_kind=ANALYSIS_KIND,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            schema_version=ANALYSIS_SCHEMA_VERSION,
            resolver_version=ANALYSIS_RESOLVER_VERSION,
            policy_version=ANALYSIS_POLICY_VERSION,
            app_version=ANALYSIS_APP_VERSION,
            input_hash=input_hash,
        )
        run = session.exec(
            select(AnalysisRun).where(AnalysisRun.idempotency_key == idempotency_key)
        ).first()
        if run is not None and run.status == "succeeded":
            return AnalysisStart(
                run.id,
                film_id,
                analysis_input,
                input_hash,
                provider,
                model,
                True,
            )
        if run is not None and run.status == "running" and run.job_id != job_id:
            previous_job = session.get(Job, run.job_id) if run.job_id else None
            if previous_job is not None and previous_job.status in ACTIVE_JOB_STATUSES:
                raise AnalysisAlreadyRunning("An equivalent analysis is already running")

        now = self._now()
        if run is None:
            run = AnalysisRun(
                film_id=film_id,
                analysis_kind=ANALYSIS_KIND,
                provider=provider,
                model=model,
                prompt_version=prompt_version,
                schema_version=ANALYSIS_SCHEMA_VERSION,
                resolver_version=ANALYSIS_RESOLVER_VERSION,
                policy_version=ANALYSIS_POLICY_VERSION,
                app_version=ANALYSIS_APP_VERSION,
                input_hash=input_hash,
                idempotency_key=idempotency_key,
                status="running",
                attempt_count=1,
                correlation_id=job_id,
                job_id=job_id,
                started_at=now,
                created_at=now,
                updated_at=now,
            )
        else:
            run.status = "running"
            run.attempt_count += 1
            run.output_hash = None
            run.input_tokens = None
            run.output_tokens = None
            run.estimated_cost = None
            run.currency = None
            run.result_summary = None
            run.started_at = now
            run.finished_at = None
            run.error_category = None
            run.error_code = None
            run.error_message = None
            run.correlation_id = job_id
            run.job_id = job_id
            run.updated_at = now
        session.add(run)
        session.flush()
        event_store.append_in_session(
            session,
            "AnalysisStarted",
            "analysis_run",
            run.id,
            {"film_id": film_id},
            command_id=job_id,
            correlation_id=job_id,
            context={"analysis_kind": ANALYSIS_KIND},
        )
        return AnalysisStart(
            run.id,
            film_id,
            analysis_input,
            input_hash,
            provider,
            model,
            False,
        )

    def build_input(self, session: Session, film_id: str) -> AnalysisV2Input:
        film = session.get(Film, film_id)
        if film is None:
            raise AnalysisRuntimeError("Canonical Film does not exist")
        titles = session.exec(
            select(FilmTitle)
            .where(FilmTitle.film_id == film_id)
            .where(FilmTitle.superseded_at.is_(None))
        ).all()
        localized = sorted(
            {
                item.title[:300]
                for item in titles
                if item.title_type in {"localized", "alternative"}
                and normalize_metadata_text(item.title)
                != normalize_metadata_text(film.canonical_title)
            },
            key=normalize_metadata_text,
        )[:20]
        countries = list(structured_metadata_synchronizer.selected_country_codes(session, film_id))[:50]
        genres: list[str] = []
        genre_assertions = session.exec(
            select(Assertion)
            .where(Assertion.subject_entity_id == film_id)
            .where(Assertion.predicate == AssertionPredicateKey.HAS_GENRE.value)
            .where(Assertion.review_status == "accepted")
            .where(Assertion.superseded_at.is_(None))
        ).all()
        for assertion in genre_assertions:
            concept = session.get(Concept, assertion.object_entity_id)
            if concept is not None and concept.kind == "genre" and concept.lifecycle_status == "active":
                genres.append(concept.canonical_name[:300])
        identities = session.exec(
            select(ExternalIdentity)
            .where(ExternalIdentity.entity_id == film_id)
            .where(ExternalIdentity.identity_status == "active")
        ).all()
        external_identities = {
            item.provider[:80]: item.external_id[:160]
            for item in sorted(identities, key=lambda value: (value.provider, value.external_id))[:20]
        }
        supported_concept_kinds = frozenset({"theme", "movement", "visual_style", "micro_genre"})
        concepts = sorted(
            (
                item
                for item in session.exec(
                    select(Concept).where(Concept.lifecycle_status == "active")
                ).all()
                if item.kind in supported_concept_kinds
            ),
            key=lambda item: (
                item.kind,
                normalize_metadata_text(item.canonical_name),
                item.id,
            ),
        )[:80]
        concept_ids = {item.id for item in concepts}
        aliases_by_concept: dict[str, list[str]] = {item.id: [] for item in concepts}
        if concept_ids:
            for alias in session.exec(
                select(ConceptAlias).where(ConceptAlias.concept_id.in_(sorted(concept_ids)))
            ).all():
                aliases_by_concept[alias.concept_id].append(alias.alias[:300])
        available_concepts = [
            AnalysisConceptOption(
                entity_id=item.id,
                kind=item.kind,
                canonical_name=item.canonical_name[:300],
                aliases=sorted(
                    {
                        alias
                        for alias in aliases_by_concept[item.id]
                        if normalize_metadata_text(alias)
                        != normalize_metadata_text(item.canonical_name)
                    },
                    key=normalize_metadata_text,
                )[:8],
            )
            for item in concepts
        ]
        return AnalysisV2Input(
            film_id=film.id,
            canonical_title=film.canonical_title[:300],
            original_title=(film.original_title or "")[:300] or None,
            localized_titles=localized,
            release_year=film.release_year if film.release_year and film.release_year >= 1888 else None,
            runtime_minutes=film.runtime_minutes,
            overview=(film.overview or "")[:5000] or None,
            genres=sorted(set(genres), key=normalize_metadata_text)[:50],
            countries=sorted(set(countries))[:50],
            external_identities=external_identities,
            available_concepts=available_concepts,
        )

    def missing_tmdb_targets(
        self,
        session: Session,
        output: AnalysisV2Output,
    ) -> dict[str, int]:
        result: dict[str, int] = {}
        for index, candidate in enumerate(output.assertions):
            target = candidate.target
            if target.provider != "tmdb.movie" or target.external_id is None:
                continue
            existing = session.exec(
                select(ExternalIdentity)
                .where(ExternalIdentity.provider == "tmdb.movie")
                .where(ExternalIdentity.external_id == target.external_id)
                .where(ExternalIdentity.identity_status == "active")
            ).first()
            if existing is not None:
                continue
            try:
                provider_id = int(target.external_id)
            except (TypeError, ValueError):
                continue
            if provider_id > 0:
                result[self.assertion_candidate_key(index)] = provider_id
        return result

    def evidence_candidates(
        self,
        session: Session,
        output: AnalysisV2Output,
        remote_targets: dict[str, dict[str, Any]],
        allowed_candidate_keys: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for index, assertion in enumerate(output.assertions):
            assertion_key = self.assertion_candidate_key(index)
            if allowed_candidate_keys is not None and assertion_key not in allowed_candidate_keys:
                continue
            if not self._preliminarily_resolvable(session, assertion, remote_targets.get(assertion_key)):
                continue
            for evidence_index, evidence in enumerate(assertion.evidence_candidates):
                result[self.evidence_candidate_key(index, evidence_index)] = evidence
        return result

    def complete(
        self,
        session: Session,
        *,
        start: AnalysisStart,
        output: AnalysisV2Output,
        input_tokens: int | None,
        output_tokens: int | None,
        estimated_cost: float | None,
        currency: str | None,
        remote_targets: dict[str, dict[str, Any]],
        remote_failures: dict[str, str],
        evidence_batch: EvidenceBatchResult,
        job_id: str,
        critic_result: AnalysisCriticResult | None = None,
    ) -> AnalysisCompletion:
        if output.subject_film_id != start.film_id:
            raise AnalysisSubjectMismatch("Analysis output subject does not match the input Film")
        run = session.get(AnalysisRun, start.run_id)
        if run is None or run.status != "running":
            raise AnalysisRuntimeError("AnalysisRun is not running")
        now = self._now()
        assertion_by_candidate: dict[str, Assertion] = {}
        review_count = 0
        accepted_keys = frozenset(critic_result.accepted_keys) if critic_result is not None else None

        for index, candidate in enumerate(output.assertions):
            candidate_key = self.assertion_candidate_key(index)
            rejection = critic_result.rejection_for(candidate_key) if critic_result is not None else None
            if accepted_keys is not None and candidate_key not in accepted_keys:
                self._upsert_review(
                    session,
                    run=run,
                    predicate=candidate.predicate.value,
                    candidate_kind="assertion",
                    reason_code=rejection.reason_code if rejection is not None else "invalid_candidate",
                    candidate_summary=self._assertion_summary(candidate),
                    now=now,
                )
                review_count += 1
                continue
            try:
                if self._has_disallowed_model_qualifiers(candidate):
                    raise ResolutionFailure("invalid_candidate")
                target_id = self._resolve_target(
                    session,
                    candidate,
                    remote_targets.get(candidate_key),
                    remote_failures.get(candidate_key),
                    now,
                )
                subject_id, object_id = (
                    (start.film_id, target_id)
                    if candidate.direction == "subject_to_target"
                    else (target_id, start.film_id)
                )
                if subject_id == object_id:
                    raise ResolutionFailure("invalid_candidate")
                assertion = self._upsert_assertion(
                    session,
                    run=run,
                    candidate=candidate,
                    subject_id=subject_id,
                    object_id=object_id,
                    now=now,
                )
                assertion_by_candidate[candidate_key] = assertion
            except ResolutionFailure as exc:
                self._upsert_review(
                    session,
                    run=run,
                    predicate=candidate.predicate.value,
                    candidate_kind="assertion",
                    reason_code=exc.reason_code,
                    candidate_summary=self._assertion_summary(candidate),
                    now=now,
                )
                review_count += 1

        for reference in output.unresolved_references:
            self._upsert_review(
                session,
                run=run,
                predicate=None,
                candidate_kind="entity_reference",
                reason_code="unresolved_reference",
                candidate_summary={"target": reference.model_dump(mode="json", exclude_none=True)},
                now=now,
            )
            review_count += 1

        evidence_count = 0
        for item in evidence_batch.verified:
            candidate_key = item.candidate_key.split(":e", 1)[0]
            assertion = assertion_by_candidate.get(candidate_key)
            if assertion is None:
                continue
            evidence = self._upsert_evidence(session, item, now)
            link = session.exec(
                select(AssertionEvidence)
                .where(AssertionEvidence.assertion_id == assertion.id)
                .where(AssertionEvidence.evidence_id == evidence.id)
                .where(AssertionEvidence.stance == item.candidate.stance)
            ).first()
            if link is None:
                session.add(
                    AssertionEvidence(
                        id=assertion_evidence_id(),
                        assertion_id=assertion.id,
                        evidence_id=evidence.id,
                        stance=item.candidate.stance,
                        link_status="active",
                        created_at=now,
                    )
                )
            evidence_count += 1

        for failure in evidence_batch.failures:
            candidate_key = failure.candidate_key.split(":e", 1)[0]
            assertion_index = self._candidate_index(candidate_key)
            if candidate_key not in assertion_by_candidate or assertion_index >= len(output.assertions):
                continue
            assertion_candidate = output.assertions[assertion_index]
            self._upsert_review(
                session,
                run=run,
                predicate=assertion_candidate.predicate.value,
                candidate_kind="evidence",
                reason_code=failure.reason_code,
                candidate_summary={
                    "predicate": assertion_candidate.predicate.value,
                    "direction": assertion_candidate.direction,
                    "target": assertion_candidate.target.model_dump(mode="json", exclude_none=True),
                    "evidence": failure.candidate.model_dump(mode="json", exclude_none=True),
                },
                now=now,
            )
            review_count += 1

        self._supersede_previous_run_provenance(session, run, now)
        run.status = "succeeded"
        run.output_hash = canonical_json_hash(output.model_dump(mode="json"))
        run.input_tokens = input_tokens
        run.output_tokens = output_tokens
        run.estimated_cost = estimated_cost
        run.currency = currency
        run.result_summary = output.summary
        run.finished_at = now
        run.error_category = None
        run.error_code = None
        run.error_message = None
        run.updated_at = now
        session.add(run)
        session.flush()

        view = self.get_analysis(session, start.film_id)
        event_store.append_in_session(
            session,
            "AnalysisCompleted",
            "analysis_run",
            run.id,
            {
                "film_id": start.film_id,
                "assertion_count": len(assertion_by_candidate),
                "evidence_count": evidence_count,
                "review_count": review_count,
            },
            command_id=job_id,
            correlation_id=job_id,
            context={"analysis_kind": ANALYSIS_KIND},
        )
        return AnalysisCompletion(
            run_id=run.id,
            assertions=len(assertion_by_candidate),
            evidence=evidence_count,
            reviews=review_count,
            view=view,
        )

    def restore_cached_result(
        self,
        session: Session,
        *,
        start: AnalysisStart,
        job_id: str,
    ) -> AnalysisCompletion:
        run = session.get(AnalysisRun, start.run_id)
        if run is None or run.status != "succeeded":
            raise AnalysisRuntimeError("Cached AnalysisRun is unavailable")
        view = self.get_analysis(session, start.film_id)
        provenance = session.exec(
            select(AssertionProvenance)
            .where(AssertionProvenance.analysis_run_id == run.id)
            .where(AssertionProvenance.superseded_at.is_(None))
        ).all()
        reviews = session.exec(
            select(AnalysisResolutionReview)
            .where(AnalysisResolutionReview.analysis_run_id == run.id)
            .where(AnalysisResolutionReview.status == "open")
        ).all()
        return AnalysisCompletion(run.id, len(provenance), 0, len(reviews), view)

    def fail(
        self,
        session: Session,
        *,
        start: AnalysisStart,
        job_id: str,
        error_category: str,
        error_code: str,
        error_message: str,
        cancelled: bool = False,
        create_output_review: bool = False,
    ) -> None:
        run = session.get(AnalysisRun, start.run_id)
        if run is None or run.status == "succeeded":
            return
        now = self._now()
        run.status = "cancelled" if cancelled else "failed"
        run.finished_at = now
        run.error_category = error_category[:80]
        run.error_code = error_code[:80]
        run.error_message = error_message[:500]
        run.updated_at = now
        session.add(run)
        if create_output_review:
            self._upsert_review(
                session,
                run=run,
                predicate=None,
                candidate_kind="output",
                reason_code="invalid_candidate",
                candidate_summary={},
                now=now,
            )
        event_store.append_in_session(
            session,
            "AnalysisFailed",
            "analysis_run",
            run.id,
            {"film_id": start.film_id, "error_code": error_code[:80]},
            command_id=job_id,
            correlation_id=job_id,
            context={"analysis_kind": ANALYSIS_KIND, "error_code": error_code[:80]},
        )

    def get_analysis(self, session: Session, film_id: str) -> dict[str, Any] | None:
        run = session.exec(
            select(AnalysisRun)
            .where(AnalysisRun.film_id == film_id)
            .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        ).first()
        if run is None:
            return None
        provenance = session.exec(
            select(AssertionProvenance)
            .where(AssertionProvenance.analysis_run_id == run.id)
            .where(AssertionProvenance.superseded_at.is_(None))
        ).all()
        assertion_ids = sorted({item.assertion_id for item in provenance})
        relations: list[dict[str, Any]] = []
        evidence_by_id: dict[str, dict[str, Any]] = {}
        for assertion_id in assertion_ids:
            assertion = session.get(Assertion, assertion_id)
            if assertion is None or assertion.review_status == "rejected" or assertion.superseded_at:
                continue
            direction = "subject_to_target"
            target_id = assertion.object_entity_id
            if assertion.object_entity_id == film_id:
                direction = "target_to_subject"
                target_id = assertion.subject_entity_id
            target_graph = session.get(GraphEntity, target_id)
            target: dict[str, Any] = {"entity_id": target_id}
            if target_graph is not None:
                target["entity_type"] = target_graph.entity_type
                if target_graph.entity_type == "film":
                    target_film = session.get(Film, target_id)
                    if target_film is not None:
                        target.update(
                            {
                                "display_name": target_film.canonical_title,
                                "release_year": target_film.release_year,
                            }
                        )
                elif target_graph.entity_type == "concept":
                    concept = session.get(Concept, target_id)
                    if concept is not None:
                        target.update({"display_name": concept.canonical_name, "kind": concept.kind})
            evidence_ids: list[str] = []
            links = session.exec(
                select(AssertionEvidence)
                .where(AssertionEvidence.assertion_id == assertion.id)
                .where(AssertionEvidence.link_status == "active")
            ).all()
            for link in links:
                evidence = session.get(Evidence, link.evidence_id)
                if evidence is None:
                    continue
                evidence_ids.append(evidence.id)
                evidence_by_id[evidence.id] = {
                    "id": evidence.id,
                    "source_title": evidence.source_title,
                    "source_uri": evidence.source_uri,
                    "publisher": evidence.publisher,
                    "claim": evidence.claim,
                    "retrieved_at": evidence.retrieved_at,
                    "stance": link.stance,
                }
            relations.append(
                {
                    "id": assertion.id,
                    "predicate": assertion.predicate,
                    "direction": direction,
                    "target": target,
                    "qualifiers": assertion.qualifiers or {},
                    "rationale": assertion.rationale,
                    "review_status": assertion.review_status,
                    "evidence_ids": sorted(evidence_ids),
                }
            )
        reviews = session.exec(
            select(AnalysisResolutionReview)
            .where(AnalysisResolutionReview.analysis_run_id == run.id)
            .order_by(AnalysisResolutionReview.created_at, AnalysisResolutionReview.id)
        ).all()
        return {
            "film_id": film_id,
            "status": run.status,
            "run": {
                "id": run.id,
                "provider": run.provider,
                "model": run.model,
                "created_at": run.created_at,
                "finished_at": run.finished_at,
                "error_code": run.error_code,
            },
            "summary": run.result_summary,
            "relations": sorted(relations, key=lambda item: (item["predicate"], item["direction"], item["id"])),
            "evidence": [evidence_by_id[key] for key in sorted(evidence_by_id)],
            "reviews": [
                {
                    "id": review.id,
                    "predicate": review.predicate,
                    "candidate_kind": review.candidate_kind,
                    "reason_code": review.reason_code,
                    "candidate_summary": review.candidate_summary,
                    "status": review.status,
                }
                for review in reviews
            ],
        }

    def _resolve_target(
        self,
        session: Session,
        candidate: AnalysisAssertionCandidate,
        remote_details: dict[str, Any] | None,
        remote_failure: str | None,
        now: str,
    ) -> str:
        target = candidate.target
        entity_id: str | None = None
        if target.entity_id:
            entity_id = target.entity_id
        elif target.provider and target.external_id:
            identity = session.exec(
                select(ExternalIdentity)
                .where(ExternalIdentity.provider == target.provider)
                .where(ExternalIdentity.external_id == target.external_id)
                .where(ExternalIdentity.identity_status == "active")
            ).first()
            if identity is not None:
                entity_id = identity.entity_id
            elif target.provider == "tmdb.movie" and remote_details is not None:
                entity_id = self._materialize_tmdb_film(session, target, remote_details, now)
            elif remote_failure:
                raise ResolutionFailure(remote_failure)
            else:
                # A claimed external identity is an atomic reference. Never
                # discard a bad provider/ID pair and silently resolve its name
                # to a different Film.
                raise ResolutionFailure("identity_conflict")
        if entity_id is None and target.display_name:
            entity_id = self._resolve_by_name(session, target, candidate.predicate.value)
        if entity_id is None:
            raise ResolutionFailure("unresolved_reference")
        entity_id = self._follow_merge(session, entity_id)
        graph = session.get(GraphEntity, entity_id)
        if graph is None or graph.entity_type != target.entity_type:
            raise ResolutionFailure("predicate_type_mismatch")
        if graph.entity_type == "film":
            self._validate_film_reference_consistency(session, target, entity_id)
        concept_kind = None
        if graph.entity_type == "concept":
            concept = session.get(Concept, entity_id)
            concept_kind = concept.kind if concept else None
        try:
            validate_assertion_semantics(
                predicate=candidate.predicate.value,
                subject_entity_type="film",
                object_entity_type=graph.entity_type,
                object_concept_kind=concept_kind,
            )
        except ValueError as exc:
            raise ResolutionFailure("predicate_type_mismatch") from exc
        return entity_id

    def _materialize_tmdb_film(
        self,
        session: Session,
        target: AnalysisEntityReference,
        details: dict[str, Any],
        now: str,
    ) -> str:
        self._validate_tmdb_reference_details(target, details)
        try:
            requested_id = int(target.external_id or "")
            returned_id = int(details.get("id"))
        except (TypeError, ValueError) as exc:
            raise ResolutionFailure("identity_conflict") from exc
        if requested_id <= 0 or returned_id != requested_id:
            raise ResolutionFailure("identity_conflict")
        imdb_id = details.get("imdb_id") or (details.get("external_ids") or {}).get("imdb_id")
        identities = [("tmdb.movie", str(requested_id))]
        if isinstance(imdb_id, str) and imdb_id.strip():
            identities.append(("imdb.title", imdb_id.strip()))
        owners: set[str] = set()
        for provider, external_id in identities:
            existing = session.exec(
                select(ExternalIdentity)
                .where(ExternalIdentity.provider == provider)
                .where(ExternalIdentity.external_id == external_id)
                .where(ExternalIdentity.identity_status == "active")
            ).first()
            if existing is not None:
                owners.add(existing.entity_id)
        if len(owners) > 1:
            raise ResolutionFailure("identity_conflict")
        if owners:
            film_id = next(iter(owners))
            graph = session.get(GraphEntity, film_id)
            film = session.get(Film, film_id)
            if graph is None or graph.entity_type != "film" or film is None:
                raise ResolutionFailure("identity_conflict")
        else:
            film_id = f"film_{uuid4().hex}"
            title = str(details.get("title") or details.get("original_title") or "").strip()
            if not title:
                raise ResolutionFailure("invalid_candidate")
            film = Film(
                id=film_id,
                canonical_title=title[:300],
                original_title=(str(details.get("original_title") or title))[:300],
                release_date=str(details.get("release_date") or "") or None,
                release_year=self._release_year(details.get("release_date")),
                runtime_minutes=self._positive_int(details.get("runtime")),
                overview=(str(details.get("overview") or ""))[:5000] or None,
                lifecycle_status="active",
                created_at=now,
                updated_at=now,
            )
            session.add(GraphEntity(id=film_id, entity_type="film", created_at=now, updated_at=now))
            session.flush()
            session.add(film)
            session.flush()
        for provider, external_id in identities:
            existing = session.exec(
                select(ExternalIdentity)
                .where(ExternalIdentity.provider == provider)
                .where(ExternalIdentity.external_id == external_id)
            ).first()
            if existing is not None and existing.entity_id != film_id:
                raise ResolutionFailure("identity_conflict")
            if existing is None:
                session.add(
                    ExternalIdentity(
                        id=f"identity_{uuid4().hex}",
                        entity_id=film_id,
                        provider=provider,
                        external_id=external_id,
                        identity_status="active",
                        verified_at=now,
                        provenance_kind="tmdb",
                        provenance_ref=f"tmdb.movie:{requested_id}",
                        created_at=now,
                        updated_at=now,
                    )
                )
        observation = tmdb_structured_metadata_observation(
            details,
            requested_id,
            language="en-US",
            observed_at=now,
        )
        limited = StructuredMetadataObservation(
            origin_kind=observation.origin_kind,
            origin_ref=observation.origin_ref,
            source_instance_id=observation.source_instance_id,
            observed_at=observation.observed_at,
            complete_fields=frozenset({"titles", "countries", "genres"}),
            titles=observation.titles,
            countries=observation.countries,
            genres=observation.genres,
            issues=tuple(issue for issue in observation.issues if issue.field_kind != "credit"),
        )
        structured_metadata_synchronizer.sync(
            session,
            film_id=film_id,
            library_item_id=None,
            observation=limited,
        )
        return film_id

    def _validate_film_reference_consistency(
        self,
        session: Session,
        target: AnalysisEntityReference,
        film_id: str,
    ) -> None:
        film = session.get(Film, film_id)
        if film is None:
            raise ResolutionFailure("identity_conflict")
        if target.release_year is not None and film.release_year != target.release_year:
            raise ResolutionFailure("identity_conflict")
        if target.display_name:
            expected = normalize_metadata_text(target.display_name)
            known_titles = {
                normalize_metadata_text(film.canonical_title),
                normalize_metadata_text(film.original_title or ""),
            }
            known_titles.update(
                item.normalized_title
                for item in session.exec(
                    select(FilmTitle)
                    .where(FilmTitle.film_id == film_id)
                    .where(FilmTitle.superseded_at.is_(None))
                ).all()
            )
            if expected not in known_titles:
                raise ResolutionFailure("identity_conflict")

    def _validate_tmdb_reference_details(
        self,
        target: AnalysisEntityReference,
        details: dict[str, Any],
    ) -> None:
        if target.release_year is not None:
            returned_year = self._release_year(details.get("release_date"))
            if returned_year != target.release_year:
                raise ResolutionFailure("identity_conflict")
        if target.display_name:
            expected = normalize_metadata_text(target.display_name)
            returned_titles = {
                normalize_metadata_text(str(details.get("title") or "")),
                normalize_metadata_text(str(details.get("original_title") or "")),
            }
            if expected not in returned_titles:
                raise ResolutionFailure("identity_conflict")

    def _resolve_by_name(
        self,
        session: Session,
        target: AnalysisEntityReference,
        predicate: str,
    ) -> str | None:
        normalized = normalize_metadata_text(target.display_name or "")
        if not normalized:
            return None
        if target.entity_type == "film":
            candidates = session.exec(
                select(Film)
                .where(Film.lifecycle_status == "active")
                .where(Film.release_year == target.release_year)
            ).all()
            matches = {
                film.id
                for film in candidates
                if normalized
                in {
                    normalize_metadata_text(film.canonical_title),
                    normalize_metadata_text(film.original_title or ""),
                }
            }
            title_rows = session.exec(
                select(FilmTitle)
                .where(FilmTitle.normalized_title == normalized)
                .where(FilmTitle.superseded_at.is_(None))
            ).all()
            candidate_ids = {film.id for film in candidates}
            matches.update(item.film_id for item in title_rows if item.film_id in candidate_ids)
            if len(matches) > 1:
                raise ResolutionFailure("ambiguous_reference")
            return next(iter(matches)) if matches else None
        if target.entity_type == "concept":
            expected_kind = {
                AssertionPredicateKey.HAS_THEME.value: "theme",
                AssertionPredicateKey.HAS_MOVEMENT.value: "movement",
                AssertionPredicateKey.HAS_VISUAL_STYLE.value: "visual_style",
                AssertionPredicateKey.HAS_MICRO_GENRE.value: "micro_genre",
            }.get(predicate)
            concepts = session.exec(
                select(Concept)
                .where(Concept.kind == expected_kind)
                .where(Concept.lifecycle_status == "active")
            ).all()
            matches = {
                concept.id
                for concept in concepts
                if normalize_metadata_text(concept.canonical_name) == normalized
            }
            aliases = session.exec(
                select(ConceptAlias).where(ConceptAlias.normalized_alias == normalized)
            ).all()
            concept_ids = {item.id for item in concepts}
            matches.update(alias.concept_id for alias in aliases if alias.concept_id in concept_ids)
            if len(matches) > 1:
                raise ResolutionFailure("ambiguous_reference")
            return next(iter(matches)) if matches else None
        return None

    def _follow_merge(self, session: Session, entity_id: str) -> str:
        seen: set[str] = set()
        current = entity_id
        for _ in range(8):
            if current in seen:
                raise ResolutionFailure("identity_conflict")
            seen.add(current)
            entity = session.get(GraphEntity, current)
            if entity is None:
                raise ResolutionFailure("unresolved_reference")
            if entity.lifecycle_status == "active":
                return current
            if entity.lifecycle_status != "merged" or not entity.merged_into_id:
                raise ResolutionFailure("unresolved_reference")
            current = entity.merged_into_id
        raise ResolutionFailure("identity_conflict")

    def _upsert_assertion(
        self,
        session: Session,
        *,
        run: AnalysisRun,
        candidate: AnalysisAssertionCandidate,
        subject_id: str,
        object_id: str,
        now: str,
    ) -> Assertion:
        validate_automatic_assertion_decision(
            predicate=candidate.predicate.value,
            source_scope="inferred",
            review_status="proposed",
            review_method="none",
            origin_kind="analysis_run",
        )
        qualifiers = candidate.qualifiers.model_dump(exclude_none=True) if candidate.qualifiers else {}
        qualifier_hash = assertion_qualifier_hash(qualifiers)
        semantic_key = assertion_semantic_key(
            subject_entity_id=subject_id,
            predicate=candidate.predicate.value,
            object_entity_id=object_id,
            qualifier_hash=qualifier_hash,
        )
        assertion = session.exec(
            select(Assertion).where(Assertion.assertion_key == semantic_key)
        ).first()
        if assertion is None:
            assertion = Assertion(
                subject_entity_id=subject_id,
                object_entity_id=object_id,
                predicate=candidate.predicate.value,
                qualifiers=qualifiers,
                qualifier_hash=qualifier_hash,
                assertion_key=semantic_key,
                source_scope="inferred",
                review_status="proposed",
                review_method="none",
                rationale=candidate.rationale,
                first_seen_at=now,
                last_seen_at=now,
                created_at=now,
                updated_at=now,
            )
        else:
            assertion.review_status = preserve_review_status(assertion.review_status, "proposed")
            if assertion.review_status == "proposed":
                assertion.rationale = candidate.rationale
            assertion.last_seen_at = now
            assertion.superseded_at = None
            assertion.updated_at = now
        session.add(assertion)
        session.flush()
        provenance = session.exec(
            select(AssertionProvenance)
            .where(AssertionProvenance.assertion_id == assertion.id)
            .where(AssertionProvenance.origin_kind == "analysis_run")
            .where(AssertionProvenance.origin_ref == run.id)
        ).first()
        payload_hash = canonical_json_hash(candidate.model_dump(mode="json", exclude_none=True))
        if provenance is None:
            provenance = AssertionProvenance(
                assertion_id=assertion.id,
                origin_kind="analysis_run",
                origin_scope="inferred",
                origin_ref=run.id,
                analysis_run_id=run.id,
                source_field="assertions",
                source_payload_hash=payload_hash,
                first_observed_at=now,
                last_observed_at=now,
            )
        else:
            provenance.last_observed_at = now
            provenance.source_payload_hash = payload_hash
            provenance.superseded_at = None
        session.add(provenance)
        return assertion

    def _upsert_evidence(self, session: Session, item, now: str) -> Evidence:
        key = evidence_semantic_key(
            source_uri=item.source_uri,
            content_hash=item.content_hash,
            claim=item.candidate.claim,
        )
        evidence = session.exec(select(Evidence).where(Evidence.evidence_key == key)).first()
        if evidence is None:
            evidence = Evidence(
                evidence_key=key,
                evidence_type="web",
                source_title=item.candidate.source_title,
                source_uri=item.source_uri,
                publisher=item.candidate.publisher,
                claim=item.candidate.claim,
                retrieved_at=item.retrieved_at,
                content_hash=item.content_hash,
                verification_policy_version=EVIDENCE_VERIFICATION_POLICY_VERSION,
                created_at=now,
                updated_at=now,
            )
            session.add(evidence)
            session.flush()
        return evidence

    def _upsert_review(
        self,
        session: Session,
        *,
        run: AnalysisRun,
        predicate: str | None,
        candidate_kind: str,
        reason_code: str,
        candidate_summary: dict[str, Any],
        now: str,
    ) -> AnalysisResolutionReview:
        candidate_summary = validate_analysis_review_candidate(candidate_summary)
        review_key, candidate_hash = analysis_review_key(
            analysis_run_id=run.id,
            candidate_kind=candidate_kind,
            reason_code=reason_code,
            predicate=predicate,
            candidate=candidate_summary,
        )
        review = session.exec(
            select(AnalysisResolutionReview).where(AnalysisResolutionReview.review_key == review_key)
        ).first()
        if review is None:
            review = AnalysisResolutionReview(
                analysis_run_id=run.id,
                film_id=run.film_id,
                predicate=predicate,
                candidate_kind=candidate_kind,
                reason_code=reason_code,
                candidate_summary=candidate_summary,
                candidate_hash=candidate_hash,
                review_key=review_key,
                status="open",
                created_at=now,
                updated_at=now,
            )
            session.add(review)
        elif review.status == "open":
            review.updated_at = now
            session.add(review)
        return review

    def _supersede_previous_run_provenance(
        self,
        session: Session,
        run: AnalysisRun,
        now: str,
    ) -> None:
        previous_runs = session.exec(
            select(AnalysisRun)
            .where(AnalysisRun.film_id == run.film_id)
            .where(AnalysisRun.analysis_kind == run.analysis_kind)
            .where(AnalysisRun.status == "succeeded")
            .where(AnalysisRun.id != run.id)
        ).all()
        previous_ids = {item.id for item in previous_runs}
        if not previous_ids:
            return
        affected: set[str] = set()
        provenance_rows = session.exec(
            select(AssertionProvenance)
            .where(AssertionProvenance.analysis_run_id.in_(previous_ids))
            .where(AssertionProvenance.superseded_at.is_(None))
        ).all()
        for provenance in provenance_rows:
            provenance.superseded_at = now
            session.add(provenance)
            affected.add(provenance.assertion_id)
        session.flush()
        for assertion_id in affected:
            assertion = session.get(Assertion, assertion_id)
            if assertion is None or assertion.review_status != "proposed":
                continue
            active = session.exec(
                select(AssertionProvenance)
                .where(AssertionProvenance.assertion_id == assertion_id)
                .where(AssertionProvenance.superseded_at.is_(None))
            ).first()
            assertion.superseded_at = None if active is not None else now
            assertion.updated_at = now
            session.add(assertion)

    def _preliminarily_resolvable(
        self,
        session: Session,
        candidate: AnalysisAssertionCandidate,
        remote_details: dict[str, Any] | None,
    ) -> bool:
        if self._has_disallowed_model_qualifiers(candidate):
            return False
        if remote_details is not None:
            try:
                self._validate_tmdb_reference_details(candidate.target, remote_details)
            except ResolutionFailure:
                return False
            return True
        if candidate.target.entity_id:
            try:
                entity_id = self._follow_merge(session, candidate.target.entity_id)
                graph = session.get(GraphEntity, entity_id)
                if graph is None or graph.entity_type != candidate.target.entity_type:
                    return False
                if graph.entity_type == "film":
                    self._validate_film_reference_consistency(session, candidate.target, entity_id)
                return True
            except ResolutionFailure:
                return False
        if candidate.target.provider and candidate.target.external_id:
            identity = session.exec(
                select(ExternalIdentity)
                .where(ExternalIdentity.provider == candidate.target.provider)
                .where(ExternalIdentity.external_id == candidate.target.external_id)
                .where(ExternalIdentity.identity_status == "active")
            ).first()
            if identity is None:
                return False
            try:
                self._validate_film_reference_consistency(session, candidate.target, identity.entity_id)
                return True
            except ResolutionFailure:
                return False
        try:
            return self._resolve_by_name(session, candidate.target, candidate.predicate.value) is not None
        except ResolutionFailure:
            return False

    @staticmethod
    def _has_disallowed_model_qualifiers(candidate: AnalysisAssertionCandidate) -> bool:
        return bool(
            candidate.qualifiers
            and candidate.qualifiers.model_dump(exclude_none=True)
        )

    @staticmethod
    def _assertion_summary(candidate: AnalysisAssertionCandidate) -> dict[str, Any]:
        return {
            "predicate": candidate.predicate.value,
            "direction": candidate.direction,
            "source_scope": candidate.source_scope,
            "target": candidate.target.model_dump(mode="json", exclude_none=True),
            "rationale": candidate.rationale,
            "qualifiers": candidate.qualifiers.model_dump(mode="json", exclude_none=True)
            if candidate.qualifiers
            else {},
        }

    @staticmethod
    def assertion_candidate_key(index: int) -> str:
        return f"a{index:03d}"

    @staticmethod
    def evidence_candidate_key(assertion_index: int, evidence_index: int) -> str:
        return f"a{assertion_index:03d}:e{evidence_index:03d}"

    @staticmethod
    def _candidate_index(candidate_key: str) -> int:
        try:
            return int(candidate_key.removeprefix("a"))
        except ValueError:
            return 10**9

    @staticmethod
    def _release_year(value: Any) -> int | None:
        try:
            year = int(str(value)[:4])
        except (TypeError, ValueError):
            return None
        return year if 1888 <= year <= 2200 else None

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


analysis_runtime_persistence = AnalysisRuntimePersistence()


__all__ = [
    "ANALYSIS_APP_VERSION",
    "ANALYSIS_KIND",
    "ANALYSIS_POLICY_VERSION",
    "ANALYSIS_RESOLVER_VERSION",
    "ANALYSIS_SCHEMA_VERSION",
    "AnalysisAlreadyRunning",
    "AnalysisCompletion",
    "AnalysisRuntimeError",
    "AnalysisStart",
    "AnalysisSubjectMismatch",
    "analysis_runtime_persistence",
]
