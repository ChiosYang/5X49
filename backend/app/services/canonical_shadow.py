from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, text

@dataclass(frozen=True)
class ShadowDifference:
    record_id: str
    field: str
    source_layer: str
    legacy_hash: str
    canonical_hash: str
    legacy_is_null: bool
    canonical_is_null: bool


@dataclass(frozen=True)
class ShadowReadReport:
    scope: str
    records_compared: int
    records_matched: int
    records_different: int
    records_missing: int
    differences: tuple[ShadowDifference, ...]


FIELD_SOURCES = {
    "title": "film",
    "title_cn": "film",
    "year": "film",
    "runtime": "film",
    "overview": "film",
    "tmdb_id": "external_identity",
    "imdb_id": "external_identity",
    "folder_name": "library_item",
    "folder_path": "library_item",
    "library_status": "library_item",
    "added_at": "library_item",
    "last_seen_at": "library_item",
    "missing_since": "library_item",
    "metadata_source": "library_item",
    "metadata_updated_at": "library_item",
    "scrape_status": "library_item",
    "scrape_error": "library_item",
    "scraped_at": "library_item",
    "tmdb_confidence": "library_item",
    "media_path": "media_asset",
    "poster_local": "media_asset",
    "backdrop_local": "media_asset",
    "poster_path": "media_asset",
    "backdrop_path": "media_asset",
    "favorite": "film_profile_state",
    "watched": "viewing",
    "watched_at": "viewing",
    "rating": "viewing",
    "notes": "viewing",
    "updated_at": "viewing",
}


class CanonicalShadowReader:
    def __init__(self, engine: Engine | None = None):
        if engine is None:
            from app.database import engine as application_engine

            engine = application_engine
        self.engine = engine

    def get_movie(self, movie_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            legacy = connection.execute(
                text("SELECT * FROM movie WHERE id = :movie_id"),
                {"movie_id": movie_id},
            ).mappings().one_or_none()
            canonical = connection.execute(
                text(
                    "SELECT a.legacy_movie_id, a.legacy_library_status, "
                    "f.id AS film_id, f.canonical_title, f.original_title, f.release_year, "
                    "f.runtime_minutes, f.overview AS film_overview, "
                    "li.id AS library_item_id, li.source_item_key, li.display_name, "
                    "li.availability_status, li.added_at, li.last_seen_at, li.missing_since, "
                    "li.metadata_source, li.metadata_updated_at, li.scrape_status, "
                    "li.scrape_error, li.scraped_at, li.match_confidence "
                    "FROM legacy_movie_alias a "
                    "JOIN film f ON f.id = a.film_id "
                    "JOIN library_item li ON li.id = a.library_item_id "
                    "WHERE a.legacy_movie_id = :movie_id"
                ),
                {"movie_id": movie_id},
            ).mappings().one_or_none()
            if canonical is None:
                return None
            assets = connection.execute(
                text(
                    "SELECT * FROM media_asset WHERE library_item_id = :item_id "
                    "OR film_id = :film_id ORDER BY asset_kind, id"
                ),
                {
                    "item_id": canonical["library_item_id"],
                    "film_id": canonical["film_id"],
                },
            ).mappings().all()
            identities = {
                row["provider"]: row["external_id"]
                for row in connection.execute(
                    text(
                        "SELECT provider, external_id FROM external_identity "
                        "WHERE entity_id = :film_id AND identity_status = 'active'"
                    ),
                    {"film_id": canonical["film_id"]},
                ).mappings()
            }

        result = dict(legacy or {})
        result.update({
            "id": movie_id,
            "title": canonical["original_title"] or canonical["canonical_title"],
            "title_cn": result.get("title_cn") or (
                canonical["canonical_title"]
                if canonical["canonical_title"] != canonical["original_title"]
                else None
            ),
            "year": canonical["release_year"] or result.get("year") or 0,
            "runtime": canonical["runtime_minutes"],
            "overview": canonical["film_overview"],
            "tmdb_id": identities.get("tmdb.movie"),
            "imdb_id": identities.get("imdb.title"),
            "folder_name": canonical["display_name"],
            "folder_path": canonical["source_item_key"],
            "library_status": (
                canonical["legacy_library_status"]
                if canonical["legacy_library_status"] == "reverted"
                else canonical["availability_status"]
            ),
            "added_at": canonical["added_at"],
            "last_seen_at": canonical["last_seen_at"],
            "missing_since": canonical["missing_since"],
            "metadata_source": canonical["metadata_source"],
            "metadata_updated_at": canonical["metadata_updated_at"],
            "scrape_status": canonical["scrape_status"],
            "scrape_error": canonical["scrape_error"],
            "scraped_at": canonical["scraped_at"],
            "tmdb_confidence": canonical["match_confidence"],
        })
        self._apply_asset_projection(result, assets, canonical["library_item_id"])
        return result

    def get_user_state(self, movie_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            alias = connection.execute(
                text(
                    "SELECT a.film_id, lp.id AS profile_id "
                    "FROM legacy_movie_alias a CROSS JOIN local_profile lp "
                    "WHERE a.legacy_movie_id = :movie_id AND lp.profile_key = 'local'"
                ),
                {"movie_id": movie_id},
            ).mappings().one_or_none()
            if alias is None:
                return None
            state = connection.execute(
                text(
                    "SELECT favorite, updated_at FROM film_profile_state "
                    "WHERE profile_id = :profile AND film_id = :film"
                ),
                {"profile": alias["profile_id"], "film": alias["film_id"]},
            ).mappings().one_or_none()
            confirmed = self._latest_viewing(
                connection,
                str(alias["profile_id"]),
                str(alias["film_id"]),
                "confirmed",
            )
            needs_review = None if confirmed else self._latest_viewing(
                connection,
                str(alias["profile_id"]),
                str(alias["film_id"]),
                "needs_review",
            )

        selected = confirmed or needs_review
        updated_values = [
            value
            for value in (
                state["updated_at"] if state else None,
                selected["updated_at"] if selected else None,
            )
            if value
        ]
        return {
            "movie_id": movie_id,
            "watched": confirmed is not None,
            "watched_at": confirmed["watched_at"] if confirmed else None,
            "rating": selected["rating"] if selected else None,
            "favorite": bool(state["favorite"]) if state else False,
            "notes": selected["review"] if selected else None,
            "updated_at": max(updated_values) if updated_values else None,
        }

    def watch_history(self) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT film_id, MAX(COALESCE(watched_at, updated_at)) AS sort_at "
                    "FROM viewing WHERE review_status = 'confirmed' AND deleted_at IS NULL "
                    "GROUP BY film_id ORDER BY sort_at DESC, film_id"
                )
            ).mappings().all()
            aliases = {
                row["film_id"]: row["legacy_movie_id"]
                for row in connection.execute(
                    text(
                        "SELECT film_id, MIN(legacy_movie_id) AS legacy_movie_id "
                        "FROM legacy_movie_alias GROUP BY film_id"
                    )
                ).mappings()
            }
        entries = []
        for row in rows:
            movie_id = aliases.get(row["film_id"])
            if not movie_id:
                continue
            movie = self.get_movie(str(movie_id))
            user_state = self.get_user_state(str(movie_id))
            if movie and user_state:
                entries.append({"movie": movie, "user_state": user_state})
        return entries

    def compare_library(self) -> ShadowReadReport:
        with self.engine.connect() as connection:
            movie_ids = [
                str(value)
                for value in connection.execute(
                    text("SELECT legacy_movie_id FROM legacy_movie_alias ORDER BY legacy_movie_id")
                ).scalars()
            ]
        return self._compare_records("library", movie_ids, self._legacy_movie, self.get_movie)

    def compare_user_states(self) -> ShadowReadReport:
        with self.engine.connect() as connection:
            movie_ids = [
                str(value)
                for value in connection.execute(
                    text("SELECT legacy_movie_id FROM legacy_movie_alias ORDER BY legacy_movie_id")
                ).scalars()
            ]
        return self._compare_records(
            "user_state",
            movie_ids,
            self._legacy_user_state,
            self.get_user_state,
        )

    def _legacy_movie(self, movie_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM movie WHERE id = :movie_id"),
                {"movie_id": movie_id},
            ).mappings().one_or_none()
        return dict(row) if row else None

    def _legacy_user_state(self, movie_id: str) -> dict[str, Any]:
        with self.engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM movie_user_state WHERE movie_id = :movie_id"),
                {"movie_id": movie_id},
            ).mappings().one_or_none()
        if row:
            result = dict(row)
            result["watched"] = bool(result["watched"])
            result["favorite"] = bool(result["favorite"])
            return result
        return {
            "movie_id": movie_id,
            "watched": False,
            "watched_at": None,
            "rating": None,
            "favorite": False,
            "notes": None,
            "updated_at": None,
        }

    def _compare_records(self, scope, record_ids, legacy_reader, canonical_reader):
        differences: list[ShadowDifference] = []
        missing = 0
        matched = 0
        differing = 0
        for record_id in record_ids:
            legacy = legacy_reader(record_id)
            canonical = canonical_reader(record_id)
            if legacy is None or canonical is None:
                missing += 1
                continue
            record_differences = self._differences(record_id, legacy, canonical)
            if record_differences:
                differing += 1
                differences.extend(record_differences)
            else:
                matched += 1
        return ShadowReadReport(
            scope=scope,
            records_compared=len(record_ids),
            records_matched=matched,
            records_different=differing,
            records_missing=missing,
            differences=tuple(differences),
        )

    @staticmethod
    def _differences(record_id, legacy, canonical):
        fields = sorted(set(legacy).intersection(canonical))
        return [
            ShadowDifference(
                record_id=_fingerprint(record_id),
                field=field,
                source_layer=FIELD_SOURCES.get(field, "legacy_projection"),
                legacy_hash=_fingerprint(legacy[field]),
                canonical_hash=_fingerprint(canonical[field]),
                legacy_is_null=legacy[field] is None,
                canonical_is_null=canonical[field] is None,
            )
            for field in fields
            if _normalized_value(legacy[field]) != _normalized_value(canonical[field])
        ]

    @staticmethod
    def _latest_viewing(connection, profile_id: str, film_id: str, review_status: str):
        return connection.execute(
            text(
                "SELECT * FROM viewing WHERE profile_id = :profile AND film_id = :film "
                "AND review_status = :status AND deleted_at IS NULL "
                "ORDER BY COALESCE(watched_at, updated_at) DESC, updated_at DESC, id DESC LIMIT 1"
            ),
            {"profile": profile_id, "film": film_id, "status": review_status},
        ).mappings().one_or_none()

    @staticmethod
    def _apply_asset_projection(result, assets, library_item_id):
        for asset in assets:
            owned_by_item = asset["library_item_id"] == library_item_id
            kind = asset["asset_kind"]
            if owned_by_item and kind == "video":
                result.update({
                    "media_path": asset["locator"],
                    "file_size": asset["file_size"],
                    "file_mtime": asset["file_mtime"],
                    "video_width": asset["width"],
                    "video_height": asset["height"],
                    "video_codec": asset["codec"],
                    "video_bitrate": asset["bitrate"],
                    "video_duration": asset["duration_seconds"],
                    "video_fps": asset["fps"],
                    "video_dynamic_range": asset["dynamic_range"],
                    "video_bit_depth": asset["bit_depth"],
                    "audio_tracks": _json_value(asset["stream_metadata"]),
                })
            elif owned_by_item and kind == "nfo":
                result.update({
                    "nfo_path": asset["locator"],
                    "nfo_size": asset["file_size"],
                    "nfo_mtime": asset["file_mtime"],
                    "nfo_fingerprint": asset["content_fingerprint"],
                })
            elif owned_by_item and kind == "poster":
                result["poster_local"] = asset["locator"]
            elif owned_by_item and kind == "backdrop":
                result["backdrop_local"] = asset["locator"]
            elif not owned_by_item and kind == "poster":
                result["poster_path"] = asset["locator"]
            elif not owned_by_item and kind == "backdrop":
                result["backdrop_path"] = asset["locator"]


def _json_value(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _normalized_value(value):
    if isinstance(value, bool):
        return int(value)
    return value


def _fingerprint(value) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
