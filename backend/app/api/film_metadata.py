from fastapi import APIRouter, HTTPException
from sqlmodel import Session
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.database import engine
from app.services.film_metadata import MetadataConflict, metadata_view, update_metadata
from app.contracts.film_metadata import MetadataUpdate
from app.utils.security import validate_resource_id
from app.services.event_bus import library_event_bus

router = APIRouter()


def validate_film(film_id: str) -> None:
    if not validate_resource_id(film_id, "film"):
        raise HTTPException(422, detail={"code": "invalid_film_id", "message": "Invalid Film ID"})


@router.get("/films/{film_id}/metadata")
def get_film_metadata(film_id: str):
    validate_film(film_id)
    try:
        with Session(engine) as session:
            return metadata_view(session, film_id)
    except LookupError as exc:
        raise HTTPException(404, detail={"code": "film_not_found", "message": str(exc)}) from exc
    except MetadataConflict as exc:
        raise HTTPException(409, detail={"code": exc.code, "message": str(exc)}) from exc


@router.patch("/films/{film_id}/metadata")
def patch_film_metadata(film_id: str, request: MetadataUpdate):
    validate_film(film_id)
    try:
        result = update_metadata(engine, film_id, request)
    except LookupError as exc:
        raise HTTPException(404, detail={"code": "film_not_found", "message": str(exc)}) from exc
    except MetadataConflict as exc:
        raise HTTPException(409, detail={"code": exc.code, "message": str(exc)}) from exc
    except OperationalError as exc:
        raise HTTPException(503, detail={"code": "metadata_temporarily_unavailable",
            "message": "Metadata is temporarily unavailable; retry the same request"}) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(500, detail={"code": "metadata_save_failed",
            "message": "Metadata could not be saved; retry the same request"}) from exc
    if not result["replayed"]:
        library_event_bus.publish_library_changed("film_metadata_updated", film_id=film_id)
    return result
