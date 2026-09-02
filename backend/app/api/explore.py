from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.services.explore_query import EXPLORE_DIMENSIONS, explore_query_service
from app.utils.security import validate_resource_id


router = APIRouter()


@router.get("/explore")
def get_explore_overview():
    return explore_query_service.overview()


@router.get("/explore/context")
def get_explore_context(
    genre: list[str] = Query(default=[]),
    person: list[str] = Query(default=[]),
    country: list[str] = Query(default=[]),
    decade: list[str] = Query(default=[]),
    view: Literal["all", "watched", "unwatched"] = "all",
    limit: int = Query(default=6, ge=1, le=12),
):
    return explore_query_service.context(
        filters=_validated_filters(genre, person, country, decade),
        view=view,
        limit=limit,
    )


@router.get("/explore/facets/{dimension}")
def get_explore_facets(
    dimension: Literal["genre", "person", "country", "decade"],
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return explore_query_service.list_facets(
        dimension,
        query=q,
        limit=limit,
        offset=offset,
    )


@router.get("/explore/films")
def get_explore_films(
    genre: list[str] = Query(default=[]),
    person: list[str] = Query(default=[]),
    country: list[str] = Query(default=[]),
    decade: list[str] = Query(default=[]),
    view: Literal["all", "watched", "unwatched"] = "all",
    sort: Literal["title", "year"] = "title",
    dir: Literal["asc", "desc"] | None = None,
    limit: int = Query(default=40, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    filters = _validated_filters(genre, person, country, decade)
    direction = dir or ("desc" if sort == "year" else "asc")
    return explore_query_service.list_films(
        filters=filters,
        view=view,
        sort=sort,
        direction=direction,
        limit=limit,
        offset=offset,
    )


def _validated_filters(
    genre: list[str],
    person: list[str],
    country: list[str],
    decade: list[str],
) -> dict[str, list[str]]:
    return {
        "genre": _validate_values("genre", genre),
        "person": _validate_values("person", person),
        "country": _validate_values("country", country),
        "decade": _validate_values("decade", decade),
    }


def _validate_values(dimension: str, values: list[str]) -> list[str]:
    normalized_values = [
        f"con_{value.removeprefix('concept_')}"
        if dimension == "genre" and value.startswith("concept_")
        else value
        for value in values
    ]
    unique = sorted(set(normalized_values))
    if len(unique) > 20:
        raise HTTPException(status_code=422, detail=f"{dimension} accepts at most 20 values")
    for value in unique:
        valid = False
        if dimension == "genre":
            valid = validate_resource_id(value, "con")
        elif dimension == "person":
            valid = validate_resource_id(value, "person")
        elif dimension == "country":
            valid = bool(re.fullmatch(r"[A-Z]{2}", value))
        elif dimension == "decade":
            valid = bool(re.fullmatch(r"[0-9]{3}0", value))
        if not valid:
            raise HTTPException(status_code=422, detail=f"Invalid {dimension} filter")
    return unique


assert set(EXPLORE_DIMENSIONS) == {"genre", "person", "country", "decade"}
