"""Local user decisions over existing Analysis entities; never calls a provider."""
from __future__ import annotations

from sqlalchemy import or_, text
from sqlmodel import Session, select

from app.canonical_models import (
    AnalysisResolutionReview, AnalysisRun, Assertion, AssertionEvidence,
    AssertionProvenance, Concept, Evidence, Film, GraphEntity, Person,
)
from app.contracts.analysis_persistence import (
    ASSERTION_PREDICATE_REGISTRY, assertion_qualifier_hash,
    assertion_semantic_key, validate_assertion_semantics,
)
from app.contracts.analysis_v2 import AnalysisPredicate
from app.contracts.structured_metadata import canonical_json_hash
from app.database import engine
from app.models import utc_now_iso
from app.services.canonical_runtime import canonical_runtime_writer
from app.services.event_store import event_store


class ReviewError(ValueError):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code = code
        self.status = status


def revision(row) -> str:
    return canonical_json_hash(row.model_dump(mode="json"))


class AnalysisReviewService:
    @staticmethod
    def _film(session, film_id):
        film = session.get(Film, film_id)
        if film is None or film.lifecycle_status != "active":
            raise ReviewError("film_not_found", 404)

    @staticmethod
    def _assertions(film_id):
        return (
            select(Assertion).join(AssertionProvenance)
            .outerjoin(AnalysisRun, AssertionProvenance.analysis_run_id == AnalysisRun.id)
            .where(or_(AnalysisRun.film_id == film_id,
                       AssertionProvenance.origin_ref == f"analysis-review:{film_id}"))
            .where(or_(Assertion.subject_entity_id == film_id, Assertion.object_entity_id == film_id))
            .where(Assertion.source_scope.in_(["inferred", "curated"]))
            .where(Assertion.predicate.in_([value.value for value in AnalysisPredicate]))
            .where(Assertion.superseded_at.is_(None)).distinct()
        )

    @staticmethod
    def _entity(session, entity_id):
        graph = session.get(GraphEntity, entity_id)
        if graph is None or graph.lifecycle_status != "active":
            raise ReviewError("target_unavailable", 422)
        model = {"film": Film, "concept": Concept, "person": Person}[graph.entity_type]
        entity = session.get(model, entity_id)
        if entity is None or entity.lifecycle_status != "active":
            raise ReviewError("target_unavailable", 422)
        return {"entity_id": entity_id, "entity_type": graph.entity_type,
                "display_name": entity.canonical_title if isinstance(entity, Film) else entity.canonical_name,
                "release_year": entity.release_year if isinstance(entity, Film) else None,
                "kind": entity.kind if isinstance(entity, Concept) else None}

    def list(self, film_id, *, offset=0, limit=50):
        with Session(engine) as session:
            self._film(session, film_id)
            assertions = session.exec(self._assertions(film_id).order_by(Assertion.created_at, Assertion.id)
                                      .offset(offset).limit(limit + 1)).all()
            reviews = session.exec(select(AnalysisResolutionReview)
                                   .where(AnalysisResolutionReview.film_id == film_id)
                                   .order_by(AnalysisResolutionReview.created_at, AnalysisResolutionReview.id)
                                   .offset(offset).limit(limit + 1)).all()
            return {
                "relations": [self._relation(session, film_id, row) for row in assertions[:limit]],
                "reviews": [{"id": row.id, "predicate": row.predicate,
                             "candidate_kind": row.candidate_kind, "reason_code": row.reason_code,
                             "candidate_summary": row.candidate_summary, "status": row.status,
                             "resolved_entity_id": row.resolved_entity_id, "revision": revision(row)}
                            for row in reviews[:limit]],
                "offset": offset, "limit": limit,
                "next_offset": offset + limit if len(assertions) > limit or len(reviews) > limit else None,
            }

    def _relation(self, session, film_id, row):
        outgoing = row.subject_entity_id == film_id
        target_id = row.object_entity_id if outgoing else row.subject_entity_id
        try:
            target = self._entity(session, target_id)
        except ReviewError:
            target = {"entity_id": target_id, "display_name": target_id}
        evidence = session.exec(select(Evidence).join(AssertionEvidence)
                                .where(AssertionEvidence.assertion_id == row.id)
                                .where(AssertionEvidence.link_status == "active")
                                .order_by(Evidence.id).limit(16)).all()
        return {"id": row.id, "predicate": row.predicate,
                "direction": "subject_to_target" if outgoing else "target_to_subject",
                "target": target, "rationale": row.rationale,
                "review_status": row.review_status, "revision": revision(row),
                "evidence": [{"id": item.id, "source_title": item.source_title,
                              "source_uri": item.source_uri} for item in evidence]}

    def targets(self, film_id, predicate, query, entity_type=None):
        definition = ASSERTION_PREDICATE_REGISTRY[predicate]
        with Session(engine) as session:
            self._film(session, film_id)
            model = {"film": Film, "concept": Concept, "person": Person}[entity_type or definition.object_entity_type]
            label = model.canonical_title if model is Film else model.canonical_name
            statement = select(model).join(GraphEntity, model.id == GraphEntity.id).where(
                model.lifecycle_status == "active", GraphEntity.lifecycle_status == "active",
                model.id != film_id,
            )
            if model is Concept and entity_type is None:
                statement = statement.where(Concept.kind == definition.object_concept_kind)
            if query.strip():
                term = query.strip()
                clause = or_(label.icontains(term, autoescape=True), model.id == term)
                if model is Film:
                    clause = or_(clause, Film.original_title.icontains(term, autoescape=True))
                statement = statement.where(clause)
            rows = session.exec(statement.order_by(label, model.id).limit(30)).all()
            return [self._entity(session, row.id) for row in rows]

    def _validate_target(self, session, film_id, predicate, target_id, direction):
        target = self._entity(session, target_id)
        if target_id == film_id or (direction == "target_to_subject" and target["entity_type"] != "film"):
            raise ReviewError("invalid_direction_or_self_reference", 422)
        try:
            validate_assertion_semantics(predicate=predicate, subject_entity_type="film",
                                         object_entity_type=target["entity_type"],
                                         object_concept_kind=target.get("kind"))
        except ValueError as exc:
            raise ReviewError("predicate_type_mismatch", 422) from exc
        return (film_id, target_id) if direction == "subject_to_target" else (target_id, film_id)

    @staticmethod
    def _decide(session, row, decision, now):
        profile_id = canonical_runtime_writer.local_profile_id(session)
        row.review_status = decision
        row.review_method = "user"
        row.review_policy_version = None
        row.reviewed_by_profile_id = profile_id
        row.reviewed_at = now
        row.updated_at = now
        session.add(row)

    def _curated(self, session, film_id, predicate, target_id, direction, now):
        subject, object_id = self._validate_target(session, film_id, predicate, target_id, direction)
        qualifier_hash = assertion_qualifier_hash({})
        key = assertion_semantic_key(subject_entity_id=subject, predicate=predicate,
                                     object_entity_id=object_id, qualifier_hash=qualifier_hash)
        row = session.exec(select(Assertion).where(Assertion.assertion_key == key)).first()
        if row is not None and (row.review_status == "rejected" or row.superseded_at or row.source_scope == "factual"):
            raise ReviewError("target_relation_conflict")
        if row is None:
            row = Assertion(subject_entity_id=subject, object_entity_id=object_id,
                            predicate=predicate, qualifiers={}, qualifier_hash=qualifier_hash,
                            assertion_key=key, source_scope="curated", first_seen_at=now, last_seen_at=now)
        self._decide(session, row, "accepted", now)
        session.flush()
        origin_ref = f"analysis-review:{film_id}"
        provenance = session.exec(select(AssertionProvenance).where(
            AssertionProvenance.assertion_id == row.id, AssertionProvenance.origin_kind == "user",
            AssertionProvenance.origin_ref == origin_ref)).first()
        if provenance is None:
            session.add(AssertionProvenance(assertion_id=row.id, origin_kind="user", origin_scope="curated",
                                           origin_ref=origin_ref, first_observed_at=now, last_observed_at=now))
        # Evidence and model rationale are never copied to a different relationship.
        return row

    def decide(self, film_id, assertion_id, request):
        with Session(engine) as session:
            session.execute(text("BEGIN IMMEDIATE"))
            self._film(session, film_id)
            row = session.exec(self._assertions(film_id).where(Assertion.id == assertion_id)).first()
            if row is None:
                raise ReviewError("assertion_not_found", 404)
            if revision(row) != request.revision:
                raise ReviewError("stale_review")
            now = utc_now_iso()
            replacement = None
            if request.correction is not None:
                if row.review_status == "rejected":
                    raise ReviewError("review_closed")
                correction = request.correction
                subject, object_id = self._validate_target(session, film_id, correction.predicate,
                                                           correction.target_entity_id, correction.direction)
                if (subject, correction.predicate, object_id) == (row.subject_entity_id, row.predicate, row.object_entity_id):
                    raise ReviewError("unchanged_correction", 422)
                replacement = self._curated(session, film_id, correction.predicate,
                                            correction.target_entity_id, correction.direction, now)
            elif request.decision == "accepted":
                outgoing = row.subject_entity_id == film_id
                self._validate_target(session, film_id, row.predicate,
                                      row.object_entity_id if outgoing else row.subject_entity_id,
                                      "subject_to_target" if outgoing else "target_to_subject")
            decision = "rejected" if replacement else request.decision
            if row.review_status != decision or row.review_method != "user":
                self._decide(session, row, decision, now)
                event_store.append_in_session(session, "AnalysisAssertionReviewed", "film", film_id,
                    {"assertion_id": row.id, "decision": decision,
                     "replacement_id": replacement.id if replacement else None}, actor_type="user")
            elif replacement:
                event_store.append_in_session(session, "AnalysisAssertionReviewed", "film", film_id,
                    {"assertion_id": row.id, "decision": decision, "replacement_id": replacement.id}, actor_type="user")
            session.commit()
            return {"status": decision, "assertion_id": row.id,
                    "replacement_id": replacement.id if replacement else None}

    def resolve(self, film_id, review_id, request):
        with Session(engine) as session:
            session.execute(text("BEGIN IMMEDIATE"))
            self._film(session, film_id)
            row = session.get(AnalysisResolutionReview, review_id)
            if row is None or row.film_id != film_id:
                raise ReviewError("review_not_found", 404)
            if revision(row) != request.revision:
                raise ReviewError("stale_review")
            desired = {"dismiss": "dismissed", "resolve": "resolved", "reopen": "open"}[request.action]
            if row.status == desired:
                return {"status": row.status, "review_id": row.id}
            if row.status != "open" and request.action != "reopen":
                raise ReviewError("review_closed")
            now = utc_now_iso()
            target_id = None
            replacement = None
            if request.action == "resolve":
                if row.candidate_kind not in {"assertion", "entity_reference"}:
                    raise ReviewError("review_cannot_be_resolved", 422)
                target_id = request.correction.target_entity_id
                if row.candidate_kind == "assertion":
                    correction = request.correction
                    replacement = self._curated(session, film_id, correction.predicate,
                                                target_id, correction.direction, now)
                else:
                    target = self._entity(session, target_id)
                    if target_id == film_id or target["entity_type"] != row.candidate_summary.get("target", {}).get("entity_type"):
                        raise ReviewError("predicate_type_mismatch", 422)
            row.status = desired
            row.resolved_entity_id = target_id
            row.resolved_at = None if desired == "open" else now
            row.updated_at = now
            session.add(row)
            event_store.append_in_session(session, "AnalysisReferenceReviewed", "film", film_id,
                {"review_id": row.id, "decision": desired,
                 "assertion_id": replacement.id if replacement else None}, actor_type="user")
            session.commit()
            return {"status": desired, "review_id": row.id}


analysis_review_service = AnalysisReviewService()
