from __future__ import annotations

import re
import asyncio
import time
from threading import Event, Lock
from collections import OrderedDict
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from app.contracts.discovery_search import DiscoveryCancel, DiscoveryIndexAction, DiscoveryQuestion, DiscoveryQuery
from app.services.ask import AskError
from app.services.discovery_search import discovery_search_service
from app.services.integrated_search import IntegratedSearch
from app.services.search_runtime import configured_evaluation
from app.services.semantic_search import SemanticError
from app.services.explore_query import EXPLORE_DIMENSIONS, explore_query_service
from app.utils.security import validate_resource_id


router = APIRouter()
_search_lock = Lock()
_search_owners = {}
_cancelled_owners = OrderedDict()


def _begin_search(identifier):
    event = Event()
    if identifier is None:
        return event
    with _search_lock:
        if len(_search_owners) >= 32 or identifier in _search_owners:
            raise SemanticError("search_busy")
        if identifier in _cancelled_owners:
            event.set()
        _search_owners[identifier] = event
    return event


def _discovery_call(callback):
    try:
        return callback()
    except AskError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code}) from None
    except SemanticError as exc:
        code = "ask_private_input" if exc.code == "private_input" else exc.code
        raise HTTPException(422 if code in {"ask_private_input", "search_snapshot_invalid"} else 503,
                            detail={"code": code}) from None


def _evaluation():
    from app.services import ask as ask_module
    return configured_evaluation(ask_module.engine)


async def _cancellable_search(http_request, runtime, request):
    cancelled = _discovery_call(lambda: _begin_search(request.request_id))
    task = asyncio.create_task(run_in_threadpool(lambda: _discovery_call(
        lambda: runtime.interpret(request, cancelled=cancelled.is_set))))
    try:
        while not task.done():
            await asyncio.wait((task,), timeout=.1)
            if await http_request.is_disconnected():
                cancelled.set()
        return await task
    finally:
        cancelled.set()
        if not task.done():
            task.cancel()
        if request.request_id is not None:
            with _search_lock:
                _search_owners.pop(request.request_id, None)


@router.post("/explore/search/cancel")
def cancel_discovery(request: DiscoveryCancel):
    # Explicit cancellation also crosses buffered/proxied HTTP hops. No model,
    # key, index or question is involved. Random request IDs are owner capabilities.
    with _search_lock:
        event = _search_owners.get(request.request_id)
        if event is not None:
            event.set()
        now = time.monotonic()
        while _cancelled_owners and (len(_cancelled_owners) >= 256
                or next(iter(_cancelled_owners.values())) < now - 120):
            _cancelled_owners.popitem(last=False)
        _cancelled_owners[request.request_id] = now
    return {"cancelled": True}


@router.post("/explore/search/interpret")
async def interpret_discovery(request: DiscoveryQuestion, http_request: Request):
    # Complete deterministic requests do not depend on optional evaluation
    # configuration, cache readiness, provider availability or credentials.
    # Special evaluation/edit/reference submissions still require their proof.
    if not (request.evaluation_only or request.edited_plan is not None or request.reference_id or request.people_ids):
        local = await run_in_threadpool(lambda: _discovery_call(lambda:
            discovery_search_service.interpret(request.model_copy(update={"allow_ai": False}))))
        if local["status"] in {"ready", "needs_clarification"}:
            return local
        if local["status"] == "keyword":
            from app.services.search_local import LocalSearch
            from app.services.content_request import short_keyword
            from app.services.discovery_search import keyword_text
            from app.services import ask as ask_module
            # The legacy keyword status also covers long descriptive sentences.
            # Preserve that semantic path when there is no literal local hit.
            text = local.get("keyword_query") or keyword_text(request.question)
            direct = (not request.allow_ai or short_keyword(text) or await run_in_threadpool(
                lambda: LocalSearch(ask_module.engine).has_keyword_matches(text)))
            if direct:
                return local
    runtime = _discovery_call(_evaluation)
    if runtime is not None:
        return await _cancellable_search(http_request, runtime, request)
    if request.evaluation_only or request.edited_plan is not None or request.reference_id:
        return IntegratedSearch.failure("search_evaluation_disabled")
    return await run_in_threadpool(lambda: _discovery_call(lambda: discovery_search_service.interpret(request)))


@router.post("/explore/search/query")
def query_discovery(request: DiscoveryQuery):
    if request.semantic_snapshot:
        runtime = _discovery_call(_evaluation)
        return (_discovery_call(lambda: runtime.query(request)) if runtime is not None
                else IntegratedSearch.failure("search_evaluation_disabled"))
    return _discovery_call(lambda: discovery_search_service.query(request))


@router.post("/explore/search/index")
def index_discovery(request: DiscoveryIndexAction):
    runtime = _discovery_call(_evaluation)
    if runtime is None:
        raise HTTPException(503, detail={"code": "search_evaluation_disabled"})
    return _discovery_call(lambda: runtime.index(request))


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
    person_match: Literal["any", "all"] = "any",
    limit: int = Query(default=6, ge=1, le=12),
):
    return explore_query_service.context(
        filters=_validated_filters(genre, person, country, decade),
        view=view,
        limit=limit,
        person_match=person_match,
    )


@router.get("/explore/collections")
def get_explore_collections(
    view: Literal["all", "watched", "unwatched"] = "all",
    limit: int = Query(default=6, ge=1, le=12),
):
    return explore_query_service.collections(view=view, limit=limit)


@router.get("/explore/catalog")
def get_explore_catalog(
    category: Literal["all", "director", "country", "decade"] = "all",
    q: str = Query(default="", max_length=200),
    featured: bool = False,
    limit: int = Query(default=24, ge=1, le=24),
    offset: int = Query(default=0, ge=0),
):
    return explore_query_service.catalog(category=category, query=q, featured=featured, limit=limit, offset=offset)


@router.get("/explore/collections/{kind}/{key}")
def get_explore_collection(
    kind: Literal["director", "person", "country", "decade"],
    key: str,
    view: Literal["all", "watched", "unwatched"] = "all",
    sort: Literal["title", "year"] = "title",
    dir: Literal["asc", "desc"] | None = None,
    limit: int = Query(default=40, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    _validate_values("person" if kind in ("director", "person") else kind, [key])
    result = explore_query_service.collection(kind, key, view=view, sort=sort,
        direction=dir or ("desc" if sort == "year" else "asc"), limit=limit, offset=offset)
    if result is None:
        raise HTTPException(status_code=404, detail="Local collection is unavailable")
    return result


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
    person_match: Literal["any", "all"] = "any",
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
        person_match=person_match,
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
