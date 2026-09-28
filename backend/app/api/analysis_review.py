from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.contracts.analysis_v2 import AnalysisPredicate
from app.services.analysis_review import ReviewError, analysis_review_service
from app.services.event_bus import library_event_bus
from app.utils.security import validate_resource_id

router = APIRouter()


class Correction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    predicate: AnalysisPredicate
    target_entity_id: str = Field(pattern=r"^(film|concept|con|person)_[0-9a-f]{32}$")
    direction: Literal["subject_to_target", "target_to_subject"] = "subject_to_target"


class AssertionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["accepted", "rejected"]
    correction: Correction | None = None

    @model_validator(mode="after")
    def validate_correction(self):
        if self.correction and self.decision != "rejected":
            raise ValueError("A correction rejects the original relationship")
        return self


class ResolutionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["resolve", "dismiss", "reopen"]
    correction: Correction | None = None

    @model_validator(mode="after")
    def validate_correction(self):
        if (self.action == "resolve") != (self.correction is not None):
            raise ValueError("Only resolution requires a selected target")
        return self


def _call(film_id, callback):
    if not validate_resource_id(film_id, "film"):
        raise HTTPException(400, "Invalid Film ID")
    try:
        return callback()
    except ReviewError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code}) from exc


@router.get("/films/{film_id}/analysis-review")
def get_analysis_review(film_id: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return _call(film_id, lambda: analysis_review_service.list(film_id, offset=offset, limit=limit))


@router.get("/films/{film_id}/analysis-review/targets")
def get_analysis_review_targets(film_id: str, predicate: AnalysisPredicate, q: str = Query("", max_length=200),
                                entity_type: Literal["film", "concept", "person"] | None = None):
    return _call(film_id, lambda: analysis_review_service.targets(film_id, predicate, q, entity_type))


@router.put("/films/{film_id}/assertions/{assertion_id}/review")
def review_assertion(film_id: str, assertion_id: str, request: AssertionDecision):
    if not validate_resource_id(assertion_id, "ast"):
        raise HTTPException(400, "Invalid Assertion ID")
    result = _call(film_id, lambda: analysis_review_service.decide(film_id, assertion_id, request))
    library_event_bus.publish_library_changed("analysis_review_updated", film_id=film_id)
    return result


@router.put("/films/{film_id}/analysis-reviews/{review_id}")
def resolve_analysis_review(film_id: str, review_id: str, request: ResolutionDecision):
    if not validate_resource_id(review_id, "arev"):
        raise HTTPException(400, "Invalid Review ID")
    result = _call(film_id, lambda: analysis_review_service.resolve(film_id, review_id, request))
    library_event_bus.publish_library_changed("analysis_review_updated", film_id=film_id)
    return result
