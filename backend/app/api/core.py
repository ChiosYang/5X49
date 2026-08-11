from fastapi import APIRouter, HTTPException

from app.api.common import MEDIA_DIR
from app.services.historian import FilmHistorian


router = APIRouter()
historian = FilmHistorian()


@router.get("/health")
def health_check():
    return {"status": "healthy"}


@router.get("/")
def read_root():
    return {"message": "Film Genealogy API is running", "media_dir": MEDIA_DIR}


@router.get("/analyze/{movie_name}")
def analyze_movie(movie_name: str):
    result = historian.analyze_genealogy(movie_name)
    if not result:
        raise HTTPException(status_code=404, detail="Film not found or analysis failed")
    return result
