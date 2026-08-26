from fastapi import APIRouter

from app.api.common import MEDIA_DIR
router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "healthy"}


@router.get("/")
def read_root():
    return {"message": "Film Genealogy API is running", "media_dir": MEDIA_DIR}
