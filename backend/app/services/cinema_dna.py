from __future__ import annotations

from fractions import Fraction
from typing import Any

from sqlmodel import Session, select

from app.canonical_models import CinemaDnaFilmReadModel, LocalProfile
from app.database import engine
from app.services.factual_facets import FACT_DIMENSIONS
from app.services.projections import PROJECTION_VERSIONS, projection_reader


FORMULA_VERSION = "cinema-dna.v1"
GLOBAL_MIN_RATED = 10
CATEGORY_MIN_RATED = 3
SAFE_SOURCES = {"canonical", "curated", "filename", "nfo", "rule", "tmdb", "user"}


def _page(items: list, limit: int, offset: int) -> dict:
    page = items[offset:offset + limit]
    return {
        "items": page, "total": len(items), "limit": limit, "offset": offset,
        "next_offset": offset + len(page) if offset + len(page) < len(items) else None,
    }


class CinemaDnaService:
    def _load(self) -> list[dict[str, Any]]:
        with Session(engine) as session:
            # sqlite3 legacy transaction control does not BEGIN for SELECT.
            # Read readiness and all input rows from one consistent snapshot.
            session.connection().exec_driver_sql("BEGIN")
            projection_reader._require(session, "cinema_dna")
            rows = session.exec(
                select(CinemaDnaFilmReadModel)
                .join(LocalProfile, LocalProfile.id == CinemaDnaFilmReadModel.profile_id)
                .where(LocalProfile.profile_key == "local")
                .order_by(CinemaDnaFilmReadModel.film_id)
            ).all()
            return [row.payload for row in rows]

    @staticmethod
    def _base(rows: list[dict]) -> dict:
        rated = sum(row["rating"] is not None for row in rows)
        return {
            "formula_version": FORMULA_VERSION,
            "projection_version": PROJECTION_VERSIONS["cinema_dna"],
            "scope": "all-time-confirmed-viewings",
            "thresholds": {"global_rated_films": GLOBAL_MIN_RATED, "category_rated_films": CATEGORY_MIN_RATED},
            "totals": {
                "watched_films": len(rows),
                "viewing_records": sum(row["viewing_count"] for row in rows),
                "rated_films": rated,
            },
            "needed_global_ratings": max(0, GLOBAL_MIN_RATED - rated),
        }

    @staticmethod
    def _coverage(rows: list[dict], dimension: str) -> dict:
        return {
            "total_films": len(rows),
            **{
                f"{status}_films": sum(row["coverage"][dimension] == status for row in rows)
                for status in ("covered", "conflicted", "missing")
            },
        }

    def overview(self) -> dict:
        rows = self._load()
        return {
            **self._base(rows),
            "dimensions": [
                {"dimension": dimension, "coverage": self._coverage(rows, dimension)}
                for dimension in FACT_DIMENSIONS
            ],
        }

    def _facets(self, rows: list[dict], dimension: str) -> list[dict]:
        global_rated = sum(row["rating"] is not None for row in rows)
        groups: dict[str, dict] = {}
        for row in rows:
            for fact in row["facts"]:
                if fact["dimension"] != dimension:
                    continue
                item = groups.setdefault(fact["key"], {
                    "key": fact["key"], "label": fact["label"], "film_count": 0,
                    "rated_count": 0, "rating_sum": 0, "viewing_count": 0,
                    "roles": set(), "source_kinds": set(),
                })
                item["film_count"] += 1
                item["viewing_count"] += row["viewing_count"]
                if row["rating"] is not None:
                    item["rated_count"] += 1
                    item["rating_sum"] += row["rating"]
                source = fact["source"]
                item["roles"].update(role for role in source.get("roles", []) if role in {"actor", "director"})
                if source.get("source_kind") in SAFE_SOURCES:
                    item["source_kinds"].add(source["source_kind"])
        for item in groups.values():
            eligible = global_rated >= GLOBAL_MIN_RATED and item["rated_count"] >= CATEGORY_MIN_RATED
            item.update({
                "denominator": len(rows),
                "share": item["film_count"] / len(rows) if rows else None,
                "preference": item["rating_sum"] / item["rated_count"] if eligible else None,
                "needed_category_ratings": max(0, CATEGORY_MIN_RATED - item["rated_count"]),
                "roles": sorted(item["roles"]),
                "source_kinds": sorted(item["source_kinds"]),
            })
        return list(groups.values())

    @staticmethod
    def _public_facet(item: dict) -> dict:
        return {key: value for key, value in item.items() if key != "rating_sum"}

    def facets(self, dimension: str, *, metric: str = "exposure", limit: int = 20, offset: int = 0) -> dict:
        rows = self._load()
        facets = self._facets(rows, dimension)
        if metric == "preference":
            facets = [item for item in facets if item["preference"] is not None]
            facets.sort(key=lambda item: (
                -Fraction(item["rating_sum"], item["rated_count"]), -item["rated_count"], item["key"],
            ))
        else:
            facets.sort(key=lambda item: (-item["film_count"], item["key"]))
        return {
            **self._base(rows), "dimension": dimension, "metric": metric,
            "coverage": self._coverage(rows, dimension),
            **_page([self._public_facet(item) for item in facets], limit, offset),
        }

    def contributors(
        self, dimension: str, key: str, *, metric: str = "exposure", limit: int = 40, offset: int = 0,
    ) -> dict:
        rows = self._load()
        facet = next((item for item in self._facets(rows, dimension) if item["key"] == key), None)
        items = []
        for row in rows:
            if metric == "preference" and row["rating"] is None:
                continue
            fact = next((fact for fact in row["facts"] if fact["dimension"] == dimension and fact["key"] == key), None)
            if fact is None:
                continue
            items.append({
                **{field: row[field] for field in ("film_id", "title", "year", "rating", "viewing_count", "in_library")},
                "fact": fact,
            })
        items.sort(key=lambda item: (item["title"].casefold(), item["film_id"]))
        return {
            **self._base(rows), "dimension": dimension, "key": key, "metric": metric,
            "facet": self._public_facet(facet) if facet else None,
            **_page(items, limit, offset),
        }


cinema_dna_service = CinemaDnaService()
