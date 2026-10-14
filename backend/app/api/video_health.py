from contextlib import contextmanager
from typing import Literal
from fastapi import APIRouter, HTTPException, Path, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from app import database
from app.health_models import VideoHealth
from app.services.video_health import video_health
from app.services import video_health_views as views

router = APIRouter(prefix="/maintenance/video-health", tags=["maintenance"])


class HealthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool | None = None
    paused: bool | None = None
    start_minute: int | None = Field(default=None, ge=0, le=1439)
    end_minute: int | None = Field(default=None, ge=0, le=1439)
    daily_budget_minutes: int | None = Field(default=None, ge=1, le=1440)


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["cancel", "retry", "acknowledge"]


@contextmanager
def errors():
    try:
        yield
    except LookupError:
        raise HTTPException(404, detail={"code": "health_not_found"}) from None
    except (ValueError, RuntimeError, OSError):
        raise HTTPException(409, detail={"code": "health_version_unavailable"}) from None
    except SQLAlchemyError:
        raise HTTPException(503, detail={"code": "health_storage_unavailable"}) from None


@router.get("")
def status(response: Response):
    response.headers["Cache-Control"] = "no-store"
    with errors():
        return views.status()


@router.put("/config")
def configure(body: HealthConfig):
    values = body.model_dump(exclude_unset=True)
    if not values or any(value is None for value in values.values()):
        raise HTTPException(422, detail={"code": "health_invalid_config"})
    with errors():
        return video_health.configure(values)


@router.post("/queue", status_code=202)
def queue():
    with errors():
        return video_health.queue_all()


@router.post("/cancel")
def cancel():
    with errors(), video_health.guard, Session(database.engine) as session:
        rows = session.exec(select(VideoHealth).where(VideoHealth.status.in_(["unchecked", "queued", "checking"]))).all()
        for row in rows:
            row.cancel_requested = True
            if row.status != "checking":
                video_health._finish_row(row, "incomplete", "cancelled")
            session.add(row)
        state = video_health.runtime(session)
        state.update(sweep=False, manual=False)
        video_health._save_setting(session, "video_health_runtime", state)
        session.commit()
        return {"cancelled": len(rows)}


@router.get("/files")
def files(status: Literal["all", "abnormal", "incomplete", "unsupported", "queued", "unchecked", "passed", "checking"] = "abnormal",
          limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=1000000)):
    with errors():
        items = [row for row in views.records() if status == "all" or row["status"] == status]
        return {"items": items[offset:offset+limit], "total": len(items), "offset": offset, "limit": limit}


@router.get("/files/{identifier}")
def detail(identifier: str = Path(pattern=r"^vh_[0-9a-f]{32}$")):
    with errors():
        return views.detail(identifier)


@router.post("/files/{identifier}")
def control(body: Control, identifier: str = Path(pattern=r"^vh_[0-9a-f]{32}$")):
    with errors():
        video_health.control(identifier, body.action)
        return {"status": "accepted"}
