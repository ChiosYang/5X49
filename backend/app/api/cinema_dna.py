from typing import Literal

from fastapi import APIRouter, Query

from app.api.explore import _validate_values
from app.services.cinema_dna import cinema_dna_service


router = APIRouter()
Dimension = Literal["genre", "person", "country", "decade"]
Metric = Literal["exposure", "preference"]


@router.get("/profile/cinema-dna")
def get_cinema_dna():
    return cinema_dna_service.overview()


@router.get("/profile/cinema-dna/facets/{dimension}")
def get_cinema_dna_facets(
    dimension: Dimension,
    metric: Metric = "exposure",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return cinema_dna_service.facets(dimension, metric=metric, limit=limit, offset=offset)


@router.get("/profile/cinema-dna/contributors")
def get_cinema_dna_contributors(
    dimension: Dimension,
    key: str = Query(max_length=100),
    metric: Metric = "exposure",
    limit: int = Query(default=40, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    normalized = _validate_values(dimension, [key])[0]
    return cinema_dna_service.contributors(dimension, normalized, metric=metric, limit=limit, offset=offset)
