from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlalchemy import case, func
from sqlmodel import Session, select

from app.canonical_models import (
    ExploreFacetReadModel,
    ExploreFilmReadModel,
    LibraryFilmReadModel,
    ProjectionState,
)
from app.database import engine
from app.services.projections import PROJECTION_VERSIONS, ProjectionUnavailable


EXPLORE_VISIBILITY_POLICY = "factual-explore.v1"
EXPLORE_PROJECTION_VERSION = "factual-explore.v1"
EXPLORE_DIMENSIONS = ("genre", "person", "country", "decade")
SAFE_SOURCE_KINDS = {"canonical", "curated", "filename", "nfo", "rule", "tmdb", "user"}
SAFE_ROLES = {"actor", "director"}
SAFE_ARTWORK_KEYS = {
    "poster_local",
    "backdrop_local",
    "poster_thumb_local",
    "backdrop_thumb_local",
    "poster_provider",
    "backdrop_provider",
}


class ExploreQueryService:
    """Serve strict factual Library exploration from synchronous read models."""

    def overview(self, *, top_limit: int = 12) -> dict[str, Any]:
        with Session(engine) as session:
            self._require(session)
            total_films = self._total_films(session)
            dimensions = []
            for dimension in EXPLORE_DIMENSIONS:
                dimensions.append(
                    {
                        "dimension": dimension,
                        "coverage": self._coverage(session, dimension, total_films),
                        "items": self._facet_items(
                            session,
                            dimension,
                            query=None,
                            limit=top_limit,
                            offset=0,
                        ),
                    }
                )
            return {
                "visibility_policy": EXPLORE_VISIBILITY_POLICY,
                "projection_version": EXPLORE_PROJECTION_VERSION,
                "projection_versions": self._projection_versions(),
                "total_films": total_films,
                "dimensions": dimensions,
            }

    def list_facets(
        self,
        dimension: str,
        *,
        query: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        with Session(engine) as session:
            self._require(session)
            total_films = self._total_films(session)
            normalized_query = (query or "").strip().casefold()
            base = (
                select(ExploreFacetReadModel.facet_key)
                .where(ExploreFacetReadModel.dimension == dimension)
                .where(ExploreFacetReadModel.eligible.is_(True))
            )
            if normalized_query:
                base = base.where(
                    ExploreFacetReadModel.normalized_label.contains(normalized_query)
                )
            total = len(set(session.exec(base).all()))
            items = self._facet_items(
                session,
                dimension,
                query=normalized_query or None,
                limit=limit,
                offset=offset,
            )
            next_offset = offset + len(items) if offset + len(items) < total else None
            return {
                "visibility_policy": EXPLORE_VISIBILITY_POLICY,
                "projection_version": EXPLORE_PROJECTION_VERSION,
                "projection_versions": self._projection_versions(),
                "dimension": dimension,
                "coverage": self._coverage(session, dimension, total_films),
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
                "next_offset": next_offset,
            }

    def context(
        self,
        *,
        filters: dict[str, list[str]],
        view: str,
        limit: int,
    ) -> dict[str, Any]:
        normalized = {
            dimension: sorted(set(filters.get(dimension, [])))
            for dimension in EXPLORE_DIMENSIONS
        }
        with Session(engine) as session:
            self._require(session)
            film_rows = list(session.exec(select(ExploreFilmReadModel)).all())
            view_ids = {
                row.film_id
                for row in film_rows
                if view == "all"
                or (view == "watched" and row.watched)
                or (view == "unwatched" and not row.watched)
            }
            facet_rows = {
                dimension: list(
                    session.exec(
                        select(ExploreFacetReadModel)
                        .where(ExploreFacetReadModel.dimension == dimension)
                        .where(ExploreFacetReadModel.eligible.is_(True))
                        .order_by(
                            ExploreFacetReadModel.normalized_label,
                            ExploreFacetReadModel.facet_key,
                            ExploreFacetReadModel.film_id,
                        )
                    ).all()
                )
                for dimension in EXPLORE_DIMENSIONS
            }
            library_rows = {
                row.film_id: row
                for row in session.exec(select(LibraryFilmReadModel)).all()
            }
            current_ids = self._strict_ids(view_ids, facet_rows, normalized)
            dimensions = []
            for dimension in EXPLORE_DIMENSIONS:
                other_filters = {
                    key: ([] if key == dimension else values)
                    for key, values in normalized.items()
                }
                base_ids = self._strict_ids(view_ids, facet_rows, other_filters)
                selected = set(normalized[dimension])
                grouped: dict[str, dict[str, Any]] = {}
                for row in facet_rows[dimension]:
                    if row.film_id not in base_ids or row.facet_key in selected:
                        continue
                    item = grouped.setdefault(
                        row.facet_key,
                        {
                            "key": row.facet_key,
                            "label": row.display_label,
                            "normalized_label": row.normalized_label,
                            "film_ids": set(),
                            "roles": set(),
                            "source_kinds": set(),
                        },
                    )
                    item["film_ids"].add(row.film_id)
                    payload = row.payload or {}
                    item["roles"].update(
                        role for role in payload.get("roles", []) if role in SAFE_ROLES
                    )
                    source_kind = payload.get("source_kind")
                    if source_kind in SAFE_SOURCE_KINDS:
                        item["source_kinds"].add(source_kind)

                candidates = []
                for item in grouped.values():
                    matching_ids = set(item.pop("film_ids"))
                    additional_ids = matching_ids - current_ids if selected else set()
                    if selected and not additional_ids:
                        continue
                    resulting_ids = current_ids | matching_ids if selected else matching_ids
                    preview_ids = additional_ids if additional_ids else resulting_ids
                    candidates.append(
                        {
                            "dimension": dimension,
                            "key": item["key"],
                            "label": item["label"],
                            "normalized_label": item["normalized_label"],
                            "roles": sorted(item["roles"]),
                            "source_kinds": sorted(item["source_kinds"]),
                            "result_count": len(resulting_ids),
                            "additional_count": len(additional_ids),
                            "preview_ids": preview_ids,
                        }
                    )
                metric = "additional_count" if selected else "result_count"
                candidates.sort(
                    key=lambda item: (
                        -item[metric],
                        item["normalized_label"],
                        item["key"],
                    )
                )
                has_more = len(candidates) > limit
                items = []
                for candidate in candidates[:limit]:
                    preview_ids = candidate.pop("preview_ids")
                    candidate.pop("normalized_label")
                    candidate["preview_film"] = self._preview_film(
                        preview_ids,
                        library_rows,
                    )
                    items.append(candidate)
                dimensions.append(
                    {
                        "dimension": dimension,
                        "operator": "or" if selected else "and",
                        "has_more": has_more,
                        "items": items,
                    }
                )
            return {
                "visibility_policy": EXPLORE_VISIBILITY_POLICY,
                "projection_version": EXPLORE_PROJECTION_VERSION,
                "projection_versions": self._projection_versions(),
                "strict": True,
                "current_total": len(current_ids),
                "dimensions": dimensions,
            }

    def list_films(
        self,
        *,
        filters: dict[str, list[str]],
        view: str,
        sort: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        normalized = {
            dimension: sorted(set(filters.get(dimension, [])))
            for dimension in EXPLORE_DIMENSIONS
        }
        with Session(engine) as session:
            self._require(session)
            active_filters, unresolved_filters = self._resolve_filters(session, normalized)
            candidate_ids: set[str] | None = None
            for dimension in EXPLORE_DIMENSIONS:
                keys = normalized[dimension]
                if not keys:
                    continue
                matching = set(
                    session.exec(
                        select(ExploreFacetReadModel.film_id)
                        .where(ExploreFacetReadModel.dimension == dimension)
                        .where(ExploreFacetReadModel.facet_key.in_(keys))
                        .where(ExploreFacetReadModel.eligible.is_(True))
                    ).all()
                )
                candidate_ids = matching if candidate_ids is None else candidate_ids & matching

            statement = select(ExploreFilmReadModel)
            if candidate_ids is not None:
                if not candidate_ids:
                    rows: list[ExploreFilmReadModel] = []
                else:
                    statement = statement.where(ExploreFilmReadModel.film_id.in_(candidate_ids))
                    rows = self._ordered_films(session, statement, view, sort, direction)
            else:
                rows = self._ordered_films(session, statement, view, sort, direction)

            total = len(rows)
            page_rows = rows[offset : offset + limit]
            page_ids = [row.film_id for row in page_rows]
            library_rows = {
                row.film_id: row
                for row in (
                    session.exec(
                        select(LibraryFilmReadModel).where(
                            LibraryFilmReadModel.film_id.in_(page_ids)
                        )
                    ).all()
                    if page_ids
                    else []
                )
            }
            matches = self._matched_facts(session, page_ids, normalized)
            items = []
            for row in page_rows:
                library_row = library_rows.get(row.film_id)
                if library_row is None:
                    continue
                items.append(
                    {
                        "film": json.loads(json.dumps(library_row.payload, ensure_ascii=False)),
                        "matched_facts": matches.get(row.film_id, []),
                    }
                )
            next_offset = offset + len(items) if offset + len(items) < total else None
            return {
                "visibility_policy": EXPLORE_VISIBILITY_POLICY,
                "projection_version": EXPLORE_PROJECTION_VERSION,
                "projection_versions": self._projection_versions(),
                "strict": True,
                "active_filters": {
                    **normalized,
                    "view": view,
                    "sort": sort,
                    "dir": direction,
                },
                "filters": active_filters,
                "unresolved_filters": unresolved_filters,
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
                "next_offset": next_offset,
            }

    def _facet_items(
        self,
        session: Session,
        dimension: str,
        *,
        query: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        film_count = func.count(func.distinct(ExploreFacetReadModel.film_id))
        watched_count = func.sum(
            case((ExploreFilmReadModel.watched.is_(True), 1), else_=0)
        )
        statement = (
            select(
                ExploreFacetReadModel.facet_key,
                ExploreFacetReadModel.display_label,
                ExploreFacetReadModel.normalized_label,
                film_count.label("film_count"),
                watched_count.label("watched_count"),
            )
            .join(
                ExploreFilmReadModel,
                ExploreFilmReadModel.film_id == ExploreFacetReadModel.film_id,
            )
            .where(ExploreFacetReadModel.dimension == dimension)
            .where(ExploreFacetReadModel.eligible.is_(True))
        )
        if query:
            statement = statement.where(ExploreFacetReadModel.normalized_label.contains(query))
        statement = (
            statement.group_by(
                ExploreFacetReadModel.facet_key,
                ExploreFacetReadModel.display_label,
                ExploreFacetReadModel.normalized_label,
            )
            .order_by(
                film_count.desc(),
                ExploreFacetReadModel.normalized_label,
                ExploreFacetReadModel.facet_key,
            )
            .offset(offset)
            .limit(limit)
        )
        rows = session.exec(statement).all()
        keys = [row[0] for row in rows]
        metadata = self._facet_metadata(session, dimension, keys)
        items = []
        for facet_key, label, _normalized, owned, watched in rows:
            watched_value = int(watched or 0)
            items.append(
                {
                    "dimension": dimension,
                    "key": facet_key,
                    "label": label,
                    "roles": metadata[facet_key]["roles"],
                    "source_kinds": metadata[facet_key]["source_kinds"],
                    "owned_count": int(owned),
                    "watched_count": watched_value,
                    "unwatched_count": int(owned) - watched_value,
                }
            )
        return items

    def _facet_metadata(
        self,
        session: Session,
        dimension: str,
        keys: list[str],
    ) -> dict[str, dict[str, list[str]]]:
        metadata = defaultdict(lambda: {"roles": set(), "source_kinds": set()})
        if keys:
            rows = session.exec(
                select(ExploreFacetReadModel)
                .where(ExploreFacetReadModel.dimension == dimension)
                .where(ExploreFacetReadModel.facet_key.in_(keys))
                .where(ExploreFacetReadModel.eligible.is_(True))
            ).all()
            for row in rows:
                payload = row.payload or {}
                source_kind = payload.get("source_kind")
                if source_kind in SAFE_SOURCE_KINDS:
                    metadata[row.facet_key]["source_kinds"].add(source_kind)
                metadata[row.facet_key]["roles"].update(
                    role for role in payload.get("roles", []) if role in SAFE_ROLES
                )
        return {
            key: {
                "roles": sorted(metadata[key]["roles"]),
                "source_kinds": sorted(metadata[key]["source_kinds"]),
            }
            for key in keys
        }

    def _resolve_filters(
        self,
        session: Session,
        filters: dict[str, list[str]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        active: list[dict[str, Any]] = []
        unresolved: list[dict[str, str]] = []
        for dimension in EXPLORE_DIMENSIONS:
            for key in filters[dimension]:
                rows = session.exec(
                    select(ExploreFacetReadModel)
                    .where(ExploreFacetReadModel.dimension == dimension)
                    .where(ExploreFacetReadModel.facet_key == key)
                    .order_by(ExploreFacetReadModel.eligible.desc(), ExploreFacetReadModel.film_id)
                ).all()
                label = rows[0].display_label if rows else key
                eligible = [row for row in rows if row.eligible]
                roles = sorted(
                    {
                        role
                        for row in eligible
                        for role in (row.payload or {}).get("roles", [])
                        if role in SAFE_ROLES
                    }
                )
                active.append(
                    {
                        "dimension": dimension,
                        "key": key,
                        "label": label,
                        "roles": roles,
                        "resolved": bool(eligible),
                    }
                )
                if not eligible:
                    unresolved.append({"dimension": dimension, "key": key, "label": label})
        return active, unresolved

    def _matched_facts(
        self,
        session: Session,
        film_ids: list[str],
        filters: dict[str, list[str]],
    ) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if not film_ids:
            return result
        for dimension in EXPLORE_DIMENSIONS:
            keys = filters[dimension]
            if not keys:
                continue
            rows = session.exec(
                select(ExploreFacetReadModel)
                .where(ExploreFacetReadModel.film_id.in_(film_ids))
                .where(ExploreFacetReadModel.dimension == dimension)
                .where(ExploreFacetReadModel.facet_key.in_(keys))
                .where(ExploreFacetReadModel.eligible.is_(True))
                .order_by(ExploreFacetReadModel.film_id, ExploreFacetReadModel.facet_key)
            ).all()
            for row in rows:
                payload = row.payload or {}
                source_kind = payload.get("source_kind")
                result[row.film_id].append(
                    {
                        "dimension": row.dimension,
                        "key": row.facet_key,
                        "label": row.display_label,
                        "roles": sorted(
                            role for role in payload.get("roles", []) if role in SAFE_ROLES
                        ),
                        "source_kind": source_kind if source_kind in SAFE_SOURCE_KINDS else None,
                        "policy_version": payload.get("policy_version"),
                        "derivation": payload.get("derivation"),
                    }
                )
        return result

    @staticmethod
    def _strict_ids(
        view_ids: set[str],
        facet_rows: dict[str, list[ExploreFacetReadModel]],
        filters: dict[str, list[str]],
    ) -> set[str]:
        candidate_ids = set(view_ids)
        for dimension in EXPLORE_DIMENSIONS:
            keys = set(filters[dimension])
            if not keys:
                continue
            matching = {
                row.film_id
                for row in facet_rows[dimension]
                if row.facet_key in keys
            }
            candidate_ids &= matching
        return candidate_ids

    @classmethod
    def _preview_film(
        cls,
        film_ids: set[str],
        library_rows: dict[str, LibraryFilmReadModel],
    ) -> dict[str, Any] | None:
        rows = [library_rows[film_id] for film_id in film_ids if film_id in library_rows]
        if not rows:
            return None
        rows.sort(key=cls._preview_sort_key)
        payload = rows[0].payload or {}
        primary_item = payload.get("primary_item") or {}
        artwork = primary_item.get("artwork") or {}
        return {
            "id": rows[0].film_id,
            "title": payload.get("title") or rows[0].film_id,
            "year": payload.get("year"),
            "artwork": {
                key: value
                for key, value in artwork.items()
                if key in SAFE_ARTWORK_KEYS and (value is None or isinstance(value, str))
            },
        }

    @staticmethod
    def _preview_sort_key(row: LibraryFilmReadModel) -> tuple[Any, ...]:
        payload = row.payload or {}
        artwork = ((payload.get("primary_item") or {}).get("artwork") or {})
        if artwork.get("poster_thumb_local") or artwork.get("backdrop_thumb_local"):
            artwork_rank = 0
        elif artwork.get("poster_provider") or artwork.get("backdrop_provider"):
            artwork_rank = 1
        elif artwork.get("poster_local") or artwork.get("backdrop_local"):
            artwork_rank = 2
        else:
            artwork_rank = 3
        return (
            artwork_rank,
            str(payload.get("title") or "").casefold(),
            row.film_id,
        )

    @staticmethod
    def _ordered_films(
        session: Session,
        statement,
        view: str,
        sort: str,
        direction: str,
    ) -> list[ExploreFilmReadModel]:
        if view == "watched":
            statement = statement.where(ExploreFilmReadModel.watched.is_(True))
        elif view == "unwatched":
            statement = statement.where(ExploreFilmReadModel.watched.is_(False))
        if sort == "year":
            year = ExploreFilmReadModel.release_year
            order = year.asc() if direction == "asc" else year.desc()
            statement = statement.order_by(
                case((year.is_(None), 1), else_=0),
                order,
                ExploreFilmReadModel.sort_title,
                ExploreFilmReadModel.film_id,
            )
        else:
            title = ExploreFilmReadModel.sort_title
            order = title.asc() if direction == "asc" else title.desc()
            statement = statement.order_by(
                order,
                ExploreFilmReadModel.release_year,
                ExploreFilmReadModel.film_id,
            )
        return list(session.exec(statement).all())

    @staticmethod
    def _total_films(session: Session) -> int:
        return int(session.exec(select(func.count()).select_from(ExploreFilmReadModel)).one())

    @staticmethod
    def _coverage(session: Session, dimension: str, total_films: int) -> dict[str, int]:
        covered = len(
            set(
                session.exec(
                    select(ExploreFacetReadModel.film_id)
                    .where(ExploreFacetReadModel.dimension == dimension)
                    .where(ExploreFacetReadModel.eligible.is_(True))
                ).all()
            )
        )
        conflicted = len(
            set(
                session.exec(
                    select(ExploreFacetReadModel.film_id)
                    .where(ExploreFacetReadModel.dimension == dimension)
                    .where(ExploreFacetReadModel.conflicted.is_(True))
                ).all()
            )
        )
        return {
            "total_films": total_films,
            "covered_films": covered,
            "conflicted_films": conflicted,
            "missing_films": max(total_films - covered - conflicted, 0),
        }

    @staticmethod
    def _require(session: Session) -> None:
        for name in ("library", "explore_films", "explore_facets"):
            state = session.get(ProjectionState, name)
            if (
                state is None
                or state.status != "ready"
                or state.projection_version != PROJECTION_VERSIONS[name]
            ):
                raise ProjectionUnavailable(f"{name} projection is unavailable")

    @staticmethod
    def _projection_versions() -> dict[str, str]:
        return {
            "films": PROJECTION_VERSIONS["explore_films"],
            "facets": PROJECTION_VERSIONS["explore_facets"],
        }


explore_query_service = ExploreQueryService()


__all__ = [
    "EXPLORE_DIMENSIONS",
    "EXPLORE_PROJECTION_VERSION",
    "EXPLORE_VISIBILITY_POLICY",
    "ExploreQueryService",
    "explore_query_service",
]
