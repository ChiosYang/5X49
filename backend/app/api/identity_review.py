from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlmodel import Session

from app.database import engine
from app.services.identity_review import identity_review_reader
from app.services.identity_decisions import IdentityDecisionError, identity_decision_service
from app.services.settings import get_media_dirs
from app.services.event_bus import library_event_bus
from app.utils.security import validate_resource_id


router = APIRouter()


class IdentityPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["keep_separate", "reconnect"]
    target_item_id: str | None = Field(default=None, pattern=r"^lib_[0-9a-f]{32}$")

    @model_validator(mode="after")
    def target_matches_action(self):
        if (self.action == "reconnect") != (self.target_item_id is not None):
            raise ValueError("Only reconnection requires a target edition")
        return self


class IdentityConfirmRequest(IdentityPreviewRequest):
    confirmation_token: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,64}$")


def _validate_id(review_id: str):
    if not validate_resource_id(review_id, "irev"):
        raise HTTPException(422, detail="Invalid identity review ID")


@router.get("/library/identity-reviews")
def get_identity_reviews(
    status: Literal["open", "resolved", "dismissed", "all"] = "open",
    limit: int = Query(default=40, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1_000_000),
):
    with Session(engine) as session:
        return identity_review_reader.page(session, status=status, limit=limit, offset=offset)


@router.get("/library/identity-reviews/{review_id}")
def get_identity_review(review_id: str):
    _validate_id(review_id)
    with Session(engine) as session:
        result = identity_review_reader.detail(session, review_id)
        if result is None:
            raise HTTPException(404, detail="Identity review not found")
        return result


@router.post("/library/identity-reviews/{review_id}/preview")
def preview_identity_decision(review_id: str, request: IdentityPreviewRequest):
    _validate_id(review_id)
    try:
        with Session(engine) as session:
            return identity_decision_service.preview(session, review_id, request.action,
                request.target_item_id, get_media_dirs())
    except IdentityDecisionError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code}) from exc


@router.post("/library/identity-reviews/{review_id}/confirm")
def confirm_identity_decision(review_id: str, request: IdentityConfirmRequest):
    _validate_id(review_id)
    try:
        result = identity_decision_service.confirm(engine, review_id,
            **request.model_dump(), media_root=get_media_dirs())
    except IdentityDecisionError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code}) from exc
    library_event_bus.publish_library_changed("identity_review_decided", film_id=result["film_id"])
    return result
