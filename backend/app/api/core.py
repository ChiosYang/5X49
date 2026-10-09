from fastapi import APIRouter

from app.services.settings import get_media_dir
from app.services.diagnostics import system_diagnostics, provider_diagnostics
router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "healthy"}


@router.get("/diagnostics")
def get_diagnostics():
    return system_diagnostics()


@router.get("/diagnostics/providers")
def check_providers():
    return provider_diagnostics()


@router.get("/")
def read_root():
    return {"message": "Film Genealogy API is running", "media_dir": get_media_dir()}
